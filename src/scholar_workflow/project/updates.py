"""Read-only lifecycle update planning; no archive overwrite or recovery execution."""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .collected import read_collected_evidence
from .collection import _record, _sha, _tree, plan_run_collection, validate_run_evidence
from .layout import open_project_root
from .models import AttemptRecord
from .reception import _directory, _read_file, _receipt


class UpdatePlanError(ValueError):
    """An update conflicts with recorded identity, lifecycle or ownership."""


def _probe(root_fd, path, *, directory=False):
    parent, _, name = path.rpartition("/")
    try:
        with _directory(root_fd, parent) as descriptor:
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        raise UpdatePlanError("Incoming path has an unsafe or conflicting local ancestor") from None
    if directory and not stat.S_ISDIR(info.st_mode):
        raise UpdatePlanError("Incoming directory collides with a local file or symlink")
    return True


def _transitions(old_run, new_run, old_files, new_files, old_attempts, new_attempts, old_artifacts, new_artifacts):
    old_recipe, new_recipe = old_run.model_dump(), new_run.model_dump()
    old_recipe.pop("record_state")
    new_recipe.pop("record_state")
    if old_recipe != new_recipe or (old_run.record_state == "frozen" and new_run.record_state != "frozen"):
        raise UpdatePlanError("Same Run cannot change its frozen recipe or source commit; use a new Run")
    old_ids = {row["attempt_id"] for row in old_attempts}
    new_ids = {row["attempt_id"] for row in new_attempts}
    if not old_ids.issubset(new_ids):
        raise UpdatePlanError("Previously collected Attempts cannot disappear")
    changes = []
    for identifier in sorted(new_ids):
        new = _record(new_files, f"attempts/{identifier}/attempt.yaml", AttemptRecord)
        if identifier not in old_ids:
            changes.append({"attempt_id": identifier, "from": None, "to": new.status})
            continue
        old = _record(old_files, f"attempts/{identifier}/attempt.yaml", AttemptRecord)
        if old.status in {"succeeded", "failed", "interrupted"} and old != new:
            raise UpdatePlanError("A completed Attempt cannot be silently rewritten; explicit correction is required")
        if old.status == "running" and new.status == "planned":
            raise UpdatePlanError("Attempt lifecycle cannot move backward")
        if (old.target_id, old.target_profile_sha256) != (new.target_id, new.target_profile_sha256):
            raise UpdatePlanError("An existing Attempt cannot change its frozen Target")
        if old.started_at is not None and old.started_at != new.started_at:
            raise UpdatePlanError("An existing start observation cannot be changed")
        if old.status != new.status:
            changes.append({"attempt_id": identifier, "from": old.status, "to": new.status})
    incoming = {item.artifact_id: item for item in new_artifacts.artifacts}
    artifact_changes = []
    old_artifact_ids = {item.artifact_id for item in old_artifacts.artifacts}
    for old in old_artifacts.artifacts:
        new = incoming.get(old.artifact_id)
        if new is None:
            raise UpdatePlanError("Previously recorded artifacts cannot disappear")
        if old == new:
            continue
        promotion = (
            old.retention == "manifest-only" and new.retention != "manifest-only"
            and (old.role, old.source_attempt_id, old.remote_source, old.backup) ==
                (new.role, new.source_attempt_id, new.remote_source, new.backup)
        )
        if not promotion:
            raise UpdatePlanError("An existing artifact fact changed; use an explicit new artifact or correction")
        artifact_changes.append({"artifact_id": old.artifact_id, "role": new.role,
                                 "source_attempt_id": new.source_attempt_id,
                                 "from": old.retention, "to": new.retention,
                                 "backup_state": new.backup.state})
    for new in new_artifacts.artifacts:
        if new.artifact_id not in old_artifact_ids:
            artifact_changes.append({"artifact_id": new.artifact_id, "role": new.role,
                                     "source_attempt_id": new.source_attempt_id,
                                     "from": None, "to": new.retention,
                                     "backup_state": new.backup.state})
    return changes, artifact_changes


