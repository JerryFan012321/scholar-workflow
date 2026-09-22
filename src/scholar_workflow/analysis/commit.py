"""Recoverable CAS commit for canonical Markdown, Canvas, and analysis sidecars."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
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


def _assert_no_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise AnalysisCommitSafetyError(f"path cannot traverse a symlink: {current}")


def _existing_root(path: Path, *, label: str) -> Path:
    _assert_no_symlink_components(path)
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"{label} must already exist: {exc}") from exc
    if not root.is_dir():
        raise AnalysisCommitSafetyError(f"{label} must be a directory")
    return root


def _state_root(path: Path) -> Path:
    _assert_no_symlink_components(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot create commit state root: {exc}") from exc
    _assert_no_symlink_components(path)
    return path.resolve(strict=True)


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


def _safe_state_path(root: Path, *parts: str, directory: bool = False) -> Path:
    current = root
    for part in parts:
        if not part or part in {".", ".."} or Path(part).name != part:
            raise AnalysisCommitSafetyError("unsafe analysis commit state component")
        current /= part
        if current.is_symlink():
            raise AnalysisCommitSafetyError("analysis commit state cannot traverse a symlink")
    if directory:
        current.mkdir(parents=True, exist_ok=True)
        if current.is_symlink() or not current.is_dir():
            raise AnalysisCommitSafetyError("analysis commit state directory is unsafe")
    elif current.exists() and (current.is_symlink() or not current.is_file()):
        raise AnalysisCommitSafetyError("analysis commit state file is unsafe")
    if not current.resolve(strict=False).is_relative_to(root):
        raise AnalysisCommitSafetyError("analysis commit state escaped its root")
    return current


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise AnalysisCommitSafetyError(f"expected a regular file: {path}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot read managed file: {exc}") from exc


def _current_hash(path: Path) -> str | None:
    if not path.exists():
        if path.is_symlink():
            raise AnalysisCommitSafetyError("managed path is a dangling symlink")
        return None
    return _sha256_bytes(_read_regular(path))


def _file_identity(path: Path) -> FileIdentity | None:
    """Return the regular file identity without following the final component."""
    if not path.exists():
        if path.is_symlink():
            raise AnalysisCommitSafetyError("managed path is a dangling symlink")
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot open managed file: {exc}") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise AnalysisCommitSafetyError("managed path must be a regular file")
        current = os.stat(path, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise AnalysisCommitConflict("managed file identity changed while inspecting it")
        return {
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "size": metadata.st_size,
        }
    finally:
        os.close(descriptor)


def _identity_matches(path: Path, expected: FileIdentity | None) -> bool:
    return _file_identity(path) == expected


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    expected_sha256: str | None | object = ...,
    expected_identity: FileIdentity | None | object = ...,
) -> None:
    if path.is_symlink():
        raise AnalysisCommitSafetyError("atomic target cannot be a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    temporary_identity: FileIdentity | None = None
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_identity = _file_identity(temporary)
        if path.is_symlink():
            raise AnalysisCommitSafetyError("atomic target became a symlink")
        if expected_sha256 is not ... and _current_hash(path) != expected_sha256:
            raise AnalysisCommitConflict(
                f"base revision changed immediately before replace: {path.name}"
            )
        if expected_identity is not ... and not _identity_matches(path, expected_identity):
            raise AnalysisCommitConflict(
                f"file identity changed immediately before replace: {path.name}"
            )
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary_identity is not None and temporary.exists():
            _unlink_if_owned(temporary, expected_identity=temporary_identity)


@contextmanager
def _commit_lock(root: Path):
    """Serialize canonical writes on the Vault inode, independent of state_root."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot lock canonical Vault root: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        current = os.stat(root, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise AnalysisCommitSafetyError("canonical Vault root changed before locking")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        current = os.stat(root, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise AnalysisCommitSafetyError("canonical Vault root changed while locking")
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AnalysisCommitSafetyError(f"invalid commit state JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise AnalysisCommitSafetyError(f"commit state JSON must be an object: {path.name}")
    return value


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
    receipt: AnalysisCommitReceipt,
) -> None:
    for record in receipt.files:
        target = _safe_target(vault_root, record.path)
        if _current_hash(target) != record.after_sha256:
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


def _write_journal(path: Path, journal: dict[str, Any]) -> None:
    _atomic_write(path, _json_bytes(journal))


def _journal_identity(value: object) -> FileIdentity | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"device", "inode", "size"}:
        raise AnalysisCommitSafetyError("commit journal contains an invalid file identity")
    if any(not isinstance(value[key], int) or value[key] < 0 for key in value):
        raise AnalysisCommitSafetyError("commit journal file identity must use nonnegative integers")
    return {key: value[key] for key in ("device", "inode", "size")}


