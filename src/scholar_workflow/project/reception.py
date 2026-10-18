"""First reception of a selected child Run; no overwrite or lifecycle updates."""
from __future__ import annotations

import ctypes
import errno
import fcntl
import json
import os
import re
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

from .collection import (
    _DIRECTORY,
    COLLECTION_UPDATE_MARKER,
    _relative,
    _sha,
    _tree,
    plan_run_collection,
)
from .layout import ProjectLayoutError, _unique_json_object, open_project_root
from .management import PROJECT_MANAGEMENT

_RECEIPT = ".collection.json"


class ReceptionError(ValueError):
    """A failed, conflicted, unavailable or partially durable reception."""

    def __init__(self, message: str, exit_code: int = 7):
        super().__init__(message)
        self.exit_code = exit_code


@contextmanager
def _directory(root_fd, relative, *, create=False):
    descriptor = os.dup(root_fd)
    try:
        for part in _relative(relative).split("/") if relative else []:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, _DIRECTORY, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _write_file(root_fd, relative, data, mode):
    path = _relative(relative)
    parent, _, name = path.rpartition("/")
    with _directory(root_fd, parent, create=True) as directory:
        descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.fsync(directory)


def _read_file(root_fd, relative, limit):
    parent, _, name = _relative(relative).rpartition("/")
    with _directory(root_fd, parent) as directory:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ReceptionError("Collected evidence is not a bounded regular file", 5)
            chunks = []
            size = 0
            while block := os.read(descriptor, min(65536, limit - size + 1)):
                size += len(block)
                if size > limit:
                    raise ReceptionError("Collected evidence grew during inspection", 5)
                chunks.append(block)
            after = os.fstat(descriptor)
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns,
            ) or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
                raise ReceptionError("Collected evidence changed during inspection", 5)
            return b"".join(chunks), stat.S_IMODE(before.st_mode)
        finally:
            os.close(descriptor)


def _receipt(plan):
    keys = ("schema_version", "parent_project_id", "child_project_id", "run_id",
            "source_commit", "recipe_hash", "evidence_sha256", "files", "directories",
            "execution_verification")
    return {key: plan[key] for key in keys}


