"""Journalled collection updates and explicit local-only commit/rollback recovery."""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager

from .collected import _validate_receipt
from .collection import COLLECTION_UPDATE_MARKER, _sha, validate_run_evidence
from .layout import _unique_json_object, open_project_root, read_project_bytes
from .management import PROJECT_MANAGEMENT, load_project_management
from .models import RUN_ID
from .reception import ReceptionError, _directory, _read_file, _write_file
from .update_package import _BASELINES, _STORE, _capture, _check, _json, stage_run_update
from .updates import _transitions, plan_run_update


def _fail(message):
    raise ReceptionError(message, 5)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_json_object)
    except (ValueError, UnicodeError):
        _fail("Malformed update journal or marker")


def _location(parent_root, child_id, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(RUN_ID, run_id):
        _fail("Invalid selected Run identity")
    management = load_project_management(parent_root)
    child = next((row for row in management.children if row.project_id == child_id), None)
    if management.kind != "research-parent" or child is None:
        _fail("Recovery requires an explicitly registered child of a research parent")
    return management.project_id, f"experiments/{child.archive_segment}/{run_id}"


@contextmanager
def _locked(parent_root):
    with open_project_root(parent_root) as root_fd:
        baseline = read_project_bytes(parent_root, PROJECT_MANAGEMENT)
        descriptor = os.open(PROJECT_MANAGEMENT, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                             dir_fd=root_fd)
        try:
            held = os.fstat(descriptor)
            if not stat.S_ISREG(held.st_mode):
                _fail("Parent declaration is unsafe")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                _fail("Parent is busy; regenerate the preview before retrying")
            def check():
                current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino) or read_project_bytes(parent_root, PROJECT_MANAGEMENT) != baseline:
                    _fail("Parent declaration changed during the update")
                with open_project_root(parent_root) as now:
                    a, b = os.fstat(now), os.fstat(root_fd)
                    if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                        _fail("Parent location changed during the update")
            check()
            yield root_fd, baseline, check
        finally:
            os.close(descriptor)


def _marker(run_fd):
    raw, _ = _read_file(run_fd, COLLECTION_UPDATE_MARKER, 1024)
    marker = _decode(raw)
    if (not isinstance(marker, dict) or set(marker) != {"schema_version", "transaction_id", "journal_sha256"}
            or type(marker["schema_version"]) is not int or marker["schema_version"] != 1
            or not isinstance(marker["transaction_id"], str)
            or not re.fullmatch(r"tx-[0-9a-f]{32}", marker["transaction_id"])
            or not _hash(marker["journal_sha256"])):
        _fail("Unknown update marker; no recovery operation was inferred")
    return raw, marker


def _load(stage_fd, transaction_id, digest):
    raw, _ = _read_file(stage_fd, "journal.json", 4 * 1024 * 1024)
    if _sha(raw) != digest:
        _fail("Update journal differs from the selected digest")
    journal = _decode(raw)
    if (not isinstance(journal, dict)
            or set(journal) != {"schema_version", "transaction_id", "state", "plan", "actions", "backup_state"}
            or type(journal["schema_version"]) is not int or journal["schema_version"] != 1
            or journal["transaction_id"] != transaction_id
            or journal["state"] != "prepared_not_applied" or journal["backup_state"] != "not-verified"
            or not isinstance(journal["plan"], dict) or not isinstance(journal["actions"], list)
            or not journal["actions"]):
        _fail("Unknown update package format")
    for index, action in enumerate(journal["actions"]):
        if not isinstance(action, dict) or set(action) != {"destination_path", "before", "after"}:
            _fail("Invalid journal action")
        for side in ("before", "after"):
            value = action[side]
            if side == "before" and value is None:
                continue
            keys = {"path", "sha256", "size", "mode", "device", "inode"}
            if side == "before":
                keys |= {"original_device", "original_inode"}
            if (not isinstance(value, dict) or set(value) != keys or value["path"] != f"{side}/{index}"
                    or not _hash(value["sha256"])
                    or any(type(value[key]) is not int or value[key] < 0 for key in keys - {"path", "sha256"})
                    or value["size"] > 128 * 1024 * 1024 or value["mode"] > 0o777):
                _fail("Unsafe update payload record")
            data, mode, info = _capture(stage_fd, value["path"], value["size"])
            if (_sha(data), len(data), mode, info.st_dev, info.st_ino) != (
                value["sha256"], value["size"], value["mode"], value["device"], value["inode"],
            ):
                _fail("Update recovery payload changed")
    return journal