def _unlink_if_owned(
    target: Path,
    *,
    expected_identity: FileIdentity,
) -> bool:
    """Unlink only the inode written by this commit, using the parent dirfd."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_descriptor = os.open(target.parent, flags)
    except OSError as exc:
        raise AnalysisCommitSafetyError(f"cannot open canonical parent directory: {exc}") from exc
    try:
        try:
            before = os.stat(target.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return True
        identity = {
            "device": before.st_dev,
            "inode": before.st_ino,
            "size": before.st_size,
        }
        if not stat.S_ISREG(before.st_mode) or identity != expected_identity:
            return False
        # Recheck through the same directory descriptor immediately before unlink.
        after = os.stat(target.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (after.st_dev, after.st_ino, after.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            return False
        os.unlink(target.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
        return True
    finally:
        os.close(parent_descriptor)


def _rollback(
    *,
    vault_root: Path,
    backup_dir: Path,
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
        target = _safe_target(vault_root, relative_path)
        current = _current_hash(target)
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
        if after_identity is None or not _identity_matches(target, after_identity):
            conflicts.append(relative_path)
            continue
        if before_sha256 is None:
            try:
                removed = _unlink_if_owned(target, expected_identity=after_identity)
            except (AnalysisCommitConflict, AnalysisCommitSafetyError, OSError):
                removed = False
            if not removed:
                conflicts.append(relative_path)
            continue
        backup_name = entry.get("backup_name")
        if not isinstance(backup_name, str):
            conflicts.append(relative_path)
            continue
        backup = _safe_state_path(backup_dir, backup_name)
        payload = _read_regular(backup)
        if _sha256_bytes(payload) != before_sha256:
            conflicts.append(relative_path)
            continue
        try:
            _atomic_write(
                target,
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
    state = _state_root(state_root)
    payloads = _canonical_payloads(request, bundle, baseline)
    fingerprint = _request_fingerprint(request)
    after_hashes = {path: _sha256_bytes(payload) for path, payload in payloads.items()}
    target_paths = {path: _safe_target(root, path) for path in request.paths.as_list()}

    commits_root = _safe_state_path(state, "analysis-commits", directory=True)
    journal_root = _safe_state_path(commits_root, "journals", directory=True)
    receipt_root = _safe_state_path(commits_root, "receipts", directory=True)
    journal_path = _safe_state_path(journal_root, f"{request.commit_id}.json")
    receipt_path = _safe_state_path(receipt_root, f"{request.commit_id}.json")
    backup_dir = _safe_state_path(
        journal_root,
        f"{request.commit_id}.files",
        directory=True,
    )

    with _commit_lock(root):
        if receipt_path.exists():
            receipt = _load_receipt(_load_json(receipt_path), source="commit receipt")
            _verify_receipt_for_request(
                receipt,
                request=request,
                fingerprint=fingerprint,
                after_hashes=after_hashes,
            )
            _verify_receipt_targets(root, receipt)
            return receipt

        if journal_path.exists():
            previous = _load_json(journal_path)
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
                current_hashes = {
                    path: _current_hash(target) for path, target in target_paths.items()
                }
                if all(current_hashes[path] == after_hashes[path] for path in payloads):
                    _atomic_write(receipt_path, _json_bytes(receipt.model_dump(mode="json")))
                    previous["status"] = "committed"
                    _write_journal(journal_path, previous)
                    return receipt
                conflicts = _rollback(
                    vault_root=root,
                    backup_dir=backup_dir,
                    journal=previous,
                )
                previous["status"] = "failed_partial" if conflicts else "rolled_back"
                previous["rollback_conflicts"] = conflicts
                _write_journal(journal_path, previous)
                if conflicts:
                    raise AnalysisCommitPartialError(
                        "interrupted commit cannot be rolled back without overwriting edits: "
                        + ", ".join(conflicts)
                    )

        before_hashes = {
            path: _current_hash(target) for path, target in target_paths.items()
        }
        before_identities = {
            path: _file_identity(target) for path, target in target_paths.items()
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
                backup_path = _safe_state_path(backup_dir, backup_name)
                _atomic_write(backup_path, _read_regular(target_paths[relative_path]))
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
        _write_journal(journal_path, journal)
        if fault_inject is not None:
            fault_inject("after-journal")

        try:
            for relative_path in request.paths.as_list():
                record = next(item for item in file_records if item.path == relative_path)
                if record.action == "unchanged":
                    continue
                if _current_hash(target_paths[relative_path]) != record.before_sha256:
                    raise AnalysisCommitConflict(
                        f"base revision changed during commit for {relative_path}"
                    )
                if fault_inject is not None:
                    fault_inject(f"before-replace:{relative_path}")
                _atomic_write(
                    target_paths[relative_path],
                    payloads[relative_path],
                    expected_sha256=record.before_sha256,
                    expected_identity=before_identities[relative_path],
                )
                identity = _file_identity(target_paths[relative_path])
                if identity is None:
                    raise AnalysisCommitSafetyError(
                        f"canonical target disappeared after replace: {relative_path}"
                    )
                journal_entry = next(
                    item for item in journal_files if item["path"] == relative_path
                )
                journal_entry["after_identity"] = identity
                _write_journal(journal_path, journal)
                if fault_inject is not None:
                    fault_inject(f"after-replace:{relative_path}")
            if fault_inject is not None:
                fault_inject("before-receipt")
            _atomic_write(receipt_path, _json_bytes(receipt.model_dump(mode="json")))
        except Exception:
            conflicts = _rollback(
                vault_root=root,
                backup_dir=backup_dir,
                journal=journal,
            )
            journal["status"] = "failed_partial" if conflicts else "rolled_back"
            journal["rollback_conflicts"] = conflicts
            _write_journal(journal_path, journal)
            if conflicts:
                raise AnalysisCommitPartialError(
                    "conditional rollback refused to overwrite concurrent edits: "
                    + ", ".join(conflicts)
                ) from None
            raise

        journal["status"] = "committed"
        _write_journal(journal_path, journal)
        return receipt