def require_no_pending_update(root_fd):
    try:
        os.stat(COLLECTION_UPDATE_MARKER, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise ReceptionError("A collection update or recovery is pending", 6)


def _existing(namespace_fd, run_id, plan):
    try:
        os.stat(run_id, dir_fd=namespace_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    with _directory(namespace_fd, run_id) as root_fd:
        require_no_pending_update(root_fd)
        try:
            content, _ = _read_file(root_fd, _RECEIPT, 1024 * 1024)
            receipt = json.loads(content, object_pairs_hook=_unique_json_object)
        except (OSError, ValueError):
            raise ReceptionError("Existing Run has no matching collection receipt; nothing overwritten", 5) from None
        if json.dumps(receipt, sort_keys=True, separators=(",", ":")) != json.dumps(
            _receipt(plan), sort_keys=True, separators=(",", ":"),
        ):
            raise ReceptionError("Existing Run differs; lifecycle update or recovery is required", 5)
        for directory in plan["directories"]:
            with _directory(root_fd, directory):
                pass
        for row in plan["files"]:
            content, mode = _read_file(root_fd, row["destination_path"], row["size"])
            if len(content) != row["size"] or _sha(content) != row["sha256"] or mode != row["mode"]:
                raise ReceptionError("Local execution evidence changed; nothing overwritten", 5)
        require_no_pending_update(root_fd)
    return True


def _publish(namespace_fd, staged, final):
    """Use a native no-replace primitive, never an ordinary rename fallback."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        operation = getattr(library, "renameatx_np", None)
        flag = 0x00000004  # RENAME_EXCL, from the platform SDK sys/stdio.h.
    elif sys.platform.startswith("linux"):
        operation = getattr(library, "renameat2", None)
        flag = 1  # RENAME_NOREPLACE.
    else:
        operation = None
        flag = 0
    if operation is None:
        raise ReceptionError("Exclusive directory publication is unavailable on this platform", 3)
    operation.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    operation.restype = ctypes.c_int
    if operation(namespace_fd, os.fsencode(staged), namespace_fd, os.fsencode(final), flag) != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ReceptionError("Run destination appeared during reception; nothing overwritten", 5)
        raise ReceptionError("Filesystem refused exclusive Run publication; no unsafe fallback")


def _check_baselines(plan, expected):
    if tuple(plan[key] for key in ("parent_sha256", "child_sha256", "evidence_sha256")) != expected:
        raise ReceptionError("Collection preview is stale; generate a new preview", 5)


def _sync_archive_parents(root_fd, namespace_fd):
    os.fsync(namespace_fd)
    with _directory(root_fd, "experiments") as experiments_fd:
        os.fsync(experiments_fd)
    os.fsync(root_fd)


def receive_run(
    parent_root: str | Path, child_root: str | Path, *, run_id: str,
    expected_parent_sha256: str, expected_child_sha256: str, expected_evidence_sha256: str,
):
    """Receive once, or verify an identical receipt; never update an existing Run."""
    expected = (expected_parent_sha256, expected_child_sha256, expected_evidence_sha256)
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in expected):
        raise ReceptionError("Reception requires all three preview SHA-256 baselines", 2)
    plan = plan_run_collection(parent_root, child_root, run_id=run_id)
    _check_baselines(plan, expected)
    if _RECEIPT in plan["directories"] or any(row["destination_path"] == _RECEIPT for row in plan["files"]):
        raise ReceptionError("Source conflicts with reserved collection receipt", 5)
    receipt = (json.dumps(_receipt(plan), indent=2) + "\n").encode()
    if len(receipt) > 1024 * 1024:
        raise ReceptionError("Collection receipt exceeds the supported record size")
    namespace = plan["destination"].rsplit("/", 1)[0]
    result = {key: plan[key] for key in (
        "parent_project_id", "child_project_id", "run_id", "destination",
        "evidence_sha256", "execution_verification",
    )}
    published = False
    existing_archive = False
    try:
        with open_project_root(parent_root) as root_fd:
            lock = os.open(PROJECT_MANAGEMENT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
            try:
                held = os.fstat(lock)
                if not stat.S_ISREG(held.st_mode):
                    raise ReceptionError("Parent declaration is unsafe")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ReceptionError("Parent is busy; preview again before retrying", 5) from None
                _check_baselines(plan_run_collection(parent_root, child_root, run_id=run_id), expected)
                with _directory(root_fd, namespace, create=True) as namespace_fd:
                    if _existing(namespace_fd, run_id, plan):
                        existing_archive = True
                        _sync_archive_parents(root_fd, namespace_fd)
                        return {**result, "status": "unchanged"}
                    staged = ".receive-" + uuid.uuid4().hex
                    os.mkdir(staged, 0o700, dir_fd=namespace_fd)
                    stage_info = os.stat(staged, dir_fd=namespace_fd, follow_symlinks=False)
                    try:
                        files, directories, modes = _tree(child_root, run_id)
                        if sorted(directories) != plan["directories"] or set(files) != {row["source_path"] for row in plan["files"]}:
                            raise ReceptionError("Source tree changed before staging", 5)
                        with _directory(namespace_fd, staged) as stage_fd:
                            for directory in plan["directories"]:
                                with _directory(stage_fd, directory, create=True):
                                    pass
                            for row in plan["files"]:
                                content = files[row["source_path"]]
                                if _sha(content) != row["sha256"] or modes[row["source_path"]] != row["mode"]:
                                    raise ReceptionError("Source evidence changed before staging", 5)
                                _write_file(stage_fd, row["destination_path"], content, row["mode"])
                            _write_file(stage_fd, _RECEIPT, receipt, 0o600)
                            for directory in sorted(plan["directories"], key=lambda path: path.count("/"), reverse=True):
                                with _directory(stage_fd, directory) as directory_fd:
                                    os.fsync(directory_fd)
                            os.fsync(stage_fd)
                        _existing(namespace_fd, staged, plan)
                        _check_baselines(plan_run_collection(parent_root, child_root, run_id=run_id), expected)
                        with open_project_root(parent_root) as current_root:
                            now, original = os.fstat(current_root), os.fstat(root_fd)
                            if (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino):
                                raise ReceptionError("Parent root changed during reception")
                        with _directory(root_fd, namespace) as current_namespace:
                            now, original = os.fstat(current_namespace), os.fstat(namespace_fd)
                            if (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino):
                                raise ReceptionError("Archive namespace changed during reception")
                        current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
                        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
                            raise ReceptionError("Parent declaration changed during reception", 5)
                        _publish(namespace_fd, staged, run_id)
                        published = True
                        _sync_archive_parents(root_fd, namespace_fd)
                        return {**result, "status": "received"}
                    finally:
                        if not published:
                            try:
                                current = os.stat(staged, dir_fd=namespace_fd, follow_symlinks=False)
                                if (current.st_dev, current.st_ino) != (stage_info.st_dev, stage_info.st_ino):
                                    raise ReceptionError("Staging location changed; cleanup requires review", 6)
                                shutil.rmtree(staged, dir_fd=namespace_fd)
                            except OSError:
                                raise ReceptionError(
                                    f"Temporary cleanup is incomplete; review {namespace}/{staged}", 6,
                                ) from None
            finally:
                os.close(lock)
    except (OSError, ProjectLayoutError):
        if published or existing_archive:
            raise ReceptionError("Run exists but durability is unconfirmed; read before retrying", 6) from None
        raise ReceptionError("Run reception failed safely; no existing Run was overwritten") from None
