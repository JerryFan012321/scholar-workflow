"""One explicitly approved, recoverable Field enrollment transaction.

The browser-facing plan accepts only an opaque Field candidate. A trusted
local author may additionally propose a bounded Markdown/Canvas bundle or a
mechanically validated legacy analysis triple. The latter binds a conservation
review and a conformant Markdown/Canvas/sidecar to exact source bytes, but
does not itself prove human approval. The journal lives outside the Vault and
is recovery state, not a backup.

The local plan can also relocate singly owned ordinary Markdown/Canvas files
within the selected Field. Each move binds both paths, source inode and bytes,
an absent destination, required directories, and explicit link rewrites. Managed
analysis pairs and external-owned notes remain outside this relocation path.

This low-level implementation assumes its existing state_root parent and
private 0700 recovery subtree are exclusively controlled by trusted processes
of the current user. Directory operations reject symlink ancestors and use
nofollow dirfds, but repeated opens cannot defeat a malicious same-user
rename/rebind of an ordinary directory. Write access must remain behind a
separate local-operator approval and an externally arranged writer-pause flow.
"""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import os
import re
import secrets
import stat
import threading
import time
import uuid
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from difflib import unified_diff
from pathlib import Path, PurePosixPath

import yaml

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.legacy_cutover import PreparedLegacyFieldPayload
from scholar_workflow.analysis.models import AnalysisBaseline
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import AnalysisUpdateError, create_baseline
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload
from scholar_workflow.hub.field_migration import (
    FieldMigrationError,
    FieldMigrationService,
    ZoteroPdfLinkResolver,
    _has_legacy_hub_reference,
    _managed_paths,
    _replacements,
    _validate_canvas,
)
from scholar_workflow.knowledge.fields import (
    _DIRECTORY_FLAGS,
    _MAX_FIELD_DOCUMENT_BYTES,
    FieldDefinition,
    FieldManifest,
    FieldRegistryError,
    FieldService,
    _assert_field_owned_markdown,
    _open_directory_chain,
    _read_regular_at,
    _safe_relative,
)

_WRITE_FLAGS = (
    os.O_WRONLY
    | os.O_CREAT
    | os.O_EXCL
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_STATE_DIR = ".scholar-workflow"
_MANIFEST = ".scholar-workflow/fields.yml"
_JOURNAL = "pending.json"
_MAX_BUNDLE_FILES = 256
_MAX_TRANSACTION_BYTES = 32 * 1024 * 1024
_MAX_PREVIEW_DIFF_BYTES = 1024 * 1024
_V2_ANALYSIS_KIND = re.compile(rb"(?m)^\s*sw_kind\s*:\s*['\"]?paper-analysis\b")
_STAGED_NAME = re.compile(r"\.scholar-field-[0-9a-f]{32}\.tmp\Z")
_RESTORE_NAME = re.compile(r"\.scholar-restore-[0-9a-f]{32}\.tmp\Z")
_SNAPSHOT_NAME = re.compile(r"originals-[0-9a-f]{16}\.zip\Z")


class FieldTransactionError(RuntimeError):
    """The proposed Field transaction is stale, unsafe, or unrecoverable."""


@dataclass(frozen=True)
class FieldTransactionChange:
    relative_path: str
    before_sha256: str | None
    after_sha256: str | None
    kind: str
    preview_diff: str


@dataclass(frozen=True)
class FieldTransactionPlan:
    plan_token: str
    plan_digest: str
    source_id: str
    field_id: str
    field_title: str
    changes: tuple[FieldTransactionChange, ...]
    replaced_links: int
    unresolved_files: tuple[str, ...]
    conflicts: tuple[str, ...]
    registry_before_sha256: str | None
    registry_after_sha256: str
    analysis_conformance: str = "not-evaluated"
    analysis_cutover_digests: tuple[str, ...] = ()
    recovery_is_verified_backup: bool = False
    relocations: tuple[FieldTransactionRelocation, ...] = ()


@dataclass(frozen=True)
class FieldTransactionRelocation:
    source_path: str
    destination_path: str
    source_sha256: str
    destination_sha256: str
    source_device: int
    source_inode: int
    created_directories: tuple[str, ...]
    link_rewrites: tuple[tuple[str, str, str, int], ...]


@dataclass(frozen=True)
class FieldTransactionResult:
    source_id: str
    field_id: str
    changed_files: tuple[str, ...]
    replaced_links: int
    recovery_snapshot: Path
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class FieldTransactionRecovery:
    source_id: str
    field_id: str
    outcome: str
    recovered_files: tuple[str, ...]
    recovery_snapshot: Path | None
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class _Target:
    relative_path: str
    before: bytes | None
    after: bytes
    device: int | None
    inode: int | None
    mode: int
    owner: int
    kind: str
    new_device: int | None = None
    new_inode: int | None = None
    restore_device: int | None = None
    restore_inode: int | None = None
    temporary_name: str | None = None
    restore_temporary_name: str | None = None

    @property
    def old_hash(self) -> str | None:
        return None if self.before is None else _hash(self.before)

    @property
    def new_hash(self) -> str:
        return _hash(self.after)


@dataclass(frozen=True)
class _Removal:
    relative_path: str
    before: bytes
    device: int
    inode: int
    mode: int
    owner: int
    restore_device: int | None = None
    restore_inode: int | None = None
    restore_temporary_name: str | None = None


@dataclass(frozen=True)
class _Directory:
    relative_path: str
    device: int | None
    inode: int | None
    new_device: int | None = None
    new_inode: int | None = None


@dataclass(frozen=True)
class _Pending:
    plan: FieldTransactionPlan
    field_definition: FieldDefinition
    root: Path
    root_device: int
    root_inode: int
    field_device: int
    field_inode: int
    candidate_token: str
    inventory_digest: str
    targets: tuple[_Target, ...]
    registry_before: bytes | None
    registry_after: bytes
    registry_revision: str
    expires_at: float
    verified_links: tuple[tuple[str, str], ...]
    removals: tuple[_Removal, ...] = ()
    directories: tuple[_Directory, ...] = ()


def _hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _identity(path: Path) -> tuple[int, int]:
    descriptor = _open_directory_chain(path)
    try:
        metadata = os.fstat(descriptor)
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(descriptor)


def _open_private_directory(path: Path) -> int:
    """Walk an absolute recovery path by descriptor, rejecting ancestor links."""
    if not path.is_absolute():
        raise FieldTransactionError("recovery directory path is not absolute")
    descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_target(
    root: Path, relative: str, *, allow_missing_parent: bool = False
) -> tuple[bytes, os.stat_result] | None:
    parts = PurePosixPath(relative).parts
    try:
        parent_fd = _open_directory_chain(root, parts[:-1])
    except FileNotFoundError:
        if relative == _MANIFEST or allow_missing_parent:
            return None
        raise FieldTransactionError(f"target parent is missing: {relative}") from None
    except OSError as exc:
        raise FieldTransactionError(f"target parent is unsafe: {relative}") from exc
    try:
        try:
            return _read_regular_at(parent_fd, parts[-1], limit=_MAX_FIELD_DOCUMENT_BYTES)
        except FileNotFoundError:
            return None
        except (OSError, FieldRegistryError) as exc:
            raise FieldTransactionError(f"target is unsafe: {relative}") from exc
    finally:
        os.close(parent_fd)


def _read_registry(path: Path) -> bytes | None:
    if path.is_symlink():
        raise FieldTransactionError("source registry is a symbolic link")
    try:
        parent_fd = _open_directory_chain(path.parent)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FieldTransactionError("source registry parent is unsafe") from exc
    try:
        try:
            content, _ = _read_regular_at(parent_fd, path.name, limit=_MAX_FIELD_DOCUMENT_BYTES)
            return content
        except FileNotFoundError:
            return None
        except (OSError, FieldRegistryError) as exc:
            raise FieldTransactionError("source registry is unsafe") from exc
    finally:
        os.close(parent_fd)


def _target_from(
    root: Path, relative: str, after: bytes, kind: str, *, allow_missing_parent: bool = False
) -> _Target:
    old = _read_target(root, relative, allow_missing_parent=allow_missing_parent)
    if old is None:
        return _Target(relative, None, after, None, None, 0o600, os.geteuid(), kind)
    content, metadata = old
    if metadata.st_uid != os.geteuid() or metadata.st_nlink != 1:
        raise FieldTransactionError(f"target is not singly linked and owned: {relative}")
    return _Target(
        relative,
        content,
        after,
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        kind,
    )


def _preview_diff(target: _Target) -> str:
    before = "" if target.before is None else target.before.decode("utf-8")
    after = target.after.decode("utf-8")
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"before/{target.relative_path}",
            tofile=f"after/{target.relative_path}",
        )
    )


def _removal_diff(removal: _Removal) -> str:
    return "".join(
        unified_diff(
            removal.before.decode("utf-8").splitlines(keepends=True),
            [],
            fromfile=f"before/{removal.relative_path}",
            tofile=f"after/{removal.relative_path}",
        )
    )


def _directory_plan(root: Path, relative: str) -> _Directory:
    try:
        device, inode = _identity(root / relative)
    except FileNotFoundError:
        return _Directory(relative, None, None)
    except OSError as exc:
        raise FieldTransactionError(f"relocation directory is unsafe: {relative}") from exc
    return _Directory(relative, device, inode)


def _directory_is_old(root: Path, directory: _Directory) -> bool:
    try:
        identity = _identity(root / directory.relative_path)
    except FileNotFoundError:
        identity = None
    except OSError as exc:
        raise FieldTransactionError(
            f"relocation directory is unsafe: {directory.relative_path}"
        ) from exc
    expected = None if directory.device is None else (directory.device, directory.inode)
    return identity == expected


