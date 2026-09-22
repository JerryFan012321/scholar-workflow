"""Local-first experiment records with immutable recipes and explicit promotion."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from scholar_workflow.project.models import (
    ActualExecution,
    ArtifactManifest,
    ArtifactRecord,
    AttemptRecord,
    BackupRecord,
    DatasetRecord,
    FileSnapshot,
    RunRecord,
    SourceRecord,
    TargetProfile,
)

RUN_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{4}-[a-z0-9][a-z0-9-]{0,47}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_PROCESS_MUTATION_LOCK = threading.RLock()


class ExperimentError(ValueError):
    """An experiment request violates a portable project or safety contract."""


@dataclass(frozen=True)
class _OwnedFile:
    """Identity and bytes created by one exclusive file operation."""

    device: int
    inode: int
    size: int
    sha256: str


def _now() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _has_symlink_component(path: Path) -> bool:
    candidate = path.absolute()
    return any(component.is_symlink() for component in (candidate, *candidate.parents))


def _regular_file(path: Path, *, label: str) -> Path:
    candidate = path.expanduser().absolute()
    if _has_symlink_component(candidate):
        raise ExperimentError(f"{label} cannot use a symlink path")
    if not candidate.is_file():
        raise ExperimentError(f"{label} must be an existing regular file")
    return candidate.resolve()


def _validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ExperimentError("run_id must use YYYYMMDD-HHMM-slug")
    return run_id


def _validate_slug(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise ExperimentError(f"{label} must be a lowercase slug")
    return value


def _project_root(value: str | Path) -> Path:
    root = Path(value).expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ExperimentError("project root must be an existing non-symlink directory")
    root = root.resolve()
    layout_path = root / "project-layout.json"
    if layout_path.is_symlink() or not layout_path.is_file():
        raise ExperimentError("project-layout.json is required; run init-project apply first")
    try:
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        raw_project_id = layout["project_id"]
        if not isinstance(raw_project_id, str):
            raise TypeError("project_id must be a canonical string")
        project_id = uuid.UUID(raw_project_id)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        raise ExperimentError("project-layout.json does not contain a valid project identity") from None
    if (
        layout.get("schema_version") != 2
        or project_id.version != 4
        or raw_project_id != str(project_id)
    ):
        raise ExperimentError("project-layout.json must use schema_version 2 and UUIDv4 identity")
    return root


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    """Open one lock-directory component without following a symlink."""

    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    except OSError as exc:
        raise ExperimentError("cannot create the experiment lock directory") from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise ExperimentError("experiment lock directory is unsafe") from exc
    if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ExperimentError("experiment lock directory must be a directory")
    return descriptor


@contextmanager
def _project_mutation_lock(root: Path) -> Iterator[None]:
    """Serialize all experiment mutations across threads and processes."""

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    with _PROCESS_MUTATION_LOCK:
        try:
            root_fd = os.open(root, directory_flags)
        except OSError as exc:
            raise ExperimentError("project root became unsafe before mutation") from exc
        control_fd = locks_fd = lock_fd = None
        try:
            control_fd = _open_or_create_directory(root_fd, ".scholar-workflow")
            locks_fd = _open_or_create_directory(control_fd, "locks")
            lock_flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
            lock_flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                lock_fd = os.open(
                    "experiments.lock",
                    lock_flags,
                    0o600,
                    dir_fd=locks_fd,
                )
            except OSError as exc:
                raise ExperimentError("experiment lockfile is unsafe") from exc
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise ExperimentError("experiment lockfile must be a regular file")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError as exc:
                raise ExperimentError("cannot acquire the experiment mutation lock") from exc
            try:
                yield
            finally:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            for descriptor in (lock_fd, locks_fd, control_fd, root_fd):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass


def _locked_mutation(operation: Callable[..., Any]) -> Callable[..., Any]:
    """Apply the project mutation lock without changing public call signatures."""

    @wraps(operation)
    def locked(project_root: str | Path, *args: Any, **kwargs: Any) -> Any:
        root = _project_root(project_root)
        with _project_mutation_lock(root):
            return operation(root, *args, **kwargs)

    return locked


def _directory(path: Path, *, label: str, create: bool = False) -> Path:
    if path.is_symlink():
        raise ExperimentError(f"{label} cannot be a symlink")
    if path.exists():
        if not path.is_dir():
            raise ExperimentError(f"{label} must be a directory")
        return path
    if not create:
        raise ExperimentError(f"{label} directory is missing")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ExperimentError(f"{label} parent must be a non-symlink directory")
    try:
        path.mkdir()
    except OSError as exc:
        raise ExperimentError(f"cannot create {label}: {exc}") from None
    return path


def _required_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise ExperimentError(f"{label} cannot be a symlink")
    if not path.is_file():
        raise ExperimentError(f"{label} must be an existing regular file")
    return path


def _experiments_directory(root: Path) -> Path:
    return _directory(root / "experiments", label="experiments")


def _targets_directory(root: Path) -> Path:
    experiments = _experiments_directory(root)
    profiles = _directory(experiments / "profiles", label="profiles")
    return _directory(profiles / "targets", label="target profiles")


def _run_directory(root: Path, run_id: str) -> Path:
    _validate_run_id(run_id)
    return _directory(
        _experiments_directory(root) / run_id,
        label=f"run {run_id}",
    )


def _attempts_directory(run_directory: Path) -> Path:
    return _directory(run_directory / "attempts", label="attempts")


def _artifacts_directory(run_directory: Path) -> Path:
    return _directory(run_directory / "artifacts", label="artifacts")


def _inside_project(root: Path, value: str | Path, *, label: str) -> Path:
    raw = Path(value).expanduser()
    candidate = raw if raw.is_absolute() else root / raw
    candidate = _regular_file(candidate, label=label)
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ExperimentError(f"{label} must be inside the registered project") from None
    return candidate


def _safe_destination(base: Path, relative: str) -> Path:
    if not isinstance(relative, str):
        raise ExperimentError("destination must be a safe relative path")
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ExperimentError("destination must be a safe relative path")
    _directory(base, label="artifacts")
    destination = base / path
    current = base
    for part in path.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ExperimentError("destination cannot traverse a symlink")
        if current.exists() and not current.is_dir():
            raise ExperimentError("destination parent must be a directory")
    if destination.is_symlink():
        raise ExperimentError("destination cannot be a symlink")
    if destination.exists() and not destination.is_file():
        raise ExperimentError("artifact destination is not a regular file")
    return destination


def _create_destination_parents(base: Path, destination: Path) -> None:
    relative_parent = destination.parent.relative_to(base)
    current = base
    for part in relative_parent.parts:
        current = _directory(
            current / part,
            label="artifact destination parent",
            create=True,
        )


def _owned_file_matches(path: Path, owned: _OwnedFile) -> bool:
    """Return true only while the pathname still names our exact bytes."""

    try:
        current = os.lstat(path)
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_dev != owned.device
            or current.st_ino != owned.inode
            or current.st_size != owned.size
        ):
            return False
        return _sha256(path) == owned.sha256
    except OSError:
        return False


def _cleanup_owned_file(path: Path, owned: _OwnedFile) -> bool:
    """Remove only a still-identical file created by this operation."""

    if not _owned_file_matches(path, owned):
        return False
    try:
        os.unlink(path)
    except OSError:
        return False
    return True


def _copy_exclusive(source: Path, destination: Path, *, expected_sha256: str) -> _OwnedFile:
    """Copy a regular file with kernel-enforced no-overwrite semantics."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise ExperimentError("artifact destination already exists") from exc
    except OSError as exc:
        raise ExperimentError("cannot reserve artifact destination") from exc

    try:
        created = os.fstat(descriptor)
        if not stat.S_ISREG(created.st_mode):
            raise ExperimentError("artifact destination is not a regular file")
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise

    digest = hashlib.sha256()
    size = 0
    owned = _OwnedFile(created.st_dev, created.st_ino, 0, digest.hexdigest())
    try:
        with source.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError("artifact copy made no progress")
                    digest.update(view[:written])
                    size += written
                    view = view[written:]
        os.fsync(descriptor)
        owned = _OwnedFile(created.st_dev, created.st_ino, size, digest.hexdigest())
        if owned.sha256 != expected_sha256:
            raise ExperimentError("artifact source changed during promotion")
    except Exception:
        owned = _OwnedFile(created.st_dev, created.st_ino, size, digest.hexdigest())
        try:
            os.close(descriptor)
        except OSError:
            pass
        _cleanup_owned_file(destination, owned)
        raise
    try:
        os.close(descriptor)
    except OSError as exc:
        _cleanup_owned_file(destination, owned)
        raise ExperimentError("artifact destination could not be closed safely") from exc
    if not _owned_file_matches(destination, owned):
        _cleanup_owned_file(destination, owned)
        raise ExperimentError("artifact destination changed during promotion")
    return owned


