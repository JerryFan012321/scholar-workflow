"""Safe reads and optimistic writes for Hub-registered Vault artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ruamel.yaml import YAML

from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.hub.models import ArtifactFormat, HubArtifact


MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_WRITE_REQUEST_BYTES = MAX_ARTIFACT_BYTES + 64 * 1024
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n",
    re.DOTALL | re.MULTILINE,
)


class ArtifactContentError(Exception):
    """Base error for the registered-artifact content boundary."""


class UnknownArtifactError(ArtifactContentError):
    """The requested ID is not present in the current HubCatalog."""


class UnsupportedArtifactError(ArtifactContentError):
    """The registered artifact is not an editable Markdown or Canvas file."""


class ArtifactPathRejectedError(ArtifactContentError):
    """The registered path escaped the Vault or contains a symbolic link."""


class ArtifactMissingError(ArtifactContentError):
    """The registered file does not currently exist as a regular file."""


class ArtifactTooLargeError(ArtifactContentError):
    """The content exceeds the bounded Hub editor payload size."""


class ArtifactEncodingError(ArtifactContentError):
    """The artifact content is not valid UTF-8 text."""


class InvalidArtifactContentError(ArtifactContentError):
    """The proposed text violates the artifact format contract."""


class RevisionConflictError(ArtifactContentError):
    """The file changed since the caller read it."""

    def __init__(self, current_revision: str) -> None:
        self.current_revision = current_revision
        super().__init__("Artifact content changed since it was read")


@dataclass(frozen=True)
class ArtifactContent:
    artifact_id: str
    kind: str
    format: str
    vault_path: str
    content: str
    revision: str
    modified_at: float

    def as_payload(self) -> dict[str, str | float]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "format": self.format,
            "vault_path": self.vault_path,
            "content": self.content,
            "revision": self.revision,
            "modified_at": self.modified_at,
        }


class ArtifactContentStore:
    """Read and update existing HubCatalog files without accepting client paths."""

    def __init__(self, vault_root: Path, catalog_provider: CatalogProvider) -> None:
        self._vault_root = Path(vault_root)
        self._catalog_provider = catalog_provider
        self._write_lock = threading.RLock()

    def read(self, artifact_id: str) -> ArtifactContent:
        artifact = self._registered_artifact(artifact_id)
        path = self._existing_path(artifact)
        return self._read_path(artifact, path)

    def write(
        self,
        artifact_id: str,
        *,
        content: str,
        base_revision: str,
    ) -> ArtifactContent:
        artifact = self._registered_artifact(artifact_id)

        with self._write_lock:
            path = self._existing_path(artifact)
            current = self._read_path(artifact, path)
            if current.revision != base_revision:
                raise RevisionConflictError(current.revision)
            prepared = _prepare_write_content(artifact, current.content, content)
            data = _encode_bounded(prepared)
            _validate_format_content(artifact, prepared)
            self._atomic_replace(path, data)
            return self._read_path(artifact, path)

    def _registered_artifact(self, artifact_id: str) -> HubArtifact:
        catalog = self._catalog_provider.load()
        artifact = next(
            (row for row in catalog.artifacts if row.artifact_id == artifact_id),
            None,
        )
        if artifact is None:
            raise UnknownArtifactError(artifact_id)
        if artifact.format not in {ArtifactFormat.MARKDOWN, ArtifactFormat.CANVAS}:
            raise UnsupportedArtifactError(artifact_id)
        expected_suffix = {
            ArtifactFormat.MARKDOWN: ".md",
            ArtifactFormat.CANVAS: ".canvas",
        }[artifact.format]
        if PurePosixPath(artifact.vault_path).suffix.lower() != expected_suffix:
            raise UnsupportedArtifactError(artifact_id)
        return artifact

    def _existing_path(self, artifact: HubArtifact) -> Path:
        root = self._vault_root.resolve()
        raw_path = self._vault_root.joinpath(*PurePosixPath(artifact.vault_path).parts)
        current = self._vault_root
        for part in PurePosixPath(artifact.vault_path).parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactPathRejectedError(artifact.vault_path)
        try:
            path = safe_vault_path(root, artifact.vault_path)
        except VaultPathError as exc:
            raise ArtifactPathRejectedError(artifact.vault_path) from exc
        if raw_path.is_symlink() or not path.exists():
            if raw_path.is_symlink():
                raise ArtifactPathRejectedError(artifact.vault_path)
            raise ArtifactMissingError(artifact.artifact_id)
        try:
            mode = path.stat(follow_symlinks=False).st_mode
        except FileNotFoundError as exc:
            raise ArtifactMissingError(artifact.artifact_id) from exc
        if not stat.S_ISREG(mode):
            raise ArtifactMissingError(artifact.artifact_id)
        return path

    def _read_path(self, artifact: HubArtifact, path: Path) -> ArtifactContent:
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactMissingError(artifact.artifact_id) from exc
        if len(data) > MAX_ARTIFACT_BYTES:
            raise ArtifactTooLargeError(artifact.artifact_id)
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArtifactEncodingError(artifact.artifact_id) from exc
        try:
            modified_at = path.stat(follow_symlinks=False).st_mtime
        except FileNotFoundError as exc:
            raise ArtifactMissingError(artifact.artifact_id) from exc
        return ArtifactContent(
            artifact_id=artifact.artifact_id,
            kind=artifact.kind.value,
            format=artifact.format.value,
            vault_path=artifact.vault_path,
            content=content,
            revision=_content_revision(data),
            modified_at=modified_at,
        )

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        mode = path.stat(follow_symlinks=False).st_mode
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                os.fchmod(handle.fileno(), stat.S_IMODE(mode))
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _content_revision(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _encode_bounded(content: str) -> bytes:
    try:
        data = content.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ArtifactEncodingError("content") from exc
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ArtifactTooLargeError("content")
    return data


def _validate_format_content(artifact: HubArtifact, content: str) -> None:
    if artifact.format != ArtifactFormat.CANVAS:
        return
    try:
        value = json.loads(
            content,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise InvalidArtifactContentError("Canvas content must be valid JSON") from exc
    if not isinstance(value, dict):
        raise InvalidArtifactContentError("Canvas content must be a JSON object")


def _prepare_write_content(
    artifact: HubArtifact,
    current: str,
    proposed: str,
) -> str:
    if artifact.format != ArtifactFormat.MARKDOWN:
        return proposed
    current_fields, _current_match = _managed_markdown_fields(current)
    proposed_fields, _proposed_match = _managed_markdown_fields(proposed)
    if proposed_fields != current_fields:
        raise InvalidArtifactContentError(
            "Hub-owned sw_* frontmatter fields cannot be added, removed, or changed"
        )
    return proposed


def _managed_markdown_fields(content: str) -> tuple[dict[str, object], re.Match | None]:
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return {}, None
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    try:
        frontmatter = yaml.load(match.group(1)) or {}
    except Exception as exc:
        raise InvalidArtifactContentError("Markdown frontmatter is not valid YAML") from exc
    if not isinstance(frontmatter, dict):
        raise InvalidArtifactContentError("Markdown frontmatter must be a YAML mapping")
    return (
        {
            str(key): value
            for key, value in frontmatter.items()
            if isinstance(key, str) and key.startswith("sw_")
        },
        match,
    )


__all__ = [
    "ArtifactContentStore",
    "ArtifactEncodingError",
    "ArtifactMissingError",
    "ArtifactPathRejectedError",
    "ArtifactTooLargeError",
    "InvalidArtifactContentError",
    "MAX_ARTIFACT_BYTES",
    "MAX_WRITE_REQUEST_BYTES",
    "RevisionConflictError",
    "UnknownArtifactError",
    "UnsupportedArtifactError",
]
