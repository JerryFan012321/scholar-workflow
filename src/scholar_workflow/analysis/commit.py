"""Recoverable CAS commit for canonical Markdown, Canvas, and analysis sidecars."""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import stat
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisCommitFile,
    AnalysisCommitReceipt,
    AnalysisCommitRequest,
    KnowledgeArtifactChange,
    KnowledgeChangeSet,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import create_baseline


class AnalysisCommitError(ValueError):
    """Base error for an analysis commit that made no unsafe assumptions."""


class AnalysisCommitConflict(AnalysisCommitError):
    """A base hash, identity, or human edit prevents the commit."""


class AnalysisCommitSafetyError(AnalysisCommitError):
    """A path or filesystem shape violates the fail-closed boundary."""


class AnalysisCommitPartialError(AnalysisCommitError):
    """Conditional rollback could not safely restore every target."""


FaultInjector = Callable[[str], None]
FileIdentity = dict[str, int]
DirectoryIdentity = tuple[int, int]
_IDENTITY_KEYS = ("device", "inode", "size", "mtime_ns", "ctime_ns")


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _request_fingerprint(request: AnalysisCommitRequest) -> str:
    payload = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _anchored_directory_path(
    path: Path,
    *,
    label: str,
    create: bool,
) -> Path:
    """Resolve a directory lexically while refusing symlinks at every component."""

    absolute = path.absolute()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        descriptor = os.open(absolute.anchor, flags)
        descriptors.append(descriptor)
        for part in absolute.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            descriptors.append(child)
            opened = os.fstat(child)
            named = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(named.st_mode)
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            ):
                raise AnalysisCommitSafetyError(f"{label} contains a rebound component")
            descriptor = child
        opened_final = os.fstat(descriptors[-1])
        named_final = os.stat(absolute, follow_symlinks=False)
        if (
            not stat.S_ISDIR(named_final.st_mode)
            or (opened_final.st_dev, opened_final.st_ino)
            != (named_final.st_dev, named_final.st_ino)
        ):
            raise AnalysisCommitSafetyError(f"{label} was rebound during validation")
        return absolute
    except AnalysisCommitSafetyError:
        raise
    except OSError as exc:
        requirement = "cannot be created" if create else "must already exist"
        raise AnalysisCommitSafetyError(f"{label} {requirement}: {exc}") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _existing_root(path: Path, *, label: str) -> Path:
    return _anchored_directory_path(path, label=label, create=False)


def _state_root(path: Path) -> Path:
    return _anchored_directory_path(path, label="commit state root", create=True)


def _safe_target(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*relative_path.split("/"))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise AnalysisCommitSafetyError("canonical target escaped the Vault root") from exc
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise AnalysisCommitSafetyError("canonical target cannot traverse a symlink")
        if not current.exists() or not current.is_dir():
            raise AnalysisCommitSafetyError(
                "canonical target parent directories must already exist"
            )
    if candidate.is_symlink():
        raise AnalysisCommitSafetyError("canonical target cannot be a symlink")
    resolved_parent = candidate.parent.resolve(strict=True)
    if not resolved_parent.is_relative_to(root):
        raise AnalysisCommitSafetyError("canonical target escaped the Vault root")
    if candidate.exists() and not candidate.is_file():
        raise AnalysisCommitSafetyError("canonical target must be a regular file")
    return candidate


def _identity_from_stat(metadata: os.stat_result) -> FileIdentity:
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
    }


def _directory_identity(metadata: os.stat_result) -> DirectoryIdentity:
    return metadata.st_dev, metadata.st_ino


def _path_directory_identity(path: Path) -> DirectoryIdentity:
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"managed directory is unavailable: {exc}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise AnalysisCommitSafetyError("managed directory must be a real directory")
    return _directory_identity(metadata)


def _validate_state_component(component: str) -> str:
    if not component or component in {".", ".."} or Path(component).name != component:
        raise AnalysisCommitSafetyError("unsafe analysis commit state component")
    return component


def _open_or_create_directory_at(parent_descriptor: int, name: str) -> int:
    name = _validate_state_component(name)
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
    except FileExistsError:
        pass
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"cannot create analysis commit state directory: {exc}"
        ) from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"analysis commit state directory is missing, rebound, or unsafe: {exc}"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or _directory_identity(metadata) != _directory_identity(named)
        ):
            raise AnalysisCommitSafetyError(
                "analysis commit state directory was rebound"
            )
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _assert_directory_binding(
    parent_descriptor: int,
    name: str,
    child_descriptor: int,
) -> None:
    try:
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        opened = os.fstat(child_descriptor)
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"analysis commit state directory binding changed: {exc}"
        ) from exc
    if (
        not stat.S_ISDIR(named.st_mode)
        or not stat.S_ISDIR(opened.st_mode)
        or _directory_identity(named) != _directory_identity(opened)
    ):
        raise AnalysisCommitSafetyError("analysis commit state directory was rebound")


