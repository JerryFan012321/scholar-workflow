"""Explicit, per-Field cleanup of legacy paper links.

This is deliberately narrower than a knowledge-template migration.  Only files
declared by one existing Field manifest may be rewritten.  Unmapped prose and
files are reported, not normalized or inferred into the manifest.  The shared
cross-process Field lock and CAS checks protect managed writes.  Synchronous
failures roll back the Field; a process crash during a multi-file commit may
require manual restoration from the explicitly unverified recovery snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
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


class FieldMigrationError(RuntimeError):
    """A Field plan is stale, unsafe, incomplete, or not explicitly approved."""


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
    crash_recovery: str = "manual-from-unverified-snapshot"
    recovery_is_verified_backup: bool = False


@dataclass(frozen=True)
class FieldMigrationResult:
    source_id: str
    field_id: str
    changed_files: tuple[str, ...]
    replaced_links: int
    recovery_snapshot: Path
    recovery_is_verified_backup: bool = False
    crash_recovery: str = "manual-from-unverified-snapshot"


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
            field_fd = _open_directory_chain(root, _field_parts(field))
            try:
                root_identity = _identity(os.fstat(root_fd))
                field_identity = _identity(os.fstat(field_fd))
            finally:
                os.close(field_fd)
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

    @classmethod
    def _restore(cls, root: Path, staged: _StagedWrite) -> None:
        cls._assert_parent(root, staged.original.relative_path, staged.parent_fd)
        current = _read_file(root, staged.original.relative_path)
        if (
            current.device,
            current.inode,
        ) != staged.prepared_identity or current.content != staged.replacement:
            raise FieldMigrationError(
                f"cannot roll back externally changed file: {staged.original.relative_path}"
            )
        restore_name = f".scholar-restore-{secrets.token_hex(8)}.tmp"
        try:
            cls._write_temp(
                staged.parent_fd,
                restore_name,
                staged.original.content,
                staged.original.mode,
            )
            _replace_at(
                restore_name,
                PurePosixPath(staged.original.relative_path).name,
                staged.parent_fd,
            )
            os.fsync(staged.parent_fd)
        finally:
            try:
                os.unlink(restore_name, dir_fd=staged.parent_fd)
            except FileNotFoundError:
                pass

    def apply(self, plan_token: str, *, approved_digest: str) -> FieldMigrationResult:
        pending = self._plans.pop(plan_token, None)
        if pending is None or pending.expires_at <= self._clock():
            raise FieldMigrationError("Field migration plan is unknown or expired")
        preview = pending.preview
        if not approved_digest or approved_digest != preview.plan_digest:
            raise FieldMigrationError("the exact Field migration plan was not approved")
        if preview.conflicts:
            raise FieldMigrationError("Field migration plan has unresolved conflicts")
        with self._field_service._field_write_guard(pending.root):
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
            committed: list[_StagedWrite] = []
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
                    except BaseException:
                        try:
                            os.unlink(temporary, dir_fd=parent_fd)
                        except FileNotFoundError:
                            pass
                        os.close(parent_fd)
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
                    committed.append(item)
                    os.fsync(item.parent_fd)
                remaining = self._remaining_legacy_links(pending.root, manifest, field)
                if remaining:
                    raise FieldMigrationError(
                        "legacy paper links remain in Field files: " + ", ".join(remaining)
                    )
            except BaseException as exc:
                rollback_errors: list[str] = []
                for item in reversed(committed):
                    try:
                        self._restore(pending.root, item)
                    except (OSError, FieldMigrationError) as rollback_exc:
                        rollback_errors.append(str(rollback_exc))
                detail = "; ".join(rollback_errors)
                if detail:
                    raise FieldMigrationError(
                        f"Field migration failed; rollback incomplete; snapshot={snapshot}; {detail}"
                    ) from exc
                raise FieldMigrationError(
                    f"Field migration failed and was rolled back; snapshot={snapshot}"
                ) from exc
            finally:
                for item in staged:
                    try:
                        os.unlink(item.temporary_name, dir_fd=item.parent_fd)
                    except FileNotFoundError:
                        pass
                    os.close(item.parent_fd)
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
