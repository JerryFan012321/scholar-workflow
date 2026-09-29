"""One journal for a reviewed Field enrollment and paper-provider placement.

This is a trusted local-operator primitive, not a browser API. It deliberately
does not infer which files belong in a Field: callers must supply every reviewed
navigation/link rewrite and every preserved old analysis path. A missing review
is a conflict, not permission to silently omit content. Recovery state is not a
verified backup. External Vault writers must be paused for apply and recovery.

The commit decision is journaled before the first publication. Interrupted
commits roll forward only while every member is either its exact old inode and
bytes or the inode and bytes staged by this transaction. A failed in-process
commit switches the durable decision to rollback and restores only owned after
inodes. Unrecognized external changes stop recovery without overwriting them.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import uuid
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import unified_diff
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote, unquote

import yaml
from ruamel.yaml import YAML

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    KnowledgeVaultBinding,
    PreparedJointPaperPlacement,
    _locked_state_root,
    finalize_joint_paper_placement,
    prepare_joint_paper_placement,
)
from scholar_workflow.analysis.commit import _canonical_payloads
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisCommitRequest,
    KnowledgeArtifactChange,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.canvas import validate_canvas_payload
from scholar_workflow.hub.field_migration import _has_legacy_hub_reference, _managed_paths
from scholar_workflow.hub.field_transaction import _has_analysis_identity, _has_analysis_sidecar
from scholar_workflow.hub.fields import (
    FieldDefinition,
    FieldManifest,
    FieldRegistryError,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
    _assert_field_owned_markdown,
    _open_directory_chain,
    _safe_relative,
)
from scholar_workflow.hub.models import ArtifactFormat, ArtifactKind, HubArtifact
from scholar_workflow.hub.paper_foldering import PaperFolderingPlan

_MANIFEST = ".scholar-workflow/fields.yml"
_ARTIFACT_MANIFEST = ".scholar-workflow/artifacts.yml"
_PROVIDER_FILE = "knowledge-provider.snapshot.json"
_PENDING = "pending.json"
_MAX_FILES = 256
_MAX_BYTES = 32 * 1024 * 1024
_MAX_DIFF = 1024 * 1024
_FIELD_TEXT_SUFFIXES = (
    ".md",
    ".canvas",
    ".analysis.json",
    ".txt",
    ".html",
    ".json",
    ".yml",
    ".yaml",
    ".ipynb",
)
_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)


class JointFieldTransactionError(RuntimeError):
    """A joint plan is stale, unsafe, incomplete, or needs conditional recovery."""


@dataclass(frozen=True)
class JointFileChange:
    domain: Literal["vault", "provider", "registry"]
    relative_path: str
    before_sha256: str | None
    after_sha256: str | None
    kind: str


@dataclass(frozen=True)
class _File:
    domain: Literal["vault", "provider", "registry"]
    relative: str
    before: bytes | None
    after: bytes | None
    device: int | None
    inode: int | None
    parent_device: int | None
    parent_inode: int | None
    mode: int
    owner: int
    kind: str


@dataclass(frozen=True)
class JointFieldPlan:
    transaction_id: str
    source_id: str
    field_id: str
    vault_root: Path
    vault_device: int
    vault_inode: int
    provider_root: Path
    provider_base: KnowledgeProviderSnapshot
    provider_before: bytes | None
    provider_before_device: int | None
    provider_before_inode: int | None
    registry_before: bytes | None
    files: tuple[_File, ...]
    preserved: tuple[_File, ...]
    prepared_provider: PreparedJointPaperPlacement
    provider_bootstrap_after: KnowledgeProviderSnapshot | None
    additional_note_relocations: tuple[tuple[str, str], ...]
    required_existing_documents: tuple[tuple[str, str, int, int], ...]
    paper_foldering_plan: PaperFolderingPlan | None
    field_relative_root: str
    field_inventory_digest: str
    changes: tuple[JointFileChange, ...]
    plan_digest: str
    preview: str
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class JointFieldResult:
    transaction_id: str
    plan_digest: str
    provider_snapshot_revision: str
    changed_files: tuple[str, ...]
    recovery_record: Path
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class JointFieldRecovery:
    transaction_id: str | None
    outcome: Literal["nothing-to-recover", "committed", "rolled-back"]
    changed_files: tuple[str, ...]
    recovery_record: Path | None
    recovery_is_verified_backup: bool = False


def _hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _human_diff(before: bytes, after: bytes, *, label: str) -> str:
    try:
        old_lines = before.decode("utf-8").splitlines(keepends=True)
        new_lines = after.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return ""
    result = "".join(
        unified_diff(old_lines, new_lines, fromfile=f"before/{label}", tofile=f"after/{label}")
    )
    if len(result.encode("utf-8")) > 128 * 1024:
        raise JointFieldTransactionError(f"human diff is too large: {label}")
    return result


def _inside(root: Path, child: Path) -> bool:
    try:
        child.relative_to(root)
    except ValueError:
        return False
    return child != root


def _root_identity(root: Path) -> tuple[int, int]:
    descriptor = _open_directory_chain(root)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid():
            raise JointFieldTransactionError("Vault root is not owned by the current user")
        return info.st_dev, info.st_ino
    finally:
        os.close(descriptor)


def _read_file(root: Path, relative: str, *, missing_parent: bool = False) -> _File:
    safe = _safe_relative(relative)
    parts = PurePosixPath(safe).parts
    try:
        parent_fd = _open_directory_chain(root, parts[:-1])
    except FileNotFoundError:
        if missing_parent:
            return _File("vault", safe, None, None, None, None, None, None, 0o600, os.geteuid(), "")
        raise JointFieldTransactionError(f"target parent is missing: {safe}") from None
    except OSError as exc:
        raise JointFieldTransactionError(f"target parent is unsafe: {safe}") from exc
    try:
        parent = os.fstat(parent_fd)
        try:
            descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return _File(
                "vault",
                safe,
                None,
                None,
                None,
                None,
                parent.st_dev,
                parent.st_ino,
                0o600,
                os.geteuid(),
                "",
            )
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid():
                raise JointFieldTransactionError(f"target is not a singly owned file: {safe}")
            if info.st_size > _MAX_BYTES:
                raise JointFieldTransactionError(f"target exceeds review limit: {safe}")
            chunks: list[bytes] = []
            while data := os.read(descriptor, 1024 * 1024):
                chunks.append(data)
            return _File(
                "vault",
                safe,
                b"".join(chunks),
                None,
                info.st_dev,
                info.st_ino,
                parent.st_dev,
                parent.st_ino,
                stat.S_IMODE(info.st_mode),
                info.st_uid,
                "",
            )
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise JointFieldTransactionError(f"target is unsafe: {safe}") from exc
    finally:
        os.close(parent_fd)


def _member(
    root: Path,
    relative: str,
    after: bytes | None,
    *,
    domain: str,
    kind: str,
    missing_parent: bool = False,
) -> _File:
    current = _read_file(root, relative, missing_parent=missing_parent)
    return _File(
        domain,
        relative,
        current.before,
        after,
        current.device,
        current.inode,
        current.parent_device,
        current.parent_inode,
        current.mode,
        current.owner,
        kind,
    )


def _member_matches(root: Path, member: _File) -> bool:
    current = _read_file(root, member.relative, missing_parent=member.before is None)
    return (
        current.before == member.before
        and current.device == member.device
        and current.inode == member.inode
        and (
            member.parent_device is None
            or (
                current.parent_device == member.parent_device
                and current.parent_inode == member.parent_inode
            )
        )
        and current.mode == member.mode
        and current.owner == member.owner
    )


def _field_path(field: FieldDefinition, relative: str) -> str:
    safe = _safe_relative(relative)
    root = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    return PurePosixPath(*root, *PurePosixPath(safe).parts).as_posix()


def _field_owns(field: FieldDefinition, relative: str) -> bool:
    base = PurePosixPath(field.relative_root)
    try:
        PurePosixPath(relative).relative_to(base)
    except ValueError:
        return field.relative_root == "."
    return True


def _validate_registry_after(
    before: KnowledgeSourceRegistryDocument,
    after: KnowledgeSourceRegistryDocument,
    *,
    source_id: str,
    vault_root: Path,
) -> None:
    old_folders = {row.folder_id: row for row in before.folders}
    old_sources = {row.source_id: row for row in before.sources}
    folders = {row.folder_id: row for row in after.folders}
    sources = {row.source_id: row for row in after.sources}
    if any(folders.get(key) != row for key, row in old_folders.items()) or any(
        sources.get(key) != row for key, row in old_sources.items()
    ):
        raise JointFieldTransactionError("joint enrollment cannot alter existing registry rows")
    extra_sources = set(sources) - set(old_sources)
    if extra_sources - {source_id} or len(set(folders) - set(old_folders)) > 1:
        raise JointFieldTransactionError("joint enrollment may add only its selected Source")
    source = sources.get(source_id)
    if source is None or not source.enabled or "write" not in source.capabilities:
        raise JointFieldTransactionError("selected Source is not enabled for writing")
    folder = folders.get(source.folder_id)
    if folder is None or not folder.enabled or "write" not in folder.capabilities:
        raise JointFieldTransactionError("selected folder is not enabled for writing")
    if folder.root != vault_root:
        raise JointFieldTransactionError("Source folder differs from selected Vault")


def _validate_manifest_after(
    before: FieldManifest | None, after: FieldManifest, *, source_id: str, field_id: str
) -> FieldDefinition:
    if after.source_id != source_id:
        raise JointFieldTransactionError("Field manifest Source ID differs from registration")
    if before is not None:
        old = {row.field_id: row for row in before.fields}
        new = {row.field_id: row for row in after.fields}
        if any(new.get(key) != row for key, row in old.items() if key != field_id):
            raise JointFieldTransactionError("joint transaction cannot change another Field")
        if set(old) - set(new) or (set(new) - set(old)) - {field_id}:
            raise JointFieldTransactionError("joint transaction changes unselected Field IDs")
    selected = next((row for row in after.fields if row.field_id == field_id), None)
    if selected is None:
        raise JointFieldTransactionError("selected Field is absent from the proposed manifest")
    return selected


def _validate_reviewed_file(
    root: Path, field: FieldDefinition, relative: str, payload: bytes
) -> None:
    if not _field_owns(field, relative) or any(
        part.startswith(".") for part in PurePosixPath(relative).parts
    ):
        raise JointFieldTransactionError("reviewed content escapes its Field or enters state")
    if not relative.endswith((".md", ".canvas")) or len(payload) > _MAX_BYTES:
        raise JointFieldTransactionError("reviewed content has an unsupported format or size")
    if relative.endswith(".md"):
        if b"\x00" in payload:
            raise JointFieldTransactionError("reviewed Markdown contains NUL")
        try:
            payload.decode("utf-8")
            _assert_field_owned_markdown(payload)
        except UnicodeDecodeError as exc:
            raise JointFieldTransactionError("reviewed Markdown is not UTF-8") from exc
    else:
        try:
            validate_canvas_payload(json.loads(payload))
        except (ValueError, UnicodeDecodeError) as exc:
            raise JointFieldTransactionError("reviewed Canvas is invalid") from exc
    current = _read_file(root, relative, missing_parent=True)
    if relative.endswith(".md") and current.before is not None:
        _assert_field_owned_markdown(current.before)
    if current.before is not None and (
        _has_analysis_identity(current.before) or _has_analysis_sidecar(root, relative)
    ):
        raise JointFieldTransactionError(
            "managed old analysis requires a separately validated paired cutover"
        )


def _rewritten_note(source: bytes, rewrites: Mapping[str, str]) -> bytes:
    try:
        content = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JointFieldTransactionError("paper owner note is not UTF-8") from exc
    for before, after in sorted(rewrites.items()):
        if not before or not after or before == after or before not in content:
            raise JointFieldTransactionError("paper note link rewrite is not exact")
        content = content.replace(before, after)
    return content.encode("utf-8")


def _foldering_note_base(
    foldering: PaperFolderingPlan | None, source: str, fallback: bytes
) -> bytes:
    if foldering is None:
        return fallback
    matches = [row for row in foldering.documents if row.source_path == source]
    if len(matches) != 1:
        raise JointFieldTransactionError(
            f"paper-foldering proposal lacks an exact moved-note candidate: {source}"
        )
    return matches[0].after_bytes


def _artifact_rows(payload: bytes) -> list[HubArtifact]:
    if len(payload) > 2 * 1024 * 1024:
        raise JointFieldTransactionError("Vault artifact manifest is too large")
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    try:
        document = parser.load(payload.decode("utf-8"))
    except Exception as exc:
        raise JointFieldTransactionError("Vault artifact manifest is invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "artifacts"}
        or document["schema_version"] != 1
        or not isinstance(document["artifacts"], list)
    ):
        raise JointFieldTransactionError("Vault artifact manifest shape is invalid")
    rows = [HubArtifact.model_validate(row) for row in document["artifacts"]]
    if len({row.artifact_id for row in rows}) != len(rows) or (
        len({row.vault_path for row in rows}) != len(rows)
    ):
        raise JointFieldTransactionError("Vault artifact manifest has duplicate identity")
    if any(
        row.kind is not ArtifactKind.ANALYSIS_CANVAS
        or row.format is not ArtifactFormat.CANVAS
        or not row.vault_path.endswith(".canvas")
        for row in rows
    ):
        raise JointFieldTransactionError("Vault artifact manifest has unsupported rows")
    return rows


def _validate_artifact_manifest_change(
    before: bytes, after: bytes, request: AnalysisCommitRequest
) -> None:
    old_rows = {row.artifact_id: row for row in _artifact_rows(before)}
    new_rows = {row.artifact_id: row for row in _artifact_rows(after)}
    if set(old_rows) != set(new_rows):
        raise JointFieldTransactionError("Vault artifact manifest identity set changed")
    selected = request.document.artifact_id + ":canvas"
    old = old_rows.get(selected)
    new = new_rows.get(selected)
    if (
        old is None
        or new is None
        or old.vault_path == request.paths.canvas
        or (new.vault_path != request.paths.canvas)
        or new.resource_id != request.resource_id
    ):
        raise JointFieldTransactionError("old analysis Canvas identity was not relocated")
    old_payload = old.model_dump(mode="json")
    new_payload = new.model_dump(mode="json")
    old_payload["vault_path"] = request.paths.canvas
    if old_payload != new_payload or any(
        old_rows[key] != new_rows[key] for key in old_rows if key != selected
    ):
        raise JointFieldTransactionError("Vault artifact manifest changes unrelated metadata")


def _bootstrap_graph_with_relocations(
    prepared: PreparedJointPaperPlacement,
    relocations: tuple[tuple[str, str], ...],
) -> KnowledgeProviderSnapshot:
    manifest = prepared.manifest.model_copy(deep=True)
    known = {row.markdown_path: row for row in manifest.atomic_resources}
    for source, destination in relocations:
        owner = known.get(source)
        if owner is None or owner.kind.value != "paper":
            raise JointFieldTransactionError(
                f"additional relocation lacks a PAPER provider owner: {source}"
            )
        owner.markdown_path = destination
    return KnowledgeProviderSnapshot(
        vault_binding=prepared.vault_binding,
        manifest=manifest,
        artifacts=list(prepared.artifacts),
        relations=list(prepared.relations),
        projections=list(prepared.projections),
        catalog=prepared.catalog,
    )


def _validate_provider_file_coverage(
    snapshot: KnowledgeProviderSnapshot,
    *,
    root: Path,
    proposed: Mapping[str, bytes | None],
    preserved_paths: Mapping[str, str | None],
) -> None:
    paths = {
        *(row.markdown_path for row in snapshot.manifest.atomic_resources),
        *(row.markdown_path for row in snapshot.manifest.core_documents),
        *(row.vault_path for row in snapshot.manifest.supporting_documents),
        *(row.vault_path for row in snapshot.artifacts),
    }
    if len(paths) > _MAX_FILES:
        raise JointFieldTransactionError("provider graph exceeds reviewed file limit")
    actual: dict[str, bytes] = {}
    for path in sorted(paths):
        content = proposed.get(path)
        if content is None:
            if path in proposed:
                raise JointFieldTransactionError(f"provider graph points at a removed file: {path}")
            current = _read_file(root, path, missing_parent=True).before
            if current is None or preserved_paths.get(path) != _hash(current):
                raise JointFieldTransactionError(
                    f"provider file lacks an immutable before receipt: {path}"
                )
            content = current
        actual[path] = content
    for artifact in snapshot.artifacts:
        if _hash(actual[artifact.vault_path]) != artifact.sha256:
            raise JointFieldTransactionError(
                f"provider artifact hash differs from planned bytes: {artifact.vault_path}"
            )


def _check_field_coverage(
    root: Path,
    field: FieldDefinition,
    proposed: Mapping[str, bytes | None],
    preserved_paths: Mapping[str, str | None],
) -> None:
    """Refuse omitted navigation, unmanaged old URLs, and unreviewed analysis originals."""
    for local in _managed_paths(field):
        path = _field_path(field, local)
        candidate = proposed.get(path)
        if candidate is None and path in proposed:
            raise JointFieldTransactionError(f"new navigation points at removed content: {path}")
        if candidate is None and _read_file(root, path, missing_parent=True).before is None:
            raise JointFieldTransactionError(f"new navigation points at missing content: {path}")
    declared_after = {_field_path(field, name) for name in _managed_paths(field)}
    field_root = root if field.relative_root == "." else root / field.relative_root
    for base, dirs, files in os.walk(field_root, followlinks=False):
        base_path = Path(base)
        for dirname in list(dirs):
            target = base_path / dirname
            if target.is_symlink():
                raise JointFieldTransactionError("Field inventory contains a symbolic link")
            if dirname.startswith("."):
                dirs.remove(dirname)
        for filename in files:
            path = base_path / filename
            if path.is_symlink():
                raise JointFieldTransactionError("Field inventory contains a symbolic link")
            suffix_name = filename.casefold()
            if filename.startswith(".") or not suffix_name.endswith(_FIELD_TEXT_SUFFIXES):
                continue
            relative = path.relative_to(root).as_posix()
            existing = _read_file(root, relative).before
            assert existing is not None
            if (
                suffix_name.endswith(".md")
                and any(part.casefold() == "paper_assets" for part in PurePosixPath(relative).parts)
                and proposed.get(relative, existing) is not None
            ):
                raise JointFieldTransactionError(
                    f"flat paper asset was not included in a reviewed relocation: {relative}"
                )
            after = proposed.get(relative, existing)
            if after is not None and _has_legacy_hub_reference(after, relative):
                raise JointFieldTransactionError(
                    f"Field retains an unreviewed old Hub URL: {relative}"
                )
            if (
                suffix_name.endswith((".md", ".canvas"))
                and relative not in proposed
                and (relative not in declared_after and relative not in preserved_paths)
            ):
                raise JointFieldTransactionError(
                    f"old Field document was omitted from navigation and preservation: {relative}"
                )
            if (
                (
                    suffix_name.endswith(".analysis.json")
                    or suffix_name.endswith(".md")
                    and _has_analysis_identity(existing)
                    or suffix_name.endswith(".canvas")
                    and _has_analysis_sidecar(root, relative)
                )
                and relative not in preserved_paths
                and relative not in proposed
            ):
                raise JointFieldTransactionError(
                    f"old managed analysis lacks an explicit preservation receipt: {relative}"
                )


def _field_inventory_digest(
    root: Path, field_relative_root: str, *, own_created_dirs: frozenset[str] = frozenset()
) -> str:
    """Bind the complete visible Field entry set without reading unrelated large assets.

    Content touched by this transaction has its own byte/inode CAS. This inventory
    additionally prevents an unreviewed new file or directory from appearing
    between preview and the durable commit decision.
    """
    field_root = root if field_relative_root == "." else root / field_relative_root
    _root_identity(field_root)
    entries: list[dict[str, object]] = []
    for base, dirs, files in os.walk(field_root, followlinks=False):
        base_path = Path(base)
        for name in sorted((*dirs, *files)):
            if name.startswith("."):
                if any(
                    part.casefold() == "paper_assets" for part in base_path.relative_to(root).parts
                ):
                    raise JointFieldTransactionError(
                        "flat paper asset inventory contains a hidden entry"
                    )
                if name in dirs:
                    dirs.remove(name)
                continue
            path = base_path / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode):
                raise JointFieldTransactionError(
                    f"Field inventory contains a symbolic link: {relative}"
                )
            if info.st_uid != os.geteuid():
                raise JointFieldTransactionError(
                    f"Field inventory contains a foreign-owned entry: {relative}"
                )
            if stat.S_ISDIR(info.st_mode):
                kind = "directory"
            elif stat.S_ISREG(info.st_mode):
                kind = "file"
            else:
                raise JointFieldTransactionError(
                    f"Field inventory contains an unsupported entry: {relative}"
                )
            if kind == "directory" and relative in own_created_dirs:
                continue
            content_sha: str | None = None
            if kind == "file" and name.casefold().endswith(_FIELD_TEXT_SUFFIXES):
                content = _read_file(root, relative).before
                assert content is not None
                content_sha = _hash(content)
            entries.append(
                {
                    "path": relative,
                    "kind": kind,
                    "device": info.st_dev,
                    "inode": info.st_ino,
                    "mode": stat.S_IMODE(info.st_mode),
                    "size": info.st_size if kind == "file" else None,
                    "mtime_ns": info.st_mtime_ns if kind == "file" else None,
                    "content_sha256": content_sha,
                }
            )
            if len(entries) > 4096:
                raise JointFieldTransactionError("Field inventory exceeds entry limit")
        dirs.sort()
    return _hash(_json_bytes(entries))


def _check_deleted_note_references(
    root: Path,
    field: FieldDefinition,
    proposed: Mapping[str, bytes | None],
    old_note_paths: tuple[str, ...],
) -> None:
    """Require explicit reviewed rewrites for links to removed flat owner notes."""
    sources: set[str] = set()
    for path in old_note_paths:
        field_relative = (
            path
            if field.relative_root == "."
            else PurePosixPath(path).relative_to(field.relative_root).as_posix()
        )
        for variant in (path, field_relative):
            sources.add(variant)
            if variant.endswith(".md"):
                sources.add(variant[:-3])
            sources.add(quote(variant, safe="/"))
    sources.discard("")
    effective: dict[str, bytes] = {}
    field_root = root if field.relative_root == "." else root / field.relative_root
    for base, dirs, files in os.walk(field_root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for name in files:
            if name.startswith(".") or not name.casefold().endswith((".md", ".canvas")):
                continue
            relative = (Path(base) / name).relative_to(root).as_posix()
            if relative in proposed:
                content = proposed[relative]
            else:
                content = _read_file(root, relative).before
            if content is not None:
                effective[relative] = content
    for relative, content in proposed.items():
        if content is not None and relative.casefold().endswith((".md", ".canvas")):
            effective[relative] = content
    for relative, content in effective.items():
        readable = content.decode("utf-8", errors="replace")
        variants = [readable]
        for _ in range(4):
            decoded = unquote(variants[-1])
            if decoded == variants[-1]:
                break
            variants.append(decoded)
        if any(
            re.search(re.escape(source) + r"(?![\w./%-])", version)
            for version in variants
            for source in sources
        ):
            raise JointFieldTransactionError(
                f"reviewed document retains a deleted paper-note path: {relative}"
            )


def _foldering_binding(plan: PaperFolderingPlan | None) -> dict[str, object] | None:
    if plan is None:
        return None
    return {
        "plan_digest": plan.plan_digest,
        "vault_root": str(plan.vault_root),
        "vault_device": plan.vault_device,
        "vault_inode": plan.vault_inode,
        "field_id": plan.field_id,
        "proposed_field": plan.proposed_field.model_dump(mode="json"),
        "moves": [row.__dict__ for row in plan.moves],
        "navigation_changes": [row.__dict__ for row in plan.navigation_changes],
        "missing_navigation_targets": list(plan.missing_navigation_targets),
        "link_changes": [row.__dict__ for row in plan.link_changes],
        "documents": [
            {
                **{key: value for key, value in row.__dict__.items() if key != "after_bytes"},
                "actual_after_sha256": _hash(row.after_bytes),
            }
            for row in plan.documents
        ],
    }


def _verify_foldering_digest(plan: PaperFolderingPlan) -> None:
    """Reject a modified planner object carrying an old review digest."""
    before_field = plan.proposed_field.model_dump(mode="json")
    seen_locations: set[str] = set()
    for change in plan.navigation_changes:
        if change.location in seen_locations:
            raise JointFieldTransactionError("paper-foldering navigation change is duplicated")
        seen_locations.add(change.location)
        if change.location == "home":
            if before_field["home"] != change.new_path:
                raise JointFieldTransactionError("paper-foldering home change is inconsistent")
            before_field["home"] = change.old_path
        else:
            match = re.fullmatch(r"navigation\[(\d+)\]\.items\[(\d+)\]", change.location)
            if match is None:
                raise JointFieldTransactionError("paper-foldering navigation location is invalid")
            group = int(match.group(1))
            item = int(match.group(2))
            try:
                current = before_field["navigation"][group]["items"][item]
            except (IndexError, KeyError) as exc:
                raise JointFieldTransactionError(
                    "paper-foldering navigation location is out of range"
                ) from exc
            if current != change.new_path:
                raise JointFieldTransactionError(
                    "paper-foldering navigation change is inconsistent"
                )
            before_field["navigation"][group]["items"][item] = change.old_path
    original_field = FieldDefinition.model_validate(before_field)
    semantic = {
        "root": str(plan.vault_root),
        "root_device": plan.vault_device,
        "root_inode": plan.vault_inode,
        "field_id": plan.field_id,
        "field_before": original_field.model_dump(mode="json"),
        "field_after": plan.proposed_field.model_dump(mode="json"),
        "moves": [row.__dict__ for row in plan.moves],
        "missing_navigation_targets": plan.missing_navigation_targets,
        "links": [row.__dict__ for row in plan.link_changes],
        "documents": [
            {key: value for key, value in row.__dict__.items() if key != "after_bytes"}
            for row in plan.documents
        ],
    }
    expected = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(semantic, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    )
    if expected != plan.plan_digest:
        raise JointFieldTransactionError("paper-foldering review digest is inconsistent")


def _validate_foldering_candidate(
    foldering: PaperFolderingPlan,
    *,
    root: Path,
    vault_identity: tuple[int, int],
    field: FieldDefinition,
    source_note: str,
    destination_note: str,
    additional: tuple[tuple[str, str], ...],
    note_link_rewrites: Mapping[str, Mapping[str, str]],
    proposed: Mapping[str, bytes | None],
) -> None:
    _verify_foldering_digest(foldering)
    if (
        foldering.vault_root != root
        or (foldering.vault_device, foldering.vault_inode) != vault_identity
        or foldering.field_id != field.field_id
        or not foldering.read_only
    ):
        raise JointFieldTransactionError("paper-foldering proposal is for another Field/Vault")
    proposed_field = foldering.proposed_field.model_dump(mode="json")
    final_field = field.model_dump(mode="json")
    missing = set(foldering.missing_navigation_targets)
    if proposed_field["home"] in missing:
        raise JointFieldTransactionError("missing paper-foldering home needs explicit repair")
    for group in proposed_field["navigation"]:
        group["items"] = [item for item in group["items"] if item not in missing]
    if proposed_field != final_field:
        raise JointFieldTransactionError(
            "Field manifest differs from reviewed paper-foldering navigation"
        )
    moves = {row.old_path: row for row in foldering.moves}
    expected = {source_note: destination_note, **dict(additional)}
    if (
        len(moves) != len(foldering.moves)
        or {source: move.new_path for source, move in moves.items()} != expected
    ):
        raise JointFieldTransactionError("joint relocations differ from paper-foldering proposal")
    documents = {row.source_path: row for row in foldering.documents}
    if len(documents) != len(foldering.documents):
        raise JointFieldTransactionError("paper-foldering proposal has duplicate documents")
    for old_path, move in moves.items():
        if not move.destination_absent or old_path not in documents:
            raise JointFieldTransactionError("paper-foldering move lacks its exact document")
        if proposed.get(old_path, b"unexpected") is not None:
            raise JointFieldTransactionError("paper-foldering old owner note was not removed")
        source = _read_file(root, old_path)
        if (
            source.before is None
            or _hash(source.before) != move.before_sha256
            or (source.device, source.inode) != (move.before_device, move.before_inode)
            or _hash(documents[old_path].after_bytes) != move.after_sha256
        ):
            raise JointFieldTransactionError("paper-foldering move receipt differs from Vault")
    for source_path, document in documents.items():
        output = expected.get(source_path, source_path)
        before = _read_file(root, source_path)
        expected_bytes = (
            _rewritten_note(document.after_bytes, note_link_rewrites.get(source_path, {}))
            if source_path in moves
            else document.after_bytes
        )
        if (
            document.output_path != output
            or before.before is None
            or _hash(before.before) != document.before_sha256
            or (before.device, before.inode) != (document.before_device, document.before_inode)
            or _hash(document.after_bytes) != document.after_sha256
            or proposed.get(output) != expected_bytes
        ):
            raise JointFieldTransactionError(
                f"joint candidate omitted or changed paper-foldering document: {source_path}"
            )


def _encode(payload: bytes | None) -> str | None:
    return None if payload is None else base64.b64encode(payload).decode("ascii")


def _decode(value: str | None) -> bytes | None:
    return None if value is None else base64.b64decode(value, validate=True)


def _plan_semantic(plan: JointFieldPlan) -> dict[str, object]:
    return {
        "transaction_id": plan.transaction_id,
        "source_id": plan.source_id,
        "field_id": plan.field_id,
        "vault_root": str(plan.vault_root),
        "vault_device": plan.vault_device,
        "vault_inode": plan.vault_inode,
        "provider_base": plan.provider_base.snapshot_revision,
        "provider_base_payload": _hash(_json_bytes(plan.provider_base.model_dump(mode="json"))),
        "provider_before": None if plan.provider_before is None else _hash(plan.provider_before),
        "provider_device": plan.provider_before_device,
        "provider_inode": plan.provider_before_inode,
        "provider_bootstrap_after": (
            None
            if plan.provider_bootstrap_after is None
            else _hash(_json_bytes(plan.provider_bootstrap_after.model_dump(mode="json")))
        ),
        "additional_note_relocations": list(plan.additional_note_relocations),
        "required_existing_documents": [
            {"path": path, "sha256": sha, "device": device, "inode": inode}
            for path, sha, device, inode in plan.required_existing_documents
        ],
        "paper_foldering": _foldering_binding(plan.paper_foldering_plan),
        "field_relative_root": plan.field_relative_root,
        "field_inventory_digest": plan.field_inventory_digest,
        "request": plan.prepared_provider.request.model_dump(mode="json"),
        "prepared_note": {
            "source": plan.prepared_provider.source_note_path,
            "destination": plan.prepared_provider.destination_note_path,
            "sha256": plan.prepared_provider.note_sha256,
        },
        "preserved": [
            {
                "path": row.relative,
                "hash": None if row.before is None else _hash(row.before),
                "device": row.device,
                "inode": row.inode,
            }
            for row in plan.preserved
        ],
        "members": [
            {
                "domain": row.domain,
                "path": row.relative,
                "before": None if row.before is None else _hash(row.before),
                "after": None if row.after is None else _hash(row.after),
                "device": row.device,
                "inode": row.inode,
                "parent_device": row.parent_device,
                "parent_inode": row.parent_inode,
                "kind": row.kind,
            }
            for row in plan.files
        ],
    }


def _root_for(domain: str, *, vault: Path, provider: Path, registry: Path) -> Path:
    if domain == "vault":
        return vault
    if domain == "provider":
        return provider
    if domain == "registry":
        return registry.parent
    raise JointFieldTransactionError("journal contains an unknown member domain")


def _directory_chain_create(root: Path, relative: str) -> list[dict[str, object]]:
    """Create only missing parents, anchored by a nofollow root descriptor."""
    parts = PurePosixPath(_safe_relative(relative)).parts[:-1]
    current = _open_directory_chain(root)
    created: list[dict[str, object]] = []
    try:
        for index, part in enumerate(parts):
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=current)
                os.fsync(current)
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
                info = os.fstat(child)
                created.append(
                    {
                        "path": PurePosixPath(*parts[: index + 1]).as_posix(),
                        "device": info.st_dev,
                        "inode": info.st_ino,
                    }
                )
            if os.fstat(child).st_uid != os.geteuid():
                os.close(child)
                raise JointFieldTransactionError("target directory is not owned by current user")
            os.close(current)
            current = child
    finally:
        os.close(current)
    return created


def _planned_missing_directories(root: Path, rows: list[dict[str, object]]) -> list[str]:
    """Durably name every absent Vault parent before creating any of them."""
    paths: set[str] = set()
    for row in rows:
        if row["domain"] != "vault" or row["after"] is None:
            continue
        parts = PurePosixPath(_safe_relative(str(row["path"]))).parts[:-1]
        for index in range(1, len(parts) + 1):
            relative = PurePosixPath(*parts[:index]).as_posix()
            try:
                descriptor = _open_directory_chain(root, parts[:index])
            except FileNotFoundError:
                paths.add(relative)
            else:
                os.close(descriptor)
    return sorted(paths, key=lambda value: (len(PurePosixPath(value).parts), value))


def _cleanup_unreceipted_prepared_directories(
    root: Path, *, planned: object, receipted: object
) -> None:
    """Never infer ownership of a directory from its path or emptiness alone."""
    if not isinstance(planned, list) or not isinstance(receipted, list):
        raise JointFieldTransactionError("prepared directory intent is invalid")
    known = {str(row["path"]) for row in receipted if isinstance(row, dict)}
    for relative in reversed(planned):
        safe = _safe_relative(str(relative))
        if safe in known:
            continue
        try:
            descriptor = _open_directory_chain(root, PurePosixPath(safe).parts)
        except FileNotFoundError:
            continue
        os.close(descriptor)
        raise JointFieldTransactionError(
            f"unreceipted prepared directory needs manual ownership review: {safe}"
        )


def _create_private_path(path: Path) -> None:
    """Create private host state directories without following symlink ancestors."""
    if not path.is_absolute():
        raise JointFieldTransactionError("state path must be absolute")
    current = _open_directory_chain(Path(path.anchor))
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=current)
                os.fsync(current)
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current,
                )
            os.close(current)
            current = child
        info = os.fstat(current)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise JointFieldTransactionError("transaction state directory is not private")
    finally:
        os.close(current)


def _write_private_json(directory: Path, name: str, value: dict[str, object]) -> None:
    raw = _json_bytes(value)
    if len(raw) > 2 * _MAX_BYTES:
        raise JointFieldTransactionError("joint journal exceeds its size limit")
    descriptor = _open_directory_chain(directory)
    temporary = f".{name}.{secrets.token_hex(12)}.tmp"
    try:
        fd = os.open(temporary, _WRITE_FLAGS, 0o600, dir_fd=descriptor)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(fd)
        os.replace(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
        except FileNotFoundError:
            pass
        os.close(descriptor)


def _seal(journal: dict[str, object]) -> dict[str, object]:
    content = {key: value for key, value in journal.items() if key != "checksum"}
    return {**content, "checksum": _hash(_json_bytes(content))}


def _read_journal(directory: Path) -> dict[str, object] | None:
    if not directory.is_dir():
        return None
    descriptor = _open_directory_chain(directory)
    try:
        try:
            fd = os.open(_PENDING, _READ_FLAGS, dir_fd=descriptor)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or (stat.S_IMODE(info.st_mode) & 0o077)
                or info.st_size > 2 * _MAX_BYTES
            ):
                raise JointFieldTransactionError("joint journal is not a private regular file")
            chunks: list[bytes] = []
            while data := os.read(fd, 1024 * 1024):
                chunks.append(data)
            journal = json.loads(b"".join(chunks))
            if (
                not isinstance(journal, dict)
                or journal.get("checksum") != _seal(journal)["checksum"]
            ):
                raise JointFieldTransactionError("joint journal checksum is invalid")
            return journal
        finally:
            os.close(fd)
    except (ValueError, UnicodeDecodeError) as exc:
        raise JointFieldTransactionError("joint journal is invalid") from exc
    finally:
        os.close(descriptor)


def _stage_file(
    root: Path,
    relative: str,
    payload: bytes,
    transaction_id: str,
    *,
    mode: int,
    staged_name: str | None = None,
) -> tuple[str, int, int]:
    parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
    name = staged_name or f".scholar-joint-{transaction_id}-{secrets.token_hex(8)}.tmp"
    if not name.startswith(f".scholar-joint-{transaction_id}-") or not name.endswith(".tmp"):
        os.close(parent)
        raise JointFieldTransactionError("staged name is not bound to the transaction")
    try:
        fd = os.open(name, _WRITE_FLAGS, mode, dir_fd=parent)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            info = os.fstat(fd)
            os.fsync(parent)
            return name, info.st_dev, info.st_ino
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _entry_status(root: Path, row: dict[str, object]) -> str:
    relative = str(row["path"])
    current = _read_file(root, relative, missing_parent=True)
    old = _decode(row["before"])
    new = _decode(row["after"])
    if (
        current.before == old
        and current.device == row["before_device"]
        and current.inode == row["before_inode"]
    ):
        return "before"
    if new is None and current.before is None:
        parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
        try:
            try:
                descriptor = os.open(str(row["delete_temp"]), _READ_FLAGS, dir_fd=parent)
            except FileNotFoundError:
                return "conflict"
            try:
                info = os.fstat(descriptor)
                chunks: list[bytes] = []
                while data := os.read(descriptor, 1024 * 1024):
                    chunks.append(data)
                if (
                    stat.S_ISREG(info.st_mode)
                    and info.st_nlink == 1
                    and info.st_uid == row["owner"]
                    and (info.st_dev, info.st_ino) == (row["before_device"], row["before_inode"])
                    and b"".join(chunks) == old
                ):
                    return "after"
            finally:
                os.close(descriptor)
        finally:
            os.close(parent)
    if (
        current.before == new
        and current.device == row["stage_device"]
        and current.inode == row["stage_inode"]
    ):
        return "after"
    return "conflict"


def _status_for_phase(root: Path, row: dict[str, object], phase: str) -> str:
    status = _entry_status(root, row)
    if status == "conflict" and phase == "committed" and row["after"] is None:
        current = _read_file(root, str(row["path"]), missing_parent=True)
        if current.before is None:
            return "after"
    if status == "conflict" and phase == "rolled-back":
        current = _read_file(root, str(row["path"]), missing_parent=True)
        if current.before == _decode(row["before"]):
            return "before"
    return status


def _publish_row(root: Path, row: dict[str, object]) -> None:
    status = _entry_status(root, row)
    if status == "after":
        return
    if status != "before":
        raise JointFieldTransactionError(f"external change conflicts with {row['path']}")
    relative = str(row["path"])
    parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
    try:
        info = os.fstat(parent)
        if row["parent_device"] is not None and (info.st_dev, info.st_ino) != (
            row["parent_device"],
            row["parent_inode"],
        ):
            raise JointFieldTransactionError(f"target parent changed: {relative}")
        if row["after"] is None:
            os.rename(
                PurePosixPath(relative).name,
                str(row["delete_temp"]),
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
        else:
            staged = os.stat(str(row["stage_temp"]), dir_fd=parent, follow_symlinks=False)
            if (staged.st_dev, staged.st_ino) != (row["stage_device"], row["stage_inode"]):
                raise JointFieldTransactionError(f"staged member changed: {relative}")
            os.replace(
                str(row["stage_temp"]),
                PurePosixPath(relative).name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
        os.fsync(parent)
        if _entry_status(root, row) != "after":
            raise JointFieldTransactionError(f"published member changed: {relative}")
    finally:
        os.close(parent)


def _rollback_row(root: Path, row: dict[str, object]) -> None:
    status = _entry_status(root, row)
    if status == "before":
        return
    if status != "after":
        # A prior interrupted rollback can have restored the old bytes in a
        # fresh inode. There is nothing left to overwrite in that state.
        current = _read_file(root, str(row["path"]), missing_parent=True)
        if current.before == _decode(row["before"]):
            return
        raise JointFieldTransactionError(f"external change conflicts with rollback: {row['path']}")
    relative = str(row["path"])
    parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
    try:
        old = _decode(row["before"])
        if row["after"] is None:
            os.rename(
                str(row["delete_temp"]),
                PurePosixPath(relative).name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
            )
        elif old is None:
            os.unlink(PurePosixPath(relative).name, dir_fd=parent)
        else:
            temporary, _, _ = _stage_file(
                root, relative, old, str(row["transaction_id"]), mode=int(row["mode"])
            )
            os.replace(
                temporary, PurePosixPath(relative).name, src_dir_fd=parent, dst_dir_fd=parent
            )
        os.fsync(parent)
    finally:
        os.close(parent)


def _cleanup_temps(root: Path, row: dict[str, object], *, committed: bool) -> None:
    relative = str(row["path"])
    try:
        parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
    except FileNotFoundError:
        if row["before"] is None and row["after"] is not None:
            return
        raise
    try:
        for key, identity_keys in (
            ("stage_temp", ("stage_device", "stage_inode")),
            ("delete_temp", ("before_device", "before_inode")),
        ):
            name = row.get(key)
            if not name:
                continue
            try:
                info = os.stat(str(name), dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if (info.st_dev, info.st_ino) != tuple(row[part] for part in identity_keys):
                raise JointFieldTransactionError("joint staged file ownership changed")
            if key == "delete_temp" and not committed:
                raise JointFieldTransactionError("rollback left an owner note in staged removal")
            os.unlink(str(name), dir_fd=parent)
            os.fsync(parent)
    finally:
        os.close(parent)


def _cleanup_prepared_stage(root: Path, row: dict[str, object]) -> None:
    """Discard a pre-decision temp named in the durable prepare journal."""
    name = row.get("stage_temp")
    if not name:
        return
    transaction_id = str(row["transaction_id"])
    if not str(name).startswith(f".scholar-joint-{transaction_id}-") or not str(name).endswith(
        ".tmp"
    ):
        raise JointFieldTransactionError("prepared stage name is invalid")
    relative = str(row["path"])
    try:
        parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
    except FileNotFoundError:
        return
    try:
        try:
            info = os.stat(str(name), dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != row["owner"]
            or (
                row.get("stage_inode") is not None
                and (info.st_dev, info.st_ino) != (row.get("stage_device"), row.get("stage_inode"))
            )
        ):
            raise JointFieldTransactionError("prepared stage ownership changed")
        os.unlink(str(name), dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def _verify_created_directories(root: Path, rows: object, *, allow_missing: bool = False) -> None:
    if not isinstance(rows, list):
        raise JointFieldTransactionError("joint directory receipt is invalid")
    for row in rows:
        if not isinstance(row, dict):
            raise JointFieldTransactionError("joint directory receipt is invalid")
        relative = _safe_relative(str(row.get("path")))
        try:
            descriptor = _open_directory_chain(root, PurePosixPath(relative).parts)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise JointFieldTransactionError(
                f"joint-created directory disappeared: {relative}"
            ) from None
        try:
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != (row.get("device"), row.get("inode")):
                raise JointFieldTransactionError(
                    f"joint-created directory changed after staging: {relative}"
                )
        finally:
            os.close(descriptor)


class JointFieldTransactionService:
    """Trusted local coordinator; no browser-supplied absolute path is accepted."""

    def __init__(self, registry: KnowledgeSourceRegistry, state_root: Path) -> None:
        self.registry = registry
        self.state_root = Path(state_root)

    def _journal_dir(self, source_id: str, field_id: str) -> Path:
        try:
            if str(uuid.UUID(source_id)) != source_id or str(uuid.UUID(field_id)) != field_id:
                raise ValueError("noncanonical ID")
        except ValueError as exc:
            raise JointFieldTransactionError("joint recovery identity is invalid") from exc
        root = Path(os.path.abspath(self.state_root))
        if root != self.state_root or not root.is_dir() or root.is_symlink():
            raise JointFieldTransactionError("joint recovery state root is unavailable")
        return root / source_id / field_id

    @contextmanager
    def _locks(self, vault_root: Path, source_id: str) -> Iterator[None]:
        """Match the existing lock order: registry EX, Vault EX, provider EX."""
        with ExitStack() as stack:
            stack.enter_context(self.registry._write_guard())
            vault_fd = _open_directory_chain(vault_root)
            stack.callback(os.close, vault_fd)
            fcntl.flock(vault_fd, fcntl.LOCK_EX)
            stack.callback(fcntl.flock, vault_fd, fcntl.LOCK_UN)
            state_dir = vault_root / ".scholar-workflow"
            if state_dir.is_symlink():
                raise JointFieldTransactionError("Vault state directory is a symbolic link")
            if not state_dir.exists():
                os.mkdir(state_dir, 0o700)
                os.fsync(vault_fd)
            state_fd = _open_directory_chain(state_dir)
            stack.callback(os.close, state_fd)
            lock_fd = os.open(
                ".field-writes.lock",
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=state_fd,
            )
            stack.callback(os.close, lock_fd)
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise JointFieldTransactionError("Vault write lock is unsafe")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            stack.callback(fcntl.flock, lock_fd, fcntl.LOCK_UN)
            provider_parent = self.registry.path.parent / "knowledge-providers"
            _create_private_path(provider_parent)
            provider_root = provider_parent / source_id
            _create_private_path(provider_root)
            stack.enter_context(_locked_state_root(provider_root))
            yield

    @staticmethod
    def _verify_plan(
        plan: JointFieldPlan,
        registry: KnowledgeSourceRegistry,
        *,
        own_created_dirs: frozenset[str] = frozenset(),
    ) -> None:
        if _hash(_json_bytes(_plan_semantic(plan))) != plan.plan_digest or (
            plan.prepared_provider.plan_digest != plan.plan_digest
        ):
            raise JointFieldTransactionError("approved joint plan digest changed")
        if _root_identity(plan.vault_root) != (plan.vault_device, plan.vault_inode):
            raise JointFieldTransactionError("Vault identity changed after preview")
        if (
            _field_inventory_digest(
                plan.vault_root,
                plan.field_relative_root,
                own_created_dirs=own_created_dirs,
            )
            != plan.field_inventory_digest
        ):
            raise JointFieldTransactionError("Field inventory changed after preview")
        if plan.provider_root != registry.path.parent / "knowledge-providers" / plan.source_id:
            raise JointFieldTransactionError("provider state root is not registered")
        for member in (*plan.files, *plan.preserved):
            root = _root_for(
                member.domain,
                vault=plan.vault_root,
                provider=plan.provider_root,
                registry=registry.path,
            )
            if not _member_matches(root, member):
                raise JointFieldTransactionError(
                    f"joint plan target changed after preview: {member.relative}"
                )
        for path, sha, device, inode in plan.required_existing_documents:
            current = _read_file(plan.vault_root, path)
            if (
                current.before is None
                or _hash(current.before) != sha
                or (current.device, current.inode) != (device, inode)
            ):
                raise JointFieldTransactionError(
                    f"required existing document changed after preview: {path}"
                )
        current_provider = _read_file(plan.provider_root, _PROVIDER_FILE)
        if (
            current_provider.before != plan.provider_before
            or current_provider.device != plan.provider_before_device
            or current_provider.inode != plan.provider_before_inode
        ):
            raise JointFieldTransactionError("provider snapshot changed after preview")
        current = (
            plan.provider_base
            if current_provider.before is None
            else KnowledgeProviderSnapshot.model_validate_json(current_provider.before)
        )
        note = next((row for row in plan.files if row.kind == "owner-note-removal"), None)
        if (
            note is None
            or note.before is None
            or _hash(note.before) != (plan.prepared_provider.note_sha256)
        ):
            raise JointFieldTransactionError("paper owner note receipt changed")
        request = plan.prepared_provider.request
        expected_artifacts = [
            KnowledgeArtifactChange(
                artifact_id=request.document.artifact_id + suffix,
                resource_id=request.resource_id,
                kind=kind,
                vault_path=path,
                sha256=_hash(
                    next(
                        row.after
                        for row in plan.files
                        if row.domain == "vault" and row.relative == path and row.after is not None
                    )
                ),
            )
            for suffix, kind, path in (
                ("", "analysis_markdown", request.paths.markdown),
                (":canvas", "analysis_canvas", request.paths.canvas),
                (":sidecar", "analysis_sidecar", request.paths.sidecar),
            )
        ]
        if tuple(expected_artifacts) != tuple(plan.prepared_provider.new_artifacts):
            raise JointFieldTransactionError(
                "prepared provider artifacts differ from reviewed bytes"
            )
        binding = KnowledgeVaultBinding(
            root_path=str(plan.vault_root),
            device=plan.vault_device,
            inode=plan.vault_inode,
        )
        refreshed = prepare_joint_paper_placement(
            snapshot=current,
            request=plan.prepared_provider.request,
            vault_binding=binding,
            transaction_id=plan.transaction_id,
            plan_digest=plan.plan_digest,
            source_note_path=plan.prepared_provider.source_note_path,
            destination_note_path=plan.prepared_provider.destination_note_path,
            note_sha256=_hash(note.before),
            new_artifacts=plan.prepared_provider.new_artifacts,
        )
        if refreshed != plan.prepared_provider:
            raise JointFieldTransactionError("joint provider graph changed after preview")
        if plan.provider_before is None:
            after = plan.provider_bootstrap_after
            if after is None or after.receipts:
                raise JointFieldTransactionError(
                    "first enrollment requires a pure provider bootstrap graph without receipts"
                )
            if after != _bootstrap_graph_with_relocations(
                refreshed, plan.additional_note_relocations
            ):
                raise JointFieldTransactionError(
                    "provider bootstrap graph differs from reviewed files"
                )
        elif plan.provider_bootstrap_after is not None:
            raise JointFieldTransactionError("existing provider cannot be bootstrapped")

    @staticmethod
    def _rows(plan: JointFieldPlan, provider_payload: bytes) -> list[dict[str, object]]:
        provider = _member(
            plan.provider_root,
            _PROVIDER_FILE,
            provider_payload,
            domain="provider",
            kind="provider-snapshot",
        )
        if (
            provider.before != plan.provider_before
            or provider.device != plan.provider_before_device
            or provider.inode != plan.provider_before_inode
        ):
            raise JointFieldTransactionError("provider changed before staging")
        members = [row for row in plan.files if row.domain == "vault" and row.before != row.after]
        members.sort(key=lambda row: (row.kind == "manifest", row.relative))
        members.append(provider)
        members.extend(
            row for row in plan.files if row.domain == "registry" and row.before != row.after
        )
        rows: list[dict[str, object]] = []
        for member in members:
            rows.append(
                {
                    "transaction_id": plan.transaction_id,
                    "domain": member.domain,
                    "path": member.relative,
                    "kind": member.kind,
                    "before": _encode(member.before),
                    "after": _encode(member.after),
                    "before_device": member.device,
                    "before_inode": member.inode,
                    "parent_device": member.parent_device,
                    "parent_inode": member.parent_inode,
                    "mode": member.mode,
                    "owner": member.owner,
                    "stage_temp": (
                        f".scholar-joint-{plan.transaction_id}-{secrets.token_hex(8)}.tmp"
                        if member.after is not None
                        else None
                    ),
                    "stage_device": None,
                    "stage_inode": None,
                    "delete_temp": (
                        f".scholar-joint-{plan.transaction_id}-{secrets.token_hex(8)}.removed"
                        if member.after is None
                        else None
                    ),
                }
            )
        return rows

    def apply(
        self,
        plan: JointFieldPlan,
        *,
        approved_digest: str,
        external_writers_paused: bool,
    ) -> JointFieldResult:
        if not external_writers_paused:
            raise JointFieldTransactionError("external Vault writers must be paused")
        if approved_digest != plan.plan_digest:
            raise JointFieldTransactionError("exact joint plan digest was not approved")
        journal_dir = self._journal_dir(plan.source_id, plan.field_id)
        if _inside(plan.vault_root, journal_dir) or _inside(plan.provider_root, journal_dir):
            raise JointFieldTransactionError("recovery state must be outside the Vault/provider")
        with self._locks(plan.vault_root, plan.source_id):
            if _read_journal(journal_dir) is not None:
                raise JointFieldTransactionError("unresolved joint recovery must run first")
            self._verify_plan(plan, self.registry)
            if plan.provider_before is None:
                assert plan.provider_bootstrap_after is not None
                provider_payload = _json_bytes(
                    plan.provider_bootstrap_after.model_dump(mode="json")
                )
                after_revision = plan.provider_bootstrap_after.snapshot_revision
            else:
                finalized = finalize_joint_paper_placement(
                    plan.prepared_provider,
                    current_snapshot=plan.provider_base,
                    committed_at=datetime.now(UTC),
                )
                provider_payload = finalized.payload
                after_revision = finalized.after_snapshot_revision
            rows = self._rows(plan, provider_payload)
            _create_private_path(journal_dir)
            planned_dirs = _planned_missing_directories(plan.vault_root, rows)
            created: list[dict[str, object]] = []
            seen_dirs: set[str] = set()
            journal: dict[str, object] = {
                "schema_version": 1,
                "phase": "prepare",
                "transaction_id": plan.transaction_id,
                "source_id": plan.source_id,
                "field_id": plan.field_id,
                "plan_digest": plan.plan_digest,
                "vault_root": str(plan.vault_root),
                "vault_device": plan.vault_device,
                "vault_inode": plan.vault_inode,
                "provider_root": str(plan.provider_root),
                "provider_after_revision": after_revision,
                "rows": rows,
                "planned_directories": planned_dirs,
                "created_directories": created,
            }
            # Journal intent, including every random temp name, before any
            # stage file or Field directory is created.
            _write_private_json(journal_dir, _PENDING, _seal(journal))
            try:
                for row in rows:
                    root = _root_for(
                        str(row["domain"]),
                        vault=plan.vault_root,
                        provider=plan.provider_root,
                        registry=self.registry.path,
                    )
                    if row["domain"] == "vault" and row["after"] is not None:
                        for directory in _directory_chain_create(root, str(row["path"])):
                            if directory["path"] not in seen_dirs:
                                seen_dirs.add(str(directory["path"]))
                                created.append(directory)
                                _write_private_json(journal_dir, _PENDING, _seal(journal))
                    if row["after"] is not None:
                        name, device, inode = _stage_file(
                            root,
                            str(row["path"]),
                            _decode(row["after"]) or b"",
                            plan.transaction_id,
                            mode=int(row["mode"]),
                            staged_name=str(row["stage_temp"]),
                        )
                        row["stage_temp"] = name
                        row["stage_device"] = device
                        row["stage_inode"] = inode
                        _write_private_json(journal_dir, _PENDING, _seal(journal))
                # A file might change even while locks are held because an external
                # editor does not participate. Recheck immediately before decision.
                self._verify_plan(
                    plan,
                    self.registry,
                    own_created_dirs=frozenset(str(row["path"]) for row in created),
                )
                journal["phase"] = "commit"
                _write_private_json(journal_dir, _PENDING, _seal(journal))
                try:
                    for row in rows:
                        _verify_created_directories(plan.vault_root, created)
                        root = _root_for(
                            str(row["domain"]),
                            vault=plan.vault_root,
                            provider=plan.provider_root,
                            registry=self.registry.path,
                        )
                        _publish_row(root, row)
                except Exception as exc:
                    journal["phase"] = "rollback"
                    _write_private_json(journal_dir, _PENDING, _seal(journal))
                    try:
                        self._recover_locked(journal_dir, journal)
                    except Exception as recovery_exc:
                        raise JointFieldTransactionError(
                            "joint commit failed and conditional recovery needs inspection"
                        ) from recovery_exc
                    raise JointFieldTransactionError("joint commit failed and rolled back") from exc
                record = self._finish_locked(journal_dir, journal, committed=True)
                return JointFieldResult(
                    plan.transaction_id,
                    plan.plan_digest,
                    after_revision,
                    tuple(f"{row['domain']}:{row['path']}" for row in rows),
                    record,
                )
            except Exception:
                if journal["phase"] == "prepare":
                    # A normal failure before the commit decision is a clean
                    # abort. A hard kill leaves this same durable phase for
                    # explicit recover(), which never publishes it.
                    self._recover_locked(journal_dir, _read_journal(journal_dir) or journal)
                raise

    def recover(
        self,
        source_id: str,
        field_id: str,
        *,
        external_writers_paused: bool,
    ) -> JointFieldRecovery:
        if not external_writers_paused:
            raise JointFieldTransactionError("external Vault writers must be paused")
        journal_dir = self._journal_dir(source_id, field_id)
        initial = _read_journal(journal_dir)
        if initial is None:
            return JointFieldRecovery(None, "nothing-to-recover", (), None)
        if initial.get("source_id") != source_id or initial.get("field_id") != field_id:
            raise JointFieldTransactionError("joint journal identity is inconsistent")
        root = Path(str(initial["vault_root"]))
        if not root.is_absolute() or initial.get("provider_root") != str(
            self.registry.path.parent / "knowledge-providers" / source_id
        ):
            raise JointFieldTransactionError("joint journal root is unsafe")
        with self._locks(root, source_id):
            current = _read_journal(journal_dir)
            if current is None:
                return JointFieldRecovery(None, "nothing-to-recover", (), None)
            return self._recover_locked(journal_dir, current)

    def _recover_locked(
        self,
        directory: Path,
        journal: dict[str, object],
    ) -> JointFieldRecovery:
        root = Path(str(journal["vault_root"]))
        if _root_identity(root) != (journal["vault_device"], journal["vault_inode"]):
            raise JointFieldTransactionError("Vault identity changed before joint recovery")
        rows = journal.get("rows")
        if not isinstance(rows, list) or len(rows) > _MAX_FILES:
            raise JointFieldTransactionError("joint journal member set is invalid")
        _verify_created_directories(
            root,
            journal.get("created_directories"),
            allow_missing=journal.get("phase") == "rolled-back",
        )
        for row in rows:
            if not isinstance(row, dict) or row.get("path") != _safe_relative(str(row.get("path"))):
                raise JointFieldTransactionError("joint journal member path is invalid")
            target = _root_for(
                str(row.get("domain")),
                vault=root,
                provider=Path(str(journal["provider_root"])),
                registry=self.registry.path,
            )
            if _status_for_phase(target, row, str(journal["phase"])) == "conflict":
                current = _read_file(target, str(row["path"]), missing_parent=True)
                if not (
                    journal["phase"] == "rollback" and current.before == _decode(row["before"])
                ):
                    raise JointFieldTransactionError(
                        f"external edit conflicts with joint recovery: {row['path']}"
                    )
        if journal["phase"] == "prepare":
            for row in rows:
                target = _root_for(
                    str(row["domain"]),
                    vault=root,
                    provider=Path(str(journal["provider_root"])),
                    registry=self.registry.path,
                )
                _cleanup_prepared_stage(target, row)
            _cleanup_unreceipted_prepared_directories(
                root,
                planned=journal.get("planned_directories"),
                receipted=journal.get("created_directories"),
            )
            record = self._finish_locked(directory, journal, committed=False)
            return JointFieldRecovery(
                str(journal["transaction_id"]),
                "rolled-back",
                tuple(str(row["path"]) for row in rows),
                record,
            )
        if journal["phase"] == "commit":
            for row in rows:
                target = _root_for(
                    str(row["domain"]),
                    vault=root,
                    provider=Path(str(journal["provider_root"])),
                    registry=self.registry.path,
                )
                _publish_row(target, row)
            record = self._finish_locked(directory, journal, committed=True)
            return JointFieldRecovery(
                str(journal["transaction_id"]),
                "committed",
                tuple(str(row["path"]) for row in rows),
                record,
            )
        if journal["phase"] == "rollback":
            for row in reversed(rows):
                target = _root_for(
                    str(row["domain"]),
                    vault=root,
                    provider=Path(str(journal["provider_root"])),
                    registry=self.registry.path,
                )
                _rollback_row(target, row)
            record = self._finish_locked(directory, journal, committed=False)
            return JointFieldRecovery(
                str(journal["transaction_id"]),
                "rolled-back",
                tuple(str(row["path"]) for row in rows),
                record,
            )
        if journal["phase"] == "committed":
            record = self._finish_locked(directory, journal, committed=True)
            return JointFieldRecovery(
                str(journal["transaction_id"]),
                "committed",
                tuple(str(row["path"]) for row in rows),
                record,
            )
        if journal["phase"] == "rolled-back":
            record = self._finish_locked(directory, journal, committed=False)
            return JointFieldRecovery(
                str(journal["transaction_id"]),
                "rolled-back",
                tuple(str(row["path"]) for row in rows),
                record,
            )
        raise JointFieldTransactionError("joint journal phase is invalid")

    def _finish_locked(
        self, directory: Path, journal: dict[str, object], *, committed: bool
    ) -> Path:
        rows = journal["rows"]
        assert isinstance(rows, list)
        root = Path(str(journal["vault_root"]))
        for row in rows:
            assert isinstance(row, dict)
            target = _root_for(
                str(row["domain"]),
                vault=root,
                provider=Path(str(journal["provider_root"])),
                registry=self.registry.path,
            )
            state = _status_for_phase(target, row, str(journal["phase"]))
            if committed and state != "after":
                raise JointFieldTransactionError("joint commit receipt is not fully published")
            if not committed and state != "before":
                current = _read_file(target, str(row["path"]), missing_parent=True)
                if current.before != _decode(row["before"]):
                    raise JointFieldTransactionError("joint rollback receipt is incomplete")
        journal["phase"] = "committed" if committed else "rolled-back"
        _write_private_json(directory, _PENDING, _seal(journal))
        for row in rows:
            target = _root_for(
                str(row["domain"]),
                vault=root,
                provider=Path(str(journal["provider_root"])),
                registry=self.registry.path,
            )
            _cleanup_temps(target, row, committed=committed)
        if not committed:
            created = journal.get("created_directories")
            if isinstance(created, list):
                for item in reversed(created):
                    if not isinstance(item, dict):
                        continue
                    relative = _safe_relative(str(item["path"]))
                    try:
                        current = _open_directory_chain(root, PurePosixPath(relative).parts)
                    except FileNotFoundError:
                        continue
                    try:
                        info = os.fstat(current)
                        if (info.st_dev, info.st_ino) != (item["device"], item["inode"]):
                            raise JointFieldTransactionError(
                                "created joint directory changed before cleanup"
                            )
                    finally:
                        os.close(current)
                    parent = _open_directory_chain(root, PurePosixPath(relative).parts[:-1])
                    try:
                        os.rmdir(PurePosixPath(relative).name, dir_fd=parent)
                        os.fsync(parent)
                    except OSError as exc:
                        raise JointFieldTransactionError(
                            "created joint directory is not empty after rollback"
                        ) from exc
                    finally:
                        os.close(parent)
        archived = directory / f"{journal['phase']}-{journal['transaction_id']}.json"
        descriptor = _open_directory_chain(directory)
        try:
            if archived.exists():
                raise JointFieldTransactionError("joint archive identity already exists")
            os.rename(_PENDING, archived.name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return archived

    def plan(
        self,
        *,
        vault_root: Path,
        source_id: str,
        field_id: str,
        registry_after: KnowledgeSourceRegistryDocument,
        manifest_after: FieldManifest,
        provider_base: KnowledgeProviderSnapshot,
        request: AnalysisCommitRequest,
        bundle: AnalysisBundle,
        baseline: AnalysisBaseline,
        source_note_path: str,
        destination_note_path: str,
        reviewed_files: Mapping[str, bytes],
        preserved_paths: Mapping[str, str | None],
        transaction_id: str | None = None,
        bootstrap_provider_after: KnowledgeProviderSnapshot | None = None,
        additional_note_relocations: Mapping[str, str] | None = None,
        note_link_rewrites: Mapping[str, Mapping[str, str]] | None = None,
        artifact_registry_after: bytes | None = None,
        required_existing_documents: Mapping[str, str] | None = None,
        paper_foldering_plan: PaperFolderingPlan | None = None,
    ) -> JointFieldPlan:
        """Make a zero-write, byte/inode-bound proposal for one selected Field."""
        try:
            source_id = str(uuid.UUID(source_id))
            field_id = str(uuid.UUID(field_id))
            txid = transaction_id or uuid.uuid4().hex
            if (
                len(txid) > 128
                or not txid
                or not txid[0].isalnum()
                or any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in txid)
            ):
                raise JointFieldTransactionError("invalid transaction ID")
            root = Path(os.path.abspath(vault_root))
            if root != vault_root or root.is_symlink() or not root.is_dir():
                raise JointFieldTransactionError("Vault root must be an absolute trusted directory")
            root_device, root_inode = _root_identity(root)
            registry_before = _read_file(self.registry.path.parent, self.registry.path.name)
            if registry_before.before is None:
                old_registration = KnowledgeSourceRegistryDocument()
            else:
                old_registration = KnowledgeSourceRegistryDocument.model_validate_json(
                    registry_before.before
                )
            registry_after = KnowledgeSourceRegistryDocument.model_validate(registry_after)
            _validate_registry_after(
                old_registration, registry_after, source_id=source_id, vault_root=root
            )
            manifest_before = _read_file(root, _MANIFEST, missing_parent=True)
            old_manifest = (
                None
                if manifest_before.before is None
                else FieldManifest.model_validate(yaml.safe_load(manifest_before.before))
            )
            manifest_after = FieldManifest.model_validate(manifest_after)
            field = _validate_manifest_after(
                old_manifest, manifest_after, source_id=source_id, field_id=field_id
            )
            field_root = root if field.relative_root == "." else root / field.relative_root
            _root_identity(field_root)
            provider_root = self.registry.path.parent / "knowledge-providers" / source_id
            if provider_root.is_symlink():
                raise JointFieldTransactionError("provider root is a symbolic link")
            provider_before = (
                _read_file(provider_root, _PROVIDER_FILE)
                if provider_root.is_dir()
                else _File(
                    "provider",
                    _PROVIDER_FILE,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0o600,
                    os.geteuid(),
                    "",
                )
            )
            provider_base = KnowledgeProviderSnapshot.model_validate(provider_base)
            expected_binding = KnowledgeVaultBinding(
                root_path=str(root), device=root_device, inode=root_inode
            )
            if provider_base.vault_binding != expected_binding:
                raise JointFieldTransactionError("provider base is not bound to this Vault")
            if provider_before.before is not None:
                disk = KnowledgeProviderSnapshot.model_validate_json(provider_before.before)
                if disk != provider_base:
                    raise JointFieldTransactionError("provider base differs from current snapshot")
            elif provider_base.receipts:
                raise JointFieldTransactionError(
                    "unpublished provider bootstrap has prior receipts"
                )
            if (provider_before.before is None) != (bootstrap_provider_after is not None):
                raise JointFieldTransactionError(
                    "absent provider requires explicit pure bootstrap after graph"
                )
            if provider_before.before is None and paper_foldering_plan is None:
                raise JointFieldTransactionError(
                    "first Field enrollment requires the exact reviewed paper-foldering proposal"
                )
            request = AnalysisCommitRequest.model_validate(request)
            payloads = _canonical_payloads(request, bundle, baseline)
            old_note = _safe_relative(source_note_path)
            new_note = _safe_relative(destination_note_path)
            if not _field_owns(field, old_note) or not _field_owns(field, new_note):
                raise JointFieldTransactionError("paper note relocation escapes selected Field")
            if old_note == new_note or not old_note.endswith(".md") or not new_note.endswith(".md"):
                raise JointFieldTransactionError(
                    "paper note relocation requires distinct Markdown paths"
                )
            note = _read_file(root, old_note)
            if note.before is None:
                raise JointFieldTransactionError("paper owner note is missing")
            if _has_analysis_identity(note.before) or _has_analysis_sidecar(root, old_note):
                raise JointFieldTransactionError("paper owner note is managed analysis content")
            _assert_field_owned_markdown(note.before)
            if _read_file(root, new_note, missing_parent=True).before is not None:
                raise JointFieldTransactionError("paper owner note destination already exists")
            rewrites = note_link_rewrites or {}
            if set(rewrites) - ({old_note} | set(additional_note_relocations or {})):
                raise JointFieldTransactionError("note rewrite does not identify a relocation")
            proposed: dict[str, bytes | None] = {
                old_note: None,
                new_note: _rewritten_note(
                    _foldering_note_base(paper_foldering_plan, old_note, note.before),
                    rewrites.get(old_note, {}),
                ),
            }
            additional = tuple(
                sorted(
                    (_safe_relative(source), _safe_relative(destination))
                    for source, destination in (additional_note_relocations or {}).items()
                )
            )
            if additional and provider_before.before is not None:
                raise JointFieldTransactionError(
                    "additional provider owner moves require a pure bootstrap graph"
                )
            for source, destination in additional:
                if (
                    source == old_note
                    or destination == new_note
                    or (source == destination or source in proposed or destination in proposed)
                ):
                    raise JointFieldTransactionError("paper note relocations overlap")
                if (
                    not _field_owns(field, source)
                    or not _field_owns(field, destination)
                    or (not source.endswith(".md") or not destination.endswith(".md"))
                ):
                    raise JointFieldTransactionError("additional note relocation is outside Field")
                original = _read_file(root, source)
                if (
                    original.before is None
                    or _has_analysis_identity(original.before)
                    or (_has_analysis_sidecar(root, source))
                ):
                    raise JointFieldTransactionError(
                        "additional relocation source is missing or managed analysis"
                    )
                _assert_field_owned_markdown(original.before)
                if _read_file(root, destination, missing_parent=True).before is not None:
                    raise JointFieldTransactionError("additional relocation destination exists")
                proposed[source] = None
                proposed[destination] = _rewritten_note(
                    _foldering_note_base(paper_foldering_plan, source, original.before),
                    rewrites.get(source, {}),
                )
            for path, payload in payloads.items():
                if not _field_owns(field, path):
                    raise JointFieldTransactionError("analysis bundle escapes selected Field")
                if path in proposed:
                    raise JointFieldTransactionError("analysis overlaps paper note relocation")
                if _read_file(root, path, missing_parent=True).before is not None:
                    raise JointFieldTransactionError("joint placement only creates a new v4 triple")
                proposed[path] = payload
            for path, payload in reviewed_files.items():
                safe = _safe_relative(path)
                if safe in proposed or not isinstance(payload, bytes):
                    raise JointFieldTransactionError("reviewed file overlaps the paper placement")
                _validate_reviewed_file(root, field, safe, payload)
                proposed[safe] = payload
            if len(proposed) + len(preserved_paths) > _MAX_FILES:
                raise JointFieldTransactionError("joint transaction exceeds the file limit")
            preserved: list[_File] = []
            for path, expected_hash in sorted(preserved_paths.items()):
                safe = _safe_relative(path)
                if not _field_owns(field, safe) or safe in proposed:
                    raise JointFieldTransactionError("preserved path escapes or overlaps placement")
                current = _read_file(root, safe, missing_parent=True)
                actual = None if current.before is None else _hash(current.before)
                if actual != expected_hash:
                    raise JointFieldTransactionError(f"preserved source changed: {safe}")
                preserved.append(current)
            new_manifest = yaml.safe_dump(
                manifest_after.model_dump(mode="json"), allow_unicode=True, sort_keys=False
            ).encode()
            new_registry = (registry_after.model_dump_json(indent=2) + "\n").encode()
            proposed[_MANIFEST] = new_manifest
            old_artifacts = _read_file(root, _ARTIFACT_MANIFEST, missing_parent=True)
            if old_artifacts.before is not None:
                old_rows = _artifact_rows(old_artifacts.before)
                selected_canvas = next(
                    (
                        row
                        for row in old_rows
                        if row.artifact_id == request.document.artifact_id + ":canvas"
                    ),
                    None,
                )
                if selected_canvas is not None and (
                    selected_canvas.vault_path != request.paths.canvas
                    and artifact_registry_after is None
                ):
                    raise JointFieldTransactionError(
                        "old Canvas identity requires an exact artifact manifest relocation"
                    )
            if artifact_registry_after is not None:
                if old_artifacts.before is None:
                    raise JointFieldTransactionError(
                        "Vault artifact manifest relocation requires an existing manifest"
                    )
                _validate_artifact_manifest_change(
                    old_artifacts.before, artifact_registry_after, request
                )
                old_canvas = next(
                    row.vault_path
                    for row in _artifact_rows(old_artifacts.before)
                    if row.artifact_id == request.document.artifact_id + ":canvas"
                )
                old_canvas_bytes = _read_file(root, old_canvas).before
                if old_canvas_bytes is None or preserved_paths.get(old_canvas) != (
                    _hash(old_canvas_bytes)
                ):
                    raise JointFieldTransactionError(
                        "old analysis Canvas must be explicitly preserved byte-for-byte"
                    )
                proposed[_ARTIFACT_MANIFEST] = artifact_registry_after
            required: list[tuple[str, str, int, int]] = []
            for path, expected_sha in sorted((required_existing_documents or {}).items()):
                safe = _safe_relative(path)
                if (
                    not _field_owns(field, safe)
                    or safe not in proposed
                    or proposed[safe] is not None
                ):
                    raise JointFieldTransactionError(
                        "required existing document was not included in note relocation"
                    )
                observed = _read_file(root, safe)
                if observed.before is None or _hash(observed.before) != expected_sha:
                    raise JointFieldTransactionError(f"required existing document changed: {safe}")
                assert observed.device is not None and observed.inode is not None
                required.append((safe, expected_sha, observed.device, observed.inode))
            if provider_before.before is None and not required:
                raise JointFieldTransactionError(
                    "first enrollment requires a complete explicit paper-note inventory"
                )
            if provider_before.before is None and {row[0] for row in required} != {
                path for path, after in proposed.items() if after is None
            }:
                raise JointFieldTransactionError(
                    "first enrollment inventory must equal every relocated paper note"
                )
            declared_navigation = {_field_path(field, name) for name in _managed_paths(field)}
            if {new_note, *(destination for _source, destination in additional)} - (
                declared_navigation
            ):
                raise JointFieldTransactionError(
                    "a relocated paper note is missing from new Field navigation"
                )
            if paper_foldering_plan is not None:
                _validate_foldering_candidate(
                    paper_foldering_plan,
                    root=root,
                    vault_identity=(root_device, root_inode),
                    field=field,
                    source_note=old_note,
                    destination_note=new_note,
                    additional=additional,
                    note_link_rewrites=rewrites,
                    proposed=proposed,
                )
            _check_field_coverage(root, field, proposed, preserved_paths)
            _check_deleted_note_references(
                root,
                field,
                proposed,
                (old_note, *(source for source, _destination in additional)),
            )
            inventory_digest = _field_inventory_digest(root, field.relative_root)
            members = [
                _member(
                    root,
                    path,
                    after,
                    domain="vault",
                    kind=(
                        "manifest"
                        if path == _MANIFEST
                        else "owner-note-removal"
                        if path == old_note
                        else "content"
                    ),
                    missing_parent=True,
                )
                for path, after in sorted(proposed.items())
            ]
            members.append(
                _member(
                    self.registry.path.parent,
                    self.registry.path.name,
                    new_registry,
                    domain="registry",
                    kind="registry",
                )
            )
            for member in members:
                if (
                    member.domain == "vault"
                    and member.relative.endswith((".md", ".canvas"))
                    and member.after is not None
                    and _has_legacy_hub_reference(member.after, member.relative)
                ):
                    raise JointFieldTransactionError(
                        f"old Hub URL remains in proposed content: {member.relative}"
                    )
            total = sum(len(row.before or b"") + len(row.after or b"") for row in members)
            if total > _MAX_BYTES:
                raise JointFieldTransactionError("joint transaction exceeds its byte limit")
            summaries = [
                {
                    "domain": row.domain,
                    "path": row.relative,
                    "before": None if row.before is None else _hash(row.before),
                    "after": None if row.after is None else _hash(row.after),
                    "device": row.device,
                    "inode": row.inode,
                    "parent_device": row.parent_device,
                    "parent_inode": row.parent_inode,
                    "kind": row.kind,
                }
                for row in members
            ]
            semantic = {
                "transaction_id": txid,
                "source_id": source_id,
                "field_id": field_id,
                "vault_root": str(root),
                "vault_device": root_device,
                "vault_inode": root_inode,
                "provider_base": provider_base.snapshot_revision,
                "provider_base_payload": _hash(_json_bytes(provider_base.model_dump(mode="json"))),
                "provider_before": None
                if provider_before.before is None
                else _hash(provider_before.before),
                "provider_bootstrap_after": (
                    None
                    if bootstrap_provider_after is None
                    else _hash(_json_bytes(bootstrap_provider_after.model_dump(mode="json")))
                ),
                "additional_note_relocations": list(additional),
                "required_existing_documents": [
                    {"path": path, "sha256": sha, "device": device, "inode": inode}
                    for path, sha, device, inode in required
                ],
                "paper_foldering": _foldering_binding(paper_foldering_plan),
                "field_relative_root": field.relative_root,
                "field_inventory_digest": inventory_digest,
                "provider_device": provider_before.device,
                "provider_inode": provider_before.inode,
                "request": request.model_dump(mode="json"),
                "prepared_note": {
                    "source": old_note,
                    "destination": new_note,
                    "sha256": _hash(note.before),
                },
                "preserved": [
                    {
                        "path": row.relative,
                        "hash": None if row.before is None else _hash(row.before),
                        "device": row.device,
                        "inode": row.inode,
                    }
                    for row in preserved
                ],
                "members": summaries,
            }
            digest = _hash(_json_bytes(semantic))
            artifacts = [
                KnowledgeArtifactChange(
                    artifact_id=request.document.artifact_id + suffix,
                    resource_id=request.resource_id,
                    kind=kind,
                    vault_path=path,
                    sha256=_hash(payloads[path]),
                )
                for suffix, kind, path in (
                    ("", "analysis_markdown", request.paths.markdown),
                    (":canvas", "analysis_canvas", request.paths.canvas),
                    (":sidecar", "analysis_sidecar", request.paths.sidecar),
                )
            ]
            prepared = prepare_joint_paper_placement(
                snapshot=provider_base,
                request=request,
                vault_binding=expected_binding,
                transaction_id=txid,
                plan_digest=digest,
                source_note_path=old_note,
                destination_note_path=new_note,
                note_sha256=_hash(note.before),
                new_artifacts=artifacts,
            )
            if bootstrap_provider_after is not None:
                bootstrap_provider_after = KnowledgeProviderSnapshot.model_validate(
                    bootstrap_provider_after
                )
                if bootstrap_provider_after.receipts or bootstrap_provider_after != (
                    _bootstrap_graph_with_relocations(prepared, additional)
                ):
                    raise JointFieldTransactionError(
                        "provider bootstrap after graph does not exactly match joint placement"
                    )
                _validate_provider_file_coverage(
                    bootstrap_provider_after,
                    root=root,
                    proposed=proposed,
                    preserved_paths=preserved_paths,
                )
            changes = tuple(
                JointFileChange(
                    row.domain,
                    row.relative,
                    None if row.before is None else _hash(row.before),
                    None if row.after is None else _hash(row.after),
                    row.kind,
                )
                for row in members
                if row.before != row.after
            )
            text_diffs: list[dict[str, str]] = []
            for row in members:
                if (
                    row.domain == "vault"
                    and row.before is not None
                    and row.after is not None
                    and row.relative.endswith((".md", ".yml"))
                    and row.before != row.after
                ):
                    diff = _human_diff(row.before, row.after, label=row.relative)
                    if diff:
                        text_diffs.append({"path": row.relative, "diff": diff})
            moves: list[dict[str, str]] = []
            for source, destination in ((old_note, new_note), *additional):
                old_bytes = next(row.before for row in members if row.relative == source)
                after_bytes = next(row.after for row in members if row.relative == destination)
                assert old_bytes is not None and after_bytes is not None
                moves.append(
                    {
                        "source": source,
                        "destination": destination,
                        "before_sha256": _hash(old_bytes),
                        "after_sha256": _hash(after_bytes),
                    }
                )
                if old_bytes != after_bytes:
                    diff = _human_diff(old_bytes, after_bytes, label=f"{source} → {destination}")
                    if diff:
                        text_diffs.append({"path": destination, "diff": diff})
            preview = json.dumps(
                {
                    "transaction_id": txid,
                    "plan_digest": digest,
                    "changes": [row.__dict__ for row in changes],
                    "preserved": [row.relative for row in preserved],
                    "provider_before": semantic["provider_before"],
                    "provider_after_catalog": prepared.after_catalog_revision,
                    "moves": moves,
                    "paper_foldering_plan_digest": (
                        None if paper_foldering_plan is None else paper_foldering_plan.plan_digest
                    ),
                    "text_diffs": text_diffs,
                },
                ensure_ascii=False,
                indent=2,
            )
            if len(preview.encode()) > _MAX_DIFF:
                raise JointFieldTransactionError("joint preview exceeds size limit")
            return JointFieldPlan(
                txid,
                source_id,
                field_id,
                root,
                root_device,
                root_inode,
                provider_root,
                provider_base,
                provider_before.before,
                provider_before.device,
                provider_before.inode,
                registry_before.before,
                tuple(members),
                tuple(preserved),
                prepared,
                bootstrap_provider_after,
                additional,
                tuple(required),
                paper_foldering_plan,
                field.relative_root,
                inventory_digest,
                changes,
                digest,
                preview,
            )
        except JointFieldTransactionError:
            raise
        except (OSError, ValueError, TypeError, FieldRegistryError) as exc:
            raise JointFieldTransactionError(str(exc)) from exc