def _state(run_fd, action):
    try:
        limit = max(item["size"] for item in (action["before"], action["after"]) if item is not None)
        data, mode, info = _capture(run_fd, action["destination_path"], limit)
    except FileNotFoundError:
        if action["before"] is None:
            return "absent"
        _fail("Previously collected execution evidence is missing")
    signature = (_sha(data), len(data), mode, info.st_dev, info.st_ino)
    for side in ("before", "after"):
        item = action[side]
        if item is None:
            continue
        common = (item["sha256"], item["size"], item["mode"])
        owned = {(item["device"], item["inode"])}
        if side == "before":
            owned.add((item["original_device"], item["original_inode"]))
        if signature[:3] == common and signature[3:] in owned:
            return side
    _fail("Execution file has unknown local changes or ownership; nothing overwritten")


def _observe(journal, stage_fd, run_fd, *, parent_id, child_id, run_id, destination):
    """Validate both full versions and exact ownership before any recovery write."""
    plan, actions = journal["plan"], journal["actions"]
    required = {"schema_version", "status", "parent_project_id", "child_project_id", "run_id", "destination",
                "parent_sha256", "child_sha256", "local_receipt_sha256", "old_evidence_sha256",
                "new_evidence_sha256", "new_receipt", "changes", "new_directories", "transitions",
                "artifact_transitions", "execution_verification"}
    if (set(plan) != required or type(plan["schema_version"]) is not int or plan["schema_version"] != 1
            or plan["status"] != "planned_update" or plan["execution_verification"] != "records_only"
            or (plan["parent_project_id"], plan["child_project_id"], plan["run_id"], plan["destination"]) !=
               (parent_id, child_id, run_id, destination)
            or any(not _hash(plan[key]) for key in (*_BASELINES, "old_evidence_sha256"))):
        _fail("Update plan identity, scope or baseline is invalid")
    last = actions[-1]
    if last["destination_path"] != ".collection.json" or last["before"] is None:
        _fail("Update receipt must be the final replacement action")
    if last["after"]["mode"] != 0o600 or any(last[side]["size"] > 1024 * 1024 for side in ("before", "after")):
        _fail("Update receipt has invalid permissions or size")
    old_raw = _read_file(stage_fd, last["before"]["path"], 1024 * 1024)[0]
    new_raw = _read_file(stage_fd, last["after"]["path"], 1024 * 1024)[0]
    old, new = _decode(old_raw), _decode(new_raw)
    for receipt in (old, new):
        _validate_receipt(receipt, parent_id, child_id, run_id)
    if (_sha(old_raw) != plan["local_receipt_sha256"] or old["evidence_sha256"] != plan["old_evidence_sha256"]
            or new["evidence_sha256"] != plan["new_evidence_sha256"] or new != plan["new_receipt"]):
        _fail("Prepared receipts differ from the update baselines")
    old_rows = {row["source_path"]: row for row in old["files"]}
    new_rows = {row["source_path"]: row for row in new["files"]}
    if not set(old_rows).issubset(new_rows) or not set(old["directories"]).issubset(new["directories"]):
        _fail("Journal would remove previously collected execution evidence")
    changes = [{"source_path": source, "destination_path": row["destination_path"],
                "kind": "replace" if source in old_rows else "add", "old": old_rows.get(source), "new": row}
               for source, row in sorted(new_rows.items()) if old_rows.get(source) != row]
    if plan["changes"] != changes or plan["new_directories"] != sorted(set(new["directories"]) - set(old["directories"])):
        _fail("Journal change set does not match the complete receipt inventories")
    if [row["destination_path"] for row in actions] != [row["destination_path"] for row in changes] + [".collection.json"]:
        _fail("Journal contains an unowned, omitted or reordered action")
    for change, action in zip(changes, actions):
        for side, row in (("before", change["old"]), ("after", change["new"])):
            item = action[side]
            if (row is None) != (item is None) or (row is not None and
                    any(row[key] != item[key] for key in ("sha256", "size", "mode"))):
                _fail("Journal payload differs from its declared execution ownership")
    states = [_state(run_fd, action) for action in actions]
    for directory in plan["new_directories"]:
        try:
            with _directory(run_fd, directory):
                pass
        except FileNotFoundError:
            continue
    changed = {action["destination_path"]: action for action in actions[:-1]}
    versions = []
    for side, receipt in (("before", old), ("after", new)):
        files = {}
        for directory in old["directories"]:
            with _directory(run_fd, directory):
                pass
        for row in receipt["files"]:
            action = changed.get(row["destination_path"])
            if action is not None:
                item = action[side]
                if item is None:
                    _fail("Missing version payload")
                data, mode = _read_file(stage_fd, item["path"], row["size"])
            else:
                data, mode = _read_file(run_fd, row["destination_path"], row["size"])
            if (_sha(data), len(data), mode) != (row["sha256"], row["size"], row["mode"]):
                _fail("Unchanged execution evidence differs from the prepared versions")
            files[row["source_path"]] = data
        run, attempts, artifacts = validate_run_evidence(files, set(receipt["directories"]), run_id)
        if run.source.commit != receipt["source_commit"] or run.recipe_hash != receipt["recipe_hash"]:
            _fail("Prepared evidence differs from its receipt recipe")
        versions.append((files, run, attempts, artifacts))
    a, b = versions
    transitions, artifacts = _transitions(a[1], b[1], a[0], b[0], a[2], b[2], a[3], b[3])
    if transitions != plan["transitions"] or artifacts != plan["artifact_transitions"]:
        _fail("Prepared lifecycle changes differ from the validated evidence")
    _temporary_states(journal, run_fd)
    return states


