"""Prepare bounded recovery material before activating a collection update.

This module does not replace archive files or create an active update marker.
Packages are recovery material, not verified backups or proof of execution.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import uuid
from pathlib import Path

from .collection import _sha, _tree
from .layout import ProjectLayoutError, open_project_root
from .management import PROJECT_MANAGEMENT
from .reception import ReceptionError, _directory, _read_file, _write_file
from .updates import plan_run_update

_BASELINES = ("parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256")
_STORE = ".scholar-workflow/collection-transactions"


def _check(plan, expected):
    if tuple(plan[key] for key in _BASELINES) != expected:
        raise ReceptionError("Update preview is stale; generate a new preview", 5)


def _json(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def _capture(root_fd, path, limit):
    """Capture bytes and the original inode without accepting a replaced path."""
    parent, _, name = path.rpartition("/")
    with _directory(root_fd, parent) as directory:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
        data, mode = _read_file(root_fd, path, limit)
        after = os.stat(name, dir_fd=directory, follow_symlinks=False)
        signature = lambda info: (info.st_dev, info.st_ino, info.st_size,
                                  info.st_mtime_ns, info.st_ctime_ns, info.st_mode)
        if signature(before) != signature(after):
            raise ReceptionError("Archive file changed while preparing recovery material", 5)
        return data, mode, before


def _save(stage_fd, name, data, mode, original=None):
    _write_file(stage_fd, name, data, mode)
    readback, actual_mode = _read_file(stage_fd, name, len(data))
    if readback != data or actual_mode != mode:
        raise ReceptionError("Recovery material failed read-back verification")
    with _directory(stage_fd, name.rpartition("/")[0]) as directory:
        info = os.stat(name.rpartition("/")[2], dir_fd=directory, follow_symlinks=False)
    result = {"path": name, "sha256": _sha(data), "size": len(data), "mode": mode,
              "device": info.st_dev, "inode": info.st_ino}
    if original is not None:
        result.update(original_device=original.st_dev, original_inode=original.st_ino)
    return result


def stage_run_update(
    parent_root: str | Path, child_root: str | Path, *, run_id: str,
    expected_parent_sha256: str, expected_child_sha256: str,
    expected_new_evidence_sha256: str, expected_local_receipt_sha256: str,
):
    """Stage exact before/after changes; leave the current archive untouched.

    Incomplete packages are retained at a reported, explicit path. They are never
    activated, silently adopted, or automatically deleted. A later writer must
    revalidate the journal and current ownership before installing any payload.
    """
    expected = (expected_parent_sha256, expected_child_sha256,
                expected_new_evidence_sha256, expected_local_receipt_sha256)
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in expected):
        raise ReceptionError("Update staging requires all four preview SHA-256 baselines", 2)
    plan = plan_run_update(parent_root, child_root, run_id=run_id)
    _check(plan, expected)
    if plan["status"] == "unchanged":
        return {"status": "unchanged", "destination": plan["destination"]}
    package_path = None
    try:
        with open_project_root(parent_root) as root_fd:
            lock = os.open(PROJECT_MANAGEMENT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                           dir_fd=root_fd)
            try:
                held = os.fstat(lock)
                if not stat.S_ISREG(held.st_mode):
                    raise ReceptionError("Parent declaration is unsafe")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ReceptionError("Parent is busy; preview again before retrying", 5) from None
                _check(plan_run_update(parent_root, child_root, run_id=run_id), expected)
                files, directories, modes = _tree(child_root, run_id)
                receipt = plan["new_receipt"]
                if set(files) != {row["source_path"] for row in receipt["files"]} or sorted(directories) != receipt["directories"]:
                    raise ReceptionError("Source tree changed before recovery staging", 5)
                for row in receipt["files"]:
                    content = files[row["source_path"]]
                    if (_sha(content), len(content), modes[row["source_path"]]) != (row["sha256"], row["size"], row["mode"]):
                        raise ReceptionError("Source bytes changed before recovery staging", 5)
                with _directory(root_fd, _STORE, create=True) as store_fd:
                    transaction_id = "tx-" + uuid.uuid4().hex
                    os.mkdir(transaction_id, 0o700, dir_fd=store_fd)
                    package_path = f"{_STORE}/{transaction_id}"
                    with _directory(store_fd, transaction_id) as stage_fd, _directory(root_fd, plan["destination"]) as run_fd:
                        if os.fstat(stage_fd).st_dev != os.fstat(run_fd).st_dev:
                            raise ReceptionError("Recovery material and archive must share a filesystem")
                        actions = []
                        rows = [(row["destination_path"], row["old"], files[row["source_path"]], row["new"]["mode"])
                                for row in plan["changes"]]
                        rows.append((".collection.json", {"size": 1024 * 1024}, _json(receipt), 0o600))
                        for index, (destination, old, content, mode) in enumerate(rows):
                            before = None
                            if old is not None:
                                previous, previous_mode, info = _capture(run_fd, destination, old["size"])
                                if destination == ".collection.json":
                                    if _sha(previous) != plan["local_receipt_sha256"]:
                                        raise ReceptionError("Local receipt changed during staging", 5)
                                elif (_sha(previous), len(previous), previous_mode) != (old["sha256"], old["size"], old["mode"]):
                                    raise ReceptionError("Local evidence changed during staging", 5)
                                before = _save(stage_fd, f"before/{index}", previous, previous_mode, info)
                            after = _save(stage_fd, f"after/{index}", content, mode)
                            actions.append({"destination_path": destination, "before": before, "after": after})
                        final = plan_run_update(parent_root, child_root, run_id=run_id)
                        _check(final, expected)
                        if final != plan:
                            raise ReceptionError("Update plan changed during staging", 5)
                        for action in actions:
                            before = action["before"]
                            if before is not None:
                                data, mode, info = _capture(run_fd, action["destination_path"], before["size"])
                                if (_sha(data), mode, info.st_dev, info.st_ino) != (
                                    before["sha256"], before["mode"], before["original_device"], before["original_inode"],
                                ):
                                    raise ReceptionError("Original ownership changed during staging", 5)
                        with open_project_root(parent_root) as current_root, _directory(root_fd, plan["destination"]) as current_run:
                            for current, original in ((current_root, root_fd), (current_run, run_fd)):
                                a, b = os.fstat(current), os.fstat(original)
                                if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                                    raise ReceptionError("Archive location changed during staging", 5)
                        current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
                        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                            raise ReceptionError("Parent declaration changed during staging", 5)
                        journal = _json({"schema_version": 1, "transaction_id": transaction_id,
                                         "state": "prepared_not_applied", "plan": plan,
                                         "actions": actions, "backup_state": "not-verified"})
                        if len(journal) > 4 * 1024 * 1024:
                            raise ReceptionError("Update journal exceeds supported record size")
                        _write_file(stage_fd, "journal.json", journal, 0o600)
                        if _read_file(stage_fd, "journal.json", len(journal))[0] != journal:
                            raise ReceptionError("Update journal failed read-back verification")
                        with _directory(root_fd, package_path) as current_stage:
                            now, original = os.fstat(current_stage), os.fstat(stage_fd)
                            if (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino):
                                raise ReceptionError("Recovery package location changed during staging")
                        for action in actions:
                            for payload in (action["before"], action["after"]):
                                if payload is None:
                                    continue
                                data, mode, info = _capture(stage_fd, payload["path"], payload["size"])
                                if (_sha(data), len(data), mode, info.st_dev, info.st_ino) != (
                                    payload["sha256"], payload["size"], payload["mode"], payload["device"], payload["inode"],
                                ):
                                    raise ReceptionError("Recovery payload changed during staging")
                        os.fsync(stage_fd)
                    os.fsync(store_fd)
                    with _directory(root_fd, ".scholar-workflow") as state_fd:
                        os.fsync(state_fd)
                    os.fsync(root_fd)
                    return {"status": "staged_not_applied", "package_path": package_path,
                            "journal_sha256": _sha(journal), "destination": plan["destination"],
                            "backup_state": "not-verified"}
            finally:
                os.close(lock)
    except (OSError, ValueError) as error:
        if package_path is not None:
            raise ReceptionError(
                f"Update not activated; preparation incomplete or durability unconfirmed; review {package_path}", 6,
            ) from error
        if isinstance(error, ReceptionError):
            raise
        if isinstance(error, (OSError, ProjectLayoutError)):
            raise ReceptionError("Recovery staging refused an unsafe storage location") from None
        raise
