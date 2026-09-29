"""Explicit, per-Field cleanup of legacy paper links.

This is deliberately narrower than a knowledge-template migration.  Only files
declared by one existing Field manifest may be rewritten.  Unmapped prose and
files are reported, not normalized or inferred into the manifest.  The shared
cross-process Field lock and CAS checks protect managed writes.  An explicitly
invoked, conditional recovery journal handles interrupted multi-file writes.
Recovery snapshots are not verified backups.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from scholar_workflow.adapters.zotero_local import (
    ZoteroLocalAdapter,
    ZoteroLocalError,
)
from scholar_workflow.hub.fields import (
    _DIRECTORY_FLAGS,
    _MAX_FIELD_DOCUMENT_BYTES,
    FieldDefinition,
    FieldManifest,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    _open_directory_chain,
    _read_regular_at,
)

_LEGACY_LINK = re.compile(
    rb"http://127\.0\.0\.1:23128/open/paper/"
    rb"(?P<key>[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})(?=$|[ \t\r\n\"'<>)}\]`])"
)
_RAW_LEGACY_HUB = re.compile(
    rb"(?:127\.0\.0\.1|localhost|\[::1\]):23128(?!\d)", re.IGNORECASE
)
_IGNORED_DIRECTORIES = {".obsidian", ".scholar-workflow", ".git", ".trash"}
_SUPPORTED_SUFFIXES = {".md", ".canvas"}
_INSPECTED_TEXT_SUFFIXES = _SUPPORTED_SUFFIXES | {
    ".txt", ".html", ".json", ".yml", ".yaml", ".ipynb"
}
_READ_LIMIT = _MAX_FIELD_DOCUMENT_BYTES
_JOURNAL_NAME = "pending.json"
_JOURNAL_SCHEMA_VERSION = 1
_ANALYSIS_KIND = re.compile(rb"(?m)^\s*sw_kind\s*:\s*['\"]?paper-analysis\b")


class FieldMigrationError(RuntimeError):
    """A Field plan is stale, unsafe, incomplete, or not explicitly approved."""


def _analysis_peer_paths(relative: str) -> tuple[str, ...]:
    """Known Markdown/Canvas/sidecar pairings, relative to the Source root."""
    path = PurePosixPath(relative)
    stem = path.name[: -len(path.suffix)]
    peers: set[str] = set()
    if path.suffix.casefold() == ".md":
        peers.update({stem + ".analysis.json", stem + ".canvas"})
        if stem.endswith("分析") and stem != "分析":
            peers.add(stem.removesuffix("分析") + "解析树.canvas")
    elif path.suffix.casefold() == ".canvas":
        peers.update({stem + ".md", stem + ".analysis.json"})
        if stem.endswith("解析树") and stem != "解析树":
            markdown_stem = stem.removesuffix("解析树") + "分析"
            peers.update({markdown_stem + ".md", markdown_stem + ".analysis.json"})
    return tuple(sorted(path.with_name(name).as_posix() for name in peers))


def _has_analysis_identity(content: bytes) -> bool:
    return (
        bool(_ANALYSIS_KIND.search(content))
        or b"sw-analysis-claim" in content
        or b"sw-analysis-field" in content
    )


@dataclass(frozen=True)
class FieldLinkChange:
    relative_path: str
    attachment_key: str
    replacement: str
    occurrences: int


@dataclass(frozen=True)
class FieldMigrationPlan:
    plan_token: str
    plan_digest: str
    source_id: str
    field_id: str
    field_title: str
    managed_files: tuple[str, ...]
    link_changes: tuple[FieldLinkChange, ...]
    unmapped_files: tuple[str, ...]
    unresolved_legacy_links: tuple[FieldLinkChange, ...]
    conflicts: tuple[str, ...]
    template_normalization: str = "manual-review-required"
    crash_recovery: str = "explicit-conditional-journal-recovery"
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class FieldMigrationResult:
    source_id: str
    field_id: str
    changed_files: tuple[str, ...]
    replaced_links: int
    recovery_snapshot: Path
    recovery_is_verified_backup: bool = False
    crash_recovery: str = "explicit-conditional-journal-recovery"


@dataclass(frozen=True)
class FieldMigrationRecovery:
    source_id: str
    field_id: str
    recovered_files: tuple[str, ...]
    recovery_snapshot: Path | None
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class _JournalFile:
    relative_path: str
    old_hash: str
    new_hash: str
    old_mode: int
    old_owner: int
    old_link_count: int
    new_device: int
    new_inode: int
    temporary_name: str


@dataclass(frozen=True)
class _RecoveryJournal:
    schema_version: int
    source_id: str
    field_id: str
    plan_digest: str
    root_device: int
    root_inode: int
    field_device: int
    field_inode: int
    manifest_hash: str
    snapshot_name: str
    files: tuple[_JournalFile, ...]


@dataclass(frozen=True)
class _FileState:
    relative_path: str
    content: bytes
    device: int
    inode: int
    mode: int
    owner: int
    link_count: int

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class _PendingPlan:
    preview: FieldMigrationPlan
    root: Path
    root_identity: tuple[int, int]
    field_identity: tuple[int, int]
    field_parts: tuple[str, ...]
    manifest: _FileState
    managed: tuple[_FileState, ...]
    inventory_digest: str
    verified_links: tuple[tuple[str, str], ...]
    expires_at: float


@dataclass
class _StagedWrite:
    original: _FileState
    replacement: bytes
    parent_fd: int
    temporary_name: str
    prepared_identity: tuple[int, int]


def _identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _replace_at(source: str, destination: str, parent_fd: int) -> None:
    os.replace(source, destination, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)


def _read_file(root: Path, relative_path: str) -> _FileState:
    parts = PurePosixPath(relative_path).parts
    try:
        parent_fd = _open_directory_chain(root, parts[:-1])
        try:
            content, metadata = _read_regular_at(parent_fd, parts[-1], limit=_READ_LIMIT)
        finally:
            os.close(parent_fd)
    except (OSError, FieldRegistryError) as exc:
        raise FieldMigrationError(f"unsafe or unreadable Field file: {relative_path}") from exc
    return _FileState(
        relative_path=relative_path,
        content=content,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=stat.S_IMODE(metadata.st_mode),
        owner=metadata.st_uid,
        link_count=metadata.st_nlink,
    )


def _field_parts(field: FieldDefinition) -> tuple[str, ...]:
    return () if field.relative_root == "." else PurePosixPath(field.relative_root).parts


def _field_path(field: FieldDefinition, relative: str) -> str:
    return PurePosixPath(*_field_parts(field), *PurePosixPath(relative).parts).as_posix()


def _managed_paths(field: FieldDefinition) -> tuple[str, ...]:
    ordered = [field.home]
    ordered.extend(item for group in field.navigation for item in group.items)
    return tuple(dict.fromkeys(ordered))


def _field_relative(path: str, field_parts: tuple[str, ...]) -> str:
    if not field_parts:
        return path
    return PurePosixPath(path).relative_to(PurePosixPath(*field_parts)).as_posix()


def _validate_canvas(content: bytes, path: str) -> None:
    try:
        canvas = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FieldMigrationError(f"invalid JSON Canvas: {path}") from exc
    if not isinstance(canvas, dict):
        raise FieldMigrationError(f"invalid JSON Canvas: {path}")
    nodes = canvas.get("nodes", [])
    edges = canvas.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise FieldMigrationError(f"invalid JSON Canvas: {path}")
    node_ids: set[str] = set()
    all_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise FieldMigrationError(f"invalid JSON Canvas node: {path}")
        kind = node.get("type")
        if not isinstance(kind, str) or kind not in {"text", "file", "link", "group"}:
            raise FieldMigrationError(f"invalid JSON Canvas node: {path}")
        required_value = {
            "text": "text",
            "file": "file",
            "link": "url",
            "group": None,
        }.get(kind)
        if any(
            not isinstance(node.get(axis), int) or isinstance(node.get(axis), bool)
            for axis in ("x", "y", "width", "height")
        ):
            raise FieldMigrationError(f"invalid JSON Canvas node: {path}")
        if required_value is not None and not isinstance(node.get(required_value), str):
            raise FieldMigrationError(f"invalid JSON Canvas node: {path}")
        identifier = node["id"]
        if identifier in all_ids:
            raise FieldMigrationError(f"duplicate JSON Canvas id: {path}")
        node_ids.add(identifier)
        all_ids.add(identifier)
    for edge in edges:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str):
            raise FieldMigrationError(f"invalid JSON Canvas edge: {path}")
        identifier = edge["id"]
        if identifier in all_ids:
            raise FieldMigrationError(f"duplicate JSON Canvas id: {path}")
        all_ids.add(identifier)
        source = edge.get("fromNode")
        target = edge.get("toNode")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in node_ids
            or target not in node_ids
        ):
            raise FieldMigrationError(f"dangling JSON Canvas edge: {path}")
        if any(
            edge.get(side) not in {None, "top", "right", "bottom", "left"}
            for side in ("fromSide", "toSide")
        ) or any(
            edge.get(end) not in {None, "none", "arrow"}
            for end in ("fromEnd", "toEnd")
        ):
            raise FieldMigrationError(f"invalid JSON Canvas edge: {path}")


def _replacements(content: bytes, relative_path: str) -> tuple[bytes, tuple[FieldLinkChange, ...]]:
    counts: dict[str, int] = {}

    def substitute(match: re.Match[bytes]) -> bytes:
        key = match.group("key").decode("ascii")
        counts[key] = counts.get(key, 0) + 1
        return f"zotero://open-pdf/library/items/{key}".encode("ascii")

    replaced = _LEGACY_LINK.sub(substitute, content)
    changes = tuple(
        FieldLinkChange(
            relative_path=relative_path,
            attachment_key=key,
            replacement=f"zotero://open-pdf/library/items/{key}",
            occurrences=count,
        )
        for key, count in sorted(counts.items())
    )
    return replaced, changes


def _has_legacy_hub_reference(content: bytes, relative_path: str) -> bool:
    if _RAW_LEGACY_HUB.search(content):
        return True
    if PurePosixPath(relative_path).suffix.casefold() not in {".canvas", ".json", ".ipynb"}:
        return False
    try:
        canvas = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FieldMigrationError(f"invalid JSON Canvas: {relative_path}") from exc

    def contains(value: object) -> bool:
        if isinstance(value, str):
            return _RAW_LEGACY_HUB.search(value.encode("utf-8")) is not None
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        if isinstance(value, list):
            return any(contains(item) for item in value)
        return False

    return contains(canvas)


class ZoteroPdfLinkResolver:
    """Prove a legacy key is a local PDF in the user's own Zotero library."""

    def __init__(
        self,
        adapter_factory: Callable[[], ZoteroLocalAdapter] = ZoteroLocalAdapter,
    ) -> None:
        self._adapter_factory = adapter_factory

    def __call__(self, attachment_key: str) -> str:
        try:
            with self._adapter_factory() as adapter:
                item = adapter.get_item(attachment_key)
                if not isinstance(item, dict) or item.get("key") != attachment_key:
                    raise FieldMigrationError("Zotero item identity does not match the link")
                library = item.get("library")
                if not isinstance(library, dict) or library.get("type") != "user":
                    raise FieldMigrationError("Zotero item is not in the user library")
                library_id = library.get("id")
                if (
                    not isinstance(library_id, (str, int))
                    or isinstance(library_id, bool)
                    or not str(library_id)
                ):
                    raise FieldMigrationError("Zotero item has no user library identity")
                data = item.get("data")
                if not isinstance(data, dict) or data.get("key") != attachment_key:
                    raise FieldMigrationError("Zotero attachment identity does not match the link")
                if data.get("itemType") != "attachment":
                    raise FieldMigrationError("Zotero item is not an attachment")
                if data.get("contentType") != "application/pdf":
                    raise FieldMigrationError("Zotero attachment is not a confirmed PDF")
                if data.get("linkMode") not in {
                    "imported_file",
                    "linked_file",
                    "imported_url",
                }:
                    raise FieldMigrationError("Zotero attachment link mode is unsupported")
                locator = adapter.resolve_attachment_locator(attachment_key)
                if (
                    locator.attachment_key != attachment_key
                    or locator.library_id != str(library_id)
                ):
                    raise FieldMigrationError("Zotero PDF locator identity does not match")
        except (ZoteroLocalError, OSError, ValueError) as exc:
            raise FieldMigrationError(f"Zotero Local API cannot verify the PDF: {exc}") from exc
        return f"zotero://open-pdf/library/items/{attachment_key}"