def _temp(journal, index, direction):
    return f".collection-{journal['transaction_id']}-{index}-{direction}"


def _temporary_states(journal, run_fd, *, cleanup=False):
    observed = []
    for index, action in enumerate(journal["actions"]):
        parent = action["destination_path"].rpartition("/")[0]
        for direction, side in (("commit", "after"), ("rollback", "before")):
            name = _temp(journal, index, direction)
            try:
                with _directory(run_fd, parent) as directory:
                    try:
                        os.stat(name, dir_fd=directory, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    item = action[side]
                    if item is None:
                        _fail("Unknown temporary file blocks recovery")
                    data, mode, info = _capture(directory, name, item["size"])
                    if (_sha(data), len(data), mode, info.st_dev, info.st_ino) != (
                        item["sha256"], item["size"], item["mode"], item["device"], item["inode"],
                    ):
                        _fail("Unknown temporary file blocks recovery")
                    observed.append((index, direction))
                    if cleanup:
                        os.unlink(name, dir_fd=directory)
                        os.fsync(directory)
            except FileNotFoundError:
                continue
    return observed


def _check_locations(root_fd, destination, run_fd, stage_path, stage_fd):
    for path, original in ((destination, run_fd), (stage_path, stage_fd)):
        with _directory(root_fd, path) as current:
            a, b = os.fstat(current), os.fstat(original)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                _fail("Run or recovery package location changed")


def _install_action(stage_fd, run_fd, journal, index, direction):
    action = journal["actions"][index]
    state = _state(run_fd, action)
    side = "after" if direction == "commit" else "before"
    desired = action[side]
    if state == side or (desired is None and state == "absent"):
        return
    parent, _, name = action["destination_path"].rpartition("/")
    with _directory(run_fd, parent, create=direction == "commit") as directory:
        if desired is None:
            if _state(run_fd, action) != "after":
                _fail("New execution file no longer belongs to this update")
            os.unlink(name, dir_fd=directory)  # The same bytes remain in the recovery package.
        else:
            source_parent, _, source_name = desired["path"].rpartition("/")
            temporary = _temp(journal, index, direction)
            with _directory(stage_fd, source_parent) as source:
                try:
                    os.link(source_name, temporary, src_dir_fd=source, dst_dir_fd=directory,
                            follow_symlinks=False)
                except FileExistsError:
                    pass
                data, mode, info = _capture(directory, temporary, desired["size"])
                if (_sha(data), len(data), mode, info.st_dev, info.st_ino) != (
                    desired["sha256"], desired["size"], desired["mode"], desired["device"], desired["inode"],
                ):
                    _fail("Unknown or changed temporary payload blocks recovery")
            # All writers cooperate under the parent lock; external editors must be quiescent.
            if _state(run_fd, action) != state:
                _fail("Execution file changed immediately before installation")
            if state == "absent":
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory,
                        follow_symlinks=False)
                os.unlink(temporary, dir_fd=directory)
            else:
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)