@dataclass(frozen=True)
class _StateLayout:
    root_path: Path
    root_descriptor: int
    commits_descriptor: int
    journals_descriptor: int
    receipts_descriptor: int
    backups_descriptor: int
    backup_directory_name: str
    journal_name: str
    receipt_name: str

    def assert_bound(self) -> None:
        try:
            named_root = os.stat(self.root_path, follow_symlinks=False)
            opened_root = os.fstat(self.root_descriptor)
        except OSError as exc:
            raise AnalysisCommitSafetyError(
                f"analysis commit state root binding changed: {exc}"
            ) from exc
        if (
            not stat.S_ISDIR(named_root.st_mode)
            or not stat.S_ISDIR(opened_root.st_mode)
            or _directory_identity(named_root) != _directory_identity(opened_root)
        ):
            raise AnalysisCommitSafetyError("analysis commit state root was rebound")
        _assert_directory_binding(
            self.root_descriptor,
            "analysis-commits",
            self.commits_descriptor,
        )
        _assert_directory_binding(
            self.commits_descriptor,
            "journals",
            self.journals_descriptor,
        )
        _assert_directory_binding(
            self.commits_descriptor,
            "receipts",
            self.receipts_descriptor,
        )
        _assert_directory_binding(
            self.journals_descriptor,
            self.backup_directory_name,
            self.backups_descriptor,
        )