def _atomic_write_text(path: Path, text: str) -> None:
    if path.is_symlink():
        raise ExperimentError(f"output file cannot be a symlink: {path.name}")
    if path.exists() and not path.is_file():
        raise ExperimentError(f"output path must be a regular file: {path.name}")
    _directory(path.parent, label=f"parent of {path.name}")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    _atomic_write_text(path, text)


def _load_yaml(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ExperimentError(f"required record is missing or symlinked: {path.name}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ExperimentError(f"cannot read {path.name}: {exc}") from None


def _model_dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _parse_run(path: Path) -> RunRecord:
    try:
        return RunRecord.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ExperimentError(f"invalid run record: {exc}") from None


def _parse_attempt(path: Path) -> AttemptRecord:
    try:
        return AttemptRecord.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ExperimentError(f"invalid attempt record: {exc}") from None


def _parse_target(path: Path) -> TargetProfile:
    try:
        return TargetProfile.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ExperimentError(f"invalid target profile: {exc}") from None


def _parse_artifacts(path: Path) -> ArtifactManifest:
    try:
        return ArtifactManifest.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise ExperimentError(f"invalid artifact manifest: {exc}") from None


def _run_record(root: Path, run_id: str) -> tuple[Path, RunRecord]:
    run_directory = _run_directory(root, run_id)
    run = _parse_run(run_directory / "run.yaml")
    if run.run_id != run_id:
        raise ExperimentError("run identity does not match its path")
    return run_directory, run


def _attempt_record(
    root: Path,
    run_id: str,
    attempt_id: str,
) -> tuple[Path, RunRecord, Path, AttemptRecord]:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    run_directory, run = _run_record(root, run_id)
    attempts = _attempts_directory(run_directory)
    attempt_directory = _directory(
        attempts / attempt_id,
        label=f"attempt {attempt_id}",
    )
    attempt = _parse_attempt(attempt_directory / "attempt.yaml")
    if attempt.run_id != run_id or attempt.attempt_id != attempt_id:
        raise ExperimentError("attempt identity does not match its path")
    return run_directory, run, attempt_directory, attempt


def _target_record(root: Path, target_id: str) -> tuple[Path, TargetProfile]:
    _validate_slug(target_id, label="target_id")
    path = _targets_directory(root) / f"{target_id}.yaml"
    target = _parse_target(path)
    if target.target_id != target_id:
        raise ExperimentError("target filename and target_id disagree")
    return path, target


def _run_directories(root: Path) -> list[Path]:
    experiments = _experiments_directory(root)
    result: list[Path] = []
    for candidate in sorted(experiments.iterdir()):
        if candidate.is_symlink():
            raise ExperimentError(f"experiments entry cannot be a symlink: {candidate.name}")
        if candidate.name == "profiles":
            _directory(candidate, label="profiles")
            continue
        if candidate.name == "index.yaml":
            _required_file(candidate, label="experiment index")
            continue
        if candidate.is_dir():
            run_record = candidate / "run.yaml"
            if run_record.is_symlink():
                raise ExperimentError(f"run record cannot be a symlink: {candidate.name}")
            if run_record.exists():
                _validate_run_id(candidate.name)
                _required_file(run_record, label=f"run record {candidate.name}")
                result.append(candidate)
            elif RUN_ID_RE.fullmatch(candidate.name):
                raise ExperimentError(f"run record is missing: {candidate.name}")
        elif RUN_ID_RE.fullmatch(candidate.name):
            raise ExperimentError(f"run {candidate.name} must be a directory")
    return result


def _validate_artifact_tree(artifacts: Path) -> None:
    for path in artifacts.rglob("*"):
        relative = path.relative_to(artifacts).as_posix()
        if path.is_symlink():
            raise ExperimentError(f"artifact storage cannot contain a symlink: {relative}")
        if not path.is_dir() and not path.is_file():
            raise ExperimentError(f"artifact storage contains an unsupported path: {relative}")


def _git_commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ExperimentError("a formal Run requires an existing Git commit")
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        check=False,
        capture_output=True,
        text=True,
    )
    if dirty.returncode != 0:
        raise ExperimentError("cannot inspect the project Git worktree")
    if dirty.stdout.strip():
        raise ExperimentError("a formal Run requires a clean tracked Git worktree")
    return commit


def _snapshot(
    source: Path,
    destination: Path,
    root: Path,
    *,
    recorded_path: Path | None = None,
) -> FileSnapshot:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if _sha256(source) != _sha256(destination):
        raise ExperimentError(f"snapshot checksum mismatch for {source.name}")
    return FileSnapshot(
        path=(recorded_path or destination).relative_to(root).as_posix(),
        sha256=_sha256(destination),
    )


def _recipe_payload(run: RunRecord) -> dict[str, Any]:
    return {
        "commit": run.source.commit,
        "entrypoint_sha256": run.entrypoint.sha256,
        "config_sha256": run.config.sha256,
        "dataset": {
            "dataset_id": run.dataset.dataset_id,
            "version": run.dataset.version,
            "split": run.dataset.split,
            "manifest_sha256": run.dataset.manifest.sha256,
        },
        "seed": run.seed,
        "environment_sha256": run.environment.sha256,
    }


def _validate_run_files(root: Path, run: RunRecord) -> None:
    for label, snapshot in (
        ("entrypoint", run.entrypoint),
        ("config", run.config),
        ("dataset manifest", run.dataset.manifest),
        ("environment", run.environment),
    ):
        path = _inside_project(root, snapshot.path, label=label)
        if _sha256(path) != snapshot.sha256:
            raise ExperimentError(f"{label} no longer matches its recorded checksum")
    if _canonical_hash(_recipe_payload(run)) != run.recipe_hash:
        raise ExperimentError("run recipe_hash does not match its machine-neutral recipe")


@_locked_mutation
def create_run(
    project_root: str | Path,
    *,
    run_id: str,
    run_script: str | Path,
    resolved_config: str | Path,
    dataset_manifest: str | Path,
    dataset_id: str,
    dataset_version: str,
    dataset_split: str,
    seed: int,
    environment_definition: str | Path,
) -> RunRecord:
    root = _project_root(project_root)
    _validate_run_id(run_id)
    commit = _git_commit(root)
    sources = {
        "entrypoint": _inside_project(root, run_script, label="run script"),
        "config": _inside_project(root, resolved_config, label="resolved config"),
        "dataset": _inside_project(root, dataset_manifest, label="dataset manifest"),
        "environment": _inside_project(
            root, environment_definition, label="environment definition"
        ),
    }
    experiments = _experiments_directory(root)
    final = experiments / run_id
    if final.exists() or final.is_symlink():
        raise ExperimentError(f"run already exists: {run_id}")
    temporary = experiments / f".{run_id}.tmp-{uuid.uuid4().hex}"
    temporary.mkdir()
    try:
        entrypoint = _snapshot(
            sources["entrypoint"],
            temporary / "run.sh",
            root,
            recorded_path=final / "run.sh",
        )
        config = _snapshot(
            sources["config"],
            temporary / "inputs" / f"resolved-config{sources['config'].suffix}",
            root,
            recorded_path=final / "inputs" / f"resolved-config{sources['config'].suffix}",
        )
        dataset = _snapshot(
            sources["dataset"],
            temporary / "inputs" / f"dataset-manifest{sources['dataset'].suffix}",
            root,
            recorded_path=final / "inputs" / f"dataset-manifest{sources['dataset'].suffix}",
        )
        environment = _snapshot(
            sources["environment"],
            temporary / "inputs" / f"environment{sources['environment'].suffix}",
            root,
            recorded_path=final / "inputs" / f"environment{sources['environment'].suffix}",
        )
        draft = RunRecord(
            run_id=run_id,
            created_at=_now(),
            record_state="draft",
            source=SourceRecord(commit=commit),
            entrypoint=entrypoint,
            config=config,
            dataset=DatasetRecord(
                dataset_id=dataset_id,
                version=dataset_version,
                split=dataset_split,
                manifest=dataset,
            ),
            seed=seed,
            environment=environment,
            recipe_hash="0" * 64,
        )
        run = draft.model_copy(update={"recipe_hash": _canonical_hash(_recipe_payload(draft))})
        _atomic_write_yaml(temporary / "run.yaml", _model_dump(run))
        _atomic_write_text(temporary / "report.md", f"# Run {run_id}\n\n")
        _atomic_write_text(temporary / "notes.md", f"# Notes for {run_id}\n\n")
        _atomic_write_yaml(
            temporary / "artifacts.yaml",
            _model_dump(ArtifactManifest(run_id=run_id, artifacts=[])),
        )
        (temporary / "artifacts").mkdir()
        (temporary / "attempts").mkdir()
        os.replace(temporary, final)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return run


@_locked_mutation
def register_target(project_root: str | Path, spec_path: str | Path) -> TargetProfile:
    root = _project_root(project_root)
    source = _regular_file(Path(spec_path), label="target spec")
    try:
        target = TargetProfile.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise ExperimentError(f"invalid target profile: {exc}") from None
    _validate_slug(target.target_id, label="target_id")
    destination = _targets_directory(root) / f"{target.target_id}.yaml"
    if destination.is_symlink():
        raise ExperimentError("target destination cannot be a symlink")
    if destination.exists():
        existing = _parse_target(destination)
        if existing != target:
            raise ExperimentError(f"target profile already exists with different content: {target.target_id}")
        return existing
    _atomic_write_yaml(destination, _model_dump(target))
    return target


@_locked_mutation
def create_attempt(
    project_root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    target_id: str,
) -> AttemptRecord:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    _validate_slug(target_id, label="target_id")
    root = _project_root(project_root)
    run_directory, run = _run_record(root, run_id)
    run_path = run_directory / "run.yaml"
    _validate_run_files(root, run)
    target_path, _ = _target_record(root, target_id)
    attempts_root = _attempts_directory(run_directory)
    attempt_directory = attempts_root / attempt_id
    if attempt_directory.exists() or attempt_directory.is_symlink():
        raise ExperimentError(f"attempt already exists: {attempt_id}")
    attempt = AttemptRecord(
        attempt_id=attempt_id,
        run_id=run_id,
        target_id=target_id,
        target_profile_sha256=_sha256(target_path),
        status="planned",
        started_at=None,
        finished_at=None,
        exit_code=None,
        actual=ActualExecution(),
        output_inventory=None,
    )
    temporary = attempts_root / f".{attempt_id}.tmp-{uuid.uuid4().hex}"
    temporary.mkdir()
    original_run = run
    run_was_frozen = False
    try:
        target_snapshot = temporary / "target.yaml"
        shutil.copyfile(target_path, target_snapshot)
        if _sha256(target_snapshot) != attempt.target_profile_sha256:
            raise ExperimentError("target profile snapshot checksum mismatch")
        _atomic_write_yaml(temporary / "attempt.yaml", _model_dump(attempt))
        if run.record_state == "draft":
            run = run.model_copy(update={"record_state": "frozen"})
            _atomic_write_yaml(run_path, _model_dump(run))
            run_was_frozen = True
        os.replace(temporary, attempt_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if run_was_frozen:
            try:
                _atomic_write_yaml(run_path, _model_dump(original_run))
            except Exception as rollback_exc:
                raise ExperimentError(
                    "attempt publication failed and the Run freeze could not be rolled back"
                ) from rollback_exc
        raise
    return attempt


@_locked_mutation
def start_attempt(
    project_root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
) -> AttemptRecord:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    root = _project_root(project_root)
    _, _, attempt_directory, attempt = _attempt_record(root, run_id, attempt_id)
    attempt_path = attempt_directory / "attempt.yaml"
    if attempt.status != "planned":
        raise ExperimentError("only a planned Attempt can be started")
    running = attempt.model_copy(update={"status": "running", "started_at": _now()})
    _atomic_write_yaml(attempt_path, _model_dump(running))
    return running


@_locked_mutation
def finalize_attempt(
    project_root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    status: str,
    exit_code: int,
    actual: dict[str, Any],
    output_inventory: str | Path | None = None,
) -> AttemptRecord:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    if status not in {"succeeded", "failed", "interrupted"}:
        raise ExperimentError("final status must be succeeded, failed, or interrupted")
    if status == "succeeded" and exit_code != 0:
        raise ExperimentError("a succeeded attempt requires exit_code 0")
    root = _project_root(project_root)
    _, run, attempt_directory, attempt = _attempt_record(root, run_id, attempt_id)
    attempt_path = attempt_directory / "attempt.yaml"
    if attempt.status != "running" or attempt.started_at is None:
        raise ExperimentError("only a running Attempt can be finalized")
    try:
        actual_model = ActualExecution.model_validate(actual)
    except ValidationError as exc:
        raise ExperimentError(f"invalid actual execution record: {exc}") from None
    if actual_model.commit is not None and actual_model.commit != run.source.commit:
        raise ExperimentError("actual commit does not match the frozen Run")
    if actual_model.recipe_hash is not None and actual_model.recipe_hash != run.recipe_hash:
        raise ExperimentError("actual recipe hash does not match the frozen Run")

    inventory_snapshot: FileSnapshot | None = None
    inventory_destination: Path | None = None
    if output_inventory is not None:
        source = _regular_file(Path(output_inventory), label="output inventory")
        destination = attempt_path.parent / f"output-inventory{source.suffix}"
        if destination.exists() or destination.is_symlink():
            raise ExperimentError("attempt output inventory already exists")
        inventory_snapshot = _snapshot(source, destination, root)
        inventory_destination = destination
    finished = attempt.model_copy(
        update={
            "status": status,
            "started_at": attempt.started_at,
            "finished_at": _now(),
            "exit_code": exit_code,
            "actual": actual_model,
            "output_inventory": inventory_snapshot,
        }
    )
    try:
        _atomic_write_yaml(attempt_path, _model_dump(finished))
    except Exception:
        if inventory_destination is not None:
            try:
                inventory_destination.unlink(missing_ok=True)
            except OSError as rollback_exc:
                raise ExperimentError(
                    "Attempt finalization failed and its output inventory could not be rolled back"
                ) from rollback_exc
        raise
    return finished


def _attempt_exists(root: Path, run_id: str, attempt_id: str) -> None:
    _attempt_record(root, run_id, attempt_id)


def _artifact_manifest(root: Path, run_id: str) -> tuple[Path, ArtifactManifest]:
    run_directory, _ = _run_record(root, run_id)
    _artifacts_directory(run_directory)
    path = run_directory / "artifacts.yaml"
    manifest = _parse_artifacts(path)
    if manifest.run_id != run_id:
        raise ExperimentError("artifact manifest run_id does not match its path")
    return path, manifest


@_locked_mutation
def promote_artifact(
    project_root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    source: str | Path,
    destination: str,
    role: str,
    retention: str,
    remote_source: str | None = None,
) -> ArtifactRecord:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    if retention not in {"local-required", "local-selected"}:
        raise ExperimentError("promotion retention must be local-required or local-selected")
    root = _project_root(project_root)
    _attempt_exists(root, run_id, attempt_id)
    source_path = _regular_file(Path(source), label="artifact source")
    run_directory = _run_directory(root, run_id)
    artifacts_root = _artifacts_directory(run_directory)
    destination_path = _safe_destination(artifacts_root, destination)
    digest = _sha256(source_path)
    artifact_id = "art_" + _canonical_hash(
        {
            "run_id": run_id,
            "attempt_id": attempt_id,
            "destination": destination,
            "sha256": digest,
        }
    )[:16]
    manifest_path, manifest = _artifact_manifest(root, run_id)
    for existing in manifest.artifacts:
        if existing.artifact_id == artifact_id:
            return existing
        if existing.relative_path == f"artifacts/{Path(destination).as_posix()}":
            raise ExperimentError("artifact destination is already registered with different content")

    try:
        artifact = ArtifactRecord(
            artifact_id=artifact_id,
            role=role,
            retention=retention,
            source_attempt_id=attempt_id,
            relative_path=f"artifacts/{Path(destination).as_posix()}",
            size=source_path.stat().st_size,
            sha256=digest,
            remote_source=remote_source,
            promoted_at=_now(),
            backup=BackupRecord(),
        )
    except ValidationError as exc:
        raise ExperimentError(f"invalid artifact metadata: {exc}") from None

    _create_destination_parents(artifacts_root, destination_path)
    owned_destination = _copy_exclusive(
        source_path,
        destination_path,
        expected_sha256=digest,
    )
    if owned_destination.size != artifact.size:
        _cleanup_owned_file(destination_path, owned_destination)
        raise ExperimentError("artifact promotion size mismatch")
    updated = ArtifactManifest.model_validate(
        {
            **_model_dump(manifest),
            "artifacts": [
                *[_model_dump(existing) for existing in manifest.artifacts],
                _model_dump(artifact),
            ],
        }
    )
    try:
        _atomic_write_yaml(manifest_path, _model_dump(updated))
    except Exception:
        _cleanup_owned_file(destination_path, owned_destination)
        raise
    return artifact


@_locked_mutation
def record_manifest_only_artifact(
    project_root: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    remote_source: str,
    role: str,
) -> ArtifactRecord:
    _validate_run_id(run_id)
    _validate_slug(attempt_id, label="attempt_id")
    if not remote_source.strip():
        raise ExperimentError("manifest-only artifact requires a remote source")
    root = _project_root(project_root)
    _attempt_exists(root, run_id, attempt_id)
    artifact_id = "art_" + _canonical_hash(
        {
            "run_id": run_id,
            "attempt_id": attempt_id,
            "remote_source": remote_source,
            "role": role,
        }
    )[:16]
    manifest_path, manifest = _artifact_manifest(root, run_id)
    for existing in manifest.artifacts:
        if existing.artifact_id == artifact_id:
            return existing
    try:
        artifact = ArtifactRecord(
            artifact_id=artifact_id,
            role=role,
            retention="manifest-only",
            source_attempt_id=attempt_id,
            relative_path=None,
            size=None,
            sha256=None,
            remote_source=remote_source,
            promoted_at=None,
            backup=BackupRecord(),
        )
    except ValidationError as exc:
        raise ExperimentError(f"invalid artifact metadata: {exc}") from None
    updated = ArtifactManifest.model_validate(
        {
            **_model_dump(manifest),
            "artifacts": [
                *[_model_dump(existing) for existing in manifest.artifacts],
                _model_dump(artifact),
            ],
        }
    )
    _atomic_write_yaml(manifest_path, _model_dump(updated))
    return artifact


def validate_project(project_root: str | Path) -> dict[str, int]:
    root = _project_root(project_root)
    target_count = 0
    targets = _targets_directory(root)
    for target_path in sorted(targets.iterdir()):
        if target_path.is_symlink():
            raise ExperimentError(
                f"target profiles cannot contain a symlink: {target_path.name}"
            )
        if not target_path.is_file():
            raise ExperimentError(
                f"target profile entry must be a regular file: {target_path.name}"
            )
        if target_path.suffix != ".yaml":
            continue
        _validate_slug(target_path.stem, label="target_id")
        target = _parse_target(target_path)
        if target_path.stem != target.target_id:
            raise ExperimentError("target filename and target_id disagree")
        target_count += 1

    run_count = attempt_count = artifact_count = 0
    for discovered_run in _run_directories(root):
        run_id = _validate_run_id(discovered_run.name)
        run_directory, run = _run_record(root, run_id)
        _required_file(run_directory / "report.md", label="run report")
        _required_file(run_directory / "notes.md", label="run notes")
        _validate_run_files(root, run)

        artifacts = _artifacts_directory(run_directory)
        _validate_artifact_tree(artifacts)
        _, manifest = _artifact_manifest(root, run_id)
        for artifact in manifest.artifacts:
            _attempt_record(root, run_id, artifact.source_attempt_id)
            if artifact.relative_path is not None and artifact.sha256 is not None:
                relative = Path(artifact.relative_path)
                if not relative.parts or relative.parts[0] != "artifacts":
                    raise ExperimentError("promoted artifact must be stored under artifacts")
                local = _inside_project(
                    root,
                    run_directory / relative,
                    label="promoted artifact",
                )
                try:
                    local.relative_to(artifacts)
                except ValueError:
                    raise ExperimentError(
                        "promoted artifact must remain inside artifact storage"
                    ) from None
                if _sha256(local) != artifact.sha256:
                    raise ExperimentError("promoted artifact checksum mismatch")
        artifact_count += len(manifest.artifacts)

        attempts = _attempts_directory(run_directory)
        for attempt_directory in sorted(attempts.iterdir()):
            if attempt_directory.is_symlink():
                raise ExperimentError(
                    f"attempt cannot be a symlink: {attempt_directory.name}"
                )
            if not attempt_directory.is_dir():
                raise ExperimentError(
                    f"attempt entry must be a directory: {attempt_directory.name}"
                )
            attempt_id = _validate_slug(
                attempt_directory.name,
                label="attempt_id",
            )
            _, _, checked_directory, attempt = _attempt_record(
                root,
                run_id,
                attempt_id,
            )
            target_snapshot = checked_directory / "target.yaml"
            snapshotted_target = _parse_target(target_snapshot)
            if snapshotted_target.target_id != attempt.target_id:
                raise ExperimentError("attempt Target snapshot identity disagrees")
            if _sha256(target_snapshot) != attempt.target_profile_sha256:
                raise ExperimentError("attempt target snapshot hash no longer matches")
            if attempt.output_inventory is not None:
                inventory = _inside_project(
                    root,
                    attempt.output_inventory.path,
                    label="attempt output inventory",
                )
                try:
                    inventory.relative_to(checked_directory)
                except ValueError:
                    raise ExperimentError(
                        "attempt output inventory must remain inside its Attempt"
                    ) from None
                if _sha256(inventory) != attempt.output_inventory.sha256:
                    raise ExperimentError("attempt output inventory checksum mismatch")
            attempt_count += 1
        run_count += 1
    return {
        "runs": run_count,
        "attempts": attempt_count,
        "targets": target_count,
        "artifacts": artifact_count,
    }


@_locked_mutation
def rebuild_index(project_root: str | Path) -> dict[str, Any]:
    root = _project_root(project_root)
    validate_project(root)
    records: list[dict[str, Any]] = []
    for run_directory in _run_directories(root):
        run_id = _validate_run_id(run_directory.name)
        _, run = _run_record(root, run_id)
        attempts = [
            _attempt_record(root, run_id, path.name)[3]
            for path in sorted(_attempts_directory(run_directory).iterdir())
        ]
        records.append(
            {
                "run_id": run.run_id,
                "created_at": run.created_at.isoformat(),
                "record_state": run.record_state,
                "recipe_hash": run.recipe_hash,
                "attempts": [
                    {"attempt_id": attempt.attempt_id, "status": attempt.status}
                    for attempt in attempts
                ],
            }
        )
    index = {"schema_version": 1, "generated_from": "experiments/*/run.yaml", "runs": records}
    path = _experiments_directory(root) / "index.yaml"
    rendered = yaml.safe_dump(index, allow_unicode=True, sort_keys=False)
    if not path.exists() or path.read_text(encoding="utf-8") != rendered:
        _atomic_write_text(path, rendered)
    return index


def legacy_migration_plan(project_root: str | Path) -> dict[str, Any]:
    root = _project_root(project_root)
    experiments = _experiments_directory(root)
    result: list[dict[str, Any]] = []
    for candidate in sorted(experiments.iterdir()):
        if candidate.is_symlink():
            raise ExperimentError(f"experiments entry cannot be a symlink: {candidate.name}")
        if not candidate.is_dir():
            continue
        if candidate.name == "profiles" or (candidate / "run.yaml").exists():
            continue
        scripts = sorted(path.name for path in candidate.glob("*.sh") if path.is_file())
        configs = sorted(
            path.name
            for suffix in ("*.json", "*.yaml", "*.yml", "*.toml")
            for path in candidate.glob(suffix)
            if path.is_file()
        )
        unresolved = []
        if len(scripts) != 1:
            unresolved.append("expected exactly one run script")
        if len(configs) != 1:
            unresolved.append("expected exactly one config")
        result.append(
            {
                "legacy_directory": candidate.name,
                "scripts": scripts,
                "configs": configs,
                "state": "candidate" if not unresolved else "unresolved",
                "unresolved": unresolved,
            }
        )
    return {"project_root": str(root), "write_performed": False, "experiments": result}