def _sync_dirs(root_fd, run_fd, plan):
    for path in sorted(plan["new_receipt"]["directories"], key=lambda value: value.count("/"), reverse=True):
        try:
            with _directory(run_fd, path) as directory:
                os.fsync(directory)
        except FileNotFoundError:
            # Rollback does not remove newly created directories or require absent ones.
            continue
    os.fsync(run_fd)
    for path in (plan["destination"].rsplit("/", 1)[0], "experiments"):
        with _directory(root_fd, path) as directory:
            os.fsync(directory)
    os.fsync(root_fd)


def _finish(root_fd, run_fd, journal, stage_fd, marker_raw, direction, check):
    plan = journal["plan"]
    identity = {key: plan[key] for key in ("run_id", "destination")}
    identity.update(parent_id=plan["parent_project_id"], child_id=plan["child_project_id"])
    def check_all():
        check()
        _check_locations(root_fd, plan["destination"], run_fd,
                         f"{_STORE}/{journal['transaction_id']}", stage_fd)
    _observe(journal, stage_fd, run_fd, **identity)
    check_all()
    if direction == "commit":
        for directory in plan["new_directories"]:
            with _directory(run_fd, directory, create=True) as descriptor:
                os.fsync(descriptor)
    for index in range(len(journal["actions"])):
        check_all()
        if _read_file(run_fd, COLLECTION_UPDATE_MARKER, 1024)[0] != marker_raw:
            _fail("Active update marker changed")
        _install_action(stage_fd, run_fd, journal, index, direction)
    states = _observe(journal, stage_fd, run_fd, **identity)
    for state, action in zip(states, journal["actions"]):
        expected = "after" if direction == "commit" else ("before" if action["before"] else "absent")
        if state != expected:
            _fail("Update did not reach the selected version")
    check_all()
    with _directory(root_fd, plan["destination"]) as now:
        a, b = os.fstat(now), os.fstat(run_fd)
        if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
            _fail("Run location changed before completion")
    if _read_file(run_fd, COLLECTION_UPDATE_MARKER, 1024)[0] != marker_raw:
        _fail("Active update marker changed before completion")
    _temporary_states(journal, run_fd, cleanup=True)
    _sync_dirs(root_fd, run_fd, plan)
    os.unlink(COLLECTION_UPDATE_MARKER, dir_fd=run_fd)
    _sync_dirs(root_fd, run_fd, plan)


def apply_run_update(parent_root, child_root, *, run_id, **baselines):
    """Prepare, activate and apply one explicitly previewed Run version."""
    staged = stage_run_update(parent_root, child_root, run_id=run_id, **baselines)
    if staged["status"] == "unchanged":
        try:
            with _locked(parent_root) as (root_fd, _, check):
                plan = plan_run_update(parent_root, child_root, run_id=run_id)
                _check(plan, tuple(baselines["expected_" + key] for key in _BASELINES))
                with _directory(root_fd, plan["destination"]) as run_fd:
                    check()
                    _sync_dirs(root_fd, run_fd, plan)
            return staged
        except (OSError, ValueError) as error:
            raise ReceptionError("Unchanged archive durability is unconfirmed; inspect before retrying", 6) from error
    active = False
    try:
        with _locked(parent_root) as (root_fd, _, check):
            plan = plan_run_update(parent_root, child_root, run_id=run_id)
            _check(plan, tuple(baselines["expected_" + key] for key in _BASELINES))
            transaction_id = staged["package_path"].rsplit("/", 1)[1]
            with _directory(root_fd, staged["package_path"]) as stage_fd, _directory(root_fd, plan["destination"]) as run_fd:
                journal = _load(stage_fd, transaction_id, staged["journal_sha256"])
                if journal["plan"] != plan:
                    _fail("Prepared update no longer matches the current preview")
                states = _observe(journal, stage_fd, run_fd, parent_id=plan["parent_project_id"],
                                  child_id=plan["child_project_id"], run_id=run_id, destination=plan["destination"])
                if any(state != ("before" if action["before"] else "absent")
                       for state, action in zip(states, journal["actions"])):
                    _fail("Update was already applied or its original ownership changed")
                marker_raw = _json({"schema_version": 1, "transaction_id": transaction_id,
                                    "journal_sha256": staged["journal_sha256"]})
                check()
                _check_locations(root_fd, plan["destination"], run_fd, staged["package_path"], stage_fd)
                active = True
                _write_file(run_fd, COLLECTION_UPDATE_MARKER, marker_raw, 0o600)
                _finish(root_fd, run_fd, journal, stage_fd, marker_raw, "commit", check)
        return {**staged, "status": "updated", "execution_verification": "records_only"}
    except (OSError, ValueError) as error:
        if active:
            raise ReceptionError("Update interrupted or durability unconfirmed; inspect explicit recovery before retrying", 6) from error
        raise


