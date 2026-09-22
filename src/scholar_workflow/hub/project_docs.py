"""Safe document operations scoped to an explicitly registered project ``docs/``."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path, PurePosixPath

from ruamel.yaml import YAML

from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload
from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.hub.directory import ProjectRegistry, RegistryError
from scholar_workflow.hub.models import ArtifactFormat

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)^(?:---|\.\.\.)[ \t]*\r?\n",
    re.DOTALL | re.MULTILINE,
)
_MANAGED_COMMENT_RE = re.compile(
    r"<!--\s*(?:sw-analysis-[\s\S]*?|scholar-workflow:(?:start|end))\s*-->",
    re.IGNORECASE,
)
_CLAIM_BLOCK_ID_RE = re.compile(
    r"(?<!\S)\^claim-[a-z0-9][a-z0-9-]{0,63}(?=\s|$)",
    re.IGNORECASE,
)
_CLAIM_BACKLINK_RE = re.compile(
    r"(?m)^[ \t]*↩[ \t]*\[\[[^\]\n]*#\^claim-[^\]\n]+\]\][ \t]*(?:\r?\n|$)",
    re.IGNORECASE,
)
_STANDALONE_WIKILINK_RE = re.compile(
    r"(?m)^[ \t]*\[\[[^\]\n]+\]\][ \t]*(?:\r?\n|$)"
)
MAX_PASTE_BYTES = 256 * 1024


class ProjectDocumentError(RuntimeError):
    """Base error for registered project document operations."""


class ProjectPathError(ProjectDocumentError):
    """A requested path escaped or violated the registered docs root."""


class ProjectDocumentMissingError(ProjectDocumentError):
    """A requested source document does not exist."""


class DocumentCollisionError(ProjectDocumentError):
    """A destination exists; Hub never overwrites or auto-renames it."""


class ProjectConfirmationRequired(ProjectDocumentError):
    """A tracked or modified source requires an explicit per-operation confirmation."""

    def __init__(self, git_state: str, *, path_role: str = "source") -> None:
        self.git_state = git_state
        self.path_role = path_role
        super().__init__(
            f"Git {path_role} path is {git_state} and requires explicit confirmation"
        )


@dataclass(frozen=True)
class DocumentOperationResult:
    project_id: str
    relative_path: str
    sha256: str
    git_state: str

    def as_payload(self) -> dict[str, str]:
        return vars(self)


@dataclass(frozen=True)
class TrashResult:
    project_id: str
    original_path: str
    trash_path: str
    sha256: str
    git_state: str
    deleted_at: str

    def as_payload(self) -> dict[str, str]:
        return vars(self)


class ProjectDocumentService:
    """Copy and recoverably delete files without accepting an absolute client path."""

    def __init__(self, project_registry: ProjectRegistry) -> None:
        self._projects = project_registry

    @contextmanager
    def _project_lock(self, project_root: Path) -> Iterator[int]:
        """Serialize docs mutations across Hub processes without following lock symlinks."""

        lock_directory = project_root / ".scholar-workflow" / "locks"
        self._prepare_directory(project_root, lock_directory)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        try:
            root_fd = os.open(project_root, directory_flags)
            if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
                os.close(root_fd)
                raise ProjectPathError("Registered project root is not a directory")
        except OSError as exc:
            raise ProjectPathError("Registered project root is unsafe") from exc
        try:
            directory_fd = os.open(lock_directory, directory_flags)
        except OSError as exc:
            os.close(root_fd)
            raise ProjectPathError("Project document lock directory is unsafe") from exc
        lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        lock_flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            try:
                lock_fd = os.open("project-docs.lock", lock_flags, 0o600, dir_fd=directory_fd)
            except OSError as exc:
                raise ProjectPathError("Project document lockfile is unsafe") from exc
            try:
                if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                    raise ProjectPathError("Project document lockfile is not regular")
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
                # Keep the verified project directory open for the complete
                # mutation.  All final file operations are relative to this
                # descriptor, so replacing an intermediate pathname with a
                # symlink cannot redirect a write outside the project.
                yield root_fd
            except OSError as exc:
                raise ProjectDocumentError("Project document lock failed") from exc
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(lock_fd)
        finally:
            os.close(directory_fd)
            os.close(root_fd)

    def copy_within(
        self,
        project_id: str,
        source_path: str,
        destination_path: str,
        *,
        confirm_git: bool = False,
    ) -> DocumentOperationResult:
        project, docs = self._docs_root(project_id)
        source = self._safe_path(docs, source_path, must_exist=True)
        destination = self._safe_path(
            docs,
            destination_path,
            must_exist=False,
            prepare_parent=False,
        )
        source_git_state = self._git_state(
            project.root,
            source.relative_to(project.root),
        )
        destination_git_state = self._git_state(
            project.root,
            destination.relative_to(project.root),
        )
        self._require_git_confirmation(
            source_git_state,
            confirm_git,
            path_role="source",
        )
        self._require_git_confirmation(
            destination_git_state,
            confirm_git,
            path_role="destination",
        )
        with self._project_lock(project.root) as project_fd:
            source = self._safe_path(docs, source_path, must_exist=True)
            destination = self._safe_path(
                docs,
                destination_path,
                must_exist=False,
                prepare_parent=False,
            )
            self._prepare_directory(docs, destination.parent)
            digest = self._copy_exclusive(
                project_fd,
                source.relative_to(project.root),
                destination.relative_to(project.root),
            )
        return DocumentOperationResult(
            project_id=project_id,
            relative_path=destination.relative_to(docs).as_posix(),
            sha256=digest,
            git_state=(
                f"source={source_git_state};destination={destination_git_state}"
            ),
        )

    def copy_knowledge_artifact(
        self,
        project_id: str,
        artifact_id: str,
        destination_path: str,
        *,
        catalog_provider: CatalogProvider,
        vault_root: Path,
        confirm_git: bool = False,
    ) -> DocumentOperationResult:
        """Make an independent copy of an explicitly registered human artifact."""
        catalog = catalog_provider.load()
        artifact = next(
            (row for row in catalog.artifacts if row.artifact_id == artifact_id),
            None,
        )
        if artifact is None:
            raise ProjectDocumentMissingError("Unknown knowledge artifact")
        if artifact.format not in {ArtifactFormat.MARKDOWN, ArtifactFormat.CANVAS}:
            raise ProjectPathError("Only human-readable Markdown or Canvas can be copied")
        try:
            source = safe_vault_path(vault_root, artifact.vault_path)
        except (VaultPathError, OSError, ValueError) as exc:
            raise ProjectPathError("Knowledge artifact path was rejected") from exc
        if source.is_symlink() or not source.is_file():
            raise ProjectDocumentMissingError("Knowledge artifact is unavailable")
        project, docs = self._docs_root(project_id)
        destination = self._safe_path(
            docs,
            destination_path,
            must_exist=False,
            prepare_parent=False,
        )
        destination_git_state = self._git_state(
            project.root,
            destination.relative_to(project.root),
        )
        self._require_git_confirmation(
            destination_git_state,
            confirm_git,
            path_role="destination",
        )
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ProjectDocumentMissingError(
                "Knowledge artifact is not readable UTF-8"
            ) from exc
        if artifact.format is ArtifactFormat.CANVAS:
            if destination.suffix != ".canvas":
                raise ProjectPathError("Canvas copies require a .canvas destination")
            rendered = json.dumps(
                _sanitize_canvas(content),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        else:
            rendered = _strip_managed_markdown(content)
        with self._project_lock(project.root) as project_fd:
            destination = self._safe_path(
                docs,
                destination_path,
                must_exist=False,
                prepare_parent=False,
            )
            self._prepare_directory(docs, destination.parent)
            digest = self._write_exclusive(
                project_fd,
                destination.relative_to(project.root),
                rendered.encode("utf-8"),
            )
        return DocumentOperationResult(
            project_id=project_id,
            relative_path=destination.relative_to(docs).as_posix(),
            sha256=digest,
            git_state=f"destination={destination_git_state}",
        )

    def paste_text(
        self,
        project_id: str,
        destination_path: str,
        content: str,
        *,
        confirm_git: bool = False,
    ) -> DocumentOperationResult:
        """Paste bounded UTF-8 text as a new project document without overwrite."""
        if not isinstance(content, str):
            raise ProjectDocumentError("Pasted document content must be text")
        data = content.encode("utf-8")
        if len(data) > MAX_PASTE_BYTES:
            raise ProjectDocumentError("Pasted document content is too large")
        project, docs = self._docs_root(project_id)
        destination = self._safe_path(
            docs,
            destination_path,
            must_exist=False,
            prepare_parent=False,
        )
        destination_git_state = self._git_state(
            project.root,
            destination.relative_to(project.root),
        )
        self._require_git_confirmation(
            destination_git_state,
            confirm_git,
            path_role="destination",
        )
        with self._project_lock(project.root) as project_fd:
            destination = self._safe_path(
                docs,
                destination_path,
                must_exist=False,
                prepare_parent=False,
            )
            self._prepare_directory(docs, destination.parent)
            digest = self._write_exclusive(
                project_fd,
                destination.relative_to(project.root),
                data,
            )
        return DocumentOperationResult(
            project_id=project_id,
            relative_path=destination.relative_to(docs).as_posix(),
            sha256=digest,
            git_state=f"destination={destination_git_state}",
        )

    def trash(
        self,
        project_id: str,
        relative_path: str,
        *,
        confirm_git: bool = False,
        now: datetime | None = None,
    ) -> TrashResult:
        project, docs = self._docs_root(project_id)
        source = self._safe_path(docs, relative_path, must_exist=True)
        git_state = self._git_state(project.root, source.relative_to(project.root))
        self._require_git_confirmation(git_state, confirm_git)
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        with self._project_lock(project.root) as project_fd:
            return self._trash_locked(
                project_id=project_id,
                project_root=project.root,
                docs=docs,
                relative_path=relative_path,
                git_state=git_state,
                timestamp=timestamp,
                project_fd=project_fd,
            )

    def _trash_locked(
        self,
        *,
        project_id: str,
        project_root: Path,
        docs: Path,
        relative_path: str,
        git_state: str,
        timestamp: datetime,
        project_fd: int,
    ) -> TrashResult:
        source = self._safe_path(docs, relative_path, must_exist=True)
        source_relative = source.relative_to(project_root)
        digest = _sha256_file_at_path(project_fd, source_relative)
        stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
        trash_root = project_root / ".scholar-workflow" / "trash" / "docs" / stamp
        self._prepare_directory(project_root, trash_root)
        destination = self._safe_path(
            trash_root,
            relative_path,
            must_exist=False,
        )
        receipt = destination.with_name(destination.name + ".trash.json")
        if receipt.exists() or receipt.is_symlink():
            raise DocumentCollisionError("Trash receipt already exists")
        destination_relative = destination.relative_to(project_root)
        self._move_exclusive(
            project_fd,
            source_relative,
            destination_relative,
            expected_digest=digest,
        )
        deleted_at = timestamp.isoformat().replace("+00:00", "Z")
        metadata = {
            "schema_version": 1,
            "project_id": project_id,
            "original_path": PurePosixPath(relative_path).as_posix(),
            "trash_path": destination.relative_to(project_root).as_posix(),
            "sha256": digest,
            "deleted_at": deleted_at,
            "git_state": git_state,
        }
        try:
            _atomic_json(
                receipt,
                metadata,
                root_fd=project_fd,
                relative_path=receipt.relative_to(project_root),
            )
        except Exception as exc:
            restored = False
            try:
                destination_unchanged = _regular_file_matches_at(
                    project_fd,
                    destination_relative,
                    digest,
                )
                source_empty = not _entry_exists_at(project_fd, source_relative)
                if source_empty and destination_unchanged:
                    self._move_exclusive(
                        project_fd,
                        destination_relative,
                        source_relative,
                        expected_digest=digest,
                    )
                    restored = True
            except (OSError, ProjectDocumentError):
                restored = False
            if restored:
                raise ProjectDocumentError(
                    "Trash receipt failed; original document was restored"
                ) from exc
            raise ProjectDocumentError(
                "Trash receipt failed after move; manual recovery is required"
            ) from exc
        return TrashResult(
            project_id=project_id,
            original_path=metadata["original_path"],
            trash_path=metadata["trash_path"],
            sha256=digest,
            git_state=git_state,
            deleted_at=deleted_at,
        )

    def _docs_root(self, project_id: str):
        try:
            project = self._projects.resolve(project_id, capability="docs")
        except RegistryError as exc:
            raise ProjectPathError(str(exc)) from exc
        docs = project.root / "docs"
        if docs.is_symlink() or not docs.is_dir():
            raise ProjectPathError("Registered project docs root is unavailable")
        resolved = docs.resolve(strict=True)
        if resolved.parent != project.root:
            raise ProjectPathError("Project docs root escaped the registered project")
        return project, resolved

    @staticmethod
    def _safe_path(
        root: Path,
        relative_path: str,
        *,
        must_exist: bool,
        prepare_parent: bool = True,
    ) -> Path:
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
            raise ProjectPathError("Document path must be a non-empty POSIX path")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.split("/")):
            raise ProjectPathError("Document path must stay inside project docs")
        candidate = root.joinpath(*path.parts)
        current = root
        for part in path.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise ProjectPathError("Document path contains a symbolic link")
            if current.exists() and not current.is_dir():
                raise ProjectPathError("Document parent is not a directory")
        if candidate.is_symlink():
            raise ProjectPathError("Document path contains a symbolic link")
        if must_exist:
            if not candidate.is_file():
                raise ProjectDocumentMissingError("Project document is missing")
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as exc:
                raise ProjectDocumentMissingError("Project document is unavailable") from exc
            if not resolved.is_relative_to(root):
                raise ProjectPathError("Document path escaped project docs")
            return resolved
        if candidate.exists():
            raise DocumentCollisionError("Destination already exists")
        if not prepare_parent:
            return candidate
        ProjectDocumentService._prepare_directory(root, candidate.parent)
        try:
            parent = candidate.parent.resolve(strict=True)
        except OSError as exc:
            raise ProjectPathError("Document parent is unavailable") from exc
        if not parent.is_relative_to(root):
            raise ProjectPathError("Document destination escaped project docs")
        return candidate

    @staticmethod
    def _prepare_directory(root: Path, directory: Path) -> None:
        """Create one directory chain without following any existing symlink."""
        try:
            relative = directory.relative_to(root)
        except ValueError as exc:
            raise ProjectPathError("Destination directory escaped its trusted root") from exc
        with _open_root_directory(root) as root_fd, _open_relative_directory(
            root_fd,
            relative.parts,
            create=True,
        ):
            pass

    @staticmethod
    def _copy_exclusive(
        project_fd: int,
        source: Path,
        destination: Path,
    ) -> str:
        return _copy_exclusive_at(project_fd, source, destination)

    @staticmethod
    def _write_exclusive(project_fd: int, destination: Path, data: bytes) -> str:
        return _write_chunks_exclusive_at(
            project_fd,
            destination,
            iter((data,)),
            create_parents=True,
        )

    @staticmethod
    def _move_exclusive(
        project_fd: int,
        source: Path,
        destination: Path,
        *,
        expected_digest: str,
    ) -> None:
        """Move a regular file without any overwrite window.

        The project trash lives on the same filesystem as ``docs``.  An exclusive hard-link
        reservation therefore gives no-replace semantics; only after verifying identity and
        content do we unlink the source name.
        """

        _move_exclusive_at(
            project_fd,
            source,
            destination,
            expected_digest=expected_digest,
        )

    @staticmethod
    def _git_state(project_root: Path, relative_path: Path) -> str:
        git_dir = project_root / ".git"
        if not git_dir.exists():
            return "not-versioned"
        try:
            result = subprocess.run(
                ["/usr/bin/git", "status", "--porcelain=v1", "--", relative_path.as_posix()],
                cwd=project_root,
                shell=False,
                timeout=3,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        if result.returncode != 0:
            return "unknown"
        marker = result.stdout[:2]
        if marker == "??":
            return "untracked"
        if marker.strip():
            return "modified"
        try:
            tracked = subprocess.run(
                [
                    "/usr/bin/git",
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    relative_path.as_posix(),
                ],
                cwd=project_root,
                shell=False,
                timeout=3,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        return "tracked" if tracked.returncode == 0 else "untracked"

    @staticmethod
    def _require_git_confirmation(
        git_state: str,
        confirmed: bool,
        *,
        path_role: str = "source",
    ) -> None:
        if git_state in {"tracked", "modified", "unknown"} and not confirmed:
            raise ProjectConfirmationRequired(git_state, path_role=path_role)


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
_DIRECTORY_FLAGS |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
_READ_FLAGS |= getattr(os, "O_CLOEXEC", 0)


def _relative_parts(relative_path: Path) -> tuple[str, ...]:
    if relative_path.is_absolute() or not relative_path.parts or any(
        part in {"", ".", ".."} for part in relative_path.parts
    ):
        raise ProjectPathError("Document path must stay inside its trusted root")
    return tuple(relative_path.parts)


@contextmanager
def _open_root_directory(root: Path) -> Iterator[int]:
    try:
        descriptor = os.open(root, _DIRECTORY_FLAGS)
    except OSError as exc:
        raise ProjectPathError("Trusted document root is unavailable or unsafe") from exc
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise ProjectPathError("Trusted document root must be a directory")
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _open_relative_directory(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> Iterator[int]:
    """Walk a directory chain with openat semantics and never follow a symlink."""

    if any(part in {"", ".", ".."} or Path(part).name != part for part in parts):
        raise ProjectPathError("Document directory path is unsafe")
    try:
        current_fd = os.dup(root_fd)
    except OSError as exc:
        raise ProjectDocumentError("Could not anchor the trusted document root") from exc
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o755, dir_fd=current_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ProjectDocumentError(
                        "Could not create destination directory"
                    ) from exc
            try:
                next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=current_fd)
            except OSError as exc:
                raise ProjectPathError(
                    "Document directory contains a symbolic link or unsafe entry"
                ) from exc
            try:
                if not stat.S_ISDIR(os.fstat(next_fd).st_mode):
                    raise ProjectPathError("Document parent is not a directory")
            except Exception:
                os.close(next_fd)
                raise
            os.close(current_fd)
            current_fd = next_fd
        yield current_fd
    finally:
        os.close(current_fd)


@contextmanager
def _open_parent_at(
    root_fd: int,
    relative_path: Path,
    *,
    create_parents: bool,
) -> Iterator[tuple[int, str, tuple[str, ...], tuple[int, int]]]:
    parts = _relative_parts(relative_path)
    parent_parts = parts[:-1]
    with _open_relative_directory(
        root_fd,
        parent_parts,
        create=create_parents,
    ) as parent_fd:
        parent_stat = os.fstat(parent_fd)
        yield (
            parent_fd,
            parts[-1],
            parent_parts,
            (parent_stat.st_dev, parent_stat.st_ino),
        )


def _directory_binding_matches(
    root_fd: int,
    parts: tuple[str, ...],
    expected_identity: tuple[int, int],
) -> bool:
    try:
        with _open_relative_directory(root_fd, parts, create=False) as current_fd:
            current = os.fstat(current_fd)
            return (current.st_dev, current.st_ino) == expected_identity
    except (OSError, ProjectDocumentError):
        return False


def _regular_stat_at(parent_fd: int, name: str) -> os.stat_result:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ProjectDocumentError("Document entry is unavailable") from exc
    if not stat.S_ISREG(current.st_mode):
        raise ProjectPathError("Document entry must remain a regular file")
    return current


def _sha256_file_at(parent_fd: int, name: str) -> str:
    try:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_fd)
    except OSError as exc:
        raise ProjectDocumentError("Document file is unavailable") from exc
    digest = hashlib.sha256()
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ProjectPathError("Document entry must remain a regular file")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
    except OSError as exc:
        raise ProjectDocumentError("Document file could not be read") from exc
    finally:
        os.close(descriptor)
    return "sha256:" + digest.hexdigest()


def _sha256_file_at_path(root_fd: int, relative_path: Path) -> str:
    with _open_parent_at(
        root_fd,
        relative_path,
        create_parents=False,
    ) as (parent_fd, name, _parts, _identity):
        return _sha256_file_at(parent_fd, name)


def _entry_exists_at(root_fd: int, relative_path: Path) -> bool:
    with _open_parent_at(
        root_fd,
        relative_path,
        create_parents=False,
    ) as (parent_fd, name, _parts, _identity):
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ProjectDocumentError("Document entry could not be inspected") from exc
        return True


def _regular_file_matches_at(
    root_fd: int,
    relative_path: Path,
    expected_digest: str,
) -> bool:
    try:
        with _open_parent_at(
            root_fd,
            relative_path,
            create_parents=False,
        ) as (parent_fd, name, _parts, _identity):
            _regular_stat_at(parent_fd, name)
            return _sha256_file_at(parent_fd, name) == expected_digest
    except (OSError, ProjectDocumentError):
        return False


def _copy_exclusive_at(
    root_fd: int,
    source: Path,
    destination: Path,
) -> str:
    with _open_parent_at(
        root_fd,
        source,
        create_parents=False,
    ) as (source_parent_fd, source_name, _parts, _identity):
        try:
            source_fd = os.open(source_name, _READ_FLAGS, dir_fd=source_parent_fd)
        except OSError as exc:
            raise ProjectDocumentError("Document source is unavailable") from exc
        try:
            if not stat.S_ISREG(os.fstat(source_fd).st_mode):
                raise ProjectPathError("Document source must remain a regular file")
            with os.fdopen(source_fd, "rb") as reader:
                source_fd = -1
                return _write_chunks_exclusive_at(
                    root_fd,
                    destination,
                    iter(lambda: reader.read(1024 * 1024), b""),
                    create_parents=True,
                )
        except ProjectDocumentError:
            raise
        except OSError as exc:
            raise ProjectDocumentError("Document copy failed") from exc
        finally:
            if source_fd >= 0:
                os.close(source_fd)


def _write_chunks_exclusive_at(
    root_fd: int,
    destination: Path,
    chunks: Iterator[bytes],
    *,
    create_parents: bool,
) -> str:
    with _open_parent_at(
        root_fd,
        destination,
        create_parents=create_parents,
    ) as (parent_fd, name, parent_parts, parent_identity):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise DocumentCollisionError("Destination already exists") from exc
        except OSError as exc:
            raise ProjectDocumentError("Could not create document destination") from exc

        try:
            created_stat = os.fstat(descriptor)
        except OSError as exc:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise ProjectDocumentError(
                "Document destination identity could not be recorded; manual cleanup is required"
            ) from exc
        identity = (created_stat.st_dev, created_stat.st_ino)
        digest = hashlib.sha256()
        written = 0
        try:
            for chunk in chunks:
                if not chunk:
                    continue
                view = memoryview(chunk)
                while view:
                    count = os.write(descriptor, view)
                    if count <= 0:
                        raise OSError("document write made no progress")
                    digest.update(view[:count])
                    written += count
                    view = view[count:]
            os.fsync(descriptor)
            if not _directory_binding_matches(
                root_fd,
                parent_parts,
                parent_identity,
            ):
                raise ProjectPathError(
                    "Document destination parent changed during the write"
                )
        except Exception as exc:
            try:
                os.close(descriptor)
            except OSError:
                pass
            _cleanup_owned_file_at(
                parent_fd,
                name,
                identity=identity,
                expected_digest="sha256:" + digest.hexdigest(),
                expected_size=written,
            )
            if isinstance(exc, ProjectDocumentError):
                raise
            raise ProjectDocumentError("Document copy failed") from exc
        try:
            os.close(descriptor)
        except OSError as exc:
            _cleanup_owned_file_at(
                parent_fd,
                name,
                identity=identity,
                expected_digest="sha256:" + digest.hexdigest(),
                expected_size=written,
            )
            raise ProjectDocumentError("Document copy close failed") from exc
        if not _directory_binding_matches(root_fd, parent_parts, parent_identity):
            _cleanup_owned_file_at(
                parent_fd,
                name,
                identity=identity,
                expected_digest="sha256:" + digest.hexdigest(),
                expected_size=written,
            )
            raise ProjectPathError("Document destination parent changed after the write")
        return "sha256:" + digest.hexdigest()


def _cleanup_owned_file_at(
    parent_fd: int,
    name: str,
    *,
    identity: tuple[int, int],
    expected_digest: str,
    expected_size: int,
) -> bool:
    """Remove only the exact inode and bytes created by the current operation."""

    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(current.st_mode)
            or (current.st_dev, current.st_ino) != identity
            or current.st_size != expected_size
            or _sha256_file_at(parent_fd, name) != expected_digest
        ):
            return False
        os.unlink(name, dir_fd=parent_fd)
        return True
    except (OSError, ProjectDocumentError):
        return False


def _move_exclusive_at(
    root_fd: int,
    source: Path,
    destination: Path,
    *,
    expected_digest: str,
) -> None:
    with _open_parent_at(
        root_fd,
        source,
        create_parents=False,
    ) as (source_parent_fd, source_name, source_parts, source_parent_identity):
        source_stat = _regular_stat_at(source_parent_fd, source_name)
        identity = (source_stat.st_dev, source_stat.st_ino)
        with _open_parent_at(
            root_fd,
            destination,
            create_parents=True,
        ) as (
            destination_parent_fd,
            destination_name,
            destination_parts,
            destination_parent_identity,
        ):
            try:
                os.link(
                    source_name,
                    destination_name,
                    src_dir_fd=source_parent_fd,
                    dst_dir_fd=destination_parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise DocumentCollisionError("Trash destination already exists") from exc
            except OSError as exc:
                raise ProjectDocumentError("Could not reserve trash destination") from exc

            try:
                destination_stat = _regular_stat_at(
                    destination_parent_fd,
                    destination_name,
                )
                source_current = _regular_stat_at(source_parent_fd, source_name)
                if (
                    (destination_stat.st_dev, destination_stat.st_ino) != identity
                    or (source_current.st_dev, source_current.st_ino) != identity
                    or _sha256_file_at(destination_parent_fd, destination_name)
                    != expected_digest
                ):
                    raise ProjectDocumentError("Trash file changed during exclusive move")
                if not _directory_binding_matches(
                    root_fd,
                    source_parts,
                    source_parent_identity,
                ) or not _directory_binding_matches(
                    root_fd,
                    destination_parts,
                    destination_parent_identity,
                ):
                    raise ProjectPathError(
                        "Trash parent changed during the exclusive move"
                    )
                os.unlink(source_name, dir_fd=source_parent_fd)
            except Exception as exc:
                _cleanup_owned_file_at(
                    destination_parent_fd,
                    destination_name,
                    identity=identity,
                    expected_digest=expected_digest,
                    expected_size=source_stat.st_size,
                )
                if isinstance(exc, ProjectDocumentError):
                    raise
                raise ProjectDocumentError(
                    "Trash move failed before source removal"
                ) from exc


def _atomic_json(
    path: Path,
    payload: dict[str, object],
    *,
    root_fd: int | None = None,
    relative_path: Path | None = None,
) -> None:
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if root_fd is not None and relative_path is not None:
        _write_chunks_exclusive_at(
            root_fd,
            relative_path,
            iter((encoded,)),
            create_parents=True,
        )
        return
    # Compatibility path for direct callers; project mutations always pass a
    # trusted root descriptor and a root-relative path.
    with _open_root_directory(path.parent) as parent_fd:
        _write_chunks_exclusive_at(
            parent_fd,
            Path(path.name),
            iter((encoded,)),
            create_parents=False,
        )


def _strip_managed_markdown(content: str) -> str:
    match = _FRONTMATTER_RE.match(content)
    if match is None:
        sanitized = content
    else:
        yaml = YAML(typ="rt")
        try:
            metadata = yaml.load(match.group(1)) or {}
        except Exception as exc:
            raise ProjectDocumentError("Knowledge Markdown frontmatter is invalid") from exc
        if not isinstance(metadata, dict):
            raise ProjectDocumentError("Knowledge Markdown frontmatter must be a mapping")
        for key in list(metadata):
            if str(key).startswith("sw_"):
                del metadata[key]
        body = content[match.end():]
        if not metadata:
            sanitized = body
        else:
            output = StringIO()
            yaml.dump(metadata, output)
            sanitized = f"---\n{output.getvalue()}---\n{body}"
    sanitized = _MANAGED_COMMENT_RE.sub("", sanitized)
    sanitized = _CLAIM_BLOCK_ID_RE.sub("", sanitized)
    return sanitized


def _sanitize_canvas(content: str) -> dict[str, list[dict[str, object]]]:
    try:
        payload = json.loads(
            content,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ProjectDocumentError("Knowledge Canvas is invalid JSON") from exc
    try:
        canvas = validate_canvas_payload(payload)
    except CanvasValidationError as exc:
        raise ProjectDocumentError(f"Knowledge Canvas is invalid: {exc}") from exc

    identity_map: dict[str, str] = {}
    nodes: list[dict[str, object]] = []
    for raw_node in canvas["nodes"]:
        source_id = raw_node.get("id")
        assert isinstance(source_id, str)
        node_type = raw_node.get("type")
        if node_type in {"file", "link"} or "file" in raw_node or "url" in raw_node:
            raise ProjectDocumentError(
                "Canvas file/link nodes cannot be copied without managed relationships"
            )
        if node_type not in {"text", "group"}:
            raise ProjectDocumentError("Knowledge Canvas contains an unsupported node type")
        new_id = _new_canvas_id(set(identity_map.values()))
        identity_map[source_id] = new_id
        node = _drop_managed_fields(raw_node)
        node["id"] = new_id
        text = node.get("text")
        if text is not None:
            if not isinstance(text, str):
                raise ProjectDocumentError("Knowledge Canvas node text must be a string")
            node["text"] = _strip_canvas_managed_text(text)
        nodes.append(node)

    edges: list[dict[str, object]] = []
    edge_ids: set[str] = set()
    source_edge_ids: set[str] = set()
    for raw_edge in canvas["edges"]:
        source_edge_id = raw_edge.get("id")
        from_node = raw_edge.get("fromNode")
        to_node = raw_edge.get("toNode")
        if (
            not isinstance(source_edge_id, str)
            or not source_edge_id
            or source_edge_id in source_edge_ids
            or not isinstance(from_node, str)
            or not isinstance(to_node, str)
            or from_node not in identity_map
            or to_node not in identity_map
        ):
            raise ProjectDocumentError("Knowledge Canvas edge identity is invalid")
        source_edge_ids.add(source_edge_id)
        edge = _drop_managed_fields(raw_edge)
        edge_id = _new_canvas_id(edge_ids)
        edge_ids.add(edge_id)
        edge["id"] = edge_id
        edge["fromNode"] = identity_map[from_node]
        edge["toNode"] = identity_map[to_node]
        edges.append(edge)
    return {"nodes": nodes, "edges": edges}


def _drop_managed_fields(value: dict[str, object]) -> dict[str, object]:
    cleaned: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key.startswith("sw_"):
            continue
        if isinstance(item, dict):
            cleaned[key] = _drop_managed_fields(item)
        elif isinstance(item, list):
            cleaned[key] = [
                _drop_managed_fields(child) if isinstance(child, dict) else child
                for child in item
            ]
        else:
            cleaned[key] = item
    return cleaned


def _strip_canvas_managed_text(text: str) -> str:
    sanitized = _MANAGED_COMMENT_RE.sub("", text)
    sanitized = _CLAIM_BACKLINK_RE.sub("", sanitized)
    sanitized = _CLAIM_BLOCK_ID_RE.sub("", sanitized)
    if "论文解析树" in sanitized or "paper analysis tree" in sanitized.casefold():
        sanitized = _STANDALONE_WIKILINK_RE.sub("", sanitized)
    return sanitized.strip()


def _new_canvas_id(existing: set[str]) -> str:
    for _ in range(32):
        candidate = secrets.token_hex(8)
        if candidate not in existing:
            return candidate
    raise ProjectDocumentError("Could not allocate independent Canvas identity")


__all__ = [
    "MAX_PASTE_BYTES",
    "DocumentCollisionError",
    "DocumentOperationResult",
    "ProjectConfirmationRequired",
    "ProjectDocumentError",
    "ProjectDocumentMissingError",
    "ProjectDocumentService",
    "ProjectPathError",
    "TrashResult",
]