@contextmanager
def _open_state_layout(root: Path, commit_id: str):
    """Keep every state directory pinned to its original inode for this commit."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        root_descriptor = os.open(root, flags)
        descriptors.append(root_descriptor)
        if _directory_identity(os.fstat(root_descriptor)) != _path_directory_identity(root):
            raise AnalysisCommitSafetyError("analysis commit state root was rebound")
        commits_descriptor = _open_or_create_directory_at(
            root_descriptor,
            "analysis-commits",
        )
        descriptors.append(commits_descriptor)
        journals_descriptor = _open_or_create_directory_at(
            commits_descriptor,
            "journals",
        )
        descriptors.append(journals_descriptor)
        receipts_descriptor = _open_or_create_directory_at(
            commits_descriptor,
            "receipts",
        )
        descriptors.append(receipts_descriptor)
        backup_directory_name = f"{_validate_state_component(commit_id)}.files"
        backups_descriptor = _open_or_create_directory_at(
            journals_descriptor,
            backup_directory_name,
        )
        descriptors.append(backups_descriptor)
        layout = _StateLayout(
            root_path=root,
            root_descriptor=root_descriptor,
            commits_descriptor=commits_descriptor,
            journals_descriptor=journals_descriptor,
            receipts_descriptor=receipts_descriptor,
            backups_descriptor=backups_descriptor,
            backup_directory_name=backup_directory_name,
            journal_name=f"{commit_id}.json",
            receipt_name=f"{commit_id}.json",
        )
        layout.assert_bound()
        yield layout
    except AnalysisCommitSafetyError:
        raise
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"cannot anchor analysis commit state directories: {exc}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _validate_target_parts(relative_path: str) -> tuple[str, ...]:
    parts = tuple(relative_path.split("/"))
    if (
        not parts
        or any(part in {"", ".", ".."} for part in parts)
        or any("/" in part or "\\" in part for part in parts)
    ):
        raise AnalysisCommitSafetyError("unsafe canonical target path")
    return parts


def _assert_vault_binding(vault_root: Path, vault_descriptor: int) -> None:
    try:
        opened_root = os.fstat(vault_descriptor)
        named_root = os.stat(vault_root, follow_symlinks=False)
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"canonical Vault root binding changed: {exc}"
        ) from exc
    if (
        not stat.S_ISDIR(opened_root.st_mode)
        or not stat.S_ISDIR(named_root.st_mode)
        or _directory_identity(opened_root) != _directory_identity(named_root)
    ):
        raise AnalysisCommitSafetyError("canonical Vault root was rebound")


def _assert_target_parent_binding(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
    parent_descriptor: int,
) -> None:
    """Verify that the pinned parent is still named by the canonical Vault path."""

    parts = _validate_target_parts(relative_path)
    _assert_vault_binding(vault_root, vault_descriptor)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        descriptor = os.dup(vault_descriptor)
        descriptors.append(descriptor)
        for part in parts[:-1]:
            descriptor = os.open(part, flags, dir_fd=descriptor)
            descriptors.append(descriptor)
        if _directory_identity(os.fstat(descriptors[-1])) != _directory_identity(
            os.fstat(parent_descriptor)
        ):
            raise AnalysisCommitSafetyError("canonical target parent was rebound")
    except AnalysisCommitSafetyError:
        raise
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"canonical target parent binding changed: {exc}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def _open_target_parent(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
):
    """Open a canonical parent from the locked Vault inode without following links."""

    parts = _validate_target_parts(relative_path)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        _assert_vault_binding(vault_root, vault_descriptor)
        descriptor = os.dup(vault_descriptor)
        descriptors.append(descriptor)
        for part in parts[:-1]:
            descriptor = os.open(part, flags, dir_fd=descriptor)
            descriptors.append(descriptor)
            metadata = os.fstat(descriptor)
            if not stat.S_ISDIR(metadata.st_mode):
                raise AnalysisCommitSafetyError(
                    "canonical target parent must remain a directory"
                )
        yield descriptors[-1], parts[-1]
        _assert_target_parent_binding(
            vault_root,
            vault_descriptor,
            relative_path,
            descriptors[-1],
        )
    except AnalysisCommitSafetyError:
        raise
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"canonical target parent is missing, rebound, or unsafe: {exc}"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _snapshot_at(
    parent_descriptor: int,
    name: str,
    *,
    include_payload: bool = False,
) -> tuple[str, FileIdentity, bytes | None] | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AnalysisCommitSafetyError(
            f"canonical target is not a safe regular file: {exc}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AnalysisCommitSafetyError("canonical target must be a regular file")
        chunks: list[bytes] = []
        digest = sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            if include_payload:
                chunks.append(chunk)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        before_identity = _identity_from_stat(before)
        after_identity = _identity_from_stat(after)
        named_identity = _identity_from_stat(named)
        if (
            before_identity != after_identity
            or after_identity != named_identity
            or not stat.S_ISREG(named.st_mode)
        ):
            raise AnalysisCommitConflict(
                "canonical target changed while its revision was inspected"
            )
        payload = b"".join(chunks) if include_payload else None
        return "sha256:" + digest.hexdigest(), after_identity, payload
    finally:
        os.close(descriptor)


def _state_snapshot(
    layout: _StateLayout,
    directory_descriptor: int,
    name: str,
    *,
    include_payload: bool = False,
) -> tuple[str, FileIdentity, bytes | None] | None:
    _validate_state_component(name)
    layout.assert_bound()
    snapshot = _snapshot_at(
        directory_descriptor,
        name,
        include_payload=include_payload,
    )
    layout.assert_bound()
    return snapshot


def _state_file_exists(
    layout: _StateLayout,
    directory_descriptor: int,
    name: str,
) -> bool:
    return _state_snapshot(layout, directory_descriptor, name) is not None


def _load_state_json(
    layout: _StateLayout,
    directory_descriptor: int,
    name: str,
) -> dict[str, Any]:
    snapshot = _state_snapshot(
        layout,
        directory_descriptor,
        name,
        include_payload=True,
    )
    if snapshot is None or snapshot[2] is None:
        raise AnalysisCommitSafetyError(f"commit state file is missing: {name}")
    try:
        value = json.loads(snapshot[2])
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AnalysisCommitSafetyError(f"invalid commit state JSON: {name}") from exc
    if not isinstance(value, dict):
        raise AnalysisCommitSafetyError(f"commit state JSON must be an object: {name}")
    return value


def _atomic_write_state(
    layout: _StateLayout,
    directory_descriptor: int,
    name: str,
    payload: bytes,
) -> FileIdentity:
    """Atomically replace one state file without resolving its parent by path."""

    _validate_state_component(name)
    layout.assert_bound()
    temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(
            temporary_name,
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot create commit state file: {exc}") from exc
    temporary_identity: FileIdentity | None = None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_identity = _identity_from_stat(os.fstat(handle.fileno()))
        layout.assert_bound()
        _snapshot_at(directory_descriptor, name)
        os.replace(
            temporary_name,
            name,
            src_dir_fd=directory_descriptor,
            dst_dir_fd=directory_descriptor,
        )
        os.fsync(directory_descriptor)
        layout.assert_bound()
        written = _snapshot_at(directory_descriptor, name)
        if (
            written is None
            or temporary_identity is None
            or (written[1]["device"], written[1]["inode"])
            != (temporary_identity["device"], temporary_identity["inode"])
            or written[0] != _sha256_bytes(payload)
        ):
            raise AnalysisCommitConflict(
                f"commit state file changed immediately after replace: {name}"
            )
        return written[1]
    finally:
        try:
            temporary = os.stat(
                temporary_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            if (
                temporary_identity is not None
                and _identity_from_stat(temporary) == temporary_identity
            ):
                os.unlink(temporary_name, dir_fd=directory_descriptor)


def _target_snapshot(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
    *,
    include_payload: bool = False,
) -> tuple[str, FileIdentity, bytes | None] | None:
    with _open_target_parent(
        vault_root,
        vault_descriptor,
        relative_path,
    ) as (parent_descriptor, name):
        return _snapshot_at(
            parent_descriptor,
            name,
            include_payload=include_payload,
        )


def _target_hash(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
) -> str | None:
    snapshot = _target_snapshot(vault_root, vault_descriptor, relative_path)
    return None if snapshot is None else snapshot[0]


def _read_target_regular(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
) -> bytes:
    snapshot = _target_snapshot(
        vault_root,
        vault_descriptor,
        relative_path,
        include_payload=True,
    )
    if snapshot is None or snapshot[2] is None:
        raise AnalysisCommitSafetyError("expected an existing canonical regular file")
    return snapshot[2]


def _atomic_write_target(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
    payload: bytes,
    *,
    expected_sha256: str | None,
    expected_identity: FileIdentity | None,
) -> FileIdentity:
    """Replace one target through an anchored dirfd and return the written inode."""

    with _open_target_parent(
        vault_root,
        vault_descriptor,
        relative_path,
    ) as (parent_descriptor, name):
        temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_descriptor)
        temporary_identity: FileIdentity | None = None
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_identity = _identity_from_stat(os.fstat(handle.fileno()))
            current = _snapshot_at(parent_descriptor, name)
            current_hash = None if current is None else current[0]
            current_identity = None if current is None else current[1]
            if current_hash != expected_sha256 or current_identity != expected_identity:
                raise AnalysisCommitConflict(
                    f"base revision or inode changed immediately before replace: {name}"
                )
            _assert_target_parent_binding(
                vault_root,
                vault_descriptor,
                relative_path,
                parent_descriptor,
            )
            os.replace(
                temporary_name,
                name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.fsync(parent_descriptor)
            _assert_target_parent_binding(
                vault_root,
                vault_descriptor,
                relative_path,
                parent_descriptor,
            )
            written = _snapshot_at(parent_descriptor, name)
            if (
                written is None
                or temporary_identity is None
                or (written[1]["device"], written[1]["inode"])
                != (temporary_identity["device"], temporary_identity["inode"])
                or written[0] != _sha256_bytes(payload)
            ):
                raise AnalysisCommitConflict(
                    f"canonical target changed immediately after replace: {name}"
                )
            return written[1]
        finally:
            try:
                temporary = os.stat(
                    temporary_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                if (
                    temporary_identity is not None
                    and _identity_from_stat(temporary) == temporary_identity
                ):
                    os.unlink(temporary_name, dir_fd=parent_descriptor)


@contextmanager
def _commit_lock(root: Path, expected_identity: DirectoryIdentity):
    """Serialize canonical writes on the Vault inode, independent of state_root."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot lock canonical Vault root: {exc}") from exc
    try:
        try:
            opened = os.fstat(descriptor)
            current = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise AnalysisCommitSafetyError(
                f"canonical Vault root changed before locking: {exc}"
            ) from exc
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or _directory_identity(opened) != expected_identity
            or _directory_identity(current) != expected_identity
        ):
            raise AnalysisCommitSafetyError("canonical Vault root changed before locking")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            current = os.stat(root, follow_symlinks=False)
        except OSError as exc:
            raise AnalysisCommitSafetyError(
                f"canonical Vault root changed while locking: {exc}"
            ) from exc
        if _directory_identity(current) != expected_identity:
            raise AnalysisCommitSafetyError("canonical Vault root changed while locking")
        yield descriptor
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _canonical_payloads(
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
) -> dict[str, bytes]:
    report = validate_bundle(request.document, bundle, note_stem=request.note_stem)
    if not report.ok:
        codes = ", ".join(finding.code for finding in report.findings)
        raise AnalysisCommitError(f"canonical commit requires a conformant bundle: {codes}")
    expected_baseline = create_baseline(
        request.document,
        bundle,
        note_stem=request.note_stem,
    )
    if baseline.model_dump(mode="json") != expected_baseline.model_dump(mode="json"):
        raise AnalysisCommitConflict("staged sidecar does not match the validated bundle")
    return {
        request.paths.markdown: bundle.markdown.encode("utf-8"),
        request.paths.canvas: _json_bytes(bundle.canvas),
        request.paths.sidecar: _json_bytes(baseline.model_dump(mode="json")),
    }


