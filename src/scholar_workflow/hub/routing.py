"""Public v3 routing contracts: destinations route; targets authorize.

Execution targets contain no host path.  Their ``registered_root_id`` is
resolved through an explicit project or knowledge-source registry at the last
possible moment.  A cmux destination is deliberately absent from that lookup:
choosing another window must never change cwd authorization.
"""
from __future__ import annotations

import json
import fcntl
import hashlib
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from scholar_workflow.hub.directory import EntityRef, ProjectRegistry, RegistryError
from scholar_workflow.knowledge.fields import FieldRegistryError, FieldService, KnowledgeSourceRegistry, _open_directory_chain
from scholar_workflow.knowledge.catalog_models import HubModel

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
_MAX_BRIEF_BYTES = 8 * 1024


class ExecutionTargetError(RuntimeError):
    """An execution target is unknown, unavailable, or insufficiently trusted."""


class ExecutionTarget(HubModel):
    target_id: str
    kind: Literal["project", "vault", "folder"]
    registered_root_id: str
    capabilities: list[str] = Field(default_factory=list)
    source_id: str | None = None
    field_id: str | None = None

    @field_validator("target_id", "registered_root_id")
    @classmethod
    def _identifier(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("execution target identifiers must be portable")
        return value

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(
            not _CAPABILITY.fullmatch(row) for row in values
        ):
            raise ValueError("invalid or duplicate execution target capability")
        return values

    @field_validator("source_id", "field_id")
    @classmethod
    def _optional_ids(cls, value: str | None) -> str | None:
        if value is not None and not _ID.fullmatch(value):
            raise ValueError("execution target context identifiers must be portable")
        return value

    @model_validator(mode="after")
    def _field_identity(self) -> ExecutionTarget:
        if self.field_id is not None and (self.kind != "vault" or self.source_id is None):
            raise ValueError("Field execution targets need a Vault source identity")
        return self


class ExecutionTargetRegistryDocument(HubModel):
    """Host-local target aliases; filesystem paths stay in root registries."""

    schema_version: int = 1
    targets: list[ExecutionTarget] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported execution target registry schema")
        return value

    @model_validator(mode="after")
    def _unique_targets(self) -> ExecutionTargetRegistryDocument:
        identifiers = [target.target_id for target in self.targets]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate execution target ID")
        return self


@dataclass(frozen=True)
class ResolvedExecutionTarget:
    """Server-only resolution result; never serialize ``cwd`` to a client."""

    target: ExecutionTarget
    cwd: Path
    capability: str


class ExecutionTargetRegistry:
    """Resolve opaque targets through explicit project/folder registrations."""

    def __init__(
        self,
        path: Path,
        *,
        project_registry: ProjectRegistry,
        source_registry: KnowledgeSourceRegistry,
    ) -> None:
        self.path = Path(path)
        self._projects = project_registry
        self._sources = source_registry

    @property
    def project_registry_path(self) -> Path:
        return self._projects.path

    @property
    def source_registry_path(self) -> Path:
        return self._sources.path

    def load(self) -> ExecutionTargetRegistryDocument:
        if not self.path.exists():
            return ExecutionTargetRegistryDocument()
        if self.path.is_symlink() or not self.path.is_file():
            raise ExecutionTargetError(
                "execution target registry must be a regular non-symlink file"
            )
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return ExecutionTargetRegistryDocument.model_validate(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ExecutionTargetError(f"invalid execution target registry: {exc}") from None

    def revision(self) -> str:
        if self.path.is_symlink():
            raise ExecutionTargetError("execution target registry cannot use a symlink")
        try:
            content = self.path.read_bytes()
        except FileNotFoundError:
            return "absent"
        return "sha256:" + hashlib.sha256(content).hexdigest()

    def save(
        self, document: ExecutionTargetRegistryDocument, *, expected_revision: str | None = None,
    ) -> None:
        """Atomically save explicit aliases without discovering host paths."""

        checked = ExecutionTargetRegistryDocument.model_validate(document)
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir() or self.path.is_symlink():
            raise ExecutionTargetError("execution target registry path cannot use a symlink")
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        lock_fd = os.open(lock_path, flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise ExecutionTargetError("execution target registry lock must be a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if expected_revision is not None and self.revision() != expected_revision:
                raise ExecutionTargetError("execution target registry changed after preview")
            self._save_locked(checked)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _save_locked(self, checked: ExecutionTargetRegistryDocument) -> None:
        parent = self.path.parent
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(checked.model_dump_json(indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, target_id: str) -> ExecutionTarget:
        if not _ID.fullmatch(target_id):
            raise ExecutionTargetError("invalid execution target ID")
        for target in self.load().targets:
            if target.target_id == target_id:
                return target
        raise ExecutionTargetError("unknown execution target")

    def resolve(self, target_id: str, *, capability: str) -> ResolvedExecutionTarget:
        """Resolve cwd from ``registered_root_id`` and never from request data."""

        if not _CAPABILITY.fullmatch(capability):
            raise ExecutionTargetError("invalid execution target capability")
        target = self.get(target_id)
        if capability not in target.capabilities:
            raise ExecutionTargetError(
                f"execution target does not allow capability: {capability}"
            )
        if target.kind == "project":
            try:
                registration = self._projects.resolve(
                    target.registered_root_id,
                    capability=capability,
                )
            except RegistryError as exc:
                raise ExecutionTargetError(str(exc)) from None
            cwd = registration.root
        else:
            cwd = self._resolve_folder(target, capability=capability)
        return ResolvedExecutionTarget(target=target, cwd=cwd, capability=capability)

    def _resolve_folder(self, target: ExecutionTarget, *, capability: str) -> Path:
        try:
            document = self._sources.load_document()
        except FieldRegistryError as exc:
            raise ExecutionTargetError(str(exc)) from None
        folder = next(
            (
                row
                for row in document.folders
                if row.folder_id == target.registered_root_id
            ),
            None,
        )
        if folder is None:
            raise ExecutionTargetError("execution target references an unknown folder")
        if not folder.enabled:
            raise ExecutionTargetError("registered execution folder is disabled")
        authorized = capability in folder.capabilities or (
            capability == "codex" and target.field_id is not None
            and f"codex.field:{target.field_id}" in folder.capabilities
        )
        if not authorized:
            raise ExecutionTargetError(
                f"registered execution folder does not allow {capability}"
            )
        if target.kind == "vault" and not any(
            source.enabled and source.folder_id == folder.folder_id
            and (target.source_id is None or source.source_id == target.source_id)
            for source in document.sources
        ):
            raise ExecutionTargetError(
                "vault execution target has no enabled knowledge source"
            )
        try:
            cwd = folder.root.resolve(strict=True)
        except OSError as exc:
            raise ExecutionTargetError("registered execution folder is unavailable") from exc
        if folder.root.is_symlink() or not cwd.is_dir():
            raise ExecutionTargetError("registered execution folder is not trusted")
        if target.field_id is not None:
            try:
                manifest = FieldService._load_manifest(cwd)
                if manifest.source_id != target.source_id:
                    raise ExecutionTargetError("Field execution target Source identity changed")
                field = next((row for row in manifest.fields if row.field_id == target.field_id), None)
                if field is None:
                    raise ExecutionTargetError("Field execution target is no longer registered")
                parts = () if field.relative_root == "." else tuple(field.relative_root.split("/"))
                descriptor = _open_directory_chain(cwd, parts)
                os.close(descriptor)
                cwd = cwd.joinpath(*parts)
            except (OSError, FieldRegistryError) as exc:
                raise ExecutionTargetError("Field execution folder is unavailable or unsafe") from exc
        return cwd


class OpenAction(HubModel):
    action_id: str
    kind: Literal["web", "pdf", "file", "native-app", "terminal", "codex"]
    entity_ref: EntityRef
    destination_required: bool

    @field_validator("action_id")
    @classmethod
    def _action_id(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("action_id must be an opaque portable identifier")
        return value


class ActionRequest(HubModel):
    """The complete browser-submittable v3 action envelope."""

    action_id: str
    destination_id: str | None = None
    target_id: str | None = None
    brief: str | None = Field(default=None, min_length=1)
    effort: Literal["fast", "standard", "deep"] | None = None

    @field_validator("action_id", "destination_id", "target_id")
    @classmethod
    def _optional_identifier(cls, value: str | None) -> str | None:
        if value is not None and not _ID.fullmatch(value):
            raise ValueError("action request identifiers must be portable")
        return value

    @field_validator("brief")
    @classmethod
    def _brief(cls, value: str | None) -> str | None:
        if value is not None and (
            "\x00" in value
            or value != value.strip()
            or len(value.encode("utf-8")) > _MAX_BRIEF_BYTES
        ):
            raise ValueError("brief must be clean bounded text")
        return value


class TaskActionRequest(ActionRequest):
    """Strict browser envelope for a server-registered task action.

    ``destination_id`` routes the terminal window only. It is intentionally
    excluded from target resolution and cwd authorization.
    """

    target_id: str
    brief: str = Field(min_length=1)
    effort: Literal["fast", "standard", "deep"] = "standard"
    model_profile_id: str | None = None
    reasoning_effort: str | None = None
    entity_refs: list[EntityRef] = Field(default_factory=list, max_length=32)
    idempotency_key: str

    @field_validator("model_profile_id")
    @classmethod
    def _model_profile(cls, value: str | None) -> str | None:
        if value is not None and not _ID.fullmatch(value):
            raise ValueError("model profile must be a registered identifier")
        return value

    @field_validator("reasoning_effort")
    @classmethod
    def _reasoning_effort(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", value):
            raise ValueError("reasoning effort must be a supported named value")
        return value

    @field_validator("entity_refs")
    @classmethod
    def _selected_entities(cls, values: list[EntityRef]) -> list[EntityRef]:
        identities = [(row.provider_id, row.entity_type, row.entity_id) for row in values]
        if len(identities) != len(set(identities)):
            raise ValueError("selected context contains duplicate entities")
        return values

    @field_validator("idempotency_key")
    @classmethod
    def _idempotency_key(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("idempotency_key must be a portable identifier")
        return value


__all__ = [
    "ActionRequest",
    "ExecutionTarget",
    "ExecutionTargetError",
    "ExecutionTargetRegistry",
    "ExecutionTargetRegistryDocument",
    "OpenAction",
    "ResolvedExecutionTarget",
    "TaskActionRequest",
]
