"""Explicit Obsidian source registration and portable Field manifests.

The browser never supplies a filesystem path.  A host-side picker resolves a
directory, :class:`FieldCandidateStore` replaces it with a short-lived opaque
token, and only an explicit confirmation may create ``fields.yml``.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import plistlib
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Self

import yaml
from pydantic import Field, field_validator, model_validator

from scholar_workflow.hub.models import HubModel

_PORTABLE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
_IGNORED_NAMES = {".obsidian", ".scholar-workflow", ".git", ".trash"}
_MAX_FIELD_DOCUMENT_BYTES = 2 * 1024 * 1024
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_HOME_NAMES = (
    "00-领域入口.md",
    "00-入口.md",
    "README.md",
    "index.md",
    "Index.md",
)
_LEGACY_PAPER_LINK = re.compile(
    r"http://127\.0\.0\.1:23128/open/paper/"
    r"(?P<attachment>[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})"
)


class FieldRegistryError(RuntimeError):
    """A source registry or portable Field manifest is invalid."""


class FieldRegistryCommitUncertain(FieldRegistryError):
    """A registry rename completed, but durable commit could not be confirmed."""


class FieldCandidateExpired(FieldRegistryError):
    """A one-time folder candidate no longer exists or was already consumed."""


def _canonical_uuid(value: str, *, name: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError(f"{name} must be a canonical UUID")
    return value


def _safe_relative(value: str, *, allow_dot: bool = False) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError("Field paths must be non-empty clean relative paths")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise ValueError("Field paths must use clean POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Field paths must stay inside their selected folder")
    normalized = path.as_posix()
    if normalized == "." and allow_dot:
        return normalized
    if normalized in {"", "."}:
        raise ValueError("Field path cannot be empty")
    return normalized


def _field_roots_overlap(first: str, second: str) -> bool:
    return (
        first == "."
        or second == "."
        or first == second
        or first.startswith(second + "/")
        or second.startswith(first + "/")
    )


def _open_directory_chain(root: Path, parts: tuple[str, ...] = ()) -> int:
    """Open a directory chain without ever following an intermediate symlink."""
    descriptor = os.open(root, _DIRECTORY_FLAGS)
    try:
        for part in parts:
            child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_at(parent_fd: int, name: str, *, limit: int) -> tuple[bytes, os.stat_result]:
    descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_fd)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise FieldRegistryError("Field path is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(limit + 1)
        if len(content) > limit:
            raise FieldRegistryError("Field document exceeds the inline size limit")
        return content, metadata
    finally:
        os.close(descriptor)


class FolderRegistration(HubModel):
    folder_id: str
    root: Path
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=lambda: ["read"])

    @field_validator("folder_id")
    @classmethod
    def _folder_id(cls, value: str) -> str:
        if not _PORTABLE_ID.fullmatch(value):
            raise ValueError("folder_id must be a portable stable identifier")
        return value

    @field_validator("root")
    @classmethod
    def _root(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("registered folder root must be absolute")
        return expanded

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            not _CAPABILITY.fullmatch(value) for value in values
        ):
            raise ValueError("invalid or duplicate folder capability")
        return values


class KnowledgeSourceRegistration(HubModel):
    source_id: str
    provider: Literal["obsidian"] = "obsidian"
    folder_id: str
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=lambda: ["read", "write"])

    @field_validator("source_id")
    @classmethod
    def _source_id(cls, value: str) -> str:
        return _canonical_uuid(value, name="source_id")

    @field_validator("folder_id")
    @classmethod
    def _folder_id(cls, value: str) -> str:
        if not _PORTABLE_ID.fullmatch(value):
            raise ValueError("folder_id must be a portable stable identifier")
        return value

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            not _CAPABILITY.fullmatch(value) for value in values
        ):
            raise ValueError("invalid or duplicate source capability")
        return values


class KnowledgeSourceRegistryDocument(HubModel):
    schema_version: int = 1
    folders: list[FolderRegistration] = Field(default_factory=list)
    sources: list[KnowledgeSourceRegistration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_document(self) -> Self:
        if self.schema_version != 1:
            raise ValueError("unsupported source registry schema version")
        folder_ids = [row.folder_id for row in self.folders]
        source_ids = [row.source_id for row in self.sources]
        if len(folder_ids) != len(set(folder_ids)):
            raise ValueError("duplicate folder_id")
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source_id")
        known = set(folder_ids)
        if any(source.folder_id not in known for source in self.sources):
            raise ValueError("source references an unknown folder_id")
        return self


class KnowledgeSourceRegistry:
    """Host-local source/folder location registry; never scans the disk."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load_document(self) -> KnowledgeSourceRegistryDocument:
        if not self.path.exists():
            return KnowledgeSourceRegistryDocument()
        if self.path.is_symlink() or not self.path.is_file():
            raise FieldRegistryError("source registry is not a trusted regular file")
        try:
            return KnowledgeSourceRegistryDocument.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise FieldRegistryError("source registry is invalid") from exc

    def revision(self) -> str:
        if self.path.is_symlink():
            raise FieldRegistryError("source registry is not a trusted regular file")
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            return "absent"
        except OSError as exc:
            raise FieldRegistryError("source registry is unavailable") from exc
        return "sha256:" + hashlib.sha256(content).hexdigest()

    def save(
        self,
        document: KnowledgeSourceRegistryDocument,
        *,
        expected_revision: str | None = None,
    ) -> None:
        validated = KnowledgeSourceRegistryDocument.model_validate(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name = f".{self.path.name}.{secrets.token_hex(8)}.tmp"
        lock_name = f".{self.path.name}.lock"
        parent_fd: int | None = None
        lock_fd: int | None = None
        replaced = False
        try:
            parent_fd = _open_directory_chain(self.path.parent)
            lock_fd = os.open(
                lock_name,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_fd,
            )
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise FieldRegistryError("source registry lock is not a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if expected_revision is not None and self._revision_at(parent_fd) != expected_revision:
                raise FieldRegistryError("source registry changed after preview")
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=parent_fd,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(validated.model_dump_json(indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(
                temporary_name,
                self.path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            replaced = True
            os.fsync(parent_fd)
        except OSError as exc:
            if replaced:
                raise FieldRegistryCommitUncertain(
                    "source registry may be committed; refresh and inspect before retrying"
                ) from exc
            raise FieldRegistryError("source registry could not be saved safely") from exc
        finally:
            if parent_fd is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except OSError:
                    pass
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(lock_fd)
            if parent_fd is not None:
                os.close(parent_fd)

    def _revision_at(self, parent_fd: int) -> str:
        try:
            descriptor = os.open(self.path.name, _READ_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return "absent"
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise FieldRegistryError("source registry is not a trusted regular file")
            digest = hashlib.sha256()
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return "sha256:" + digest.hexdigest()
        finally:
            os.close(descriptor)

    def resolve(self, source_id: str, *, capability: str = "read") -> Path:
        document = self.load_document()
        source = next((row for row in document.sources if row.source_id == source_id), None)
        if source is None or not source.enabled:
            raise FieldRegistryError("knowledge source is unknown or disabled")
        if capability not in source.capabilities:
            raise FieldRegistryError(f"knowledge source does not allow {capability}")
        folder = next(row for row in document.folders if row.folder_id == source.folder_id)
        if not folder.enabled or capability not in folder.capabilities:
            raise FieldRegistryError(f"registered folder does not allow {capability}")
        try:
            root = folder.root.resolve(strict=True)
        except OSError as exc:
            raise FieldRegistryError("registered source folder is unavailable") from exc
        if folder.root.is_symlink() or not root.is_dir():
            raise FieldRegistryError("registered source folder is not trusted")
        return root


class FieldNavigationGroup(HubModel):
    label: str = Field(min_length=1, max_length=120)
    items: list[str] = Field(default_factory=list)

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("navigation label must be clean text")
        return value

    @field_validator("items")
    @classmethod
    def _items(cls, values: list[str]) -> list[str]:
        normalized = [_safe_relative(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("duplicate navigation item")
        return normalized


class FieldDefinition(HubModel):
    field_id: str
    title: str = Field(min_length=1, max_length=200)
    relative_root: str
    home: str
    navigation: list[FieldNavigationGroup] = Field(default_factory=list)

    @field_validator("field_id")
    @classmethod
    def _field_id(cls, value: str) -> str:
        return _canonical_uuid(value, name="field_id")

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Field title must be clean text")
        return value

    @field_validator("relative_root")
    @classmethod
    def _relative_root(cls, value: str) -> str:
        return _safe_relative(value, allow_dot=True)

    @field_validator("home")
    @classmethod
    def _home(cls, value: str) -> str:
        return _safe_relative(value)


class FieldManifest(HubModel):
    schema_version: int = 1
    source_id: str
    fields: list[FieldDefinition]

    @field_validator("source_id")
    @classmethod
    def _source_id(cls, value: str) -> str:
        return _canonical_uuid(value, name="source_id")

    @model_validator(mode="after")
    def _valid_manifest(self) -> Self:
        if self.schema_version != 1:
            raise ValueError("unsupported Field manifest schema version")
        if not self.fields:
            raise ValueError("Field manifest must contain at least one Field")
        identifiers = [field.field_id for field in self.fields]
        roots = [field.relative_root for field in self.fields]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate field_id")
        if len(roots) != len(set(roots)):
            raise ValueError("duplicate Field relative_root")
        if any(
            _field_roots_overlap(first, second)
            for index, first in enumerate(roots)
            for second in roots[index + 1:]
        ):
            raise ValueError("Field relative_root entries must not overlap")
        return self


class FieldPreview(HubModel):
    candidate_token: str
    source_id: str
    folder_id: str
    existing_manifest: bool
    registration_only: bool = False
    fields: list[FieldDefinition]
    registered_fields: list[FieldDefinition] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    template_changes: list[str] = Field(default_factory=list)
    ignored_files: list[str] = Field(default_factory=list)
    unmapped_markdown: list[str] = Field(default_factory=list)
    legacy_link_changes: list[LegacyLinkChange] = Field(default_factory=list)
    manifest_base_hash: str
    registry_base_hash: str


class LegacyLinkChange(HubModel):
    relative_path: str
    attachment_key: str
    replacement: str
    occurrences: int = Field(ge=1)

    @field_validator("relative_path")
    @classmethod
    def _relative_path(cls, value: str) -> str:
        return _safe_relative(value)

    @field_validator("attachment_key")
    @classmethod
    def _attachment_key(cls, value: str) -> str:
        if not re.fullmatch(r"[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}", value):
            raise ValueError("attachment_key must be a Zotero item key")
        return value

    @field_validator("replacement")
    @classmethod
    def _replacement(cls, value: str) -> str:
        expected_prefix = "zotero://open-pdf/library/items/"
        if not value.startswith(expected_prefix):
            raise ValueError("legacy link replacement must be a stable Zotero URI")
        return value


@dataclass(frozen=True)
class _Candidate:
    root: Path
    preview: FieldPreview
    root_identity: tuple[int, int, int]
    content_base_hash: str
    expires_at: float


class FieldCandidateStore:
    """Process-local one-time mapping from opaque token to a selected folder."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("candidate TTL must be positive")
        self._ttl = ttl_seconds
        self._clock = clock
        self._candidates: dict[str, _Candidate] = {}

    def issue(
        self,
        root: Path,
        preview: FieldPreview,
        *,
        root_identity: tuple[int, int, int],
        content_base_hash: str,
    ) -> str:
        token = f"fld_{secrets.token_urlsafe(24)}"
        self._candidates[token] = _Candidate(
            root=Path(root),
            preview=preview.model_copy(update={"candidate_token": token}),
            root_identity=root_identity,
            content_base_hash=content_base_hash,
            expires_at=self._clock() + self._ttl,
        )
        return token

    def peek(self, token: str) -> _Candidate:
        candidate = self._candidates.get(token)
        if candidate is None or candidate.expires_at <= self._clock():
            self._candidates.pop(token, None)
            raise FieldCandidateExpired("Field candidate expired; choose the folder again")
        return candidate

    def consume(self, token: str) -> _Candidate:
        candidate = self.peek(token)
        del self._candidates[token]
        return candidate


class SystemFolderPicker:
    """Use the operating-system picker; the returned path never reaches the browser."""

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._runner = runner

    def choose(self) -> Path:
        if sys.platform != "darwin":
            raise FieldRegistryError("system folder selection is currently available on macOS")
        script = 'POSIX path of (choose folder with prompt "选择 Obsidian Vault 或领域目录")'
        result = self._runner(
            ["/usr/bin/osascript", "-e", script],
            shell=False,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise FieldRegistryError("folder selection was cancelled or failed")
        raw = result.stdout.strip()
        if not raw or "\x00" in raw:
            raise FieldRegistryError("folder picker returned an invalid path")
        return Path(raw)


class FieldService:
    """Preview and explicitly initialize one selected Vault or subdirectory."""

    def __init__(
        self,
        registry: KnowledgeSourceRegistry,
        candidates: FieldCandidateStore | None = None,
    ) -> None:
        self.registry = registry
        self.candidates = candidates or FieldCandidateStore()
        self._write_lock = threading.RLock()

    def preview(self, selected_root: Path) -> FieldPreview:
        root = self._trusted_root(selected_root)
        root_identity = self._root_identity(root)
        content_base_hash = self._preview_content_hash(root)
        manifest_bytes = self._manifest_bytes(root)
        existing = manifest_bytes is not None
        manifest_hash = self._manifest_hash(root)
        registry_hash = self.registry.revision()
        conflicts: list[str] = []
        fields, ignored, unmapped = self._infer_preview(root)
        registered_fields: list[FieldDefinition] = []
        if existing:
            manifest = self._load_manifest(root)
            registered_fields = manifest.fields
            source_id = manifest.source_id
            self._validate_manifest_paths(root, manifest)
            fields = [
                field for field in fields
                if not any(
                    self._field_roots_overlap(field.relative_root, registered.relative_root)
                    for registered in registered_fields
                )
            ]
        else:
            source_id = str(uuid.uuid4())
        registry_document = self.registry.load_document()
        conflicts.extend(self._registered_root_conflicts(root, source_id, registry_document))
        registered_source = next(
            (
                row for row in registry_document.sources
                if row.source_id == source_id
            ),
            None,
        )
        registration_only = existing and registered_source is None
        if registration_only:
            fields = []
        elif not fields:
            conflicts.append("No unregistered Markdown Field candidate was found")
        folder_id = (
            registered_source.folder_id
            if registered_source is not None
            else f"obsidian-{hashlib.sha256(str(root).encode()).hexdigest()[:16]}"
        )
        provisional = FieldPreview(
            candidate_token="pending",
            source_id=source_id,
            folder_id=folder_id,
            existing_manifest=existing,
            registration_only=registration_only,
            fields=fields,
            registered_fields=registered_fields,
            conflicts=conflicts,
            template_changes=[
                (
                    "Register the existing Source and all portable Fields on this host; "
                    "do not rewrite .scholar-workflow/fields.yml"
                    if registration_only else (
                        "Append only the selected Field to .scholar-workflow/fields.yml"
                        if existing else "Create .scholar-workflow/fields.yml with the selected Field only"
                    )
                )
            ],
            ignored_files=ignored,
            unmapped_markdown=unmapped,
            legacy_link_changes=self._legacy_link_changes(root),
            manifest_base_hash=manifest_hash,
            registry_base_hash=registry_hash,
        )
        token = self.candidates.issue(
            root,
            provisional,
            root_identity=root_identity,
            content_base_hash=content_base_hash,
        )
        return self.candidates.peek(token).preview

    @staticmethod
    def _field_roots_overlap(first: str, second: str) -> bool:
        return _field_roots_overlap(first, second)

    @staticmethod
    def _registered_root_conflicts(
        root: Path,
        source_id: str,
        document: KnowledgeSourceRegistryDocument,
    ) -> list[str]:
        folders = {folder.folder_id: folder for folder in document.folders}
        conflicts: list[str] = []
        for source in document.sources:
            folder = folders[source.folder_id]
            try:
                registered_root = folder.root.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                raise FieldRegistryError("registered Source folder is invalid") from exc
            if source.source_id == source_id and registered_root == root:
                continue
            if (
                registered_root == root
                or registered_root in root.parents
                or root in registered_root.parents
            ):
                conflicts.append(
                    f"Selected folder overlaps registered Source {source.source_id}"
                )
        return conflicts

    def confirm(self, token: str, field_id: str) -> FieldManifest:
        candidate = self.candidates.peek(token)
        preview = candidate.preview
        if preview.registration_only:
            raise FieldRegistryError("Existing Source requires explicit Source registration")
        selected = next((field for field in preview.fields if field.field_id == field_id), None)
        if selected is None:
            raise FieldRegistryError("Field candidate is not in the preview")
        with self._write_lock:
            candidate = self.candidates.consume(token)
            root = self._validate_candidate(candidate)
            previous_manifest = self._manifest_bytes(root)
            fields = [*preview.registered_fields, selected]
            manifest = FieldManifest(source_id=preview.source_id, fields=fields)
            self._validate_manifest_paths(root, manifest)
            registration = self._planned_registration(root, manifest, preview.folder_id)
            payload = yaml.safe_dump(
                manifest.model_dump(mode="json"),
                allow_unicode=True,
                sort_keys=False,
            ).encode()
            payload_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
            try:
                self._write_manifest_cas(
                    root,
                    payload,
                    preview.manifest_base_hash,
                    expected_root_identity=candidate.root_identity,
                    expected_content_hash=candidate.content_base_hash,
                )
                self.registry.save(
                    registration,
                    expected_revision=preview.registry_base_hash,
                )
            except FieldRegistryCommitUncertain:
                raise
            except Exception as exc:
                if self._manifest_hash(root) != payload_hash:
                    raise
                try:
                    self._restore_manifest(
                        root,
                        previous_manifest,
                        payload_hash,
                    )
                except Exception as rollback_exc:
                    raise FieldRegistryError(
                        "Field initialization failed and manifest rollback failed"
                    ) from rollback_exc
                raise FieldRegistryError("Field initialization failed; Field was rolled back") from exc
            return manifest

    def confirm_source(self, token: str, source_id: str) -> FieldManifest:
        candidate = self.candidates.peek(token)
        preview = candidate.preview
        if not preview.registration_only or source_id != preview.source_id:
            raise FieldRegistryError("Source registration is not in the preview")
        with self._write_lock:
            candidate = self.candidates.consume(token)
            root = self._validate_candidate(candidate)
            manifest = self._load_manifest(root)
            if manifest.source_id != source_id or manifest.fields != preview.registered_fields:
                raise FieldRegistryError("Existing Source manifest changed after preview")
            registration = self._planned_registration(root, manifest, preview.folder_id)
            self.registry.save(registration, expected_revision=preview.registry_base_hash)
            return manifest

    def _validate_candidate(self, candidate: _Candidate) -> Path:
        preview = candidate.preview
        root = self._trusted_root(candidate.root)
        if preview.conflicts:
            raise FieldRegistryError("Field preview has unresolved conflicts")
        if self._root_identity(root) != candidate.root_identity:
            raise FieldRegistryError("Selected folder changed after preview")
        if self._preview_content_hash(root) != candidate.content_base_hash:
            raise FieldRegistryError("Selected folder content changed after preview")
        if self._manifest_hash(root) != preview.manifest_base_hash:
            raise FieldRegistryError("Field manifest changed after preview")
        if self.registry.revision() != preview.registry_base_hash:
            raise FieldRegistryError("source registry changed after preview")
        return root

    @staticmethod
    def _trusted_root(selected_root: Path) -> Path:
        path = Path(selected_root).expanduser()
        if not path.is_absolute() or path.is_symlink():
            raise FieldRegistryError("selected folder must be an absolute non-symlink directory")
        try:
            root = path.resolve(strict=True)
        except OSError as exc:
            raise FieldRegistryError("selected folder is unavailable") from exc
        if not root.is_dir() or root == Path(root.anchor):
            raise FieldRegistryError("selected folder is not a safe knowledge root")
        return root

    @staticmethod
    def _root_identity(root: Path) -> tuple[int, int, int]:
        try:
            metadata = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise FieldRegistryError("selected folder is unavailable") from exc
        if not stat.S_ISDIR(metadata.st_mode):
            raise FieldRegistryError("selected folder is no longer a real directory")
        return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)

    @staticmethod
    def _preview_content_hash(root: Path) -> str:
        """Bind a candidate to the names and bytes that informed its preview."""
        digest = hashlib.sha256(b"scholar-field-preview-v1\0")
        obsidian = root / ".obsidian"
        digest.update(b"obsidian\0")
        digest.update(b"1" if obsidian.is_dir() and not obsidian.is_symlink() else b"0")
        for path in sorted(root.rglob("*.md")):
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if any(part in _IGNORED_NAMES for part in relative.parts):
                continue
            digest.update(b"\0path\0")
            digest.update(relative.as_posix().encode("utf-8"))
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FieldRegistryError("selected folder changed during preview") from exc
            digest.update(f"\0mode={stat.S_IFMT(metadata.st_mode)}\0".encode())
            if stat.S_ISLNK(metadata.st_mode):
                digest.update(b"symlink")
                continue
            if not stat.S_ISREG(metadata.st_mode):
                continue
            try:
                encoded = path.read_bytes()
            except OSError as exc:
                raise FieldRegistryError("selected Markdown is not readable") from exc
            digest.update(hashlib.sha256(encoded).digest())
        return "sha256:" + digest.hexdigest()

    @staticmethod
    def _manifest_bytes(root: Path) -> bytes | None:
        try:
            root_fd = _open_directory_chain(root)
        except OSError as exc:
            raise FieldRegistryError(
                "Field root is not a trusted real directory"
            ) from exc
        state_fd: int | None = None
        try:
            try:
                metadata = os.stat(
                    ".scholar-workflow",
                    dir_fd=root_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return None
            if not stat.S_ISDIR(metadata.st_mode):
                raise FieldRegistryError(
                    "Field state directory is not a trusted real directory"
                )
            state_fd = os.open(".scholar-workflow", _DIRECTORY_FLAGS, dir_fd=root_fd)
            try:
                content, _metadata = _read_regular_at(
                    state_fd,
                    "fields.yml",
                    limit=_MAX_FIELD_DOCUMENT_BYTES,
                )
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise FieldRegistryError(
                    "Field manifest is not a trusted regular file"
                ) from exc
            return content
        finally:
            if state_fd is not None:
                os.close(state_fd)
            os.close(root_fd)

    @classmethod
    def _manifest_hash(cls, root: Path) -> str:
        content = cls._manifest_bytes(root)
        if content is None:
            return "absent"
        return "sha256:" + hashlib.sha256(content).hexdigest()

    @classmethod
    def _load_manifest(cls, root: Path) -> FieldManifest:
        try:
            content = cls._manifest_bytes(root)
            if content is None:
                raise FieldRegistryError("Field manifest is missing")
            payload = yaml.safe_load(content.decode("utf-8"))
            return FieldManifest.model_validate(payload)
        except FieldRegistryError:
            raise
        except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            raise FieldRegistryError("Field manifest is invalid") from exc

    @classmethod
    def _write_manifest_cas(
        cls,
        root: Path,
        payload: bytes,
        expected_hash: str,
        *,
        expected_root_identity: tuple[int, int, int] | None = None,
        expected_content_hash: str | None = None,
    ) -> None:
        if len(payload) > _MAX_FIELD_DOCUMENT_BYTES:
            raise FieldRegistryError("Field manifest exceeds the size limit")
        try:
            root_fd = _open_directory_chain(root)
        except OSError as exc:
            raise FieldRegistryError("selected folder is no longer trusted") from exc
        state_fd: int | None = None
        state_created = False
        temporary_name = f".fields.{secrets.token_hex(8)}.tmp"
        try:
            fcntl.flock(root_fd, fcntl.LOCK_EX)

            def check_candidate() -> None:
                if expected_root_identity is not None:
                    opened = os.fstat(root_fd)
                    opened_identity = (
                        opened.st_dev,
                        opened.st_ino,
                        stat.S_IFMT(opened.st_mode),
                    )
                    if (
                        opened_identity != expected_root_identity
                        or cls._root_identity(root) != expected_root_identity
                    ):
                        raise FieldRegistryError("Selected folder changed after preview")
                if (
                    expected_content_hash is not None
                    and cls._preview_content_hash(root) != expected_content_hash
                ):
                    raise FieldRegistryError("Selected folder content changed after preview")

            check_candidate()
            if cls._manifest_hash(root) != expected_hash:
                raise FieldRegistryError("Field manifest changed after preview")
            try:
                state_fd = os.open(".scholar-workflow", _DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                if expected_hash != "absent":
                    raise FieldRegistryError("Field manifest changed after preview") from None
                try:
                    os.mkdir(".scholar-workflow", 0o700, dir_fd=root_fd)
                    state_created = True
                except FileExistsError:
                    pass
                state_fd = os.open(".scholar-workflow", _DIRECTORY_FLAGS, dir_fd=root_fd)

            def check_state_binding() -> None:
                assert state_fd is not None
                current_fd = os.open(".scholar-workflow", _DIRECTORY_FLAGS, dir_fd=root_fd)
                try:
                    opened = os.fstat(state_fd)
                    current = os.fstat(current_fd)
                    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                        raise FieldRegistryError("Field state directory changed during save")
                finally:
                    os.close(current_fd)

            check_state_binding()
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
                dir_fd=state_fd,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            check_candidate()
            if cls._manifest_hash(root) != expected_hash:
                raise FieldRegistryError("Field manifest changed after preview")
            check_state_binding()
            if expected_hash == "absent":
                os.link(
                    temporary_name,
                    "fields.yml",
                    src_dir_fd=state_fd,
                    dst_dir_fd=state_fd,
                    follow_symlinks=False,
                )
            else:
                os.replace(
                    temporary_name,
                    "fields.yml",
                    src_dir_fd=state_fd,
                    dst_dir_fd=state_fd,
                )
            check_state_binding()
            if cls._manifest_hash(root) != "sha256:" + hashlib.sha256(payload).hexdigest():
                raise FieldRegistryError("Field manifest is not visible in the selected folder")
            os.fsync(state_fd)
        except FieldRegistryError:
            raise
        except OSError as exc:
            raise FieldRegistryError(
                "Field manifest could not be saved in a trusted state directory"
            ) from exc
        finally:
            if state_fd is not None:
                try:
                    os.unlink(temporary_name, dir_fd=state_fd)
                except OSError:
                    pass
                os.close(state_fd)
            if state_created:
                try:
                    os.rmdir(".scholar-workflow", dir_fd=root_fd)
                except OSError:
                    pass
            try:
                fcntl.flock(root_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(root_fd)

    @classmethod
    def _restore_manifest(
        cls,
        root: Path,
        previous: bytes | None,
        expected_hash: str,
    ) -> None:
        if previous is not None:
            cls._write_manifest_cas(root, previous, expected_hash)
            return
        try:
            root_fd = _open_directory_chain(root)
            try:
                fcntl.flock(root_fd, fcntl.LOCK_EX)
                if cls._manifest_hash(root) != expected_hash:
                    raise FieldRegistryError("Field manifest changed before rollback")
                state_fd = os.open(".scholar-workflow", _DIRECTORY_FLAGS, dir_fd=root_fd)
                try:
                    os.unlink("fields.yml", dir_fd=state_fd)
                    os.fsync(state_fd)
                finally:
                    os.close(state_fd)
                try:
                    os.rmdir(".scholar-workflow", dir_fd=root_fd)
                except OSError:
                    pass
            finally:
                fcntl.flock(root_fd, fcntl.LOCK_UN)
                os.close(root_fd)
        except OSError as exc:
            raise FieldRegistryError("Field manifest rollback failed") from exc

    @classmethod
    def _validate_manifest_paths(cls, root: Path, manifest: FieldManifest) -> None:
        for field in manifest.fields:
            cls._validate_document_path(root, field, field.home)
            for group in field.navigation:
                for item in group.items:
                    cls._validate_document_path(root, field, item)

    @staticmethod
    def _document_parts(field: FieldDefinition, relative: str) -> tuple[str, ...]:
        root_parts = (
            ()
            if field.relative_root == "."
            else PurePosixPath(field.relative_root).parts
        )
        return (*root_parts, *PurePosixPath(relative).parts)

    @classmethod
    def _validate_document_path(
        cls,
        root: Path,
        field: FieldDefinition,
        relative: str,
    ) -> None:
        parts = cls._document_parts(field, relative)
        if not parts:
            raise FieldRegistryError("Field document path is empty")
        try:
            parent_fd = _open_directory_chain(root, parts[:-1])
            try:
                descriptor = os.open(parts[-1], _READ_FLAGS, dir_fd=parent_fd)
                try:
                    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                        raise FieldRegistryError("Field document is not a regular file")
                finally:
                    os.close(descriptor)
            finally:
                os.close(parent_fd)
        except FieldRegistryError:
            raise
        except OSError as exc:
            raise FieldRegistryError(f"Field path is unavailable: {relative}") from exc

    @staticmethod
    def _resolve_inside(root: Path, relative: str) -> Path:
        parts = () if relative == "." else PurePosixPath(relative).parts
        target = root if not parts else root.joinpath(*parts)
        current = root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise FieldRegistryError("Field path crosses a symbolic link")
        try:
            resolved = target.resolve(strict=True)
        except OSError as exc:
            raise FieldRegistryError(f"Field path is unavailable: {relative}") from exc
        if resolved != root and root not in resolved.parents:
            raise FieldRegistryError("Field path escaped its registered root")
        return resolved

    @classmethod
    def _infer_preview(
        cls,
        root: Path,
    ) -> tuple[list[FieldDefinition], list[str], list[str]]:
        if (root / ".obsidian").is_dir() and not (root / ".obsidian").is_symlink():
            directories = [
                entry
                for entry in sorted(root.iterdir(), key=lambda item: item.name.casefold())
                if entry.is_dir()
                and not entry.is_symlink()
                and entry.name not in _IGNORED_NAMES
            ]
            candidates = [
                directory for directory in directories if list(directory.rglob("*.md"))
            ]
        else:
            # A selected subdirectory is one Field, regardless of its internal
            # navigation folders.  Public categories come only from its manifest.
            candidates = [root] if list(root.rglob("*.md")) else []
        fields: list[FieldDefinition] = []
        mapped: set[Path] = set()
        for candidate in candidates:
            markdown = [
                path for path in sorted(candidate.rglob("*.md"))
                if path.is_file() and not path.is_symlink()
                and not any(part in _IGNORED_NAMES for part in path.relative_to(root).parts)
            ]
            if not markdown:
                continue
            home = next(
                (candidate / name for name in _HOME_NAMES if (candidate / name).is_file()),
                markdown[0],
            )
            relative_root = "." if candidate == root else candidate.relative_to(root).as_posix()
            home_relative = home.relative_to(candidate).as_posix()
            remaining = [
                path.relative_to(candidate).as_posix()
                for path in markdown
                if path != home
            ]
            groups = [FieldNavigationGroup(label="入口", items=[home_relative])]
            if remaining:
                groups.append(FieldNavigationGroup(label="文档", items=remaining))
            fields.append(
                FieldDefinition(
                    field_id=str(uuid.uuid4()),
                    title=candidate.name,
                    relative_root=relative_root,
                    home=home_relative,
                    navigation=groups,
                )
            )
            mapped.update(markdown)
        all_markdown = {
            path for path in root.rglob("*.md")
            if path.is_file() and not path.is_symlink()
            and not any(part in _IGNORED_NAMES for part in path.relative_to(root).parts)
        }
        unmapped = sorted(path.relative_to(root).as_posix() for path in all_markdown - mapped)
        ignored = sorted(
            entry.name for entry in root.iterdir()
            if entry.name.startswith(".") and entry.name not in {".", ".."}
        )
        return fields, ignored, unmapped

    @staticmethod
    def _legacy_link_changes(root: Path) -> list[LegacyLinkChange]:
        """Describe stable-URI replacements without mutating selected Markdown."""
        changes: list[LegacyLinkChange] = []
        for path in sorted(root.rglob("*.md")):
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if (
                not path.is_file()
                or path.is_symlink()
                or any(part in _IGNORED_NAMES for part in relative.parts)
            ):
                continue
            try:
                encoded = path.read_bytes()
            except OSError:
                continue
            if len(encoded) > _MAX_FIELD_DOCUMENT_BYTES:
                continue
            try:
                content = encoded.decode("utf-8")
            except UnicodeDecodeError:
                continue
            counts: dict[str, int] = {}
            for match in _LEGACY_PAPER_LINK.finditer(content):
                key = match.group("attachment")
                counts[key] = counts.get(key, 0) + 1
            for key, count in sorted(counts.items()):
                changes.append(
                    LegacyLinkChange(
                        relative_path=relative.as_posix(),
                        attachment_key=key,
                        replacement=f"zotero://open-pdf/library/items/{key}",
                        occurrences=count,
                    )
                )
        return changes

    def _planned_registration(
        self,
        root: Path,
        manifest: FieldManifest,
        folder_id: str,
    ) -> KnowledgeSourceRegistryDocument:
        document = self.registry.load_document()
        conflicts = self._registered_root_conflicts(root, manifest.source_id, document)
        if conflicts:
            raise FieldRegistryError(conflicts[0])
        folders = list(document.folders)
        sources = list(document.sources)
        folder = next((row for row in folders if row.folder_id == folder_id), None)
        if folder is None:
            folders.append(FolderRegistration(
                folder_id=folder_id,
                root=root,
                capabilities=["read", "write"],
            ))
        elif folder.root != root or not folder.enabled or not {"read", "write"}.issubset(
            folder.capabilities
        ):
            raise FieldRegistryError("registered folder conflicts with the selected Source")
        source = next((row for row in sources if row.source_id == manifest.source_id), None)
        if source is None:
            sources.append(KnowledgeSourceRegistration(
                source_id=manifest.source_id,
                folder_id=folder_id,
                capabilities=["read", "write"],
            ))
        elif source.folder_id != folder_id or not source.enabled or not {
            "read", "write"
        }.issubset(source.capabilities):
            raise FieldRegistryError("registered Source conflicts with the Field manifest")
        return KnowledgeSourceRegistryDocument(folders=folders, sources=sources)

    def list_fields(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        document = self.registry.load_document()
        for source in document.sources:
            if not source.enabled:
                continue
            try:
                root = self.registry.resolve(source.source_id, capability="read")
                manifest = self._load_manifest(root)
                self._validate_manifest_paths(root, manifest)
            except FieldRegistryError as exc:
                result.append(
                    {
                        "source_id": source.source_id,
                        "available": False,
                        "detail": str(exc),
                    }
                )
                continue
            for field in manifest.fields:
                result.append(
                    {
                        "source_id": source.source_id,
                        "field_id": field.field_id,
                        "title": field.title,
                        "home": field.home,
                        "relative_root": field.relative_root,
                        "navigation": [
                            group.model_dump(mode="json") for group in field.navigation
                        ],
                        "available": True,
                    }
                )
        return result

    def _resolve_field(
        self,
        field_id: str,
        *,
        capability: str,
    ) -> tuple[Path, FieldDefinition]:
        document = self.registry.load_document()
        for source in document.sources:
            if not source.enabled:
                continue
            try:
                root = self.registry.resolve(source.source_id, capability=capability)
                manifest = self._load_manifest(root)
            except FieldRegistryError:
                continue
            field = next((row for row in manifest.fields if row.field_id == field_id), None)
            if field is not None:
                try:
                    parts = (
                        ()
                        if field.relative_root == "."
                        else PurePosixPath(field.relative_root).parts
                    )
                    field_fd = _open_directory_chain(root, parts)
                except OSError as exc:
                    raise FieldRegistryError("Field root is unavailable or unsafe") from exc
                else:
                    os.close(field_fd)
                return root, field
        raise FieldRegistryError("Field is unknown, disabled, or lacks the requested capability")

    @contextmanager
    def _field_write_guard(self, root: Path) -> Iterator[None]:
        """Serialize CAS writes in-process and across managed Hub processes."""
        with self._write_lock:
            state_fd: int | None = None
            lock_fd: int | None = None
            try:
                state_fd = _open_directory_chain(root, (".scholar-workflow",))
                lock_fd = os.open(
                    ".field-writes.lock",
                    os.O_RDWR
                    | os.O_CREAT
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=state_fd,
                )
            except OSError as exc:
                if state_fd is not None:
                    os.close(state_fd)
                raise FieldRegistryError("Field write lock is unavailable or unsafe") from exc
            try:
                assert lock_fd is not None
                assert state_fd is not None
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise FieldRegistryError("Field write lock is not a regular file")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                yield
            except OSError as exc:
                raise FieldRegistryError("Field write lock failed") from exc
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(lock_fd)
                os.close(state_fd)

    def read_document(self, field_id: str, relative_path: str) -> dict[str, str]:
        """Read one manifest-owned Markdown document without exposing its host path."""
        root, field = self._resolve_field(field_id, capability="read")
        normalized = _safe_relative(relative_path)
        allowed = {field.home}
        allowed.update(item for group in field.navigation for item in group.items)
        if normalized not in allowed:
            raise FieldRegistryError("Document is not declared by the Field manifest")
        if PurePosixPath(normalized).suffix.casefold() != ".md":
            raise FieldRegistryError("Field document is not readable Markdown")
        parts = self._document_parts(field, normalized)
        try:
            parent_fd = _open_directory_chain(root, parts[:-1])
            try:
                encoded, _metadata = _read_regular_at(
                    parent_fd,
                    parts[-1],
                    limit=_MAX_FIELD_DOCUMENT_BYTES,
                )
            finally:
                os.close(parent_fd)
            content = encoded.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise FieldRegistryError("Field document is not readable UTF-8") from exc
        revision = "sha256:" + hashlib.sha256(encoded).hexdigest()
        return {"content": content, "revision": revision}

    def write_document(
        self,
        field_id: str,
        relative_path: str,
        *,
        content: str,
        base_revision: str,
    ) -> dict[str, str]:
        """CAS-write one declared Markdown document inside a registered Source."""
        if not isinstance(content, str) or "\x00" in content:
            raise FieldRegistryError("Field content must be UTF-8 text without NUL bytes")
        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_FIELD_DOCUMENT_BYTES:
            raise FieldRegistryError("Field document exceeds the inline size limit")
        root, field = self._resolve_field(field_id, capability="write")
        normalized = _safe_relative(relative_path)
        allowed = {field.home}
        allowed.update(item for group in field.navigation for item in group.items)
        if normalized not in allowed:
            raise FieldRegistryError("Document is not declared by the Field manifest")
        if PurePosixPath(normalized).suffix.casefold() != ".md":
            raise FieldRegistryError("Field document is not writable Markdown")
        parts = self._document_parts(field, normalized)
        temporary_name = f".{parts[-1]}.{secrets.token_hex(8)}.tmp"
        with self._field_write_guard(root):
            try:
                parent_fd = _open_directory_chain(root, parts[:-1])
            except OSError as exc:
                raise FieldRegistryError("Field document parent is unavailable or unsafe") from exc
            try:
                try:
                    current, current_metadata = _read_regular_at(
                        parent_fd,
                        parts[-1],
                        limit=_MAX_FIELD_DOCUMENT_BYTES,
                    )
                except OSError as exc:
                    raise FieldRegistryError("Field document could not be read safely") from exc
                current_revision = "sha256:" + hashlib.sha256(current).hexdigest()
                if base_revision != current_revision:
                    raise FieldRegistryError("Field document changed after it was loaded")
                descriptor = os.open(
                    temporary_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    stat.S_IMODE(current_metadata.st_mode),
                    dir_fd=parent_fd,
                )
                try:
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(encoded)
                        handle.flush()
                        os.fsync(handle.fileno())
                    latest, latest_metadata = _read_regular_at(
                        parent_fd,
                        parts[-1],
                        limit=_MAX_FIELD_DOCUMENT_BYTES,
                    )
                    if (
                        latest != current
                        or latest_metadata.st_dev != current_metadata.st_dev
                        or latest_metadata.st_ino != current_metadata.st_ino
                    ):
                        raise FieldRegistryError("Field document changed after it was loaded")
                    check_fd = _open_directory_chain(root, parts[:-1])
                    try:
                        verified_parent = os.fstat(check_fd)
                        opened_parent = os.fstat(parent_fd)
                        if (
                            verified_parent.st_dev != opened_parent.st_dev
                            or verified_parent.st_ino != opened_parent.st_ino
                        ):
                            raise FieldRegistryError(
                                "Field document parent changed during save"
                            )
                    finally:
                        os.close(check_fd)
                    os.replace(
                        temporary_name,
                        parts[-1],
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    os.fsync(parent_fd)
                finally:
                    try:
                        os.unlink(temporary_name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
            finally:
                os.close(parent_fd)
        revision = "sha256:" + hashlib.sha256(encoded).hexdigest()
        return {"content": content, "revision": revision}


def read_obsidian_version(app_path: Path = Path("/Applications/Obsidian.app")) -> str | None:
    """Read the installed app version without launching or upgrading Obsidian."""
    info = app_path / "Contents" / "Info.plist"
    try:
        with info.open("rb") as handle:
            payload = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return None
    value = payload.get("CFBundleShortVersionString")
    return value if isinstance(value, str) and value else None


__all__ = [
    "FieldCandidateExpired",
    "FieldCandidateStore",
    "FieldDefinition",
    "FieldManifest",
    "FieldPreview",
    "FieldRegistryCommitUncertain",
    "FieldRegistryError",
    "FieldService",
    "FolderRegistration",
    "KnowledgeSourceRegistration",
    "KnowledgeSourceRegistry",
    "KnowledgeSourceRegistryDocument",
    "SystemFolderPicker",
    "read_obsidian_version",
]
