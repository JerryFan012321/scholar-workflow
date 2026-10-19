"""Add an explicit role declaration to an existing project without reinitializing it."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path

from .layout import (
    MAX_PROJECT_MANIFEST_BYTES,
    PROJECT_LAYOUT,
    ProjectLayoutError,
    _unique_json_object,
    open_project_root,
    validate_project_layout,
)
from .management import PROJECT_MANAGEMENT, validate_project_management
from .reception import ReceptionError, _read_file
from .registration import ProjectRegistrationError

_PROTECTED = (PROJECT_LAYOUT, PROJECT_MANAGEMENT, "AGENTS.md", "AGENT.md", "CLAUDE.md",
              ".gitignore", "PROJECT.md", "SCHEDULE.md", "project-context.json")


class ProjectRoleAdoptionError(ProjectRegistrationError):
    """A role declaration is invalid, conflicted, unsafe or partially published."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _snapshot(root):
    files, baselines = {}, {}
    with open_project_root(root) as root_fd:
        root_info = os.fstat(root_fd)
        location = {"device": root_info.st_dev, "inode": root_info.st_ino}
        for name in _PROTECTED:
            try:
                before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                files[name], baselines[name] = None, None
                continue
            except OSError:
                raise ProjectRoleAdoptionError(f"{name} cannot be safely inspected", 7) from None
            if not stat.S_ISREG(before.st_mode):
                raise ProjectRoleAdoptionError(f"{name} must be a regular file, not a symlink", 7)
            try:
                data, mode = _read_file(root_fd, name, MAX_PROJECT_MANIFEST_BYTES)
                after = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except (OSError, ReceptionError):
                raise ProjectRoleAdoptionError(f"{name} is unsafe, changed or exceeds its size limit", 7) from None
            if _file_identity(before) != _file_identity(after):
                raise ProjectRoleAdoptionError("Project entry changed during preview; inspect again", 5)
            files[name] = data
            baselines[name] = {"sha256": _sha(data), "mode": mode,
                               "identity": list(_file_identity(after))}
    return location, files, baselines


def _json(data):
    try:
        return json.loads(data, object_pairs_hook=_unique_json_object)
    except (TypeError, UnicodeError, json.JSONDecodeError):
        raise ProjectRoleAdoptionError("Project declaration must be valid UTF-8 JSON") from None