def _pending(root_fd, parent_id, child_id, run_id, destination, baseline):
    with _directory(root_fd, destination) as run_fd:
        raw, marker = _marker(run_fd)
        with _directory(root_fd, f"{_STORE}/{marker['transaction_id']}") as stage_fd:
            journal = _load(stage_fd, marker["transaction_id"], marker["journal_sha256"])
            states = _observe(journal, stage_fd, run_fd, parent_id=parent_id, child_id=child_id,
                              run_id=run_id, destination=destination)
            temps = _temporary_states(journal, run_fd)
            if _observe(journal, stage_fd, run_fd, parent_id=parent_id, child_id=child_id,
                        run_id=run_id, destination=destination) != states:
                _fail("Execution evidence changed during recovery planning")
            _check_locations(root_fd, destination, run_fd, f"{_STORE}/{marker['transaction_id']}", stage_fd)
            revision = _sha(_json({"marker": _sha(raw), "declaration": _sha(baseline),
                                   "states": states, "temporary_links": temps}))
            if _read_file(run_fd, COLLECTION_UPDATE_MARKER, 1024)[0] != raw:
                _fail("Update marker changed during recovery planning")
            return raw, marker, journal, states, revision


def plan_run_recovery(parent_root, *, child_project_id, run_id):
    """Inspect only the selected local pending transaction; never infer a live worker."""
    parent_id, destination = _location(parent_root, child_project_id, run_id)
    baseline = read_project_bytes(parent_root, PROJECT_MANAGEMENT)
    try:
        with open_project_root(parent_root) as root_fd:
            _raw, marker, journal, states, revision = _pending(
                root_fd, parent_id, child_project_id, run_id, destination, baseline,
            )
            if read_project_bytes(parent_root, PROJECT_MANAGEMENT) != baseline:
                _fail("Parent declaration changed during recovery planning")
            return {"status": "pending_update", "destination": destination,
                    "transaction_id": marker["transaction_id"], "revision_sha256": revision,
                    "actions": [{"destination_path": action["destination_path"], "state": state}
                                for action, state in zip(journal["actions"], states)],
                    "backup_state": "not-verified", "execution_verification": "records_only"}
    except (OSError, ValueError) as error:
        if isinstance(error, ReceptionError):
            raise
        raise ReceptionError("Selected recovery material is missing, invalid or unsafe", 5) from error


def recover_run_update(parent_root, *, child_project_id, run_id, direction, expected_revision):
    """Commit or roll back a reviewed pending version without consulting the source."""
    if direction not in {"commit", "rollback"} or not _hash(expected_revision):
        raise ReceptionError("Recovery requires commit/rollback and a preview revision SHA-256", 2)
    active = False
    try:
        with _locked(parent_root) as (root_fd, baseline, check):
            parent_id, destination = _location(parent_root, child_project_id, run_id)
            raw, marker, journal, _states, revision = _pending(
                root_fd, parent_id, child_project_id, run_id, destination, baseline,
            )
            if revision != expected_revision:
                _fail("Recovery preview is stale; inspect the selected transaction again")
            with _directory(root_fd, destination) as run_fd, _directory(root_fd, f"{_STORE}/{marker['transaction_id']}") as stage_fd:
                check()
                active = True
                _finish(root_fd, run_fd, journal, stage_fd, raw, direction, check)
            return {"status": "committed" if direction == "commit" else "rolled_back",
                    "destination": destination, "transaction_id": marker["transaction_id"],
                    "backup_state": "not-verified", "execution_verification": "records_only",
                    "recovery_material_retained": True,
                    "new_empty_directories_may_remain": direction == "rollback"}
    except (OSError, ValueError) as error:
        if active:
            raise ReceptionError("Recovery interrupted or durability unconfirmed; inspect again before retrying", 6) from error
        if isinstance(error, ReceptionError):
            raise
        raise ReceptionError("Recovery refused missing, invalid or unsafe material", 5) from error