def _make_change_set(
    request: AnalysisCommitRequest,
    after_hashes: dict[str, str],
) -> KnowledgeChangeSet:
    artifacts = [
        KnowledgeArtifactChange(
            artifact_id=request.document.artifact_id,
            resource_id=request.resource_id,
            kind="analysis_markdown",
            vault_path=request.paths.markdown,
            sha256=after_hashes[request.paths.markdown],
        ),
        KnowledgeArtifactChange(
            artifact_id=f"{request.document.artifact_id}:canvas",
            resource_id=request.resource_id,
            kind="analysis_canvas",
            vault_path=request.paths.canvas,
            sha256=after_hashes[request.paths.canvas],
        ),
        KnowledgeArtifactChange(
            artifact_id=f"{request.document.artifact_id}:sidecar",
            resource_id=request.resource_id,
            kind="analysis_sidecar",
            vault_path=request.paths.sidecar,
            sha256=after_hashes[request.paths.sidecar],
        ),
    ]
    semantic_payload = {
        "source_receipt": f"analysis-commit:{request.commit_id}",
        "base_catalog_revision": request.base_catalog_revision,
        "upsert_artifacts": [item.model_dump(mode="json") for item in artifacts],
        "upsert_relations": [
            item.model_dump(mode="json") for item in request.relations
        ],
        "upsert_projections": [
            item.model_dump(mode="json") for item in request.projections
        ],
        "expected_base_hashes": request.base_revisions,
    }
    change_hash = sha256(
        json.dumps(
            semantic_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return KnowledgeChangeSet(
        change_id=f"change:{change_hash}",
        **semantic_payload,
    )


def _verify_receipt_targets(
    vault_root: Path,
    vault_descriptor: int,
    receipt: AnalysisCommitReceipt,
) -> None:
    for record in receipt.files:
        _safe_target(vault_root, record.path)
        if (
            _target_hash(vault_root, vault_descriptor, record.path)
            != record.after_sha256
        ):
            raise AnalysisCommitConflict(
                f"canonical file changed after receipt: {record.path}"
            )


def _load_receipt(value: dict[str, Any], *, source: str) -> AnalysisCommitReceipt:
    try:
        return AnalysisCommitReceipt.model_validate(value)
    except ValidationError as exc:
        raise AnalysisCommitSafetyError(f"invalid {source}: {exc}") from exc


def _expected_file_records(
    request: AnalysisCommitRequest,
    after_hashes: dict[str, str],
) -> list[AnalysisCommitFile]:
    records: list[AnalysisCommitFile] = []
    for relative_path in request.paths.as_list():
        before = request.base_revisions[relative_path]
        after = after_hashes[relative_path]
        action = "unchanged" if before == after else ("created" if before is None else "replaced")
        records.append(
            AnalysisCommitFile(
                path=relative_path,
                before_sha256=before,
                after_sha256=after,
                action=action,
            )
        )
    return records


def _verify_receipt_for_request(
    receipt: AnalysisCommitReceipt,
    *,
    request: AnalysisCommitRequest,
    fingerprint: str,
    after_hashes: dict[str, str],
) -> None:
    expected_files = _expected_file_records(request, after_hashes)
    expected_change_set = _make_change_set(request, after_hashes)
    mismatches: list[str] = []
    if (
        receipt.commit_id != request.commit_id
        or receipt.request_fingerprint != fingerprint
    ):
        raise AnalysisCommitConflict("commit_id was reused for different input")
    if receipt.artifact_id != request.document.artifact_id:
        mismatches.append("artifact_id")
    if receipt.files != expected_files:
        mismatches.append("files")
    if receipt.change_set != expected_change_set:
        mismatches.append("change_set")
    if mismatches:
        raise AnalysisCommitSafetyError(
            "commit receipt does not match the request: " + ", ".join(mismatches)
        )


def _verify_journal_for_request(
    journal: dict[str, Any],
    *,
    request: AnalysisCommitRequest,
    fingerprint: str,
    after_hashes: dict[str, str],
    receipt: AnalysisCommitReceipt,
) -> None:
    """Bind recovery metadata to the same request before any rollback action."""

    expected_keys = {
        "schema_version",
        "commit_id",
        "request_fingerprint",
        "status",
        "files",
        "rollback_conflicts",
        "receipt",
    }
    if set(journal) != expected_keys:
        raise AnalysisCommitSafetyError("commit journal has an unexpected shape")
    if (
        journal.get("schema_version") != 1
        or journal.get("commit_id") != request.commit_id
        or journal.get("request_fingerprint") != fingerprint
        or journal.get("status") not in {"committing", "committed"}
        or journal.get("receipt") != receipt.model_dump(mode="json")
    ):
        raise AnalysisCommitSafetyError("commit journal does not match the request")
    rollback_conflicts = journal.get("rollback_conflicts")
    if not isinstance(rollback_conflicts, list) or any(
        not isinstance(item, str) for item in rollback_conflicts
    ):
        raise AnalysisCommitSafetyError("commit journal rollback conflicts are invalid")

    files = journal.get("files")
    expected_files = _expected_file_records(request, after_hashes)
    if not isinstance(files, list) or len(files) != len(expected_files):
        raise AnalysisCommitSafetyError("commit journal does not bind three files")
    for index, (entry, expected) in enumerate(zip(files, expected_files, strict=True)):
        if not isinstance(entry, dict) or set(entry) != {
            "path",
            "before_sha256",
            "after_sha256",
            "action",
            "backup_name",
            "before_identity",
            "after_identity",
        }:
            raise AnalysisCommitSafetyError("commit journal file entry is invalid")
        try:
            record = AnalysisCommitFile.model_validate(
                {
                    key: entry[key]
                    for key in ("path", "before_sha256", "after_sha256", "action")
                }
            )
        except ValidationError as exc:
            raise AnalysisCommitSafetyError(
                f"commit journal file record is invalid: {exc}"
            ) from exc
        if record != expected:
            raise AnalysisCommitSafetyError(
                "commit journal file record does not match the request"
            )
        expected_backup = f"{index}.before" if expected.action == "replaced" else None
        if entry["backup_name"] != expected_backup:
            raise AnalysisCommitSafetyError("commit journal backup identity is invalid")
        before_identity = _journal_identity(entry["before_identity"])
        after_identity = _journal_identity(entry["after_identity"])
        if (expected.before_sha256 is None) != (before_identity is None):
            raise AnalysisCommitSafetyError(
                "commit journal base identity does not match its revision"
            )
        if expected.action == "unchanged" and after_identity is not None:
            raise AnalysisCommitSafetyError(
                "unchanged journal files cannot claim a written inode"
            )


def _write_journal(layout: _StateLayout, journal: dict[str, Any]) -> None:
    _atomic_write_state(
        layout,
        layout.journals_descriptor,
        layout.journal_name,
        _json_bytes(journal),
    )


def _journal_identity(value: object) -> FileIdentity | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(_IDENTITY_KEYS):
        raise AnalysisCommitSafetyError("commit journal contains an invalid file identity")
    if any(not isinstance(value[key], int) or value[key] < 0 for key in value):
        raise AnalysisCommitSafetyError("commit journal file identity must use nonnegative integers")
    return {key: value[key] for key in _IDENTITY_KEYS}


def _unlink_target_if_owned(
    vault_root: Path,
    vault_descriptor: int,
    relative_path: str,
    *,
    expected_sha256: str,
    expected_identity: FileIdentity,
) -> bool:
    """Unlink only the exact canonical inode/revision through an anchored dirfd."""

    with _open_target_parent(
        vault_root,
        vault_descriptor,
        relative_path,
    ) as (parent_descriptor, name):
        snapshot = _snapshot_at(parent_descriptor, name)
        if snapshot is None:
            return True
        if snapshot[0] != expected_sha256 or snapshot[1] != expected_identity:
            return False
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if _identity_from_stat(named) != expected_identity:
            return False
        _assert_target_parent_binding(
            vault_root,
            vault_descriptor,
            relative_path,
            parent_descriptor,
        )
        os.unlink(name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        return True


def _rollback(
    *,
    vault_root: Path,
    vault_descriptor: int,
    state_layout: _StateLayout,
    journal: dict[str, Any],
) -> list[str]:
    conflicts: list[str] = []
    files = journal.get("files")
    if not isinstance(files, list):
        return ["journal-files-invalid"]
    for entry in reversed(files):
        if not isinstance(entry, dict) or entry.get("action") == "unchanged":
            continue
        relative_path = entry.get("path")
        after_sha256 = entry.get("after_sha256")
        before_sha256 = entry.get("before_sha256")
        if not isinstance(relative_path, str) or not isinstance(after_sha256, str):
            conflicts.append("journal-entry-invalid")
            continue
        try:
            _safe_target(vault_root, relative_path)
            snapshot = _target_snapshot(
                vault_root,
                vault_descriptor,
                relative_path,
            )
        except (AnalysisCommitConflict, AnalysisCommitSafetyError, OSError):
            conflicts.append(relative_path)
            continue
        current = None if snapshot is None else snapshot[0]
        if current == before_sha256:
            continue
        if current != after_sha256:
            conflicts.append(relative_path)
            continue
        try:
            after_identity = _journal_identity(entry.get("after_identity"))
        except AnalysisCommitSafetyError:
            conflicts.append(relative_path)
            continue
        if after_identity is None or snapshot is None or snapshot[1] != after_identity:
            conflicts.append(relative_path)
            continue
        if before_sha256 is None:
            try:
                removed = _unlink_target_if_owned(
                    vault_root,
                    vault_descriptor,
                    relative_path,
                    expected_sha256=after_sha256,
                    expected_identity=after_identity,
                )
            except (AnalysisCommitConflict, AnalysisCommitSafetyError, OSError):
                removed = False
            if not removed:
                conflicts.append(relative_path)
            continue
        backup_name = entry.get("backup_name")
        if not isinstance(backup_name, str):
            conflicts.append(relative_path)
            continue
        try:
            _validate_state_component(backup_name)
            backup_snapshot = _snapshot_at(
                state_layout.backups_descriptor,
                backup_name,
                include_payload=True,
            )
        except (AnalysisCommitConflict, AnalysisCommitSafetyError, OSError):
            conflicts.append(relative_path)
            continue
        if backup_snapshot is None or backup_snapshot[2] is None:
            conflicts.append(relative_path)
            continue
        payload = backup_snapshot[2]
        if _sha256_bytes(payload) != before_sha256:
            conflicts.append(relative_path)
            continue
        try:
            _atomic_write_target(
                vault_root,
                vault_descriptor,
                relative_path,
                payload,
                expected_sha256=after_sha256,
                expected_identity=after_identity,
            )
        except (AnalysisCommitConflict, AnalysisCommitSafetyError, OSError):
            conflicts.append(relative_path)
    return conflicts


def commit_analysis_bundle(
    *,
    vault_root: Path,
    state_root: Path,
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
    fault_inject: FaultInjector | None = None,
) -> AnalysisCommitReceipt:
    """Commit one validated pair and sidecar with CAS, journal, and safe rollback.

    The function never scans Markdown for relations.  Its ``KnowledgeChangeSet``
    contains only the three committed artifacts plus relations and projections
    supplied explicitly in ``request``.
    """

    root = _existing_root(vault_root, label="Vault root")
    root_identity = _path_directory_identity(root)
    state = _state_root(state_root)
    payloads = _canonical_payloads(request, bundle, baseline)
    fingerprint = _request_fingerprint(request)
    after_hashes = {path: _sha256_bytes(payload) for path, payload in payloads.items()}
    target_paths = {path: _safe_target(root, path) for path in request.paths.as_list()}

    with (
        _open_state_layout(state, request.commit_id) as state_layout,
        _commit_lock(root, root_identity) as vault_descriptor,
    ):
        if _state_file_exists(
            state_layout,
            state_layout.receipts_descriptor,
            state_layout.receipt_name,
        ):
            receipt = _load_receipt(
                _load_state_json(
                    state_layout,
                    state_layout.receipts_descriptor,
                    state_layout.receipt_name,
                ),
                source="commit receipt",
            )
            _verify_receipt_for_request(
                receipt,
                request=request,
                fingerprint=fingerprint,
                after_hashes=after_hashes,
            )
            _verify_receipt_targets(root, vault_descriptor, receipt)
            return receipt

        if _state_file_exists(
            state_layout,
            state_layout.journals_descriptor,
            state_layout.journal_name,
        ):
            previous = _load_state_json(
                state_layout,
                state_layout.journals_descriptor,
                state_layout.journal_name,
            )
            if previous.get("request_fingerprint") != fingerprint:
                raise AnalysisCommitConflict("commit_id was reused for different input")
            status = previous.get("status")
            if status == "failed_partial":
                raise AnalysisCommitPartialError(
                    "previous commit requires manual recovery before reuse"
                )
            if status in {"committing", "committed"}:
                receipt_value = previous.get("receipt")
                if not isinstance(receipt_value, dict):
                    raise AnalysisCommitSafetyError("commit journal has no valid receipt draft")
                receipt = _load_receipt(receipt_value, source="commit journal receipt")
                _verify_receipt_for_request(
                    receipt,
                    request=request,
                    fingerprint=fingerprint,
                    after_hashes=after_hashes,
                )
                _verify_journal_for_request(
                    previous,
                    request=request,
                    fingerprint=fingerprint,
                    after_hashes=after_hashes,
                    receipt=receipt,
                )
                current_hashes = {
                    path: _target_hash(root, vault_descriptor, path)
                    for path in target_paths
                }
                if all(current_hashes[path] == after_hashes[path] for path in payloads):
                    _atomic_write_state(
                        state_layout,
                        state_layout.receipts_descriptor,
                        state_layout.receipt_name,
                        _json_bytes(receipt.model_dump(mode="json")),
                    )
                    previous["status"] = "committed"
                    _write_journal(state_layout, previous)
                    return receipt
                conflicts = _rollback(
                    vault_root=root,
                    vault_descriptor=vault_descriptor,
                    state_layout=state_layout,
                    journal=previous,
                )
                previous["status"] = "failed_partial" if conflicts else "rolled_back"
                previous["rollback_conflicts"] = conflicts
                _write_journal(state_layout, previous)
                if conflicts:
                    raise AnalysisCommitPartialError(
                        "interrupted commit cannot be rolled back without overwriting edits: "
                        + ", ".join(conflicts)
                    )
            elif status != "rolled_back":
                raise AnalysisCommitSafetyError("commit journal has an unknown status")

        before_snapshots = {
            path: _target_snapshot(root, vault_descriptor, path)
            for path in target_paths
        }
        before_hashes = {
            path: None if snapshot is None else snapshot[0]
            for path, snapshot in before_snapshots.items()
        }
        before_identities = {
            path: None if snapshot is None else snapshot[1]
            for path, snapshot in before_snapshots.items()
        }
        for relative_path, expected in request.base_revisions.items():
            if before_hashes[relative_path] != expected:
                raise AnalysisCommitConflict(
                    f"base revision changed for {relative_path}; refusing to overwrite"
                )

        file_records = _expected_file_records(request, after_hashes)
        journal_files: list[dict[str, Any]] = []
        for index, record in enumerate(file_records):
            relative_path = record.path
            backup_name: str | None = None
            if record.action == "replaced":
                backup_name = f"{index}.before"
                _atomic_write_state(
                    state_layout,
                    state_layout.backups_descriptor,
                    backup_name,
                    _read_target_regular(root, vault_descriptor, relative_path),
                )
            journal_files.append(
                {
                    **record.model_dump(mode="json"),
                    "backup_name": backup_name,
                    "before_identity": before_identities[relative_path],
                    "after_identity": None,
                }
            )

        change_set = _make_change_set(request, after_hashes)
        receipt = AnalysisCommitReceipt(
            commit_id=request.commit_id,
            request_fingerprint=fingerprint,
            artifact_id=request.document.artifact_id,
            committed_at=datetime.now(UTC),
            files=file_records,
            change_set=change_set,
        )
        journal: dict[str, Any] = {
            "schema_version": 1,
            "commit_id": request.commit_id,
            "request_fingerprint": fingerprint,
            "status": "committing",
            "files": journal_files,
            "rollback_conflicts": [],
            "receipt": receipt.model_dump(mode="json"),
        }
        _write_journal(state_layout, journal)
        if fault_inject is not None:
            fault_inject("after-journal")

        try:
            for relative_path in request.paths.as_list():
                record = next(item for item in file_records if item.path == relative_path)
                if record.action == "unchanged":
                    continue
                if (
                    _target_hash(root, vault_descriptor, relative_path)
                    != record.before_sha256
                ):
                    raise AnalysisCommitConflict(
                        f"base revision changed during commit for {relative_path}"
                    )
                if fault_inject is not None:
                    fault_inject(f"before-replace:{relative_path}")
                identity = _atomic_write_target(
                    root,
                    vault_descriptor,
                    relative_path,
                    payloads[relative_path],
                    expected_sha256=record.before_sha256,
                    expected_identity=before_identities[relative_path],
                )
                journal_entry = next(
                    item for item in journal_files if item["path"] == relative_path
                )
                journal_entry["after_identity"] = identity
                _write_journal(state_layout, journal)
                if fault_inject is not None:
                    fault_inject(f"after-replace:{relative_path}")
            if fault_inject is not None:
                fault_inject("before-receipt")
            _atomic_write_state(
                state_layout,
                state_layout.receipts_descriptor,
                state_layout.receipt_name,
                _json_bytes(receipt.model_dump(mode="json")),
            )
        except Exception:
            conflicts = _rollback(
                vault_root=root,
                vault_descriptor=vault_descriptor,
                state_layout=state_layout,
                journal=journal,
            )
            journal["status"] = "failed_partial" if conflicts else "rolled_back"
            journal["rollback_conflicts"] = conflicts
            _write_journal(state_layout, journal)
            if conflicts:
                raise AnalysisCommitPartialError(
                    "conditional rollback refused to overwrite concurrent edits: "
                    + ", ".join(conflicts)
                ) from None
            raise

        journal["status"] = "committed"
        _write_journal(state_layout, journal)
        return receipt
