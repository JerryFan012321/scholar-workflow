"""Runtime-only cmux capability and opaque workspace registry.

The canonical HubCatalog never stores cmux identifiers.  Raw workspace IDs are
kept in this process and are exposed to the browser only through random opaque
handles.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


DEFAULT_CMUX_PATH = Path("/Applications/cmux.app/Contents/Resources/bin/cmux")
_INSTANCE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_BASE_CHILD_ENV_KEYS = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL")
_CMUX_CHILD_ENV_KEYS = ("CMUX_WORKSPACE_ID", "CMUX_SOCKET_PATH")
_UUID_RE = re.compile(
    r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)


class CmuxControlError(RuntimeError):
    """A cmux capability could not be queried or executed."""


class UnknownWorkspaceError(CmuxControlError):
    """A browser supplied an unknown or expired opaque workspace handle."""


@dataclass(frozen=True)
class PublicWorkspace:
    """Safe runtime workspace metadata that may be sent to the browser."""

    id: str
    label: str
    is_current: bool
    contains_hub: bool


@dataclass(frozen=True)
class WorkspaceListing:
    """Current workspace capability surface, including an explicit failure."""

    workspaces: tuple[PublicWorkspace, ...]
    capability_error: str | None = None


class CmuxControl:
    """Small argv-only adapter for the cmux CLI."""

    def __init__(
        self,
        configured_path: str | Path | None = None,
        *,
        timeout: float = 5.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._configured_path = Path(configured_path).expanduser() if configured_path else None
        self._timeout = timeout
        self._runner = runner

    def tree_all(self) -> Any:
        """Return the parsed result of ``cmux --json tree --all``."""
        result = self._invoke([str(self.executable()), "--json", "tree", "--all"])
        self._require_success(result)
        try:
            payload = json.loads(result.stdout or "")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CmuxControlError("cmux returned invalid workspace JSON") from exc
        if not isinstance(payload, (dict, list)):
            raise CmuxControlError("cmux returned invalid workspace JSON")
        return payload

    def open(self, target: str, *, workspace_id: str) -> subprocess.CompletedProcess[str]:
        """Open one server-validated target in an already resolved workspace."""
        self._clean_value(target, "cmux target")
        self._clean_value(workspace_id, "cmux workspace ID")
        result = self._invoke(
            [
                str(self.executable()),
                "open",
                target,
                "--workspace",
                workspace_id,
                "--focus",
                "true",
            ]
        )
        self._require_success(result, secrets=(target, workspace_id))
        return result

    def new_codex_session(
        self,
        *,
        workspace_id: str,
        working_directory: Path,
    ) -> subprocess.CompletedProcess[str]:
        """Create a blank native Codex surface with no browser-provided command."""
        self._clean_value(workspace_id, "cmux workspace ID")
        directory = Path(working_directory)
        if not directory.is_absolute() or not directory.is_dir():
            raise CmuxControlError("Codex working directory is not an existing absolute directory")
        result = self._invoke(
            [
                str(self.executable()),
                "new-surface",
                "--type",
                "agent-session",
                "--provider",
                "codex",
                "--working-directory",
                str(directory),
                "--workspace",
                workspace_id,
                "--focus",
                "true",
            ]
        )
        self._require_success(
            result,
            secrets=(workspace_id, str(directory)),
        )
        return result

    def executable(self) -> Path:
        if self._configured_path is not None:
            if self._is_executable(self._configured_path):
                return self._configured_path
            raise CmuxControlError(
                f"Configured cmux CLI is not executable: {self._configured_path}"
            )
        path_candidate = shutil.which("cmux")
        if path_candidate:
            path = Path(path_candidate)
            if self._is_executable(path):
                return path
        if self._is_executable(DEFAULT_CMUX_PATH):
            return DEFAULT_CMUX_PATH
        raise CmuxControlError("cmux CLI was not found")

    def _invoke(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        env = minimal_child_environment(include_cmux=True)
        try:
            return self._runner(
                argv,
                shell=False,
                timeout=self._timeout,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CmuxControlError(
                f"cmux command timed out after {self._timeout:g} seconds"
            ) from exc
        except OSError as exc:
            raise CmuxControlError(f"Could not execute cmux: {exc}") from exc

    @staticmethod
    def _require_success(
        result: subprocess.CompletedProcess[str],
        *,
        secrets: tuple[str, ...] = (),
    ) -> None:
        if result.returncode == 0:
            return
        detail = _public_error(
            (result.stderr or result.stdout or "").strip()[:500],
            secrets=secrets,
        )
        raise CmuxControlError(detail or f"cmux exited with status {result.returncode}")

    @staticmethod
    def _is_executable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    @staticmethod
    def _clean_value(value: str, name: str) -> None:
        if not isinstance(value, str) or not value or value != value.strip():
            raise CmuxControlError(f"{name} must be a non-empty clean string")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise CmuxControlError(f"{name} contains control characters")


class WorkspaceRegistry:
    """Refresh cmux workspaces and map raw IDs to process-local opaque IDs."""

    def __init__(
        self,
        control: CmuxControl,
        *,
        current_workspace_id: str | None = None,
        hub_url: str = "http://127.0.0.1:23128/hub/",
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._control = control
        self._current_workspace_id = (
            current_workspace_id
            if current_workspace_id is not None
            else os.environ.get("CMUX_WORKSPACE_ID")
        )
        self._hub_url = hub_url
        self._id_factory = id_factory or self._default_id
        self._lock = threading.RLock()
        self._raw_to_opaque: dict[str, str] = {}
        self._opaque_to_raw: dict[str, str] = {}

    @staticmethod
    def _default_id() -> str:
        return f"ws_{secrets.token_urlsafe(24)}"

    def public_workspaces(self, *, instance_token: str | None = None) -> WorkspaceListing:
        if instance_token is not None and not _INSTANCE_TOKEN_RE.fullmatch(instance_token):
            raise ValueError("Invalid Hub instance token")
        try:
            payload = self._control.tree_all()
            nodes = list(_workspace_nodes(payload))
            records = _workspace_records(nodes)
        except CmuxControlError as exc:
            with self._lock:
                self._raw_to_opaque.clear()
                self._opaque_to_raw.clear()
            return WorkspaceListing(workspaces=(), capability_error=str(exc))

        current = self._preferred_current(records)
        with self._lock:
            live_raw_ids = {raw_id for raw_id, _node in records}
            stale_ids = set(self._raw_to_opaque) - live_raw_ids
            for raw_id in stale_ids:
                opaque = self._raw_to_opaque.pop(raw_id)
                self._opaque_to_raw.pop(opaque, None)

            public: list[PublicWorkspace] = []
            for position, (raw_id, node) in enumerate(records, start=1):
                opaque = self._raw_to_opaque.get(raw_id)
                if opaque is None:
                    opaque = self._allocate_id()
                    self._raw_to_opaque[raw_id] = opaque
                    self._opaque_to_raw[opaque] = raw_id
                public.append(
                    PublicWorkspace(
                        id=opaque,
                        label=_workspace_label(node, position, raw_ids=live_raw_ids),
                        is_current=raw_id == current,
                        contains_hub=_contains_hub(node, self._hub_url, instance_token),
                    )
                )
            return WorkspaceListing(workspaces=tuple(public))

    def resolve(self, opaque_id: str) -> str:
        if not isinstance(opaque_id, str) or not opaque_id:
            raise UnknownWorkspaceError("A workspace selection is required")
        with self._lock:
            try:
                return self._opaque_to_raw[opaque_id]
            except KeyError as exc:
                raise UnknownWorkspaceError("Unknown or expired cmux workspace") from exc

    def _allocate_id(self) -> str:
        for _ in range(32):
            candidate = self._id_factory()
            if candidate and candidate not in self._opaque_to_raw:
                return candidate
        raise CmuxControlError("Could not allocate an opaque workspace ID")

    def _preferred_current(self, records: list[tuple[str, dict[str, Any]]]) -> str | None:
        raw_ids = {raw_id for raw_id, _node in records}
        if self._current_workspace_id in raw_ids:
            return self._current_workspace_id
        for raw_id, node in records:
            if any(
                node.get(field) is True
                for field in ("is_current", "current", "selected", "active", "focused")
            ):
                return raw_id
        return None


def _workspace_nodes(payload: Any) -> Iterator[dict[str, Any]]:
    """Yield workspace objects from both nested and typed cmux JSON shapes."""
    if isinstance(payload, list):
        for value in payload:
            yield from _workspace_nodes(value)
        return
    if not isinstance(payload, dict):
        return

    workspaces = payload.get("workspaces")
    if isinstance(workspaces, list):
        for workspace in workspaces:
            if isinstance(workspace, dict):
                yield workspace
        for key, value in payload.items():
            if key != "workspaces":
                yield from _workspace_nodes(value)
        return

    node_type = str(payload.get("type") or payload.get("kind") or "").lower()
    if node_type == "workspace":
        yield payload
        return
    for value in payload.values():
        yield from _workspace_nodes(value)


def _workspace_records(
    nodes: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for node in nodes:
        raw_id = next(
            (
                value
                for field in ("workspace_id", "workspaceId", "id", "uuid")
                if isinstance((value := node.get(field)), str) and value
            ),
            None,
        )
        if raw_id is None or raw_id in seen:
            continue
        seen.add(raw_id)
        records.append((raw_id, node))
    return records


def _workspace_label(
    node: dict[str, Any],
    position: int,
    *,
    raw_ids: set[str],
) -> str:
    for field in ("title", "name", "label", "workspace_title"):
        value = node.get(field)
        if isinstance(value, str) and value.strip():
            label = value.strip()[:160]
            for raw_id in sorted(raw_ids, key=len, reverse=True):
                label = label.replace(raw_id, "<workspace>")
            label = _UUID_RE.sub("<workspace>", label).strip()
            return label or f"Workspace {position}"
    return f"Workspace {position}"


def _contains_hub(
    node: dict[str, Any],
    hub_url: str,
    instance_token: str | None,
) -> bool:
    try:
        expected = urlsplit(hub_url)
    except ValueError:
        return False
    expected_path = expected.path.rstrip("/") or "/"
    for candidate in _url_values(node):
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        candidate_path = parsed.path.rstrip("/") or "/"
        same_hub = (
            parsed.scheme.lower() == expected.scheme.lower()
            and parsed.hostname == expected.hostname
            and parsed.port == expected.port
            and candidate_path == expected_path
        )
        if not same_hub:
            continue
        if instance_token is None:
            return True
        if parse_qs(parsed.query, keep_blank_values=True).get("instance") == [instance_token]:
            return True
    return False


def _url_values(value: Any, *, key: str = "") -> Iterator[str]:
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from _url_values(child, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _url_values(child, key=key)
    elif isinstance(value, str) and key.lower() in {"url", "uri", "current_url", "currenturl"}:
        yield value


def minimal_child_environment(*, include_cmux: bool = False) -> dict[str, str]:
    """Return the small environment required by local launch helpers."""
    keys = _BASE_CHILD_ENV_KEYS + (_CMUX_CHILD_ENV_KEYS if include_cmux else ())
    return {
        key: value
        for key in keys
        if (value := os.environ.get(key)) is not None
    }


def _public_error(detail: str, *, secrets: tuple[str, ...] = ()) -> str:
    """Keep capability errors useful without leaking UUIDs or socket paths."""
    first_line = detail.strip().splitlines()[0] if detail.strip() else ""
    lowered = first_line.lower()
    if "no live cmux socket" in lowered:
        return "No live cmux socket found"
    if "permission denied" in lowered or "access denied" in lowered:
        return "cmux workspace control is not permitted"
    sanitized = first_line
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        sanitized = sanitized.replace(secret, "<redacted>")
    sanitized = _UUID_RE.sub("<workspace>", sanitized)
    home = str(Path.home())
    if home:
        sanitized = sanitized.replace(home, "~")
    socket_path = os.environ.get("CMUX_SOCKET_PATH")
    if socket_path:
        sanitized = sanitized.replace(socket_path, "<cmux socket>")
    return sanitized[:300]


__all__ = [
    "CmuxControl",
    "CmuxControlError",
    "PublicWorkspace",
    "UnknownWorkspaceError",
    "WorkspaceListing",
    "WorkspaceRegistry",
    "minimal_child_environment",
]
