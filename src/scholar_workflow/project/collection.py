"""Read-only, child-qualified preflight for one explicitly selected Run."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .experiments import _canonical_hash, _recipe_payload
from .layout import open_project_root, read_project_bytes
from .management import PROJECT_MANAGEMENT, load_project_management, validate_management_pair
from .models import RUN_ID, ArtifactManifest, AttemptRecord, RunRecord, TargetProfile

_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_MAX_BYTES = 128 * 1024 * 1024
COLLECTION_UPDATE_MARKER = ".collection-update.json"
COLLECTION_RESERVED = frozenset({".collection.json", COLLECTION_UPDATE_MARKER})


class CollectionPlanError(ValueError):
    """Selected evidence is unsafe, inconsistent, unavailable or changed."""


class _UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise CollectionPlanError("Duplicate fields in an execution record")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _tree(root: str | Path, run_id: str) -> tuple[dict[str, bytes], set[str], dict[str, int]]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    modes: dict[str, int] = {}
    total = 0

    def walk(descriptor, prefix):
        nonlocal total
        before = os.fstat(descriptor)
        for name in sorted(os.listdir(descriptor)):
            if "\\" in name:
                raise CollectionPlanError("Run paths cannot contain backslashes")
            relative = f"{prefix}/{name}" if prefix else name
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, _DIRECTORY, dir_fd=descriptor)
                try:
                    directories.add(relative)
                    walk(child, relative)
                    current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    opened = os.fstat(child)
                    if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                        raise CollectionPlanError("Run directory changed during inspection")
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                if total + info.st_size > _MAX_BYTES:
                    raise CollectionPlanError("Run exceeds the 128 MiB preflight limit; retain large data remotely")
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                        raise CollectionPlanError("Run file changed during inspection")
                    chunks = []
                    size = 0
                    while block := os.read(child, min(65536, info.st_size - size + 1)):
                        size += len(block)
                        if size > info.st_size:
                            raise CollectionPlanError("Run file grew during inspection")
                        chunks.append(block)
                    after = os.fstat(child)
                    current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                    ) or (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                        raise CollectionPlanError("Run file changed during inspection")
                    total += size
                    files[relative] = b"".join(chunks)
                    modes[relative] = stat.S_IMODE(info.st_mode)
                    if modes[relative] & 0o7000:
                        raise CollectionPlanError("Special execution permissions are not transferable")
                finally:
                    os.close(child)
            else:
                raise CollectionPlanError("Run contains a symlink or unsupported file type")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns,
        ):
            raise CollectionPlanError("Run directory changed during inspection")

    try:
        with open_project_root(root) as root_fd:
            experiments = os.open("experiments", _DIRECTORY, dir_fd=root_fd)
            try:
                selected = os.open(run_id, _DIRECTORY, dir_fd=experiments)
                try:
                    walk(selected, "")
                    current = os.stat(run_id, dir_fd=experiments, follow_symlinks=False)
                    opened = os.fstat(selected)
                    if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                        raise CollectionPlanError("Selected Run changed during inspection")
                finally:
                    os.close(selected)
            finally:
                os.close(experiments)
    except OSError:
        raise CollectionPlanError("Selected Run is missing, unsafe or changed during inspection") from None
    return files, directories, modes


def _record(files, name, model):
    try:
        if len(files[name]) > 1024 * 1024:
            raise CollectionPlanError("Execution record exceeds its 1 MiB limit")
        return model.model_validate(yaml.load(files[name], Loader=_UniqueLoader))
    except (KeyError, TypeError, ValueError, yaml.YAMLError, ValidationError):
        raise CollectionPlanError(f"Invalid or missing execution record: {name}") from None


def _relative(value: str) -> str:
    if not isinstance(value, str) or "\\" in value or any(p in {"", ".", ".."} for p in value.split("/")):
        raise CollectionPlanError("Evidence path must be a safe relative file path")
    return value


def _check_snapshot(files, snapshot, run_id, *, attempt_id=None):
    path = _relative(snapshot.path)
    prefix = f"experiments/{run_id}/"
    if not path.startswith(prefix):
        raise CollectionPlanError("Required evidence is outside the selected Run snapshot")
    relative = path.removeprefix(prefix)
    if attempt_id and not relative.startswith(f"attempts/{attempt_id}/"):
        raise CollectionPlanError("Output inventory is outside its Attempt")
    if relative not in files or _sha(files[relative]) != snapshot.sha256:
        raise CollectionPlanError("Required snapshot is missing or its checksum differs")


def validate_run_evidence(files: dict[str, bytes], directories: set[str], run_id: str):
    """Validate a captured Run using original child-relative evidence paths."""
    if not isinstance(run_id, str) or not re.fullmatch(RUN_ID, run_id):
        raise CollectionPlanError("Invalid Run identity")
    run = _record(files, "run.yaml", RunRecord)
    if run.run_id != run_id or run.record_state == "incomplete_legacy":
        raise CollectionPlanError("Run identity or formal recipe state is invalid")
    for snapshot in (run.entrypoint, run.config, run.dataset.manifest, run.environment):
        _check_snapshot(files, snapshot, run_id)
    if _canonical_hash(_recipe_payload(run)) != run.recipe_hash:
        raise CollectionPlanError("Run recipe hash differs from captured inputs")
    if not {"attempts", "artifacts"}.issubset(directories) or not {"report.md", "notes.md"}.issubset(files):
        raise CollectionPlanError("Required Run directories or execution notes are missing")
    attempts = []
    for directory in sorted(path for path in directories if path.startswith("attempts/") and path.count("/") == 1):
        identifier = directory.split("/")[1]
        attempt = _record(files, f"{directory}/attempt.yaml", AttemptRecord)
        target = _record(files, f"{directory}/target.yaml", TargetProfile)
        if attempt.run_id != run_id or attempt.attempt_id != identifier or target.target_id != attempt.target_id:
            raise CollectionPlanError("Attempt or Target identity differs from its recorded location")
        if _sha(files[f"{directory}/target.yaml"]) != attempt.target_profile_sha256:
            raise CollectionPlanError("Attempt Target snapshot checksum differs")
        if attempt.status == "planned":
            valid_time = attempt.started_at is None and attempt.finished_at is None and attempt.exit_code is None
        elif attempt.status == "running":
            valid_time = attempt.started_at is not None and attempt.finished_at is None and attempt.exit_code is None
        else:
            valid_time = (attempt.started_at is not None and attempt.finished_at is not None
                          and attempt.exit_code is not None)
            if valid_time:
                try:
                    valid_time = attempt.finished_at >= attempt.started_at
                except TypeError:
                    valid_time = False
            if attempt.status == "succeeded" and attempt.exit_code != 0:
                valid_time = False
        if not valid_time:
            raise CollectionPlanError("Attempt status, execution times or exit code disagree")
        if ((attempt.actual.commit is not None and attempt.actual.commit != run.source.commit)
                or (attempt.actual.recipe_hash is not None and attempt.actual.recipe_hash != run.recipe_hash)):
            raise CollectionPlanError("Actual execution differs from the frozen child recipe")
        if attempt.output_inventory:
            _check_snapshot(files, attempt.output_inventory, run_id, attempt_id=identifier)
        attempts.append({"attempt_id": identifier, "status": attempt.status,
                         "target_id": attempt.target_id, "exit_code": attempt.exit_code,
                         "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                         "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                         "actual_commit": attempt.actual.commit,
                         "actual_recipe_hash": attempt.actual.recipe_hash})
    if any(path.startswith("attempts/") and path.count("/") == 1 for path in files):
        raise CollectionPlanError("Attempt entries must be directories")
    if attempts and run.record_state != "frozen":
        raise CollectionPlanError("A Run with Attempts must have a frozen recipe")
    artifacts = _record(files, "artifacts.yaml", ArtifactManifest)
    if artifacts.run_id != run_id:
        raise CollectionPlanError("Artifact manifest Run identity differs")
    for artifact in artifacts.artifacts:
        if artifact.source_attempt_id not in {row["attempt_id"] for row in attempts}:
            raise CollectionPlanError("Artifact references an unknown Attempt")
        if artifact.relative_path is not None:
            relative = _relative(artifact.relative_path)
            if not relative.startswith("artifacts/") or relative not in files:
                raise CollectionPlanError("Local artifact is missing or outside artifact storage")
            if _sha(files[relative]) != artifact.sha256 or len(files[relative]) != artifact.size:
                raise CollectionPlanError("Local artifact checksum or size differs")
    return run, attempts, artifacts


def plan_run_collection(parent_root: str | Path, child_root: str | Path, *, run_id: str) -> dict[str, Any]:
    """Validate selected declared facts and produce path mapping, never receive or execute."""
    if not isinstance(run_id, str) or not re.fullmatch(RUN_ID, run_id):
        raise CollectionPlanError("Invalid Run identity")
    before = [read_project_bytes(root, PROJECT_MANAGEMENT) for root in (parent_root, child_root)]
    parent, child = load_project_management(parent_root), load_project_management(child_root)
    validate_management_pair(parent, child)
    entry = next(row for row in parent.children if row.project_id == child.project_id)
    files, directories, modes = _tree(child_root, run_id)
    if any(path.split("/", 1)[0] in COLLECTION_RESERVED for path in (*files, *directories)):
        raise CollectionPlanError("Source contains reserved collection transaction metadata")
    run, attempts, _ = validate_run_evidence(files, directories, run_id)
    mapped = []
    destinations = set()
    for name, data in sorted(files.items()):
        destination = {"report.md": "execution-report.md", "notes.md": "execution-notes.md"}.get(name, name)
        if destination in destinations:
            raise CollectionPlanError("Execution notes conflict with a destination filename")
        destinations.add(destination)
        mapped.append({"source_path": name, "destination_path": destination,
                       "sha256": _sha(data), "size": len(data), "mode": modes[name]})
    if _tree(child_root, run_id) != (files, directories, modes):
        raise CollectionPlanError("Run evidence changed during planning")
    if before != [read_project_bytes(root, PROJECT_MANAGEMENT) for root in (parent_root, child_root)]:
        raise CollectionPlanError("Parent or child declaration changed during planning")
    return {
        "schema_version": 1, "status": "planned_not_received", "parent_project_id": parent.project_id,
        "child_project_id": child.project_id, "run_id": run_id,
        "destination": f"experiments/{entry.archive_segment}/{run_id}",
        "source_commit": run.source.commit, "recipe_hash": run.recipe_hash,
        "parent_sha256": _sha(before[0]), "child_sha256": _sha(before[1]),
        "evidence_sha256": _sha(json.dumps({"files": mapped, "directories": sorted(directories)},
                                           sort_keys=True, separators=(",", ":")).encode()),
        "attempts": attempts, "files": mapped, "directories": sorted(directories),
        "execution_verification": "records_only",
        "mutable_execution": any(row["status"] in {"planned", "running"} for row in attempts),
    }