def _directory_is_new(root: Path, directory: _Directory) -> bool:
    if directory.new_device is None or directory.new_inode is None:
        return False
    try:
        descriptor = _open_directory_chain(root / directory.relative_path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise FieldTransactionError(
            f"relocation directory is unsafe: {directory.relative_path}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        return (
            (metadata.st_dev, metadata.st_ino) == (directory.new_device, directory.new_inode)
            and metadata.st_uid == os.geteuid()
            and stat.S_IMODE(metadata.st_mode) == 0o700
        )
    finally:
        os.close(descriptor)


def _removal_is_old(current: tuple[bytes, os.stat_result] | None, removal: _Removal) -> bool:
    if current is None:
        return False
    content, metadata = current
    return (
        content == removal.before
        and (metadata.st_dev, metadata.st_ino) == (removal.device, removal.inode)
        and stat.S_IMODE(metadata.st_mode) == removal.mode
        and metadata.st_uid == removal.owner
        and metadata.st_nlink == 1
    )


def _removal_is_restored(current: tuple[bytes, os.stat_result] | None, removal: _Removal) -> bool:
    if current is None:
        return False
    content, metadata = current
    return (
        content == removal.before
        and (metadata.st_dev, metadata.st_ino)
        in {(removal.device, removal.inode), (removal.restore_device, removal.restore_inode)}
        and stat.S_IMODE(metadata.st_mode) == removal.mode
        and metadata.st_uid == removal.owner
        and metadata.st_nlink == 1
    )


def _has_analysis_identity(content: bytes) -> bool:
    return (
        bool(_V2_ANALYSIS_KIND.search(content))
        or b"sw-analysis-claim" in content
        or b"sw-analysis-field" in content
    )


def _has_analysis_sidecar(root: Path, relative: str) -> bool:
    path = PurePosixPath(relative)
    candidates = {path.with_suffix(".analysis.json").as_posix()}
    if path.name.endswith("解析树.canvas"):
        candidates.add(
            path.with_name(
                path.name.removesuffix("解析树.canvas") + "分析.analysis.json"
            ).as_posix()
        )
    return any(_read_target(root, candidate) is not None for candidate in candidates)


def _inspect_existing_v2_analyses(
    root: Path,
    field: FieldDefinition,
    inventory: Sequence[str],
    validated_legacy_paths: set[str],
) -> tuple[tuple[tuple[str, str, str, str], ...], tuple[str, ...]]:
    """Read-only conformance gate for already present analysis triples.

    A Canvas next to an ordinary Markdown file is not, by itself, an analysis
    identity. A v2 marker, an analysis claim marker, or an analysis sidecar is.
    Existing files replaced by a separately validated cutover are exempt.
    """
    field_parts = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    owned_markdown = {
        PurePosixPath(*field_parts, *PurePosixPath(name).parts).as_posix()
        for name in _managed_paths(field)
        if PurePosixPath(name).suffix.casefold() == ".md"
    }
    present = set(inventory)
    notes: set[str] = set()
    for relative in inventory:
        name = PurePosixPath(relative).name
        if name.casefold().endswith(".analysis.json"):
            notes.add(relative[: -len(".analysis.json")] + ".md")
        elif PurePosixPath(relative).suffix.casefold() == ".md":
            current = _read_target(root, relative)
            assert current is not None
            if _has_analysis_identity(current[0]):
                notes.add(relative)
        elif PurePosixPath(relative).suffix.casefold() == ".canvas":
            current = _read_target(root, relative)
            assert current is not None
            if not _has_analysis_identity(current[0]):
                continue
            canvas_path = PurePosixPath(relative)
            possible_notes = {canvas_path.with_suffix(".md").as_posix()}
            if canvas_path.name.endswith("解析树.canvas"):
                possible_notes.add(
                    canvas_path.with_name(
                        canvas_path.name.removesuffix("解析树.canvas") + "分析.md"
                    ).as_posix()
                )
            matching_notes = possible_notes & present
            notes.update(matching_notes or possible_notes)

    validated: list[tuple[str, str, str, str]] = []
    conflicts: list[str] = []
    claimed_canvas: set[str] = set()
    for relative in sorted(notes):
        if relative in validated_legacy_paths:
            continue
        markdown = PurePosixPath(relative)
        sidecar_path = markdown.with_suffix(".analysis.json").as_posix()
        canvas_paths = {markdown.with_suffix(".canvas").as_posix()}
        if markdown.name.endswith("分析.md"):
            canvas_paths.add(
                markdown.with_name(
                    markdown.name.removesuffix("分析.md") + "解析树.canvas"
                ).as_posix()
            )
        existing_canvas = sorted(canvas_paths & present)
        if (
            relative not in owned_markdown
            or relative not in present
            or sidecar_path not in present
            or len(existing_canvas) != 1
            or existing_canvas[0] in claimed_canvas
        ):
            conflicts.append(
                f"existing paper analysis requires a complete owned pair or validated cutover: {relative}"
            )
            continue
        markdown_source = _read_target(root, relative)
        canvas_source = _read_target(root, existing_canvas[0])
        sidecar_source = _read_target(root, sidecar_path)
        assert markdown_source is not None and canvas_source is not None
        assert sidecar_source is not None
        if not _V2_ANALYSIS_KIND.search(markdown_source[0]):
            conflicts.append(
                f"existing paper analysis lacks v2 identity; validated cutover required: {relative}"
            )
            continue
        try:
            baseline = AnalysisBaseline.model_validate_json(sidecar_source[0])
            candidate = AnalysisBundle(
                markdown_source[0].decode("utf-8"), json.loads(canvas_source[0])
            )
            if baseline.note_stem != markdown.stem:
                raise ValueError("baseline note stem differs from its Markdown")
            report = validate_bundle(baseline.document, candidate, note_stem=markdown.stem)
            if not report.ok:
                raise ValueError("Markdown/Canvas conformance failed")
            expected = create_baseline(baseline.document, candidate, note_stem=markdown.stem)
            if expected.model_dump(mode="json") != baseline.model_dump(mode="json"):
                raise ValueError("sidecar baseline does not bind the pair")
        except (AnalysisUpdateError, TypeError, UnicodeDecodeError, ValueError) as exc:
            conflicts.append(
                f"existing paper analysis is not conformant; validated cutover required: {relative}: {exc}"
            )
            continue
        claimed_canvas.add(existing_canvas[0])
        validated.append(
            (
                relative,
                _hash(markdown_source[0]),
                _hash(canvas_source[0]),
                _hash(sidecar_source[0]),
            )
        )
    return tuple(validated), tuple(conflicts)


def _current_is_old(current: tuple[bytes, os.stat_result] | None, target: _Target) -> bool:
    if target.before is None:
        return current is None
    if current is None:
        return False
    content, metadata = current
    return (
        content == target.before
        and (metadata.st_dev, metadata.st_ino) == (target.device, target.inode)
        and stat.S_IMODE(metadata.st_mode) == target.mode
        and metadata.st_uid == target.owner
        and metadata.st_nlink == 1
    )


def _current_is_new(current: tuple[bytes, os.stat_result] | None, target: _Target) -> bool:
    if current is None or target.new_device is None or target.new_inode is None:
        return False
    content, metadata = current
    return (
        content == target.after
        and (metadata.st_dev, metadata.st_ino) == (target.new_device, target.new_inode)
        and stat.S_IMODE(metadata.st_mode) == target.mode
        and metadata.st_uid == target.owner
        and metadata.st_nlink == 1
    )


def _restored_is_old(current: tuple[bytes, os.stat_result] | None, target: _Target) -> bool:
    if target.before is None:
        return current is None
    if current is None:
        return False
    content, metadata = current
    return (
        content == target.before
        and (metadata.st_dev, metadata.st_ino)
        in {
            (target.device, target.inode),
            (target.restore_device, target.restore_inode),
        }
        and stat.S_IMODE(metadata.st_mode) == target.mode
        and metadata.st_uid == target.owner
        and metadata.st_nlink == 1
    )


def _validate_bundle_path(field: FieldDefinition, name: str, content: bytes) -> str:
    try:
        relative = _safe_relative(name)
    except ValueError as exc:
        raise FieldTransactionError("staged bundle contains an unsafe path") from exc
    if len(content) > _MAX_FIELD_DOCUMENT_BYTES:
        raise FieldTransactionError(f"staged file is too large: {relative}")
    if any(part.startswith(".") for part in PurePosixPath(relative).parts):
        raise FieldTransactionError("staged bundle cannot write hidden or state paths")
    if relative.endswith(".analysis.json"):
        raise FieldTransactionError(
            "analysis sidecar requires a validated bundle receipt before staging"
        )
    elif relative.endswith(".canvas"):
        try:
            validate_canvas_payload(json.loads(content))
            _validate_canvas(content, relative)
        except (CanvasValidationError, FieldMigrationError, ValueError, UnicodeDecodeError) as exc:
            raise FieldTransactionError(f"invalid JSON Canvas: {relative}") from exc
    elif relative.endswith(".md"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FieldTransactionError(f"invalid Markdown UTF-8: {relative}") from exc
        if b"\x00" in content:
            raise FieldTransactionError(f"invalid Markdown NUL byte: {relative}")
    else:
        raise FieldTransactionError(
            "staged bundle accepts only Markdown, Canvas, or analysis sidecars"
        )
    field_parts = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    return PurePosixPath(*field_parts, *PurePosixPath(relative).parts).as_posix()


def _validate_manifest_with_staged_documents(
    field_service: FieldService,
    root: Path,
    manifest: FieldManifest,
    selected: FieldDefinition,
    staged: Mapping[str, bytes],
    *,
    allow_missing_parents: set[str] | None = None,
) -> None:
    """Permit new selected-Field documents only when their bytes are staged."""
    for field in manifest.fields:
        field_parts = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
        for name in _managed_paths(field):
            relative = PurePosixPath(*field_parts, *PurePosixPath(name).parts).as_posix()
            if field.field_id == selected.field_id and relative in staged:
                # A missing leaf is allowed, but its parent and any existing
                # target must already be safe regular filesystem objects.
                previous = _read_target(
                    root,
                    relative,
                    allow_missing_parent=relative in (allow_missing_parents or set()),
                )
                if relative.endswith(".md"):
                    if previous is not None:
                        _assert_field_owned_markdown(previous[0])
                    _assert_field_owned_markdown(staged[relative])
            else:
                field_service._validate_document_path(root, field, name)


def _validated_legacy_files(
    root: Path,
    field: FieldDefinition,
    payload: PreparedLegacyFieldPayload,
) -> dict[str, bytes]:
    """Bind one mechanically checked analysis triple to exact current files."""
    if not isinstance(payload, PreparedLegacyFieldPayload):
        raise FieldTransactionError("legacy analysis requires a validated payload")
    markdown = PurePosixPath(payload.markdown_path)
    same_stem_canvas = markdown.with_suffix(".canvas").as_posix()
    canonical_canvas = (
        markdown.with_name(markdown.name.removesuffix("分析.md") + "解析树.canvas").as_posix()
        if markdown.name.endswith("分析.md")
        else None
    )
    if (
        markdown.suffix != ".md"
        or payload.canvas_path not in {same_stem_canvas, canonical_canvas}
        or payload.sidecar_path != markdown.with_suffix(".analysis.json").as_posix()
    ):
        raise FieldTransactionError("legacy analysis paths do not match the note pair")
    paths = (payload.markdown_path, payload.canvas_path, payload.sidecar_path)
    files = (payload.markdown, payload.canvas, payload.sidecar)
    sources = (
        payload.source_markdown_sha256,
        payload.source_canvas_sha256,
        payload.source_sidecar_sha256,
    )
    proposed: dict[str, bytes] = {}
    for index, (name, content, expected_source) in enumerate(
        zip(paths, files, sources, strict=True)
    ):
        try:
            safe = _safe_relative(name)
        except ValueError as exc:
            raise FieldTransactionError("legacy analysis path is unsafe") from exc
        if any(part.startswith(".") for part in PurePosixPath(safe).parts):
            raise FieldTransactionError("legacy analysis path is hidden")
        if not isinstance(content, bytes) or len(content) > _MAX_FIELD_DOCUMENT_BYTES:
            raise FieldTransactionError("legacy analysis candidate is invalid or too large")
        if index < 2:
            relative = _validate_bundle_path(field, safe, content)
        else:
            field_parts = (
                () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
            )
            relative = PurePosixPath(*field_parts, *PurePosixPath(safe).parts).as_posix()
        current = _read_target(root, relative)
        actual_source = None if current is None else hashlib.sha256(current[0]).hexdigest()
        if actual_source != expected_source:
            raise FieldTransactionError(f"legacy analysis source changed: {relative}")
        if index < 2 and current is None:
            raise FieldTransactionError(f"legacy analysis source is missing: {relative}")
        proposed[relative] = content
    try:
        baseline = AnalysisBaseline.model_validate_json(payload.sidecar)
        candidate = AnalysisBundle(payload.markdown.decode("utf-8"), json.loads(payload.canvas))
        if baseline.note_stem != markdown.stem:
            raise FieldTransactionError("legacy analysis baseline stem changed")
        conformance = validate_bundle(baseline.document, candidate, note_stem=markdown.stem)
        if not conformance.ok:
            raise FieldTransactionError("legacy analysis bundle is not conformant")
        expected_baseline = create_baseline(baseline.document, candidate, note_stem=markdown.stem)
        if expected_baseline.model_dump(mode="json") != baseline.model_dump(mode="json"):
            raise FieldTransactionError("legacy analysis sidecar does not bind the candidate")
    except (UnicodeDecodeError, ValueError, AnalysisUpdateError) as exc:
        raise FieldTransactionError("legacy analysis sidecar or bundle is invalid") from exc
    digest_payload = {
        "kind": "legacy-field-payload",
        "schema_version": 1,
        "cutover_digest": payload.cutover_digest,
        "sources": {name: digest for name, digest in zip(paths, sources, strict=True)},
        "targets": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in zip(paths, files, strict=True)
        },
    }
    actual_digest = hashlib.sha256(
        json.dumps(
            digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if actual_digest != payload.payload_digest or not re.fullmatch(
        r"[0-9a-f]{64}", payload.cutover_digest
    ):
        raise FieldTransactionError("legacy analysis payload digest changed")
    return proposed


class FieldTransactionService:
    """Stage one previewed Field, then commit its files and identity together."""

    def __init__(
        self,
        field_service: FieldService,
        *,
        state_root: Path,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
        link_resolver: Callable[[str], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("plan TTL must be positive")
        self.field_service = field_service
        self.registry = field_service.registry
        if not self.registry.path.is_absolute():
            raise ValueError("source registry path must be absolute")
        self.state_root = Path(state_root)
        if not self.state_root.is_absolute() or self.state_root == Path(self.state_root.anchor):
            raise ValueError("state_root must be a private absolute directory")
        self._ttl = ttl_seconds
        self._clock = clock
        self._link_resolver = link_resolver or ZoteroPdfLinkResolver()
        self._plans: dict[str, _Pending] = {}
        self._lock = threading.RLock()

    def plan(
        self,
        candidate_token: str,
        field_id: str,
        *,
        field_definition: FieldDefinition | None = None,
        staged_bundle: Mapping[str, bytes] | None = None,
        legacy_payloads: Sequence[PreparedLegacyFieldPayload] = (),
        relocations: Mapping[str, str] | None = None,
        link_rewrites: Mapping[str, Mapping[str, str]] | None = None,
    ) -> FieldTransactionPlan:
        """Read only: compute every proposed byte and bind one Field approval."""
        with self._lock:
            candidate = self.field_service.candidates.peek(candidate_token)
            preview = candidate.preview
            if preview.registration_only:
                raise FieldTransactionError("portable Source registration uses confirm_source")
            selected = next((field for field in preview.fields if field.field_id == field_id), None)
            if selected is None:
                raise FieldTransactionError("Field was not selected in this preview")
            preview_managed_names = set(_managed_paths(selected))
            if field_definition is not None:
                try:
                    revised = FieldDefinition.model_validate(field_definition.model_dump())
                except (AttributeError, ValueError) as exc:
                    raise FieldTransactionError("invalid proposed Field definition") from exc
                if (revised.field_id, revised.relative_root) != (
                    selected.field_id,
                    selected.relative_root,
                ):
                    raise FieldTransactionError("proposed Field changed its preview identity")
                relocation_names = set(relocations or {})
                omitted = (
                    set(_managed_paths(selected)) - set(_managed_paths(revised)) - relocation_names
                )
                if omitted:
                    raise FieldTransactionError(
                        "proposed Field navigation omitted previewed documents: "
                        + ", ".join(sorted(omitted))
                    )
                selected = revised
            try:
                root = self.field_service._validate_candidate(candidate)
                manifest = FieldManifest(
                    source_id=preview.source_id,
                    fields=[*preview.registered_fields, selected],
                )
                registration = self.field_service._planned_registration(
                    root, manifest, preview.folder_id
                )
            except FieldRegistryError as exc:
                raise FieldTransactionError(str(exc)) from exc
            bundle = staged_bundle or {}
            if len(bundle) + 3 * len(legacy_payloads) > _MAX_BUNDLE_FILES:
                raise FieldTransactionError("staged bundle has too many files")
            if (
                sum(len(content) for content in bundle.values() if isinstance(content, bytes))
                + sum(
                    len(content)
                    for payload in legacy_payloads
                    for content in (payload.markdown, payload.canvas, payload.sidecar)
                )
                > _MAX_TRANSACTION_BYTES
            ):
                raise FieldTransactionError("staged bundle is too large")
            proposed: dict[str, bytes] = {}
            removals: list[_Removal] = []
            directory_by_path: dict[str, _Directory] = {}
            relocation_pairs: dict[str, str] = {}
            recorded_rewrites: list[tuple[str, str, str, int]] = []
            field_parts = (
                () if selected.relative_root == "." else PurePosixPath(selected.relative_root).parts
            )
            declared_names = set(_managed_paths(selected))
            for name, content in bundle.items():
                if not isinstance(content, bytes):
                    raise FieldTransactionError("staged bundle values must be bytes")
                relative = _validate_bundle_path(selected, name, content)
                if name.endswith(".md") and name not in declared_names:
                    raise FieldTransactionError(
                        "new Markdown requires a previewed manifest navigation change"
                    )
                if name.endswith((".canvas", ".analysis.json")):
                    stem = (
                        name.removesuffix(".canvas")
                        if name.endswith(".canvas")
                        else name.removesuffix(".analysis.json")
                    )
                    if stem + ".md" not in declared_names:
                        raise FieldTransactionError(
                            "Canvas and sidecar require a manifest-owned Markdown peer"
                        )
                existing = _read_target(root, relative)
                if existing is not None and existing[0] != content:
                    raise FieldTransactionError(
                        "existing Markdown or Canvas requires a validated migration bundle"
                    )
                if relative in proposed:
                    raise FieldTransactionError("duplicate staged path")
                proposed[relative] = content
            validated_legacy_paths: set[str] = set()
            legacy_digests: list[tuple[str, str]] = []
            for payload in legacy_payloads:
                if payload.markdown_path not in declared_names:
                    raise FieldTransactionError(
                        "legacy analysis Markdown is not owned by the proposed Field"
                    )
                legacy_files = _validated_legacy_files(root, selected, payload)
                if any(relative in proposed for relative in legacy_files):
                    raise FieldTransactionError("legacy analysis overlaps another staged file")
                proposed.update(legacy_files)
                validated_legacy_paths.update(legacy_files)
                legacy_digests.append((payload.cutover_digest, payload.payload_digest))
            if relocations is not None and not isinstance(relocations, Mapping):
                raise FieldTransactionError("Field relocations must be a path mapping")
            if (
                relocations
                and len(relocations) + len(bundle) + 3 * len(legacy_payloads) > _MAX_BUNDLE_FILES
            ):
                raise FieldTransactionError("Field relocation has too many files")
            normalized_relocations: dict[str, str] = {}
            for source_name, destination_name in (relocations or {}).items():
                if not isinstance(source_name, str) or not isinstance(destination_name, str):
                    raise FieldTransactionError("Field relocation paths must be strings")
                try:
                    source_safe = _safe_relative(source_name)
                    destination_safe = _safe_relative(destination_name)
                except ValueError as exc:
                    raise FieldTransactionError("Field relocation path is unsafe") from exc
                if any(
                    part.startswith(".")
                    for part in (
                        *PurePosixPath(source_safe).parts,
                        *PurePosixPath(destination_safe).parts,
                    )
                ):
                    raise FieldTransactionError("Field relocation path is hidden")
                if source_safe in normalized_relocations:
                    raise FieldTransactionError("duplicate Field relocation source")
                normalized_relocations[source_safe] = destination_safe
            if len(set(normalized_relocations.values())) != len(normalized_relocations):
                raise FieldTransactionError("Field relocation destinations must be unique")
            if set(normalized_relocations) & set(normalized_relocations.values()):
                raise FieldTransactionError("Field relocation paths overlap")
            for source_safe, destination_safe in sorted(normalized_relocations.items()):
                if source_safe == destination_safe:
                    raise FieldTransactionError("Field relocation paths overlap")
                source_relative = PurePosixPath(
                    *field_parts, *PurePosixPath(source_safe).parts
                ).as_posix()
                destination_relative = PurePosixPath(
                    *field_parts, *PurePosixPath(destination_safe).parts
                ).as_posix()
                if source_relative in proposed or destination_relative in proposed:
                    raise FieldTransactionError("Field relocation overlaps a staged file")
                source = _read_target(root, source_relative)
                if source is None:
                    raise FieldTransactionError(
                        f"Field relocation source is missing: {source_safe}"
                    )
                source_content, source_meta = source
                if source_meta.st_uid != os.geteuid() or source_meta.st_nlink != 1:
                    raise FieldTransactionError(
                        "Field relocation source is not singly linked and owned"
                    )
                if source_safe.endswith(".analysis.json") or _has_analysis_identity(source_content):
                    raise FieldTransactionError(
                        "managed analysis relocation requires a validated paired cutover"
                    )
                if source_safe.endswith((".md", ".canvas")) and _has_analysis_sidecar(
                    root, source_relative
                ):
                    raise FieldTransactionError(
                        "managed analysis relocation requires a validated paired cutover"
                    )
                if source_safe.endswith(".md"):
                    try:
                        _assert_field_owned_markdown(source_content)
                    except FieldRegistryError as exc:
                        raise FieldTransactionError(
                            "external-owned Markdown cannot be relocated"
                        ) from exc
                _validate_bundle_path(selected, destination_safe, source_content)
                if _read_target(root, destination_relative, allow_missing_parent=True) is not None:
                    raise FieldTransactionError(
                        f"Field relocation destination already exists: {destination_safe}"
                    )
                if source_safe in declared_names or (
                    source_safe in preview_managed_names and destination_safe not in declared_names
                ):
                    raise FieldTransactionError(
                        "relocated navigation document requires path substitution in the manifest"
                    )
                for depth in range(
                    len(field_parts) + 1, len(PurePosixPath(destination_relative).parts)
                ):
                    parent_relative = PurePosixPath(
                        *PurePosixPath(destination_relative).parts[:depth]
                    ).as_posix()
                    directory_by_path.setdefault(
                        parent_relative, _directory_plan(root, parent_relative)
                    )
                for depth in range(len(field_parts) + 1, len(PurePosixPath(source_relative).parts)):
                    parent_relative = PurePosixPath(
                        *PurePosixPath(source_relative).parts[:depth]
                    ).as_posix()
                    directory_by_path.setdefault(
                        parent_relative, _directory_plan(root, parent_relative)
                    )
                relocation_pairs[source_relative] = destination_relative
                proposed[destination_relative] = source_content
                removals.append(
                    _Removal(
                        source_relative,
                        source_content,
                        source_meta.st_dev,
                        source_meta.st_ino,
                        stat.S_IMODE(source_meta.st_mode),
                        source_meta.st_uid,
                    )
                )
            if link_rewrites and not relocations:
                raise FieldTransactionError("path link rewrites require a Field relocation")
            for document_name, replacements in sorted((link_rewrites or {}).items()):
                if not isinstance(document_name, str) or not isinstance(replacements, Mapping):
                    raise FieldTransactionError("Field link rewrite is invalid")
                try:
                    document_safe = _safe_relative(document_name)
                except ValueError as exc:
                    raise FieldTransactionError("Field link rewrite path is unsafe") from exc
                relative = PurePosixPath(
                    *field_parts, *PurePosixPath(document_safe).parts
                ).as_posix()
                destination = relocation_pairs.get(relative, relative)
                if destination in proposed and relative not in relocation_pairs:
                    raise FieldTransactionError("Field link rewrite overlaps a staged file")
                if relative not in relocation_pairs:
                    current = _read_target(root, relative)
                    if current is None:
                        raise FieldTransactionError("Field link rewrite document is missing")
                    if _has_analysis_identity(current[0]) or _has_analysis_sidecar(root, relative):
                        raise FieldTransactionError("managed analysis links require paired update")
                    if document_safe.endswith(".md"):
                        try:
                            _assert_field_owned_markdown(current[0])
                        except FieldRegistryError as exc:
                            raise FieldTransactionError(
                                "external-owned Markdown links cannot be rewritten"
                            ) from exc
                    proposed[destination] = current[0]
                revised_bytes = proposed[destination]
                for old_text, new_text in sorted(replacements.items()):
                    if (
                        not isinstance(old_text, str)
                        or not isinstance(new_text, str)
                        or not old_text
                        or old_text == new_text
                    ):
                        raise FieldTransactionError("Field link rewrite text is invalid")
                    before = old_text.encode("utf-8")
                    count = revised_bytes.count(before)
                    if count == 0:
                        raise FieldTransactionError("Field link rewrite source is absent")
                    revised_bytes = revised_bytes.replace(before, new_text.encode("utf-8"))
                    recorded_rewrites.append((relative, old_text, new_text, count))
                _validate_bundle_path(selected, document_safe, revised_bytes)
                if document_safe.endswith(".md"):
                    try:
                        _assert_field_owned_markdown(revised_bytes)
                    except FieldRegistryError as exc:
                        raise FieldTransactionError(
                            "external-owned Markdown links cannot be rewritten"
                        ) from exc
                proposed[destination] = revised_bytes
            try:
                _validate_manifest_with_staged_documents(
                    self.field_service,
                    root,
                    manifest,
                    selected,
                    proposed,
                    allow_missing_parents=set(relocation_pairs.values()),
                )
            except FieldRegistryError as exc:
                raise FieldTransactionError(str(exc)) from exc
            replaced_links = 0
            verified: dict[str, str] = {}
            for name in _managed_paths(selected):
                if PurePosixPath(name).suffix.casefold() not in {".md", ".canvas"}:
                    raise FieldTransactionError("manifest declares an unsupported managed file")
                relative = PurePosixPath(*field_parts, *PurePosixPath(name).parts).as_posix()
                old = _read_target(
                    root,
                    relative,
                    allow_missing_parent=relative in relocation_pairs.values(),
                )
                if old is None:
                    if relative in proposed:
                        continue
                    raise FieldTransactionError(f"manifest-owned file is missing: {name}")
                if relative in validated_legacy_paths:
                    # Rewriting a validated projection would invalidate its
                    # sidecar. Inspect old links only for identity checks.
                    _ignored, changes = _replacements(old[0], name)
                else:
                    before = proposed.get(relative, old[0])
                    after, changes = _replacements(before, name)
                    proposed[relative] = after
                replaced_links += sum(change.occurrences for change in changes)
                for change in changes:
                    verified[change.attachment_key] = change.replacement
            for destination in relocation_pairs.values():
                after, changes = _replacements(proposed[destination], destination)
                proposed[destination] = after
                replaced_links += sum(change.occurrences for change in changes)
                for change in changes:
                    verified[change.attachment_key] = change.replacement
            for relative, content in proposed.items():
                if _has_legacy_hub_reference(content, relative):
                    raise FieldTransactionError(f"old Hub URL remains in staged file: {relative}")
            inventory, inventory_digest, inventory_conflicts = FieldMigrationService._inventory(
                root, manifest, selected
            )
            conflicts = list(preview.conflicts) + list(inventory_conflicts)
            existing_validated, existing_analysis_conflicts = _inspect_existing_v2_analyses(
                root, selected, inventory, validated_legacy_paths
            )
            conflicts.extend(existing_analysis_conflicts)
            unresolved: list[str] = []
            for relative in inventory:
                current = _read_target(root, relative)
                assert current is not None
                if (
                    relative.endswith(".md")
                    and relative not in validated_legacy_paths
                    and b"sw-analysis-field" in current[0]
                ):
                    conflicts.append(
                        f"legacy analysis requires a validated paired cutover: {relative}"
                    )
                if relative in proposed or relative in relocation_pairs:
                    continue
                if _has_legacy_hub_reference(current[0], relative):
                    unresolved.append(relative)
            for source_relative, destination_relative in relocation_pairs.items():
                field_relative_source = (
                    PurePosixPath(source_relative)
                    .relative_to(PurePosixPath(*field_parts) if field_parts else PurePosixPath("."))
                    .as_posix()
                )
                references = {source_relative.encode("utf-8")}
                if "/" in field_relative_source:
                    references.add(field_relative_source.encode("utf-8"))
                field_relative_destination = (
                    PurePosixPath(destination_relative)
                    .relative_to(PurePosixPath(*field_parts) if field_parts else PurePosixPath("."))
                    .as_posix()
                )
                destination_references = {
                    destination_relative.encode("utf-8"),
                    field_relative_destination.encode("utf-8"),
                }
                for relative in inventory:
                    effective = proposed.get(relocation_pairs.get(relative, relative))
                    if effective is None:
                        existing = _read_target(root, relative)
                        assert existing is not None
                        effective = existing[0]
                    without_new_paths = effective
                    for destination_reference in destination_references:
                        without_new_paths = without_new_paths.replace(destination_reference, b"")
                    if any(reference in without_new_paths for reference in references):
                        conflicts.append(
                            f"Field relocation retains a source-path reference: {relative}"
                        )
            if unresolved:
                conflicts.append("unmapped Field files retain old Hub URLs")
            for key, expected in sorted(verified.items()):
                try:
                    actual = self._link_resolver(key)
                except (OSError, RuntimeError, ValueError) as exc:
                    conflicts.append(f"Zotero attachment {key} could not be verified: {exc}")
                    continue
                if actual != expected:
                    conflicts.append(f"Zotero attachment {key} has a different identity")
            manifest_bytes = yaml.safe_dump(
                manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False
            ).encode("utf-8")
            registry_bytes = (registration.model_dump_json(indent=2) + "\n").encode("utf-8")
            targets: list[_Target] = []
            for relative, content in sorted(proposed.items()):
                target = _target_from(
                    root,
                    relative,
                    content,
                    "relocation-destination"
                    if relative in relocation_pairs.values()
                    else "content",
                    allow_missing_parent=relative in relocation_pairs.values(),
                )
                if target.before != target.after:
                    sidecar_peer = (
                        PurePosixPath(relative).with_suffix(".analysis.json").as_posix()
                        if relative.endswith((".md", ".canvas"))
                        else None
                    )
                    if (
                        target.before is not None
                        and relative not in validated_legacy_paths
                        and (
                            relative.endswith(".analysis.json")
                            or relative.endswith((".md", ".canvas"))
                            and _has_analysis_identity(target.before)
                            or sidecar_peer is not None
                            and _read_target(root, sidecar_peer) is not None
                        )
                    ):
                        raise FieldTransactionError(
                            "legacy analysis changes require a separately validated migration"
                        )
                    targets.append(target)
            manifest_target = _target_from(root, _MANIFEST, manifest_bytes, "manifest")
            if manifest_target.before == manifest_target.after:
                raise FieldTransactionError("the selected Field already exists in the manifest")
            targets.append(manifest_target)
            if (
                sum(len(target.after) + len(target.before or b"") for target in targets)
                + sum(len(removal.before) for removal in removals)
                > _MAX_TRANSACTION_BYTES
            ):
                raise FieldTransactionError("Field transaction exceeds the snapshot limit")
            registry_before = _read_registry(self.registry.path)
            registry_revision = "absent" if registry_before is None else _hash(registry_before)
            changes = tuple(
                FieldTransactionChange(
                    target.relative_path,
                    target.old_hash,
                    target.new_hash,
                    target.kind,
                    _preview_diff(target),
                )
                for target in targets
            ) + tuple(
                FieldTransactionChange(
                    removal.relative_path,
                    _hash(removal.before),
                    None,
                    "relocation-source",
                    _removal_diff(removal),
                )
                for removal in removals
            )
            if (
                sum(len(change.preview_diff.encode("utf-8")) for change in changes)
                > _MAX_PREVIEW_DIFF_BYTES
            ):
                raise FieldTransactionError("Field diff is too large for explicit preview")
            digest_payload = {
                "source_id": preview.source_id,
                "field_id": field_id,
                "root_identity": _identity(root),
                "field_identity": _identity(root.joinpath(*field_parts)),
                "manifest_base": preview.manifest_base_hash,
                "registry_base": registry_revision,
                "registry_new": _hash(registry_bytes),
                "inventory": inventory_digest,
                "changes": [asdict(change) for change in changes],
                "relocations": [
                    {
                        "source_path": removal.relative_path,
                        "destination_path": relocation_pairs[removal.relative_path],
                        "source_device": removal.device,
                        "source_inode": removal.inode,
                        "source_mode": removal.mode,
                        "source_owner": removal.owner,
                        "source_sha256": _hash(removal.before),
                        "destination_sha256": _hash(
                            proposed[relocation_pairs[removal.relative_path]]
                        ),
                    }
                    for removal in removals
                ],
                "relocation_directories": [asdict(row) for row in directory_by_path.values()],
                "path_link_rewrites": recorded_rewrites,
                "validated_legacy_payloads": sorted(legacy_digests),
                "validated_existing_analyses": existing_validated,
                "conflicts": conflicts,
                "unresolved": unresolved,
            }
            plan_digest = _hash(json.dumps(digest_payload, sort_keys=True).encode("utf-8"))
            relocation_details = tuple(
                FieldTransactionRelocation(
                    removal.relative_path,
                    relocation_pairs[removal.relative_path],
                    _hash(removal.before),
                    _hash(proposed[relocation_pairs[removal.relative_path]]),
                    removal.device,
                    removal.inode,
                    tuple(
                        row.relative_path
                        for row in directory_by_path.values()
                        if row.device is None
                        and PurePosixPath(row.relative_path).parts
                        == PurePosixPath(relocation_pairs[removal.relative_path]).parts[
                            : len(PurePosixPath(row.relative_path).parts)
                        ]
                    ),
                    tuple(recorded_rewrites),
                )
                for removal in removals
            )
            token = f"ft_{secrets.token_urlsafe(24)}"
            plan = FieldTransactionPlan(
                token,
                plan_digest,
                preview.source_id,
                field_id,
                selected.title,
                changes,
                replaced_links,
                tuple(unresolved),
                tuple(conflicts),
                None if registry_before is None else _hash(registry_before),
                _hash(registry_bytes),
                (
                    "validated-legacy-and-existing-v2"
                    if legacy_digests and existing_validated
                    else "validated-legacy-cutover"
                    if legacy_digests
                    else "validated-existing-v2"
                    if existing_validated
                    else "not-evaluated"
                ),
                tuple(digest for digest, _payload_digest in sorted(legacy_digests)),
                relocations=relocation_details,
            )
            root_device, root_inode = _identity(root)
            field_device, field_inode = _identity(root.joinpath(*field_parts))
            self._plans[token] = _Pending(
                plan,
                selected,
                root,
                root_device,
                root_inode,
                field_device,
                field_inode,
                candidate_token,
                inventory_digest,
                tuple(targets),
                registry_before,
                registry_bytes,
                registry_revision,
                self._clock() + self._ttl,
                tuple(sorted(verified.items())),
                tuple(removals),
                tuple(directory_by_path.values()),
            )
            return plan

    def _state_directory(
        self, root: Path | None, source_id: str, field_id: str, *, create: bool
    ) -> Path:
        try:
            if str(uuid.UUID(source_id)) != source_id or str(uuid.UUID(field_id)) != field_id:
                raise ValueError("noncanonical UUID")
        except ValueError as exc:
            raise FieldTransactionError("invalid Field recovery identity") from exc
        if self.state_root.is_symlink():
            raise FieldTransactionError("recovery state root is a symbolic link")
        prospective = self.state_root.resolve(strict=False)
        if root is not None and (prospective == root or root in prospective.parents):
            raise FieldTransactionError("recovery state must be outside the Vault")
        path = self.state_root.parent
        try:
            directory_fd = _open_private_directory(path)
        except OSError as exc:
            raise FieldTransactionError("recovery state parent is unavailable or unsafe") from exc
        try:
            state_root_identity: tuple[int, int] | None = None
            for part in (self.state_root.name, "field-transactions", source_id, field_id):
                try:
                    child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                except FileNotFoundError:
                    if not create:
                        return self.state_root / "field-transactions" / source_id / field_id
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                    child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                    try:
                        os.fsync(child_fd)
                        os.fsync(directory_fd)
                    except BaseException:
                        os.close(child_fd)
                        raise
                if stat.S_IMODE(os.fstat(child_fd).st_mode) & 0o077:
                    os.close(child_fd)
                    raise FieldTransactionError("recovery directory must be private")
                if part == self.state_root.name and state_root_identity is None:
                    stat_result = os.fstat(child_fd)
                    state_root_identity = stat_result.st_dev, stat_result.st_ino
                os.close(directory_fd)
                directory_fd = child_fd
                path /= part
            resolved_base = self.state_root.resolve(strict=True)
            if root is not None and (resolved_base == root or root in resolved_base.parents):
                raise FieldTransactionError("recovery state must be outside the Vault")
            resolved_fd = _open_private_directory(resolved_base)
            try:
                resolved_stat = os.fstat(resolved_fd)
                resolved_identity = resolved_stat.st_dev, resolved_stat.st_ino
            finally:
                os.close(resolved_fd)
            if resolved_identity != state_root_identity:
                raise FieldTransactionError("recovery state directory changed during creation")
            return path
        except OSError as exc:
            raise FieldTransactionError("recovery directory could not be durably created") from exc
        finally:
            os.close(directory_fd)

    @contextmanager
    def _guard(self, root: Path) -> Iterator[Callable[[], None]]:
        root_fd = _open_directory_chain(root)
        state_fd: int | None = None
        lock_fd: int | None = None
        try:
            fcntl.flock(root_fd, fcntl.LOCK_EX)

            def ensure_state_lock() -> None:
                nonlocal state_fd, lock_fd
                if lock_fd is not None:
                    return
                try:
                    state_fd = _open_directory_chain(root, (_STATE_DIR,))
                except FileNotFoundError:
                    os.mkdir(_STATE_DIR, 0o700, dir_fd=root_fd)
                    os.fsync(root_fd)
                    state_fd = _open_directory_chain(root, (_STATE_DIR,))
                assert state_fd is not None
                lock_fd = os.open(
                    ".field-writes.lock",
                    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=state_fd,
                )
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise FieldTransactionError("Field write lock is unsafe")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)

            if (root / _STATE_DIR).is_symlink():
                raise FieldTransactionError("Field state directory is a symbolic link")
            if (root / _STATE_DIR).exists():
                ensure_state_lock()
            yield ensure_state_lock
        finally:
            if lock_fd is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            if state_fd is not None:
                os.close(state_fd)
            fcntl.flock(root_fd, fcntl.LOCK_UN)
            os.close(root_fd)

    @staticmethod
    def _snapshot(directory: Path, pending: _Pending) -> Path:
        path = directory / f"originals-{secrets.token_hex(8)}.zip"
        directory_fd = _open_private_directory(directory)
        try:
            descriptor = os.open(path.name, _WRITE_FLAGS, 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as handle:
                with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED) as archive:
                    receipt = {
                        "schema_version": 2 if pending.removals else 1,
                        "plan_digest": pending.plan.plan_digest,
                        "source_id": pending.plan.source_id,
                        "field_id": pending.plan.field_id,
                        "verified_backup": False,
                        "originals": {
                            target.relative_path: target.old_hash for target in pending.targets
                        },
                    }
                    if pending.removals:
                        receipt["removed_originals"] = {
                            removal.relative_path: _hash(removal.before)
                            for removal in pending.removals
                        }
                        receipt["directories"] = [
                            {
                                "relative_path": row.relative_path,
                                "device": row.device,
                                "inode": row.inode,
                            }
                            for row in pending.directories
                        ]
                        receipt["relocations"] = [
                            {
                                "source_path": row.source_path,
                                "destination_path": row.destination_path,
                                "source_sha256": row.source_sha256,
                                "destination_sha256": row.destination_sha256,
                            }
                            for row in pending.plan.relocations
                        ]
                    archive.writestr("recovery.json", json.dumps(receipt, sort_keys=True))
                    for target in pending.targets:
                        if target.before is not None:
                            archive.writestr("original/" + target.relative_path, target.before)
                        archive.writestr("proposed/" + target.relative_path, target.after)
                    for removal in pending.removals:
                        archive.writestr("removed/" + removal.relative_path, removal.before)
                    if pending.registry_before is not None:
                        archive.writestr("registry/original", pending.registry_before)
                    archive.writestr("registry/proposed", pending.registry_after)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(directory_fd)
        except BaseException:
            try:
                os.unlink(path.name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(directory_fd)
        return path

    def _write_journal(
        self, directory: Path, pending: _Pending, snapshot_name: str
    ) -> dict[str, object]:
        field = pending.field_definition
        payload = {
            "schema_version": 3 if pending.removals else 2,
            "plan_digest": pending.plan.plan_digest,
            "source_id": pending.plan.source_id,
            "field_id": pending.plan.field_id,
            "root": str(pending.root),
            "root_device": pending.root_device,
            "root_inode": pending.root_inode,
            "field_device": pending.field_device,
            "field_inode": pending.field_inode,
            "field_relative_root": field.relative_root,
            "registry_path": str(self.registry.path),
            "registry_old_hash": None
            if pending.registry_before is None
            else _hash(pending.registry_before),
            "registry_new_hash": _hash(pending.registry_after),
            "manifest_new_hash": next(
                target.new_hash for target in pending.targets if target.kind == "manifest"
            ),
            "snapshot_name": snapshot_name,
            "targets": [
                {
                    "relative_path": target.relative_path,
                    "old_hash": target.old_hash,
                    "new_hash": target.new_hash,
                    "device": target.device,
                    "inode": target.inode,
                    "mode": target.mode,
                    "owner": target.owner,
                    "kind": target.kind,
                    "new_device": None,
                    "new_inode": None,
                    "restore_device": None,
                    "restore_inode": None,
                    "temporary_name": f".scholar-field-{secrets.token_hex(16)}.tmp",
                    "restore_temporary_name": None,
                }
                for target in pending.targets
            ],
        }
        if pending.removals:
            payload["relocations"] = [
                {
                    "source_path": row.source_path,
                    "destination_path": row.destination_path,
                    "source_sha256": row.source_sha256,
                    "destination_sha256": row.destination_sha256,
                }
                for row in pending.plan.relocations
            ]
            payload["removals"] = [
                {
                    "relative_path": removal.relative_path,
                    "old_hash": _hash(removal.before),
                    "device": removal.device,
                    "inode": removal.inode,
                    "mode": removal.mode,
                    "owner": removal.owner,
                    "restore_device": None,
                    "restore_inode": None,
                    "restore_temporary_name": None,
                }
                for removal in pending.removals
            ]
            payload["directories"] = [
                {
                    "relative_path": row.relative_path,
                    "device": row.device,
                    "inode": row.inode,
                    "new_device": None,
                    "new_inode": None,
                }
                for row in pending.directories
            ]
        content = json.dumps(payload, sort_keys=True).encode("utf-8")
        if len(content) > _MAX_FIELD_DOCUMENT_BYTES:
            raise FieldTransactionError("recovery journal is too large")
        temporary = f".journal-{secrets.token_hex(8)}.tmp"
        directory_fd = _open_private_directory(directory)
        try:
            descriptor = os.open(temporary, _WRITE_FLAGS, 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(
                temporary,
                _JOURNAL,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)
        return payload

    @staticmethod
    def _commit_journal_update(directory: Path, payload: dict[str, object]) -> None:
        content = json.dumps(payload, sort_keys=True).encode("utf-8")
        if len(content) > _MAX_FIELD_DOCUMENT_BYTES:
            raise FieldTransactionError("Field journal update exceeds the size limit")
        directory_fd = _open_private_directory(directory)
        temporary = f".journal-{secrets.token_hex(16)}.tmp"
        try:
            descriptor = os.open(temporary, _WRITE_FLAGS, 0o600, dir_fd=directory_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, _JOURNAL, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            os.close(directory_fd)

    def _set_journal_owner(
        self,
        directory: Path,
        source_id: str,
        field_id: str,
        relative: str,
        *,
        phase: str,
        temporary_name: str | None,
        device: int | None,
        inode: int | None,
    ) -> None:
        payload = self._read_journal(directory, source_id, field_id)
        rows = payload["targets"]
        assert isinstance(rows, list)
        row = next(
            (
                item
                for item in rows
                if isinstance(item, dict) and item.get("relative_path") == relative
            ),
            None,
        )
        if row is None or phase not in {"new", "restore"}:
            if payload.get("schema_version") == 3 and phase in {"directory", "remove-restore"}:
                collection = payload["directories" if phase == "directory" else "removals"]
                assert isinstance(collection, list)
                owner_row = next(
                    (
                        item
                        for item in collection
                        if isinstance(item, dict) and item.get("relative_path") == relative
                    ),
                    None,
                )
                if owner_row is None:
                    raise FieldTransactionError("Field journal ownership target is invalid")
                if phase == "directory":
                    if (
                        "temporary_name" in owner_row
                        or temporary_name is not None
                        or device is None
                        or inode is None
                    ):
                        raise FieldTransactionError("Field directory ownership is not reserved")
                    owner_row["new_device"] = device
                    owner_row["new_inode"] = inode
                else:
                    if owner_row.get("restore_temporary_name") not in {None, temporary_name}:
                        raise FieldTransactionError("Field removal restore ownership changed")
                    owner_row["restore_temporary_name"] = temporary_name
                    owner_row["restore_device"] = device
                    owner_row["restore_inode"] = inode
                self._commit_journal_update(directory, payload)
                return
            raise FieldTransactionError("Field journal ownership target is invalid")
        if phase == "new":
            if row.get("temporary_name") != temporary_name or device is None or inode is None:
                raise FieldTransactionError("Field staged ownership is not reserved")
            row["new_device"] = device
            row["new_inode"] = inode
        else:
            prior = row.get("restore_temporary_name")
            if prior not in {None, temporary_name}:
                raise FieldTransactionError("Field restore ownership changed")
            row["restore_temporary_name"] = temporary_name
            row["restore_device"] = device
            row["restore_inode"] = inode
        self._commit_journal_update(directory, payload)

    def _assert_current(self, pending: _Pending) -> None:
        candidate = self.field_service.candidates.peek(pending.candidate_token)
        try:
            root = self.field_service._validate_candidate(candidate)
        except FieldRegistryError as exc:
            raise FieldTransactionError(str(exc)) from exc
        if root != pending.root or _identity(root) != (pending.root_device, pending.root_inode):
            raise FieldTransactionError("Field root changed after plan")
        field = pending.field_definition
        parts = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
        if _identity(root.joinpath(*parts)) != (pending.field_device, pending.field_inode):
            raise FieldTransactionError("Field folder changed after plan")
        manifest = FieldManifest(
            source_id=pending.plan.source_id,
            fields=[*candidate.preview.registered_fields, field],
        )
        _inventory, digest, conflicts = FieldMigrationService._inventory(root, manifest, field)
        if conflicts or digest != pending.inventory_digest:
            raise FieldTransactionError("Field inventory changed after plan")
        for target in pending.targets:
            if not _current_is_old(
                _read_target(
                    root,
                    target.relative_path,
                    allow_missing_parent=target.kind == "relocation-destination",
                ),
                target,
            ):
                raise FieldTransactionError(
                    f"Field target changed after plan: {target.relative_path}"
                )
        for removal in pending.removals:
            if not _removal_is_old(_read_target(root, removal.relative_path), removal):
                raise FieldTransactionError(
                    f"Field relocation source changed after plan: {removal.relative_path}"
                )
        for directory in pending.directories:
            if not _directory_is_old(root, directory):
                raise FieldTransactionError(
                    f"Field relocation directory changed after plan: {directory.relative_path}"
                )
        registry = _read_registry(self.registry.path)
        if registry != pending.registry_before:
            raise FieldTransactionError("source registry changed after plan")

    @staticmethod
    def _replace(
        root: Path,
        target: _Target,
        content: bytes,
        *,
        expect_new: bool,
        temporary_name: str,
        record_owner: Callable[[int, int], None],
    ) -> tuple[int, int]:
        relative = target.relative_path
        parts = PurePosixPath(relative).parts
        if relative == _MANIFEST and target.before is None:
            root_fd = _open_directory_chain(root)
            try:
                try:
                    os.mkdir(_STATE_DIR, 0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
            finally:
                os.close(root_fd)
        parent_fd = _open_directory_chain(root, parts[:-1])
        temporary = temporary_name
        try:
            current = _read_target(root, relative)
            if expect_new:
                if not _current_is_new(current, target):
                    raise FieldTransactionError(f"Field target changed before recovery: {relative}")
            elif not _current_is_old(current, target):
                raise FieldTransactionError(f"Field target changed before commit: {relative}")
            descriptor = os.open(temporary, _WRITE_FLAGS, target.mode, dir_fd=parent_fd)
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), target.mode)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                prepared = os.fstat(handle.fileno())
            record_owner(prepared.st_dev, prepared.st_ino)
            check_fd = _open_directory_chain(root, parts[:-1])
            try:
                if (os.fstat(check_fd).st_dev, os.fstat(check_fd).st_ino) != (
                    os.fstat(parent_fd).st_dev,
                    os.fstat(parent_fd).st_ino,
                ):
                    raise FieldTransactionError("Field parent changed before replace")
            finally:
                os.close(check_fd)
            current = _read_target(root, relative)
            if expect_new:
                if not _current_is_new(current, target):
                    raise FieldTransactionError(f"Field target changed before recovery: {relative}")
            elif not _current_is_old(current, target):
                raise FieldTransactionError(f"Field target changed before commit: {relative}")
            if target.before is None and not expect_new:
                os.link(
                    temporary,
                    parts[-1],
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            else:
                os.replace(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
            return prepared.st_dev, prepared.st_ino
        finally:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)

    @staticmethod
    def _remove_created(root: Path, target: _Target) -> None:
        parts = PurePosixPath(target.relative_path).parts
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            if not _current_is_new(_read_target(root, target.relative_path), target):
                raise FieldTransactionError(f"created Field target changed: {target.relative_path}")
            os.unlink(parts[-1], dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    @staticmethod
    def _create_directory(
        root: Path,
        directory: _Directory,
        *,
        record_owner: Callable[[int, int], None],
    ) -> tuple[int, int]:
        if directory.device is not None or not _directory_is_old(root, directory):
            raise FieldTransactionError("Field relocation directory changed before creation")
        parts = PurePosixPath(directory.relative_path).parts
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            # mkdir at the final name is no-replace. If the process stops
            # before its inode reaches the journal, recovery leaves the
            # unowned directory untouched for manual review.
            os.mkdir(parts[-1], mode=0o700, dir_fd=parent_fd)
            child_fd = os.open(parts[-1], _DIRECTORY_FLAGS, dir_fd=parent_fd)
            try:
                metadata = os.fstat(child_fd)
                os.fsync(child_fd)
            finally:
                os.close(child_fd)
            os.fsync(parent_fd)
            record_owner(metadata.st_dev, metadata.st_ino)
            return metadata.st_dev, metadata.st_ino
        finally:
            os.close(parent_fd)

    @staticmethod
    def _remove_source(root: Path, removal: _Removal) -> None:
        parts = PurePosixPath(removal.relative_path).parts
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            if not _removal_is_old(_read_target(root, removal.relative_path), removal):
                raise FieldTransactionError(
                    f"Field relocation source changed: {removal.relative_path}"
                )
            os.unlink(parts[-1], dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    @staticmethod
    def _restore_source(
        root: Path,
        removal: _Removal,
        *,
        temporary_name: str,
        record_owner: Callable[[int, int], None],
    ) -> tuple[int, int]:
        parts = PurePosixPath(removal.relative_path).parts
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            if _read_target(root, removal.relative_path) is not None:
                raise FieldTransactionError("Field relocation source was externally recreated")
            descriptor = os.open(temporary_name, _WRITE_FLAGS, removal.mode, dir_fd=parent_fd)
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), removal.mode)
                handle.write(removal.before)
                handle.flush()
                os.fsync(handle.fileno())
                prepared = os.fstat(handle.fileno())
            record_owner(prepared.st_dev, prepared.st_ino)
            if _read_target(root, removal.relative_path) is not None:
                raise FieldTransactionError("Field relocation source was externally recreated")
            os.link(
                temporary_name,
                parts[-1],
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.fsync(parent_fd)
            return prepared.st_dev, prepared.st_ino
        finally:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            os.close(parent_fd)

    @staticmethod
    def _remove_created_directory(root: Path, directory: _Directory) -> None:
        if not _directory_is_new(root, directory):
            raise FieldTransactionError(
                f"created Field directory changed: {directory.relative_path}"
            )
        parts = PurePosixPath(directory.relative_path).parts
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            os.rmdir(parts[-1], dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)

    @staticmethod
    def _clean_removal_temps(root: Path, removals: Sequence[_Removal]) -> None:
        for removal in removals:
            name = removal.restore_temporary_name
            if name is None:
                continue
            parts = PurePosixPath(removal.relative_path).parts
            parent_fd = _open_directory_chain(root, parts[:-1])
            try:
                try:
                    content, metadata = _read_regular_at(
                        parent_fd, name, limit=_MAX_FIELD_DOCUMENT_BYTES
                    )
                except FileNotFoundError:
                    continue
                if (
                    (metadata.st_dev, metadata.st_ino)
                    != (removal.restore_device, removal.restore_inode)
                    or content != removal.before
                    or metadata.st_uid != removal.owner
                    or stat.S_IMODE(metadata.st_mode) != removal.mode
                    or metadata.st_nlink not in {1, 2}
                ):
                    raise FieldTransactionError(
                        f"Field relocation restore staging is uncertain: {removal.relative_path}"
                    )
                if metadata.st_nlink == 2:
                    current = _read_target(root, removal.relative_path)
                    if current is None or (current[1].st_dev, current[1].st_ino) != (
                        removal.restore_device,
                        removal.restore_inode,
                    ):
                        raise FieldTransactionError(
                            f"Field relocation restore link is uncertain: {removal.relative_path}"
                        )
                os.unlink(name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)

    @staticmethod
    def _clear_journal(directory: Path) -> None:
        directory_fd = _open_private_directory(directory)
        try:
            os.unlink(_JOURNAL, dir_fd=directory_fd)
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    @staticmethod
    def _clean_staged_temps(root: Path, targets: list[_Target]) -> None:
        """Remove only inode-owned temps; unknown staging state needs manual review."""
        for target in targets:
            for name, identity, expected in (
                (
                    target.temporary_name,
                    (target.new_device, target.new_inode),
                    target.after,
                ),
                (
                    target.restore_temporary_name,
                    (target.restore_device, target.restore_inode),
                    target.before,
                ),
            ):
                if name is None:
                    continue
                parts = PurePosixPath(target.relative_path).parts
                try:
                    parent_fd = _open_directory_chain(root, parts[:-1])
                except FileNotFoundError:
                    continue
                try:
                    try:
                        content, metadata = _read_regular_at(
                            parent_fd, name, limit=_MAX_FIELD_DOCUMENT_BYTES
                        )
                    except FileNotFoundError:
                        continue
                    if (
                        identity[0] is None
                        or identity[1] is None
                        or (metadata.st_dev, metadata.st_ino) != identity
                        or content != expected
                        or metadata.st_uid != target.owner
                        or stat.S_IMODE(metadata.st_mode) != target.mode
                        or metadata.st_nlink not in {1, 2}
                    ):
                        raise FieldTransactionError(
                            f"Field staged ownership is uncertain: {target.relative_path}"
                        )
                    if metadata.st_nlink == 2:
                        current = _read_target(root, target.relative_path)
                        if current is None or (current[1].st_dev, current[1].st_ino) != identity:
                            raise FieldTransactionError(
                                f"Field staged hard link is uncertain: {target.relative_path}"
                            )
                    os.unlink(name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)

    def apply(
        self,
        plan_token: str,
        *,
        approved_digest: str,
        external_writers_paused: bool = False,
    ) -> FieldTransactionResult:
        """Commit an approved Field only during a caller-enforced external-writer pause.

        The directory lock serializes Scholar writers, not Obsidian or another
        external process. Its check-then-replace cannot provide filesystem-wide
        compare-and-swap; without an external quiet window this fails closed.
        """
        with self._lock:
            if external_writers_paused is not True:
                raise FieldTransactionError("external Field writers must be paused before apply")
            pending = self._plans.pop(plan_token, None)
            if pending is None or pending.expires_at <= self._clock():
                raise FieldTransactionError("Field transaction plan is unknown or expired")
            if approved_digest != pending.plan.plan_digest:
                raise FieldTransactionError("the exact Field transaction plan was not approved")
            if pending.plan.conflicts:
                raise FieldTransactionError("Field transaction has unresolved conflicts")
            # All cooperating writers take Source registry before Vault inode.
            # Keep that lock through publication and conditional recovery.
            with (
                self.registry._write_guard() as registry_parent_fd,
                self._guard(pending.root) as ensure_state_lock,
            ):
                self._assert_current(pending)
                for key, expected in pending.verified_links:
                    try:
                        actual = self._link_resolver(key)
                    except Exception as exc:
                        raise FieldTransactionError(
                            f"Zotero attachment {key} cannot be reverified"
                        ) from exc
                    if actual != expected:
                        raise FieldTransactionError(f"Zotero attachment {key} changed after plan")
                directory = self._state_directory(
                    pending.root, pending.plan.source_id, pending.plan.field_id, create=True
                )
                if (directory / _JOURNAL).exists():
                    raise FieldTransactionError("Field recovery is required before another apply")
                snapshot = self._snapshot(directory, pending)
                try:
                    journal = self._write_journal(directory, pending, snapshot.name)
                except BaseException as exc:
                    if not (directory / _JOURNAL).exists():
                        directory_fd = _open_private_directory(directory)
                        try:
                            try:
                                os.unlink(snapshot.name, dir_fd=directory_fd)
                            except FileNotFoundError:
                                pass
                            os.fsync(directory_fd)
                        finally:
                            os.close(directory_fd)
                        raise FieldTransactionError(
                            "Field journal could not be persisted; no Vault content changed"
                        ) from exc
                    raise FieldTransactionError(
                        "Field journal commit is uncertain; recover explicitly before retrying"
                    ) from exc
                try:
                    # On a new Source, the portable lock directory itself is a
                    # Vault write. Only create it after the recovery journal is
                    # durable, then recheck CAS under the shared Field lock.
                    ensure_state_lock()
                    self._assert_current(pending)
                    journal_rows = {row["relative_path"]: row for row in journal["targets"]}
                    owned_directories: list[_Directory] = []
                    if pending.removals:
                        for row in pending.directories:
                            if row.device is not None:
                                owned_directories.append(row)
                                continue
                            device, inode = self._create_directory(
                                pending.root,
                                row,
                                record_owner=lambda device, inode, relative=row.relative_path: (
                                    self._set_journal_owner(
                                        directory,
                                        pending.plan.source_id,
                                        pending.plan.field_id,
                                        relative,
                                        phase="directory",
                                        temporary_name=None,
                                        device=device,
                                        inode=inode,
                                    )
                                ),
                            )
                            owned_directories.append(
                                replace(row, new_device=device, new_inode=inode)
                            )
                    owned_targets: list[_Target] = []
                    for target in pending.targets:
                        temporary = journal_rows[target.relative_path]["temporary_name"]
                        device, inode = self._replace(
                            pending.root,
                            target,
                            target.after,
                            expect_new=False,
                            temporary_name=temporary,
                            record_owner=lambda device, inode, relative=target.relative_path, temporary=temporary: (
                                self._set_journal_owner(
                                    directory,
                                    pending.plan.source_id,
                                    pending.plan.field_id,
                                    relative,
                                    phase="new",
                                    temporary_name=temporary,
                                    device=device,
                                    inode=inode,
                                )
                            ),
                        )
                        owned_targets.append(replace(target, new_device=device, new_inode=inode))
                    for removal in pending.removals:
                        self._remove_source(pending.root, removal)
                    if pending.registry_before != pending.registry_after:
                        candidate = self.field_service.candidates.peek(pending.candidate_token)
                        manifest = FieldManifest(
                            source_id=pending.plan.source_id,
                            fields=[*candidate.preview.registered_fields, pending.field_definition],
                        )
                        registration = self.field_service._planned_registration(
                            pending.root, manifest, candidate.preview.folder_id
                        )
                        self.registry._save_locked(
                            registration,
                            registry_parent_fd,
                            expected_revision=pending.registry_revision,
                        )
                    if any(
                        not _current_is_new(
                            _read_target(pending.root, target.relative_path), target
                        )
                        for target in owned_targets
                    ):
                        raise FieldTransactionError("Field target changed during commit")
                    if any(
                        _read_target(pending.root, removal.relative_path) is not None
                        for removal in pending.removals
                    ):
                        raise FieldTransactionError("Field relocation source changed during commit")
                    if any(
                        row.device is None and not _directory_is_new(pending.root, row)
                        for row in owned_directories
                    ):
                        raise FieldTransactionError(
                            "Field relocation directory changed during commit"
                        )
                    if _read_registry(self.registry.path) != pending.registry_after:
                        raise FieldTransactionError("source registry changed during commit")
                except BaseException as exc:
                    try:
                        recovery = self._recover_locked(
                            pending.plan.source_id, pending.plan.field_id, directory
                        )
                    except (FieldTransactionError, OSError) as recovery_exc:
                        raise FieldTransactionError(
                            f"Field commit is incomplete; recover explicitly; snapshot={snapshot}; "
                            f"{recovery_exc}"
                        ) from exc
                    if recovery.outcome == "committed":
                        raise FieldTransactionError(
                            f"Field publication may have committed; inspect before retrying; snapshot={snapshot}"
                        ) from exc
                    raise FieldTransactionError(
                        f"Field transaction failed and was rolled back; snapshot={snapshot}"
                    ) from exc
                try:
                    self._clear_journal(directory)
                    self.field_service.candidates.consume(pending.candidate_token)
                except Exception as exc:
                    raise FieldTransactionError(
                        "Field commit may already be published; inspect registry and "
                        "recovery status before any retry"
                    ) from exc
                return FieldTransactionResult(
                    pending.plan.source_id,
                    pending.plan.field_id,
                    tuple(change.relative_path for change in pending.plan.changes),
                    pending.plan.replaced_links,
                    snapshot,
                )

    def recover(
        self,
        source_id: str,
        field_id: str,
        *,
        external_writers_paused: bool = False,
    ) -> FieldTransactionRecovery:
        """Conditionally finish a published transaction or restore exact old bytes."""
        with self._lock:
            directory = self._state_directory(None, source_id, field_id, create=False)
            journal_path = directory / _JOURNAL
            if not journal_path.exists() and not journal_path.is_symlink():
                return FieldTransactionRecovery(source_id, field_id, "nothing-to-recover", (), None)
            journal = self._read_journal(directory, source_id, field_id)
            if external_writers_paused is not True:
                raise FieldTransactionError(
                    "external Field writers must be paused before recovery"
                )
            root = Path(journal["root"])
            if root == Path(root.anchor):
                raise FieldTransactionError("Field recovery root is too broad")
            self._state_directory(root, source_id, field_id, create=False)
            with self.registry._write_guard(), self._guard(root) as ensure_state_lock:
                ensure_state_lock()
                return self._recover_locked(source_id, field_id, directory)

    def _read_journal(self, directory: Path, source_id: str, field_id: str) -> dict[str, object]:
        try:
            directory_fd = _open_private_directory(directory)
            try:
                encoded, metadata = _read_regular_at(
                    directory_fd, _JOURNAL, limit=_MAX_FIELD_DOCUMENT_BYTES
                )
            finally:
                os.close(directory_fd)
            if (
                stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
            ):
                raise FieldTransactionError("Field journal is not a private regular file")
            payload = json.loads(encoded)
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") not in {2, 3}
                or payload.get("source_id") != source_id
                or payload.get("field_id") != field_id
                or not isinstance(payload.get("root"), str)
                or not Path(payload["root"]).is_absolute()
                or payload.get("registry_path") != str(self.registry.path)
                or not isinstance(payload.get("targets"), list)
                or not isinstance(payload.get("snapshot_name"), str)
                or _SNAPSHOT_NAME.fullmatch(payload["snapshot_name"]) is None
            ):
                raise FieldTransactionError("Field recovery journal identity is invalid")
            return payload
        except (OSError, ValueError, TypeError, UnicodeDecodeError, FieldRegistryError) as exc:
            raise FieldTransactionError("Field recovery journal is invalid") from exc

    def _recover_locked(
        self, source_id: str, field_id: str, directory: Path
    ) -> FieldTransactionRecovery:
        journal = self._read_journal(directory, source_id, field_id)
        root = Path(journal["root"])
        if root.is_symlink() or _identity(root) != (
            journal.get("root_device"),
            journal.get("root_inode"),
        ):
            raise FieldTransactionError("Field recovery root identity changed")
        field_relative = journal.get("field_relative_root")
        if not isinstance(field_relative, str):
            raise FieldTransactionError("Field recovery Field root is invalid")
        try:
            safe_field = _safe_relative(field_relative, allow_dot=True)
        except ValueError as exc:
            raise FieldTransactionError("Field recovery Field root is unsafe") from exc
        field_parts = () if safe_field == "." else PurePosixPath(safe_field).parts
        if _identity(root.joinpath(*field_parts)) != (
            journal.get("field_device"),
            journal.get("field_inode"),
        ):
            raise FieldTransactionError("Field recovery Field directory changed")
        snapshot_name = journal["snapshot_name"]
        snapshot = directory / snapshot_name
        try:
            directory_fd = _open_private_directory(directory)
            try:
                descriptor = os.open(
                    snapshot_name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                with os.fdopen(descriptor, "rb") as handle:
                    metadata = os.fstat(handle.fileno())
                    if (
                        not stat.S_ISREG(metadata.st_mode)
                        or stat.S_IMODE(metadata.st_mode) != 0o600
                        or metadata.st_uid != os.geteuid()
                        or metadata.st_nlink != 1
                        or metadata.st_size
                        > 2 * _MAX_TRANSACTION_BYTES + 3 * _MAX_FIELD_DOCUMENT_BYTES
                    ):
                        raise FieldTransactionError("Field recovery snapshot is unsafe")
                    snapshot_bytes = handle.read()
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise FieldTransactionError("Field recovery snapshot is unsafe") from exc
        rows = journal["targets"]
        if not isinstance(rows, list) or len(rows) > _MAX_BUNDLE_FILES + 1:
            raise FieldTransactionError("Field recovery targets are invalid")
        targets: list[_Target] = []
        removals: list[_Removal] = []
        directories: list[_Directory] = []
        try:
            with zipfile.ZipFile(io.BytesIO(snapshot_bytes)) as archive:
                infos = archive.infolist()
                if (
                    len(infos)
                    > (3 if journal.get("schema_version") == 3 else 2) * (_MAX_BUNDLE_FILES + 1) + 4
                    or sum(info.file_size for info in infos)
                    > 2 * _MAX_TRANSACTION_BYTES + 3 * _MAX_FIELD_DOCUMENT_BYTES
                ):
                    raise FieldTransactionError("Field recovery snapshot exceeds its limits")
                if len({info.filename for info in infos}) != len(infos):
                    raise FieldTransactionError("Field recovery snapshot has duplicate entries")
                if archive.getinfo("recovery.json").file_size > _MAX_FIELD_DOCUMENT_BYTES:
                    raise FieldTransactionError("Field recovery receipt is too large")
                receipt = json.loads(archive.read("recovery.json"))
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("source_id") != source_id
                    or receipt.get("field_id") != field_id
                    or receipt.get("plan_digest") != journal.get("plan_digest")
                    or receipt.get("verified_backup") is not False
                    or receipt.get("schema_version")
                    != (2 if journal.get("schema_version") == 3 else 1)
                ):
                    raise FieldTransactionError("Field recovery snapshot receipt changed")
                seen: set[str] = set()
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("relative_path"), str):
                        raise FieldTransactionError("Field recovery target is invalid")
                    relative = row["relative_path"]
                    try:
                        safe = _safe_relative(relative)
                    except ValueError as exc:
                        raise FieldTransactionError("Field recovery target path is unsafe") from exc
                    if safe in seen:
                        raise FieldTransactionError("duplicate Field recovery target")
                    seen.add(safe)
                    if (
                        safe != _MANIFEST
                        and PurePosixPath(safe).parts[: len(field_parts)] != field_parts
                    ):
                        raise FieldTransactionError("Field recovery target escaped its Field")
                    if safe != _MANIFEST and not safe.endswith(
                        (".md", ".canvas", ".analysis.json")
                    ):
                        raise FieldTransactionError("Field recovery target type is unsafe")
                    kind = row.get("kind")
                    if (safe == _MANIFEST and kind != "manifest") or (
                        safe != _MANIFEST
                        and kind
                        not in (
                            {"content", "relocation-destination"}
                            if journal.get("schema_version") == 3
                            else {"content"}
                        )
                    ):
                        raise FieldTransactionError("Field recovery target kind is invalid")
                    proposed_info = archive.getinfo("proposed/" + safe)
                    if proposed_info.file_size > _MAX_FIELD_DOCUMENT_BYTES:
                        raise FieldTransactionError("Field recovery proposal is too large")
                    after = archive.read(proposed_info)
                    old_hash = row.get("old_hash")
                    before: bytes | None = None
                    if old_hash is not None:
                        original_info = archive.getinfo("original/" + safe)
                        if original_info.file_size > _MAX_FIELD_DOCUMENT_BYTES:
                            raise FieldTransactionError("Field recovery original is too large")
                        before = archive.read(original_info)
                    if (
                        _hash(after) != row.get("new_hash")
                        or (None if before is None else _hash(before)) != old_hash
                        or receipt.get("originals", {}).get(safe) != old_hash
                        or not isinstance(row.get("mode"), int)
                        or not isinstance(row.get("owner"), int)
                        or row.get("owner") != os.geteuid()
                    ):
                        raise FieldTransactionError("Field recovery target hash or owner changed")
                    new_device = row.get("new_device")
                    new_inode = row.get("new_inode")
                    restore_device = row.get("restore_device")
                    restore_inode = row.get("restore_inode")
                    if (
                        (new_device is None) != (new_inode is None)
                        or (restore_device is None) != (restore_inode is None)
                        or any(
                            value is not None
                            and (not isinstance(value, int) or isinstance(value, bool) or value < 0)
                            for value in (new_device, new_inode, restore_device, restore_inode)
                        )
                    ):
                        raise FieldTransactionError("Field recovery inode ownership is invalid")
                    temporary_name = row.get("temporary_name")
                    restore_temporary_name = row.get("restore_temporary_name")
                    if (
                        not isinstance(temporary_name, str)
                        or _STAGED_NAME.fullmatch(temporary_name) is None
                        or (
                            restore_temporary_name is not None
                            and (
                                not isinstance(restore_temporary_name, str)
                                or _RESTORE_NAME.fullmatch(restore_temporary_name) is None
                            )
                        )
                    ):
                        raise FieldTransactionError("Field recovery staged name is invalid")
                    targets.append(
                        _Target(
                            safe,
                            before,
                            after,
                            row.get("device"),
                            row.get("inode"),
                            row["mode"],
                            row["owner"],
                            kind,
                            new_device,
                            new_inode,
                            restore_device,
                            restore_inode,
                            temporary_name,
                            restore_temporary_name,
                        )
                    )
                if journal.get("schema_version") == 3:
                    removal_rows = journal.get("removals")
                    directory_rows = journal.get("directories")
                    if (
                        not isinstance(removal_rows, list)
                        or not removal_rows
                        or len(removal_rows) > _MAX_BUNDLE_FILES
                        or not isinstance(directory_rows, list)
                        or len(directory_rows) > 8 * _MAX_BUNDLE_FILES
                    ):
                        raise FieldTransactionError("Field recovery relocations are invalid")
                    for row in removal_rows:
                        if not isinstance(row, dict) or not isinstance(
                            row.get("relative_path"), str
                        ):
                            raise FieldTransactionError("Field recovery removal is invalid")
                        try:
                            safe = _safe_relative(row["relative_path"])
                        except ValueError as exc:
                            raise FieldTransactionError(
                                "Field recovery removal path is unsafe"
                            ) from exc
                        if (
                            safe in seen
                            or PurePosixPath(safe).parts[: len(field_parts)] != field_parts
                            or not safe.endswith((".md", ".canvas"))
                        ):
                            raise FieldTransactionError("Field recovery removal path is invalid")
                        seen.add(safe)
                        content_info = archive.getinfo("removed/" + safe)
                        if content_info.file_size > _MAX_FIELD_DOCUMENT_BYTES:
                            raise FieldTransactionError("Field recovery removal is too large")
                        before = archive.read(content_info)
                        if (
                            _hash(before) != row.get("old_hash")
                            or receipt.get("removed_originals", {}).get(safe) != _hash(before)
                            or any(
                                not isinstance(row.get(key), int)
                                or isinstance(row.get(key), bool)
                                or row[key] < 0
                                for key in ("device", "inode", "mode", "owner")
                            )
                            or row["owner"] != os.geteuid()
                        ):
                            raise FieldTransactionError("Field recovery removal identity changed")
                        restore_device = row.get("restore_device")
                        restore_inode = row.get("restore_inode")
                        temporary_name = row.get("restore_temporary_name")
                        if (
                            (restore_device is None) != (restore_inode is None)
                            or any(
                                value is not None
                                and (
                                    not isinstance(value, int)
                                    or isinstance(value, bool)
                                    or value < 0
                                )
                                for value in (restore_device, restore_inode)
                            )
                            or (
                                temporary_name is not None
                                and (
                                    not isinstance(temporary_name, str)
                                    or _RESTORE_NAME.fullmatch(temporary_name) is None
                                )
                            )
                        ):
                            raise FieldTransactionError("Field recovery removal restore is invalid")
                        removals.append(
                            _Removal(
                                safe,
                                before,
                                row["device"],
                                row["inode"],
                                row["mode"],
                                row["owner"],
                                restore_device,
                                restore_inode,
                                temporary_name,
                            )
                        )
                    seen_directories: set[str] = set()
                    for row in directory_rows:
                        if not isinstance(row, dict) or not isinstance(
                            row.get("relative_path"), str
                        ):
                            raise FieldTransactionError("Field recovery directory is invalid")
                        try:
                            safe = _safe_relative(row["relative_path"])
                        except ValueError as exc:
                            raise FieldTransactionError(
                                "Field recovery directory path is unsafe"
                            ) from exc
                        if (
                            safe in seen_directories
                            or PurePosixPath(safe).parts[: len(field_parts)] != field_parts
                            or safe == _MANIFEST
                        ):
                            raise FieldTransactionError("Field recovery directory path is invalid")
                        seen_directories.add(safe)
                        device, inode = row.get("device"), row.get("inode")
                        new_device, new_inode = row.get("new_device"), row.get("new_inode")
                        if (
                            (device is None) != (inode is None)
                            or (new_device is None) != (new_inode is None)
                            or any(
                                value is not None
                                and (
                                    not isinstance(value, int)
                                    or isinstance(value, bool)
                                    or value < 0
                                )
                                for value in (device, inode, new_device, new_inode)
                            )
                            or "temporary_name" in row
                            or (device is not None and new_device is not None)
                        ):
                            raise FieldTransactionError(
                                "Field recovery directory identity is invalid"
                            )
                        directories.append(_Directory(safe, device, inode, new_device, new_inode))
                    expected_directory_receipt = [
                        {
                            "relative_path": row.relative_path,
                            "device": row.device,
                            "inode": row.inode,
                        }
                        for row in directories
                    ]
                    if receipt.get("directories") != expected_directory_receipt:
                        raise FieldTransactionError("Field recovery directory snapshot changed")
                    relocation_rows = journal.get("relocations")
                    if (
                        not isinstance(relocation_rows, list)
                        or len(relocation_rows) != len(removals)
                        or receipt.get("relocations") != relocation_rows
                    ):
                        raise FieldTransactionError("Field recovery relocation mapping changed")
                    removal_by_path = {row.relative_path: row for row in removals}
                    destination_by_path = {
                        row.relative_path: row
                        for row in targets
                        if row.kind == "relocation-destination"
                    }
                    seen_destinations: set[str] = set()
                    seen_sources: set[str] = set()
                    for row in relocation_rows:
                        if not isinstance(row, dict):
                            raise FieldTransactionError(
                                "Field recovery relocation mapping is invalid"
                            )
                        source_path = row.get("source_path")
                        destination_path = row.get("destination_path")
                        if (
                            not isinstance(source_path, str)
                            or not isinstance(destination_path, str)
                            or source_path not in removal_by_path
                            or destination_path not in destination_by_path
                            or source_path in seen_sources
                            or destination_path in seen_destinations
                            or not destination_path.endswith((".md", ".canvas"))
                            or row.get("source_sha256")
                            != _hash(removal_by_path[source_path].before)
                            or row.get("destination_sha256")
                            != destination_by_path[destination_path].new_hash
                            or destination_by_path[destination_path].before is not None
                        ):
                            raise FieldTransactionError(
                                "Field recovery relocation mapping is invalid"
                            )
                        seen_sources.add(source_path)
                        seen_destinations.add(destination_path)
                    if seen_destinations != set(destination_by_path):
                        raise FieldTransactionError(
                            "Field recovery relocation destinations changed"
                        )
                    expected_directory_paths = {
                        PurePosixPath(*PurePosixPath(path).parts[:depth]).as_posix()
                        for row in relocation_rows
                        for path in (row["source_path"], row["destination_path"])
                        for depth in range(len(field_parts) + 1, len(PurePosixPath(path).parts))
                    }
                    if seen_directories != expected_directory_paths:
                        raise FieldTransactionError("Field recovery directory mapping changed")
                if (
                    len(
                        [
                            target
                            for target in targets
                            if target.kind == "manifest" and target.relative_path == _MANIFEST
                        ]
                    )
                    != 1
                ):
                    raise FieldTransactionError("Field recovery manifest target is invalid")
                if archive.getinfo("registry/proposed").file_size > _MAX_FIELD_DOCUMENT_BYTES:
                    raise FieldTransactionError("Field recovery registry is too large")
                if journal.get("registry_old_hash"):
                    if archive.getinfo("registry/original").file_size > _MAX_FIELD_DOCUMENT_BYTES:
                        raise FieldTransactionError("Field recovery registry is too large")
                    registry_old = archive.read("registry/original")
                else:
                    registry_old = None
                registry_new = archive.read("registry/proposed")
                expected_entries = {
                    "recovery.json",
                    "registry/proposed",
                    *("proposed/" + target.relative_path for target in targets),
                    *(
                        "original/" + target.relative_path
                        for target in targets
                        if target.before is not None
                    ),
                }
                if registry_old is not None:
                    expected_entries.add("registry/original")
                expected_entries.update("removed/" + removal.relative_path for removal in removals)
                if {info.filename for info in infos} != expected_entries:
                    raise FieldTransactionError("Field recovery snapshot entries changed")
        except FieldTransactionError:
            raise
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
            raise FieldTransactionError("Field recovery snapshot is invalid") from exc
        if (None if registry_old is None else _hash(registry_old)) != journal.get(
            "registry_old_hash"
        ) or _hash(registry_new) != journal.get("registry_new_hash"):
            raise FieldTransactionError("Field recovery registry snapshot changed")
        self._clean_staged_temps(root, targets)
        self._clean_removal_temps(root, removals)
        registry_current = _read_registry(self.registry.path)
        if registry_current not in (registry_old, registry_new):
            raise FieldTransactionError("Field recovery conflicts with external registry edit")
        current = {
            target.relative_path: _read_target(
                root,
                target.relative_path,
                allow_missing_parent=target.kind == "relocation-destination",
            )
            for target in targets
        }
        for target in targets:
            state = current[target.relative_path]
            if not _restored_is_old(state, target) and not _current_is_new(state, target):
                raise FieldTransactionError(
                    f"Field recovery conflicts with external edit: {target.relative_path}"
                )
        for removal in removals:
            state = _read_target(root, removal.relative_path)
            if state is not None and not _removal_is_restored(state, removal):
                raise FieldTransactionError(
                    f"Field recovery conflicts with external edit: {removal.relative_path}"
                )
        for row in directories:
            if not _directory_is_old(root, row) and not _directory_is_new(root, row):
                raise FieldTransactionError(
                    f"Field recovery conflicts with external directory edit: {row.relative_path}"
                )
        manifest_target = next(target for target in targets if target.kind == "manifest")
        published = (
            registry_current == registry_new
            if registry_old != registry_new
            else _current_is_new(current[_MANIFEST], manifest_target)
        )
        if published:
            if (
                any(
                    not _current_is_new(current[target.relative_path], target) for target in targets
                )
                or any(
                    _read_target(root, removal.relative_path) is not None for removal in removals
                )
                or any(
                    row.device is None and not _directory_is_new(root, row) for row in directories
                )
            ):
                raise FieldTransactionError(
                    "published Field has incomplete targets; manual review required"
                )
            self._clear_journal(directory)
            return FieldTransactionRecovery(source_id, field_id, "committed", (), snapshot)
        recovered: list[str] = []
        for index in range(len(removals) - 1, -1, -1):
            removal = removals[index]
            state = _read_target(root, removal.relative_path)
            if _removal_is_restored(state, removal):
                continue
            if state is not None:
                raise FieldTransactionError(
                    f"Field recovery conflicts with external edit: {removal.relative_path}"
                )
            temporary = removal.restore_temporary_name or (
                f".scholar-restore-{secrets.token_hex(16)}.tmp"
            )
            self._set_journal_owner(
                directory,
                source_id,
                field_id,
                removal.relative_path,
                phase="remove-restore",
                temporary_name=temporary,
                device=None,
                inode=None,
            )
            device, inode = self._restore_source(
                root,
                removal,
                temporary_name=temporary,
                record_owner=lambda device, inode, relative=removal.relative_path, temporary=temporary: (
                    self._set_journal_owner(
                        directory,
                        source_id,
                        field_id,
                        relative,
                        phase="remove-restore",
                        temporary_name=temporary,
                        device=device,
                        inode=inode,
                    )
                ),
            )
            removals[index] = replace(
                removal,
                restore_device=device,
                restore_inode=inode,
                restore_temporary_name=temporary,
            )
            recovered.append(removal.relative_path)
        for index in range(len(targets) - 1, -1, -1):
            target = targets[index]
            state = _read_target(
                root,
                target.relative_path,
                allow_missing_parent=target.kind == "relocation-destination",
            )
            if _restored_is_old(state, target):
                continue
            if not _current_is_new(state, target):
                raise FieldTransactionError(
                    f"Field recovery conflicts with external edit: {target.relative_path}"
                )
            if target.before is None:
                self._remove_created(root, target)
            else:
                temporary = target.restore_temporary_name or (
                    f".scholar-restore-{secrets.token_hex(16)}.tmp"
                )
                self._set_journal_owner(
                    directory,
                    source_id,
                    field_id,
                    target.relative_path,
                    phase="restore",
                    temporary_name=temporary,
                    device=None,
                    inode=None,
                )
                device, inode = self._replace(
                    root,
                    target,
                    target.before,
                    expect_new=True,
                    temporary_name=temporary,
                    record_owner=lambda device, inode, relative=target.relative_path, temporary=temporary: (
                        self._set_journal_owner(
                            directory,
                            source_id,
                            field_id,
                            relative,
                            phase="restore",
                            temporary_name=temporary,
                            device=device,
                            inode=inode,
                        )
                    ),
                )
                targets[index] = replace(
                    target,
                    restore_device=device,
                    restore_inode=inode,
                    restore_temporary_name=temporary,
                )
            recovered.append(target.relative_path)
        for row in reversed(directories):
            if row.device is not None or _directory_is_old(root, row):
                continue
            if not _directory_is_new(root, row):
                raise FieldTransactionError(
                    f"Field recovery conflicts with external directory edit: {row.relative_path}"
                )
            self._remove_created_directory(root, row)
            recovered.append(row.relative_path)
        if (
            any(
                not _restored_is_old(
                    _read_target(
                        root,
                        target.relative_path,
                        allow_missing_parent=target.kind == "relocation-destination",
                    ),
                    target,
                )
                for target in targets
            )
            or any(
                not _removal_is_restored(_read_target(root, removal.relative_path), removal)
                for removal in removals
            )
            or any(not _directory_is_old(root, row) for row in directories)
        ):
            raise FieldTransactionError("Field recovery verification failed")
        self._clear_journal(directory)
        if manifest_target.before is None:
            try:
                (root / _STATE_DIR).rmdir()
            except OSError:
                pass
        return FieldTransactionRecovery(
            source_id, field_id, "rolled-back", tuple(recovered), snapshot
        )


__all__ = [
    "FieldTransactionChange",
    "FieldTransactionError",
    "FieldTransactionPlan",
    "FieldTransactionRecovery",
    "FieldTransactionRelocation",
    "FieldTransactionResult",
    "FieldTransactionService",
]
