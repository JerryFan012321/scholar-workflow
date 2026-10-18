"""Explicit single-file child registration with byte-bound previews; no host discovery."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path
from typing import Any

from .layout import (
    MAX_PROJECT_MANIFEST_BYTES,
    open_project_root,
    read_project_bytes,
)
from .management import (
    PROJECT_MANAGEMENT,
    ChildDeclaration,
    ProjectManagementError,
    load_project_management,
    validate_management_pair,
    validate_project_management,
)


class ProjectRegistrationError(ProjectManagementError):
    """A registration stopped with an explicit input/conflict/safety/partial outcome."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot(root: str | Path):
    before = read_project_bytes(root, PROJECT_MANAGEMENT)
    declaration = load_project_management(root)
    if read_project_bytes(root, PROJECT_MANAGEMENT) != before:
        raise ProjectRegistrationError("Declaration changed while planning; preview again", 5)
    return before, declaration


def plan_child_registration(
    parent_root: str | Path, child_root: str | Path, *, archive_segment: str,
) -> dict[str, Any]:
    """Preview exactly two selected declarations without locks, writes or network."""
    parent_bytes, parent = _snapshot(parent_root)
    child_bytes, child = _snapshot(child_root)
    if parent.kind != "research-parent" or child.kind != "execution-child":
        raise ProjectRegistrationError("Registration requires a research parent and execution child")
    if child.parent_project_id != parent.project_id:
        raise ProjectRegistrationError("Child declares a different parent identity", 5)
    row = ChildDeclaration(child.project_id, archive_segment, child.primary)
    existing = next((item for item in parent.children if item.project_id == child.project_id), None)
    if existing is not None and existing != row:
        raise ProjectRegistrationError("Child is already registered differently; explicit migration required", 5)
    proposed = parent.model_dump()
    if existing is None:
        proposed["children"].append(row.model_dump())
    try:
        candidate = validate_project_management(proposed)
    except ProjectManagementError as exc:
        raise ProjectRegistrationError(str(exc), 5) from None
    validate_management_pair(candidate, child)
    if read_project_bytes(parent_root, PROJECT_MANAGEMENT) != parent_bytes:
        raise ProjectRegistrationError("Parent changed while planning; preview again", 5)
    return {
        "status": "unchanged" if existing is not None else "planned",
        "parent_project_id": parent.project_id, "child_project_id": child.project_id,
        "archive_segment": archive_segment, "primary": child.primary,
        "parent_sha256": _sha(parent_bytes), "child_sha256": _sha(child_bytes),
        "proposed_parent": proposed,
        "remote_availability": "not_verified",
    }


def register_child(
    parent_root: str | Path, child_root: str | Path, *, archive_segment: str,
    expected_parent_sha256: str, expected_child_sha256: str,
) -> dict[str, Any]:
    """Append one declared child; never mutate it or implicitly migrate existing entries."""
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
               for value in (expected_parent_sha256, expected_child_sha256)):
        raise ProjectRegistrationError("Apply requires both preview SHA-256 baselines")
    with open_project_root(parent_root) as root_fd:
        descriptor = None
        temporary = ".project-management-" + uuid.uuid4().hex + ".tmp"
        staged = False
        replaced = False
        try:
            descriptor = os.open(
                PROJECT_MANAGEMENT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd,
            )
            held = os.fstat(descriptor)
            if not stat.S_ISREG(held.st_mode):
                raise ProjectRegistrationError("Parent declaration must be a regular file", 7)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProjectRegistrationError("Parent registration is busy; preview again before retrying", 5) from None
            current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
            if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                raise ProjectRegistrationError("Parent declaration changed while waiting; preview again", 5)
            plan = plan_child_registration(parent_root, child_root, archive_segment=archive_segment)
            if (plan["parent_sha256"], plan["child_sha256"]) != (
                expected_parent_sha256, expected_child_sha256,
            ):
                raise ProjectRegistrationError("Preview is stale; parent or child bytes changed", 5)
            if plan["status"] == "unchanged":
                return plan
            output = (json.dumps(plan["proposed_parent"], indent=2) + "\n").encode()
            if len(output) > MAX_PROJECT_MANIFEST_BYTES:
                raise ProjectRegistrationError("Proposed parent exceeds the declaration size limit", 7)
            temp_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                              mode=0o600, dir_fd=root_fd)
            staged = True
            with os.fdopen(temp_fd, "wb") as stream:
                os.fchmod(stream.fileno(), stat.S_IMODE(held.st_mode) & 0o777)
                stream.write(output)
                stream.flush()
                os.fsync(stream.fileno())
            with open_project_root(parent_root) as current_fd:
                now = os.fstat(current_fd)
                original = os.fstat(root_fd)
                if (now.st_dev, now.st_ino) != (original.st_dev, original.st_ino):
                    raise ProjectRegistrationError("Parent root changed during registration", 7)
            current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
            if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                raise ProjectRegistrationError("Parent declaration was replaced during registration", 5)
            final = plan_child_registration(parent_root, child_root, archive_segment=archive_segment)
            if (final["parent_sha256"], final["child_sha256"]) != (
                expected_parent_sha256, expected_child_sha256,
            ):
                raise ProjectRegistrationError("Declaration changed during registration; preview again", 5)
            os.replace(temporary, PROJECT_MANAGEMENT, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            replaced = True
            os.fsync(root_fd)
            return {**plan, "status": "registered", "parent_sha256": _sha(output)}
        except OSError:
            if replaced:
                raise ProjectRegistrationError(
                    "Registration was replaced but durability is unconfirmed; read before retrying", 6,
                ) from None
            raise ProjectRegistrationError("Registration could not be safely written", 7) from None
        finally:
            try:
                if staged and not replaced:
                    try:
                        os.unlink(temporary, dir_fd=root_fd)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        raise ProjectRegistrationError(
                            "Parent was not replaced but temporary cleanup is incomplete", 6,
                        ) from None
            finally:
                if descriptor is not None:
                    os.close(descriptor)