def plan_role_adoption(root: str | Path, *, role: str, parent_project_id: str | None = None,
                       primary: bool = False):
    """Preview one missing declaration; preserve existing role and content ownership."""
    if role not in {"research-parent", "execution-child"} or type(primary) is not bool:
        raise ProjectRoleAdoptionError("Choose an explicit research-parent or execution-child role")
    if role == "research-parent" and (parent_project_id is not None or primary):
        raise ProjectRoleAdoptionError("A research parent cannot have child-only role options")
    location, files, baselines = _snapshot(root)
    layout = validate_project_layout(_json(files[PROJECT_LAYOUT]))
    if role == "research-parent" and (layout.source_profile is not None or layout.addons):
        raise ProjectRoleAdoptionError("Parent adoption requires a separately reviewed source-profile migration", 5)
    candidate = {"schema_version": 1, "project_id": layout.project_id, "kind": role}
    if role == "research-parent":
        candidate["children"] = []
    else:
        candidate.update(parent_project_id=parent_project_id, primary=primary)
    candidate = validate_project_management(candidate).model_dump()
    existing_bytes = files[PROJECT_MANAGEMENT]
    if existing_bytes is not None:
        existing = validate_project_management(_json(existing_bytes)).model_dump()
        if existing["project_id"] != layout.project_id or existing["kind"] != role:
            raise ProjectRoleAdoptionError("Existing management identity or role conflicts; not overwritten", 5)
        if role == "execution-child" and existing != candidate:
            raise ProjectRoleAdoptionError("Existing child parent or primary conflicts; not overwritten", 5)
        candidate = existing
    if _snapshot(root) != (location, files, baselines):
        raise ProjectRoleAdoptionError("Project entries changed during preview; inspect again", 5)
    result = {
        "status": "planned" if existing_bytes is None else "unchanged",
        "project_id": layout.project_id, "role": role,
        "changes": [{"path": PROJECT_MANAGEMENT, "operation": "create"}]
        if existing_bytes is None else [],
        "proposed_declaration": candidate, "root_identity": location,
        "baselines": baselines,
        "remaining_review": ["guidance_and_git_policy", "project_entry_and_plan",
                             "native_git_topology", "child_registration_and_archive_collection"],
        "migration_state": "declaration_only_not_full_migration",
    }
    result["plan_sha256"] = _sha(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
    return result


def _check_root(root, root_fd):
    with open_project_root(root) as current_fd:
        current, held = os.fstat(current_fd), os.fstat(root_fd)
        if (current.st_dev, current.st_ino) != (held.st_dev, held.st_ino):
            raise ProjectRoleAdoptionError("Project root changed during adoption", 7)


def _remove_owned_stage(root_fd, temporary, identity, expected_data):
    try:
        current = os.stat(temporary, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) != identity or not stat.S_ISREG(current.st_mode):
        raise ProjectRoleAdoptionError("Unknown adoption staging file retained for inspection", 6)
    try:
        actual, mode = _read_file(root_fd, temporary, MAX_PROJECT_MANIFEST_BYTES)
    except (OSError, ReceptionError):
        raise ProjectRoleAdoptionError("Changed adoption staging file retained for inspection", 6) from None
    if actual != expected_data or mode != 0o600:
        raise ProjectRoleAdoptionError("Changed adoption staging file retained for inspection", 6)
    os.unlink(temporary, dir_fd=root_fd)


def adopt_project_role(root: str | Path, *, role: str, expected_plan_sha256: str,
                       parent_project_id: str | None = None, primary: bool = False):
    """Create only the missing role file, with no overwrite, migration or remote work."""
    if not isinstance(expected_plan_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256):
        raise ProjectRoleAdoptionError("Apply requires the current preview SHA-256")
    with open_project_root(root) as root_fd:
        descriptor = None
        temporary = ".project-role-" + uuid.uuid4().hex + ".tmp"
        staged_identity = None
        published = False
        try:
            descriptor = os.open(PROJECT_LAYOUT, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=root_fd)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ProjectRoleAdoptionError("Project layout must be a regular file", 7)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProjectRoleAdoptionError("Role adoption is busy; preview before retrying", 5) from None
            plan = plan_role_adoption(root, role=role, parent_project_id=parent_project_id, primary=primary)
            if plan["plan_sha256"] != expected_plan_sha256:
                raise ProjectRoleAdoptionError("Preview is stale; project entries changed", 5)
            if plan["status"] == "unchanged":
                return plan
            data = (json.dumps(plan["proposed_declaration"], indent=2) + "\n").encode()
            stage_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                               0o600, dir_fd=root_fd)
            held = os.fstat(stage_fd)
            staged_identity = held.st_dev, held.st_ino
            with os.fdopen(stage_fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            _check_root(root, root_fd)
            final = plan_role_adoption(root, role=role, parent_project_id=parent_project_id, primary=primary)
            if final["plan_sha256"] != expected_plan_sha256:
                raise ProjectRoleAdoptionError("Project entries changed while staging; preview again", 5)
            current = os.stat(temporary, dir_fd=root_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != staged_identity or not stat.S_ISREG(current.st_mode):
                raise ProjectRoleAdoptionError("Role staging was replaced; publication refused", 7)
            staged_data, staged_mode = _read_file(root_fd, temporary, MAX_PROJECT_MANIFEST_BYTES)
            if staged_data != data or staged_mode != 0o600:
                raise ProjectRoleAdoptionError("Role staging content changed; publication refused", 7)
            try:
                os.link(temporary, PROJECT_MANAGEMENT, src_dir_fd=root_fd,
                        dst_dir_fd=root_fd, follow_symlinks=False)
            except FileExistsError:
                raise ProjectRoleAdoptionError("Management declaration already exists; not overwritten", 5) from None
            published = True
            current = os.stat(PROJECT_MANAGEMENT, dir_fd=root_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != staged_identity:
                raise ProjectRoleAdoptionError("Published declaration changed; inspect actual state", 6)
            actual, mode = _read_file(root_fd, PROJECT_MANAGEMENT, MAX_PROJECT_MANIFEST_BYTES)
            if actual != data or mode != 0o600:
                raise ProjectRoleAdoptionError("Published declaration differs; inspect actual state", 6)
            _check_root(root, root_fd)
            location, _, baselines = _snapshot(root)
            if location != plan["root_identity"] or any(
                baselines[name] != plan["baselines"][name]
                for name in _PROTECTED if name != PROJECT_MANAGEMENT
            ):
                raise ProjectRoleAdoptionError("Published role context changed; inspect before retrying", 6)
            os.fsync(root_fd)
            _remove_owned_stage(root_fd, temporary, staged_identity, data)
            staged_identity = None
            os.fsync(root_fd)
            return {**plan, "status": "adopted"}
        except ProjectRoleAdoptionError as exc:
            if published and exc.exit_code != 6:
                raise ProjectRoleAdoptionError("Published declaration requires inspection; adoption is partial", 6) from None
            raise
        except (OSError, ReceptionError):
            if published:
                raise ProjectRoleAdoptionError(
                    "project-management.json exists but durability is unconfirmed; inspect before retrying", 6,
                ) from None
            raise ProjectRoleAdoptionError("Role declaration could not be safely created", 7) from None
        except ProjectLayoutError:
            if published:
                raise ProjectRoleAdoptionError("Published project location requires inspection; adoption is partial", 6) from None
            raise
        finally:
            try:
                if staged_identity is not None and not published:
                    try:
                        _remove_owned_stage(root_fd, temporary, staged_identity, data)
                    except OSError:
                        raise ProjectRoleAdoptionError("Role was not adopted; temporary cleanup is incomplete", 6) from None
            finally:
                if descriptor is not None:
                    os.close(descriptor)