def plan_run_update(parent_root: str | Path, child_root: str | Path, *, run_id: str):
    """Describe exact changes and byte baselines without creating locks, stages or files."""
    incoming = plan_run_collection(parent_root, child_root, run_id=run_id)
    new_files, new_directories, new_modes = _tree(child_root, run_id)
    if set(new_files) != {row["source_path"] for row in incoming["files"]} or sorted(new_directories) != incoming["directories"]:
        raise UpdatePlanError("Incoming source tree changed during update planning")
    for row in incoming["files"]:
        if (_sha(new_files[row["source_path"]]), len(new_files[row["source_path"]]), new_modes[row["source_path"]]) != (
            row["sha256"], row["size"], row["mode"],
        ):
            raise UpdatePlanError("Incoming source evidence changed during update planning")
    new_run, new_attempts, new_artifacts = validate_run_evidence(new_files, new_directories, run_id)
    namespace = incoming["destination"].rsplit("/", 1)[0]
    with open_project_root(parent_root) as root_fd, _directory(root_fd, namespace) as namespace_fd:
        raw_receipt, old_receipt, old_files, old_run, old_attempts, old_artifacts = read_collected_evidence(
            namespace_fd, incoming["parent_project_id"], incoming["child_project_id"], run_id,
        )
        transitions, artifact_transitions = _transitions(old_run, new_run, old_files, new_files, old_attempts,
                                                         new_attempts, old_artifacts, new_artifacts)
        old_rows = {row["source_path"]: row for row in old_receipt["files"]}
        new_rows = {row["source_path"]: row for row in incoming["files"]}
        if not set(old_rows).issubset(new_rows) or not set(old_receipt["directories"]).issubset(new_directories):
            raise UpdatePlanError("Previously collected evidence cannot be removed by lifecycle update")
        changes = []
        with _directory(namespace_fd, run_id) as run_fd:
            for directory in sorted(new_directories - set(old_receipt["directories"])):
                _probe(run_fd, directory, directory=True)
            for source, row in sorted(new_rows.items()):
                old = old_rows.get(source)
                if old is None and _probe(run_fd, row["destination_path"]):
                    raise UpdatePlanError("New execution file collides with unowned local content; nothing overwritten")
                if old is not None and old["destination_path"] != row["destination_path"]:
                    raise UpdatePlanError("An existing ownership mapping cannot change implicitly")
                if old != row:
                    changes.append({"source_path": source, "destination_path": row["destination_path"],
                                    "kind": "replace" if old else "add", "old": old, "new": row})
            if _read_file(run_fd, ".collection.json", 1024 * 1024)[0] != raw_receipt:
                raise UpdatePlanError("Local receipt changed during planning")
        again = read_collected_evidence(namespace_fd, incoming["parent_project_id"], incoming["child_project_id"], run_id)
        if again[0] != raw_receipt or again[2] != old_files:
            raise UpdatePlanError("Local execution evidence changed during planning")
        final = plan_run_collection(parent_root, child_root, run_id=run_id)
        keys = ("parent_sha256", "child_sha256", "evidence_sha256")
        if any(final[key] != incoming[key] for key in keys):
            raise UpdatePlanError("Incoming declaration or evidence changed during planning")
        with open_project_root(parent_root) as current_fd, _directory(root_fd, namespace) as current_namespace:
            for current, original in ((os.fstat(current_fd), os.fstat(root_fd)),
                                      (os.fstat(current_namespace), os.fstat(namespace_fd))):
                if (current.st_dev, current.st_ino) != (original.st_dev, original.st_ino):
                    raise UpdatePlanError("Local archive location changed during planning")
    return {
        "schema_version": 1, "status": "planned_update" if old_receipt["evidence_sha256"] != incoming["evidence_sha256"] else "unchanged",
        "parent_project_id": incoming["parent_project_id"], "child_project_id": incoming["child_project_id"],
        "run_id": run_id, "destination": incoming["destination"],
        "parent_sha256": incoming["parent_sha256"], "child_sha256": incoming["child_sha256"],
        "local_receipt_sha256": _sha(raw_receipt), "old_evidence_sha256": old_receipt["evidence_sha256"],
        "new_evidence_sha256": incoming["evidence_sha256"], "new_receipt": _receipt(incoming),
        "changes": changes, "new_directories": sorted(new_directories - set(old_receipt["directories"])),
        "transitions": transitions, "artifact_transitions": artifact_transitions,
        "execution_verification": "records_only",
    }