class FieldMigrationService:
    """Plan without writes, then apply one approved, CAS-bound Field transaction."""

    def __init__(
        self,
        registry: KnowledgeSourceRegistry,
        *,
        state_root: Path,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
        link_resolver: Callable[[str], str] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("plan TTL must be positive")
        state_root = Path(state_root)
        if not state_root.is_absolute() or state_root == Path(state_root.anchor):
            raise ValueError("state_root must be a private absolute directory")
        self.registry = registry
        self.state_root = state_root
        self._ttl = ttl_seconds
        self._clock = clock
        self._link_resolver = link_resolver or ZoteroPdfLinkResolver()
        self._plans: dict[str, _PendingPlan] = {}
        self._field_service = FieldService(registry)

    def _resolve(
        self, source_id: str, field_id: str, *, capability: str
    ) -> tuple[Path, FieldManifest, FieldDefinition, tuple[int, int], tuple[int, int]]:
        try:
            root = self.registry.resolve(source_id, capability=capability)
            manifest = FieldService._load_manifest(root)
        except FieldRegistryError as exc:
            raise FieldMigrationError("registered Field source is unavailable") from exc
        if manifest.source_id != source_id:
            raise FieldMigrationError("Field manifest source identity conflicts with registry")
        field = next((row for row in manifest.fields if row.field_id == field_id), None)
        if field is None:
            raise FieldMigrationError("Field is not declared by its source manifest")
        try:
            root_fd = _open_directory_chain(root)
            try:
                field_fd = _open_directory_chain(root, _field_parts(field))
                try:
                    root_identity = _identity(os.fstat(root_fd))
                    field_identity = _identity(os.fstat(field_fd))
                finally:
                    os.close(field_fd)
            finally:
                os.close(root_fd)
        except OSError as exc:
            raise FieldMigrationError("Field root is unavailable or unsafe") from exc
        return root, manifest, field, root_identity, field_identity

    @staticmethod
    def _inventory(
        root: Path, manifest: FieldManifest, field: FieldDefinition
    ) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        """Inventory one Field only; sibling subtrees are never traversed."""
        field_parts = _field_parts(field)
        field_root = root.joinpath(*field_parts)
        sibling_roots = {
            tuple(PurePosixPath(row.relative_root).parts)
            for row in manifest.fields
            if row.field_id != field.field_id and row.relative_root != "."
        }
        conflicts: list[str] = []
        found: list[str] = []
        digest = hashlib.sha256(b"scholar-field-inventory-v1\0")
        def traversal_failed(exc: OSError) -> None:
            raise FieldMigrationError("Field directory traversal failed") from exc

        for current, directories, files in os.walk(
            field_root, followlinks=False, onerror=traversal_failed
        ):
            current_path = Path(current)
            current_parts = current_path.relative_to(root).parts
            kept: list[str] = []
            for name in sorted(directories):
                parts = (*current_parts, name)
                if name in _IGNORED_DIRECTORIES or parts in sibling_roots:
                    continue
                if (current_path / name).is_symlink():
                    conflicts.append(f"symlinked Field directory: {PurePosixPath(*parts)}")
                    continue
                kept.append(name)
            directories[:] = kept
            for name in sorted(files):
                if PurePosixPath(name).suffix.casefold() not in _INSPECTED_TEXT_SUFFIXES:
                    continue
                relative = PurePosixPath(*current_parts, name).as_posix()
                path = current_path / name
                if path.is_symlink():
                    conflicts.append(f"symlinked Field file: {relative}")
                    continue
                state = _read_file(root, relative)
                try:
                    state.content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise FieldMigrationError(
                        f"Field text file is not UTF-8: {relative}"
                    ) from exc
                found.append(relative)
                digest.update(relative.encode("utf-8") + b"\0")
                digest.update(f"{state.device}:{state.inode}:{state.mode}".encode() + b"\0")
                digest.update(hashlib.sha256(state.content).digest())
        return tuple(found), digest.hexdigest(), tuple(conflicts)

    def plan(self, source_id: str, field_id: str) -> FieldMigrationPlan:
        root, manifest, field, root_identity, field_identity = self._resolve(
            source_id, field_id, capability="read"
        )
        unfinished = self._read_journal(root, source_id, field_id)
        if unfinished is not None:
            os.close(unfinished[2])
            raise FieldMigrationError("Field recovery is required before a new plan; run recover")
        manifest_state = _read_file(root, ".scholar-workflow/fields.yml")
        managed_names = _managed_paths(field)
        managed: list[_FileState] = []
        conflicts: list[str] = []
        changes: list[FieldLinkChange] = []
        sibling_managed = {
            _field_path(other, name)
            for other in manifest.fields
            if other.field_id != field_id
            for name in _managed_paths(other)
        }
        sibling_roots = {
            tuple(PurePosixPath(other.relative_root).parts)
            for other in manifest.fields
            if other.field_id != field_id and other.relative_root != "."
        }
        for name in managed_names:
            relative = _field_path(field, name)
            if relative in sibling_managed or any(
                PurePosixPath(relative).parts[: len(sibling)] == sibling
                for sibling in sibling_roots
            ):
                conflicts.append(f"Field ownership overlaps a sibling: {name}")
                continue
            if PurePosixPath(name).suffix.casefold() not in _SUPPORTED_SUFFIXES:
                conflicts.append(f"unsupported managed file type: {name}")
                continue
            try:
                state = _read_file(root, relative)
                if state.owner != os.geteuid() or state.link_count != 1:
                    raise FieldMigrationError(
                        "managed file must be singly linked and owned by this user"
                    )
                if PurePosixPath(relative).suffix.casefold() == ".canvas":
                    _validate_canvas(state.content, relative)
                else:
                    state.content.decode("utf-8")
                replacement, file_changes = _replacements(state.content, name)
                if _has_legacy_hub_reference(replacement, relative):
                    conflicts.append(f"unrecognized legacy Hub URL in managed file: {name}")
                if (
                    PurePosixPath(relative).suffix.casefold() == ".canvas"
                    and replacement != state.content
                ):
                    _validate_canvas(replacement, relative)
            except (FieldMigrationError, UnicodeDecodeError) as exc:
                conflicts.append(f"managed file cannot be safely migrated: {name}: {exc}")
                continue
            managed.append(state)
            changes.extend(file_changes)
        inventory, inventory_digest, inventory_conflicts = self._inventory(root, manifest, field)
        conflicts.extend(inventory_conflicts)
        inventory_paths = set(inventory)
        for state in managed:
            replacement, _ = _replacements(state.content, state.relative_path)
            if replacement == state.content:
                continue
            if _has_analysis_identity(state.content) or inventory_paths.intersection(
                _analysis_peer_paths(state.relative_path)
            ):
                conflicts.append(
                    "managed paper analysis requires a validated Field transaction: "
                    + state.relative_path
                )
        declared = {_field_path(field, name) for name in managed_names}
        unmapped = tuple(
            PurePosixPath(path).relative_to(PurePosixPath(*_field_parts(field))).as_posix()
            if _field_parts(field)
            else path
            for path in inventory
            if path not in declared
        )
        unresolved: list[FieldLinkChange] = []
        for name in unmapped:
            relative = _field_path(field, name)
            try:
                state = _read_file(root, relative)
                replacement, file_changes = _replacements(state.content, name)
                if _has_legacy_hub_reference(replacement, relative):
                    conflicts.append(f"unrecognized legacy Hub URL in unmapped file: {name}")
            except FieldMigrationError as exc:
                conflicts.append(f"unmapped file cannot be checked: {name}: {exc}")
                continue
            unresolved.extend(file_changes)
        if unresolved:
            conflicts.append(
                "Unmapped Field files still contain legacy paper links; "
                "declare ownership or resolve them before apply"
            )
        verified_links: list[tuple[str, str]] = []
        attachment_keys = {
            change.attachment_key for change in (*changes, *unresolved)
        }
        for key in sorted(attachment_keys):
            try:
                replacement = self._link_resolver(key)
                if replacement != f"zotero://open-pdf/library/items/{key}":
                    raise FieldMigrationError("Zotero resolver returned an unsupported URI")
            except (FieldMigrationError, ZoteroLocalError, OSError, ValueError) as exc:
                conflicts.append(f"Zotero attachment {key} cannot be verified: {exc}")
            else:
                verified_links.append((key, replacement))
        digest_payload = {
            "source_id": source_id,
            "field_id": field_id,
            "manifest": manifest_state.digest,
            "managed": [(state.relative_path, state.digest, state.inode) for state in managed],
            "inventory": inventory_digest,
            "changes": [change.__dict__ for change in changes],
            "unresolved": [change.__dict__ for change in unresolved],
            "verified_links": verified_links,
            "conflicts": conflicts,
        }
        plan_digest = _sha256(json.dumps(digest_payload, sort_keys=True).encode())
        token = f"fm_{secrets.token_urlsafe(24)}"
        preview = FieldMigrationPlan(
            plan_token=token,
            plan_digest=plan_digest,
            source_id=source_id,
            field_id=field_id,
            field_title=field.title,
            managed_files=managed_names,
            link_changes=tuple(changes),
            unmapped_files=unmapped,
            unresolved_legacy_links=tuple(unresolved),
            conflicts=tuple(conflicts),
        )
        self._plans[token] = _PendingPlan(
            preview=preview,
            root=root,
            root_identity=root_identity,
            field_identity=field_identity,
            field_parts=_field_parts(field),
            manifest=manifest_state,
            managed=tuple(managed),
            inventory_digest=inventory_digest,
            verified_links=tuple(verified_links),
            expires_at=self._clock() + self._ttl,
        )
        return preview

    @staticmethod
    def _assert_same_file(root: Path, expected: _FileState) -> None:
        actual = _read_file(root, expected.relative_path)
        if (
            actual.device != expected.device
            or actual.inode != expected.inode
            or actual.mode != expected.mode
            or actual.owner != expected.owner
            or actual.link_count != expected.link_count
            or actual.content != expected.content
        ):
            raise FieldMigrationError(f"Field changed after preview: {expected.relative_path}")

    def _assert_current(self, pending: _PendingPlan) -> None:
        preview = pending.preview
        root, manifest, field, root_identity, field_identity = self._resolve(
            preview.source_id, preview.field_id, capability="write"
        )
        if root != pending.root or root_identity != pending.root_identity:
            raise FieldMigrationError("registered source root changed after preview")
        if field_identity != pending.field_identity:
            raise FieldMigrationError("Field folder changed after preview")
        self._assert_same_file(root, pending.manifest)
        for state in pending.managed:
            self._assert_same_file(root, state)
        _inventory, digest, conflicts = self._inventory(root, manifest, field)
        if conflicts or digest != pending.inventory_digest:
            raise FieldMigrationError("Field inventory changed after preview")

    def _recovery_snapshot(self, pending: _PendingPlan) -> Path:
        root = pending.root
        state_root = self.state_root
        if state_root.is_symlink():
            raise FieldMigrationError("recovery state root is a symbolic link")
        prospective = state_root.resolve(strict=False)
        if prospective == root or root in prospective.parents:
            raise FieldMigrationError("recovery state must be outside the Vault")
        state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_fd = _open_directory_chain(state_root.parent)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        resolved = state_root.resolve(strict=True)
        if not resolved.is_dir() or resolved == root or root in resolved.parents:
            raise FieldMigrationError("recovery state must be outside the Vault")
        if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
            raise FieldMigrationError("recovery state directory must be private")
        recovery_parts = (
            "field-recovery",
            pending.preview.source_id,
            pending.preview.field_id,
        )
        recovery = resolved.joinpath(*recovery_parts)
        try:
            directory_fd = _open_directory_chain(resolved)
        except OSError as exc:
            raise FieldMigrationError("recovery directory is unsafe") from exc
        try:
            for part in recovery_parts:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                except FileExistsError:
                    pass
                child_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
                try:
                    os.fsync(directory_fd)
                except BaseException:
                    os.close(child_fd)
                    raise
                os.close(directory_fd)
                directory_fd = child_fd
                if stat.S_IMODE(os.fstat(directory_fd).st_mode) & 0o077:
                    raise FieldMigrationError("recovery directory must be private")
        except BaseException as exc:
            os.close(directory_fd)
            if isinstance(exc, FieldMigrationError):
                raise
            raise FieldMigrationError("recovery directory is unsafe") from exc
        archive_name = f"{int(time.time())}-{secrets.token_hex(8)}.zip"
        archive = recovery / archive_name
        try:
            descriptor = os.open(
                archive_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_fd,
            )
        except BaseException:
            os.close(directory_fd)
            raise
        try:
            with os.fdopen(descriptor, "wb") as handle:
                with zipfile.ZipFile(handle, mode="w", compression=zipfile.ZIP_STORED) as bundle:
                    metadata = {
                        "schema_version": 1,
                        "source_id": pending.preview.source_id,
                        "field_id": pending.preview.field_id,
                        "plan_digest": pending.preview.plan_digest,
                        "created_at_unix": time.time(),
                        "verified_backup": False,
                        "files": {
                            state.relative_path: {
                                "sha256": _sha256(state.content),
                                "mode": oct(state.mode),
                            }
                            for state in (pending.manifest, *pending.managed)
                        },
                    }
                    bundle.writestr("recovery.json", json.dumps(metadata, sort_keys=True))
                    for state in (pending.manifest, *pending.managed):
                        bundle.writestr("original/" + state.relative_path, state.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.fsync(directory_fd)
        except BaseException:
            try:
                os.unlink(archive_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(directory_fd)
        return archive

    def _open_recovery_directory(
        self, root: Path, source_id: str, field_id: str
    ) -> tuple[Path, int] | None:
        """Open an existing private recovery directory without creating state."""
        if any(part in {"", ".", ".."} or "/" in part for part in (source_id, field_id)):
            raise FieldMigrationError("invalid Field recovery identity")
        if self.state_root.is_symlink():
            raise FieldMigrationError("recovery state root is a symbolic link")
        if not self.state_root.exists():
            return None
        try:
            resolved = self.state_root.resolve(strict=True)
            if resolved == root or root in resolved.parents:
                raise FieldMigrationError("recovery state must be outside the Vault")
            if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
                raise FieldMigrationError("recovery state directory must be private")
            directory = resolved / "field-recovery" / source_id / field_id
            try:
                directory_fd = _open_directory_chain(
                    resolved, ("field-recovery", source_id, field_id)
                )
            except FileNotFoundError:
                return None
            if stat.S_IMODE(os.fstat(directory_fd).st_mode) & 0o077:
                os.close(directory_fd)
                raise FieldMigrationError("recovery directory must be private")
            return directory, directory_fd
        except FieldMigrationError:
            raise
        except OSError as exc:
            raise FieldMigrationError("recovery directory is unsafe") from exc

    def _read_journal(
        self, root: Path, source_id: str, field_id: str
    ) -> tuple[_RecoveryJournal, Path, int] | None:
        opened = self._open_recovery_directory(root, source_id, field_id)
        if opened is None:
            return None
        directory, directory_fd = opened
        try:
            try:
                content, metadata = _read_regular_at(
                    directory_fd, _JOURNAL_NAME, limit=_READ_LIMIT
                )
            except FileNotFoundError:
                os.close(directory_fd)
                return None
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise FieldMigrationError("Field recovery journal is not private")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise TypeError("journal is not an object")
            files = payload.pop("files")
            if not isinstance(files, list) or not all(isinstance(row, dict) for row in files):
                raise ValueError("invalid journal files")
            journal = _RecoveryJournal(
                **payload, files=tuple(_JournalFile(**row) for row in files)
            )
            if (
                journal.schema_version != _JOURNAL_SCHEMA_VERSION
                or journal.source_id != source_id
                or journal.field_id != field_id
                or not isinstance(journal.snapshot_name, str)
                or not journal.snapshot_name.endswith(".zip")
                or Path(journal.snapshot_name).name != journal.snapshot_name
                or len({row.relative_path for row in journal.files}) != len(journal.files)
            ):
                raise ValueError("journal identity or schema is invalid")
            return journal, directory, directory_fd
        except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError, FieldRegistryError) as exc:
            os.close(directory_fd)
            raise FieldMigrationError("Field recovery journal is invalid; manual review required") from exc
        except BaseException:
            os.close(directory_fd)
            raise

    @staticmethod
    def _write_journal(directory_fd: int, journal: _RecoveryJournal) -> None:
        payload = json.dumps(asdict(journal), sort_keys=True).encode("utf-8")
        if len(payload) > _READ_LIMIT:
            raise FieldMigrationError("Field recovery journal exceeds the size limit")
        temporary = f".journal-{secrets.token_hex(8)}.tmp"
        linked = False
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(
                temporary,
                _JOURNAL_NAME,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            linked = True
            os.fsync(directory_fd)
        except OSError as exc:
            if linked:
                try:
                    os.unlink(_JOURNAL_NAME, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except OSError:
                    pass
            raise FieldMigrationError("Field recovery journal could not be committed") from exc
        finally:
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass

    @staticmethod
    def _read_snapshot(
        directory_fd: int, journal: _RecoveryJournal
    ) -> dict[str, bytes]:
        try:
            descriptor = os.open(
                journal.snapshot_name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            with os.fdopen(descriptor, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
                    raise FieldMigrationError("Field recovery snapshot is not a private file")
                with zipfile.ZipFile(handle) as archive:
                    if archive.getinfo("recovery.json").file_size > _READ_LIMIT:
                        raise FieldMigrationError("Field recovery receipt is too large")
                    receipt = json.loads(archive.read("recovery.json"))
                    if not isinstance(receipt, dict):
                        raise FieldMigrationError("Field recovery receipt is invalid")
                    if (
                        receipt.get("source_id") != journal.source_id
                        or receipt.get("field_id") != journal.field_id
                        or receipt.get("plan_digest") != journal.plan_digest
                    ):
                        raise FieldMigrationError("Field recovery snapshot identity changed")
                    originals: dict[str, bytes] = {}
                    for row in journal.files:
                        name = "original/" + row.relative_path
                        info = archive.getinfo(name)
                        if info.file_size > _READ_LIMIT:
                            raise FieldMigrationError("Field recovery snapshot file is too large")
                        content = archive.read(info)
                        if _sha256(content) != row.old_hash:
                            raise FieldMigrationError("Field recovery snapshot hash changed")
                        originals[row.relative_path] = content
                    return originals
        except FieldMigrationError:
            raise
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
            raise FieldMigrationError("Field recovery snapshot is invalid; manual review required") from exc

    @staticmethod
    def _clear_journal(directory_fd: int) -> None:
        try:
            os.unlink(_JOURNAL_NAME, dir_fd=directory_fd)
        except OSError as exc:
            raise FieldMigrationError("Field journal cleanup failed; journal retained") from exc
        try:
            os.fsync(directory_fd)
        except OSError as exc:
            raise FieldMigrationError(
                "Field journal finalization uncertain after unlink; inspect before further writes"
            ) from exc

    @staticmethod
    def _cleanup_temp_and_close(parent_fd: int, temporary_name: str) -> str | None:
        errors: list[str] = []
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"unlink {temporary_name}: {exc}")
        try:
            os.close(parent_fd)
        except OSError as exc:
            errors.append(f"close staged directory: {exc}")
        return "; ".join(errors) or None

    @staticmethod
    def _journal_file_is_new(state: _FileState, row: _JournalFile) -> bool:
        return (
            _sha256(state.content) == row.new_hash
            and (state.device, state.inode) == (row.new_device, row.new_inode)
            and state.mode == row.old_mode
            and state.owner == row.old_owner
            and state.link_count == 1
        )

    def _recover_opened(
        self,
        root: Path,
        manifest: FieldManifest,
        field: FieldDefinition,
        root_identity: tuple[int, int],
        field_identity: tuple[int, int],
        opened: tuple[_RecoveryJournal, Path, int],
    ) -> FieldMigrationRecovery:
        journal, directory, directory_fd = opened
        if (
            root_identity != (journal.root_device, journal.root_inode)
            or field_identity != (journal.field_device, journal.field_inode)
            or _sha256(_read_file(root, ".scholar-workflow/fields.yml").content)
            != journal.manifest_hash
            or manifest.source_id != journal.source_id
        ):
            raise FieldMigrationError("Field recovery identity changed; manual review required")
        allowed = {_field_path(field, path) for path in _managed_paths(field)}
        for row in journal.files:
            if (
                row.relative_path not in allowed
                or PurePosixPath(row.relative_path).suffix.casefold() not in _SUPPORTED_SUFFIXES
                or not isinstance(row.temporary_name, str)
                or not row.temporary_name.startswith(".scholar-migrate-")
                or Path(row.temporary_name).name != row.temporary_name
                or not isinstance(row.old_hash, str)
                or not isinstance(row.new_hash, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", row.old_hash)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", row.new_hash)
                or not isinstance(row.new_device, int)
                or not isinstance(row.new_inode, int)
                or not isinstance(row.old_mode, int)
                or not isinstance(row.old_owner, int)
                or row.old_link_count != 1
            ):
                raise FieldMigrationError("Field recovery journal has an unsafe file entry")
        originals = self._read_snapshot(directory_fd, journal)
        states: dict[str, _FileState] = {}
        for row in journal.files:
            current = _read_file(root, row.relative_path)
            is_original = (
                _sha256(current.content) == row.old_hash
                and current.mode == row.old_mode
                and current.owner == row.old_owner
                and current.link_count == row.old_link_count
            )
            if not is_original and not self._journal_file_is_new(current, row):
                raise FieldMigrationError(
                    f"Field recovery conflicts with external edit: {row.relative_path}"
                )
            states[row.relative_path] = current
            parent_fd = _open_directory_chain(root, PurePosixPath(row.relative_path).parts[:-1])
            try:
                self._assert_parent(root, row.relative_path, parent_fd)
                try:
                    temporary, temp_meta = _read_regular_at(
                        parent_fd, row.temporary_name, limit=_READ_LIMIT
                    )
                except FileNotFoundError:
                    pass
                else:
                    if (
                        _sha256(temporary) != row.new_hash
                        or _identity(temp_meta) != (row.new_device, row.new_inode)
                    ):
                        raise FieldMigrationError(
                            f"Field staged file changed externally: {row.relative_path}"
                        )
            finally:
                os.close(parent_fd)
        recovered: list[str] = []
        for row in journal.files:
            if _sha256(states[row.relative_path].content) == row.old_hash:
                continue
            parent_fd = _open_directory_chain(root, PurePosixPath(row.relative_path).parts[:-1])
            restore_name = f".scholar-restore-{secrets.token_hex(8)}.tmp"
            try:
                self._assert_parent(root, row.relative_path, parent_fd)
                current = _read_file(root, row.relative_path)
                if not self._journal_file_is_new(current, row):
                    raise FieldMigrationError(
                        f"Field recovery conflicts with external edit: {row.relative_path}"
                    )
                self._write_temp(
                    parent_fd, restore_name, originals[row.relative_path], row.old_mode
                )
                _replace_at(
                    restore_name,
                    PurePosixPath(row.relative_path).name,
                    parent_fd,
                )
                os.fsync(parent_fd)
                recovered.append(row.relative_path)
            finally:
                primary = sys.exception()
                cleanup_error = self._cleanup_temp_and_close(parent_fd, restore_name)
                if cleanup_error:
                    if primary is not None:
                        raise FieldMigrationError(
                            f"{primary}; restore temp cleanup failed; journal retained: "
                            f"{cleanup_error}"
                        ) from primary
                    raise FieldMigrationError(
                        f"restore temp cleanup failed; journal retained: {cleanup_error}"
                    )
        for row in journal.files:
            restored = _read_file(root, row.relative_path)
            if (
                _sha256(restored.content) != row.old_hash
                or restored.mode != row.old_mode
                or restored.owner != row.old_owner
                or restored.link_count != row.old_link_count
            ):
                raise FieldMigrationError("Field recovery verification failed; journal retained")
            parent_fd = _open_directory_chain(root, PurePosixPath(row.relative_path).parts[:-1])
            try:
                try:
                    temporary, temp_meta = _read_regular_at(
                        parent_fd, row.temporary_name, limit=_READ_LIMIT
                    )
                except FileNotFoundError:
                    continue
                if (
                    _sha256(temporary) != row.new_hash
                    or _identity(temp_meta) != (row.new_device, row.new_inode)
                ):
                    raise FieldMigrationError("Field staged file changed; journal retained")
                os.unlink(row.temporary_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        self._clear_journal(directory_fd)
        return FieldMigrationRecovery(
            source_id=journal.source_id,
            field_id=journal.field_id,
            recovered_files=tuple(recovered),
            recovery_snapshot=directory / journal.snapshot_name,
        )

    def recover(self, source_id: str, field_id: str) -> FieldMigrationRecovery:
        """Explicitly restore only journal-owned bytes; never overwrite external edits."""
        root, manifest, field, root_identity, field_identity = self._resolve(
            source_id, field_id, capability="write"
        )
        with self._field_service._field_write_guard(root):
            current_root, manifest, field, current_root_identity, current_field_identity = (
                self._resolve(source_id, field_id, capability="write")
            )
            if (
                current_root != root
                or current_root_identity != root_identity
                or current_field_identity != field_identity
            ):
                raise FieldMigrationError("registered Field changed before recovery lock")
            opened = self._read_journal(root, source_id, field_id)
            if opened is None:
                return FieldMigrationRecovery(source_id, field_id, (), None)
            try:
                try:
                    return self._recover_opened(
                        root,
                        manifest,
                        field,
                        current_root_identity,
                        current_field_identity,
                        opened,
                    )
                except OSError as exc:
                    raise FieldMigrationError(
                        "Field recovery IO failed; journal retained for retry"
                    ) from exc
            finally:
                os.close(opened[2])

    @staticmethod
    def _write_temp(parent_fd: int, name: str, content: bytes, mode: int) -> None:
        descriptor = os.open(
            name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            mode,
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _remaining_legacy_links(
        root: Path, manifest: FieldManifest, field: FieldDefinition
    ) -> tuple[str, ...]:
        inventory, _digest, conflicts = FieldMigrationService._inventory(root, manifest, field)
        if conflicts:
            raise FieldMigrationError("Field inventory became unsafe during commit")
        return tuple(
            _field_relative(path, _field_parts(field))
            for path in inventory
            if _has_legacy_hub_reference(_read_file(root, path).content, path)
        )

    @staticmethod
    def _assert_parent(root: Path, relative: str, parent_fd: int) -> None:
        parts = PurePosixPath(relative).parts
        try:
            check_fd = _open_directory_chain(root, parts[:-1])
            try:
                if _identity(os.fstat(check_fd)) != _identity(os.fstat(parent_fd)):
                    raise FieldMigrationError("Field parent changed during migration")
            finally:
                os.close(check_fd)
        except OSError as exc:
            raise FieldMigrationError("Field parent is no longer safe") from exc

    def apply(
        self,
        plan_token: str,
        *,
        approved_digest: str,
        external_writers_paused: bool = False,
    ) -> FieldMigrationResult:
        if external_writers_paused is not True:
            raise FieldMigrationError(
                "external Field writers must be paused before migration apply"
            )
        pending = self._plans.pop(plan_token, None)
        if pending is None or pending.expires_at <= self._clock():
            raise FieldMigrationError("Field migration plan is unknown or expired")
        preview = pending.preview
        if not approved_digest or approved_digest != preview.plan_digest:
            raise FieldMigrationError("the exact Field migration plan was not approved")
        if preview.conflicts:
            raise FieldMigrationError("Field migration plan has unresolved conflicts")
        with self._field_service._field_write_guard(pending.root):
            unfinished = self._read_journal(
                pending.root, preview.source_id, preview.field_id
            )
            if unfinished is not None:
                os.close(unfinished[2])
                raise FieldMigrationError("Field recovery is required before apply; run recover")
            self._assert_current(pending)
            for key, approved_uri in pending.verified_links:
                try:
                    current_uri = self._link_resolver(key)
                except (FieldMigrationError, ZoteroLocalError, OSError, ValueError) as exc:
                    raise FieldMigrationError(
                        f"Zotero attachment {key} cannot be reverified before apply: {exc}"
                    ) from exc
                if current_uri != approved_uri:
                    raise FieldMigrationError(
                        f"Zotero attachment {key} changed after migration preview"
                    )
            manifest = FieldService._load_manifest(pending.root)
            field = next(row for row in manifest.fields if row.field_id == preview.field_id)
            changes: list[tuple[_FileState, bytes]] = []
            for state in pending.managed:
                relative = _field_relative(state.relative_path, pending.field_parts)
                replacement, _file_changes = _replacements(state.content, relative)
                if replacement != state.content:
                    changes.append((state, replacement))
            snapshot = self._recovery_snapshot(pending)
            staged: list[_StagedWrite] = []
            journal: _RecoveryJournal | None = None
            recovery_fd: int | None = None
            journal_written = False
            try:
                for state, replacement in changes:
                    parts = PurePosixPath(state.relative_path).parts
                    parent_fd = _open_directory_chain(pending.root, parts[:-1])
                    temporary = f".scholar-migrate-{secrets.token_hex(8)}.tmp"
                    try:
                        self._write_temp(parent_fd, temporary, replacement, state.mode)
                        prepared, metadata = _read_regular_at(
                            parent_fd, temporary, limit=_READ_LIMIT
                        )
                        if prepared != replacement:
                            raise FieldMigrationError("staged Field file changed unexpectedly")
                    except BaseException as exc:
                        cleanup_error = self._cleanup_temp_and_close(parent_fd, temporary)
                        if cleanup_error:
                            raise FieldMigrationError(
                                f"{exc}; staging cleanup failed before commit: "
                                f"{cleanup_error}"
                            ) from exc
                        raise
                    staged.append(
                        _StagedWrite(
                            state,
                            replacement,
                            parent_fd,
                            temporary,
                            _identity(metadata),
                        )
                    )
                self._assert_current(pending)
                opened = self._open_recovery_directory(
                    pending.root, preview.source_id, preview.field_id
                )
                if opened is None or opened[0] != snapshot.parent:
                    raise FieldMigrationError("Field recovery directory changed before commit")
                _directory, recovery_fd = opened
                journal = _RecoveryJournal(
                    schema_version=_JOURNAL_SCHEMA_VERSION,
                    source_id=preview.source_id,
                    field_id=preview.field_id,
                    plan_digest=preview.plan_digest,
                    root_device=pending.root_identity[0],
                    root_inode=pending.root_identity[1],
                    field_device=pending.field_identity[0],
                    field_inode=pending.field_identity[1],
                    manifest_hash=_sha256(pending.manifest.content),
                    snapshot_name=snapshot.name,
                    files=tuple(
                        _JournalFile(
                            relative_path=item.original.relative_path,
                            old_hash=_sha256(item.original.content),
                            new_hash=_sha256(item.replacement),
                            old_mode=item.original.mode,
                            old_owner=item.original.owner,
                            old_link_count=item.original.link_count,
                            new_device=item.prepared_identity[0],
                            new_inode=item.prepared_identity[1],
                            temporary_name=item.temporary_name,
                        )
                        for item in staged
                    ),
                )
                self._read_snapshot(recovery_fd, journal)
                self._write_journal(recovery_fd, journal)
                journal_written = True
                for item in staged:
                    self._assert_parent(pending.root, item.original.relative_path, item.parent_fd)
                    self._assert_same_file(pending.root, item.original)
                    prepared, prepared_metadata = _read_regular_at(
                        item.parent_fd, item.temporary_name, limit=_READ_LIMIT
                    )
                    if (
                        prepared != item.replacement
                        or _identity(prepared_metadata) != item.prepared_identity
                    ):
                        raise FieldMigrationError("staged Field file changed before commit")
                    name = PurePosixPath(item.original.relative_path).name
                    _replace_at(item.temporary_name, name, item.parent_fd)
                    os.fsync(item.parent_fd)
                remaining = self._remaining_legacy_links(pending.root, manifest, field)
                if remaining:
                    raise FieldMigrationError(
                        "legacy paper links remain in Field files: " + ", ".join(remaining)
                    )
                assert journal is not None
                for row in journal.files:
                    current = _read_file(pending.root, row.relative_path)
                    if not self._journal_file_is_new(current, row):
                        raise FieldMigrationError(
                            f"Field target changed during commit: {row.relative_path}"
                        )
            except BaseException as exc:
                if journal_written:
                    assert journal is not None and recovery_fd is not None
                    try:
                        self._recover_opened(
                            pending.root,
                            manifest,
                            field,
                            pending.root_identity,
                            pending.field_identity,
                            (journal, snapshot.parent, recovery_fd),
                        )
                    except (OSError, FieldMigrationError) as rollback_exc:
                        raise FieldMigrationError(
                            "Field migration failed; conditional rollback incomplete; "
                            f"snapshot={snapshot}; {rollback_exc}"
                        ) from exc
                raise FieldMigrationError(
                    f"Field migration failed and was rolled back; {exc}; snapshot={snapshot}"
                ) from exc
            else:
                assert recovery_fd is not None
                try:
                    self._clear_journal(recovery_fd)
                except OSError as exc:
                    raise FieldMigrationError(
                        "Field commit completed but journal finalization is uncertain; "
                        "inspect before further writes"
                    ) from exc
            finally:
                primary = sys.exception()
                cleanup_errors: list[str] = []
                for item in staged:
                    detail = self._cleanup_temp_and_close(
                        item.parent_fd, item.temporary_name
                    )
                    if detail:
                        cleanup_errors.append(detail)
                if recovery_fd is not None:
                    try:
                        os.close(recovery_fd)
                    except OSError as exc:
                        cleanup_errors.append(f"close recovery directory: {exc}")
                if cleanup_errors:
                    detail = "; ".join(cleanup_errors)
                    if primary is not None:
                        raise FieldMigrationError(
                            f"{primary}; staged cleanup failed; inspect journal state: {detail}"
                        ) from primary
                    raise FieldMigrationError(
                        f"staged cleanup failed; inspect journal state: {detail}"
                    )
        changed = tuple(
            _field_relative(item.original.relative_path, pending.field_parts) for item in staged
        )
        return FieldMigrationResult(
            source_id=preview.source_id,
            field_id=preview.field_id,
            changed_files=changed,
            replaced_links=sum(change.occurrences for change in preview.link_changes),
            recovery_snapshot=snapshot,
        )


__all__ = [
    "FieldLinkChange",
    "FieldMigrationError",
    "FieldMigrationPlan",
    "FieldMigrationResult",
    "FieldMigrationService",
]
