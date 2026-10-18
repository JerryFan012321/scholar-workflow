"""Resolve selected execution-code declarations without connecting or launching tools."""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from scholar_workflow.assets.servers import read_servers

from .collection import _record, _sha
from .context import PROJECT_CONTEXT, ExecutionCodeRef, load_project_context
from .layout import open_project_root, read_project_bytes
from .management import PROJECT_MANAGEMENT, load_project_management
from .models import SLUG, TargetProfile
from .reception import _directory, _read_file


class RemoteCodeError(ValueError):
    """An explicit locator is missing, inconsistent, unsafe or changed."""


def _remote_root(value):
    if (not isinstance(value, str) or len(value) > 4096 or value != value.strip()
            or not value.startswith("/") or value.startswith("//") or value == "/"
            or "\\" in value or any(ord(char) < 32 for char in value)
            or any(part in {"", ".", ".."} for part in value[1:].split("/"))):
        raise RemoteCodeError("Remote code requires a selected, non-root absolute POSIX Target directory")
    return PurePosixPath(value)


def plan_remote_code(parent_root, *, entry_id, target_id, env_records_root: Path):
    """Project identity is checked locally; remote child/commit/access remain unverified.

    Target selection is per-request, not a persistent claim that its directory
    contains this child. Native SSH/VS Code tools retain connection/auth policy.
    """
    if not isinstance(target_id, str) or re.fullmatch(SLUG, target_id) is None:
        raise RemoteCodeError("Invalid selected Target identity")
    names = ("project-layout.json", PROJECT_MANAGEMENT, PROJECT_CONTEXT)
    baseline = {name: read_project_bytes(parent_root, name) for name in names}
    context = load_project_context(parent_root)
    management = load_project_management(parent_root)
    entry = next((item for item in context.entries if item.entry_id == entry_id), None)
    if entry is None or entry.kind != "code" or not isinstance(entry.ref, ExecutionCodeRef):
        raise RemoteCodeError("Select one declared execution-code entry; no location was guessed")
    if (management.kind != "research-parent" or not any(
            child.project_id == entry.ref.child_project_id for child in management.children)):
        raise RemoteCodeError("Execution child is not registered in this research parent")
    relative = f"experiments/profiles/targets/{target_id}.yaml"
    try:
        with open_project_root(parent_root) as root_fd:
            target_raw, _ = _read_file(root_fd, relative, 1024 * 1024)
            target = _record({relative: target_raw}, relative, TargetProfile)
            if target.target_id != target_id or target.kind != "ssh":
                raise RemoteCodeError("Selected Target is not the matching SSH declaration")
            root = _remote_root(target.project_root)
            inventory = read_servers(Path(env_records_root))
            if inventory["status"] != "available":
                raise RemoteCodeError("Existing server ledger is unavailable; no ledger was created")
            server = next((item for item in inventory["servers"] if item["alias"] == target.server_alias), None)
            if server is None:
                raise RemoteCodeError("Selected Target server is not registered; no connection was inferred")
            connection = {key: server[key] for key in ("host", "user")}
            connection.update(server_alias=server["alias"], port=server.get("port", 22))
            if server.get("jump"):
                connection["jump_alias"] = server["jump"]
            remote_path = str(root if entry.ref.relative_path == "." else root / entry.ref.relative_path)
            if _read_file(root_fd, relative, 1024 * 1024)[0] != target_raw:
                raise RemoteCodeError("Selected Target changed during location planning")
            if any(read_project_bytes(parent_root, name) != value for name, value in baseline.items()):
                raise RemoteCodeError("Project declarations changed during location planning")
            again = read_servers(Path(env_records_root))
            if again["status"] != "available" or again["revision"] != inventory["revision"]:
                raise RemoteCodeError("Server ledger changed during location planning")
            with open_project_root(parent_root) as current:
                old, now = os.fstat(root_fd), os.fstat(current)
                if (old.st_dev, old.st_ino) != (now.st_dev, now.st_ino):
                    raise RemoteCodeError("Parent location changed during planning")
            # Reopening the exact relative target also rejects an ancestor symlink swap.
            with _directory(root_fd, "experiments/profiles/targets"):
                pass
            return {
                "schema_version": 1, "status": "declared_not_remote_verified",
                "project_id": context.project_id, "child_project_id": entry.ref.child_project_id,
                "entry_id": entry.entry_id, "title": entry.title, "target_id": target_id,
                "relative_path": entry.ref.relative_path, "remote_path": remote_path,
                "requested_commit": entry.ref.commit, "connection": connection,
                "baselines": {**{name: _sha(raw) for name, raw in baseline.items()},
                              "target_sha256": _sha(target_raw), "server_ledger_revision": inventory["revision"]},
                "verification": {"child_identity": "not_checked", "remote_path": "not_checked",
                                 "commit": "not_checked", "access": "not_checked",
                                 "ssh_config_alias": "not_checked"},
                "diagnostics": ["Target selection does not verify which project occupies its remote directory.",
                                "Native tools retain SSH aliases, keys, jump routing and access policy."],
            }
    except (OSError, ValueError) as error:
        if isinstance(error, RemoteCodeError):
            raise
        raise RemoteCodeError("Selected code location or Target cannot be inspected safely") from None
