"""Opaque Hub actions and safe external-app launchers.

The browser receives only an action id. Targets remain in the in-process registry
and are resolved immediately before execution.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

from scholar_workflow.adapters.obsidian import VaultPathError, safe_vault_path
from scholar_workflow.hub.cmux import (
    CmuxControl,
    CmuxControlError,
    WorkspaceListing,
    WorkspaceRegistry,
    minimal_child_environment,
)


DEFAULT_CMUX_PATH = Path("/Applications/cmux.app/Contents/Resources/bin/cmux")
_CMUX_BUNDLE_ID = "com.cmuxterm.app"
_NOTION_HOSTS = ("notion.so", "notion.com", "notion.site")
_NO_SOCKET_MARKERS = (
    "no live cmux socket",
    "could not connect to cmux",
    "failed to connect to cmux",
    "connection refused",
)
_NOTION_PAGE_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?"
    r"[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
)
_ZOTERO_KEY_RE = re.compile(r"^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$")
_CODEX_BLANK_TARGET = "codex:blank"


class ActionError(RuntimeError):
    """Base class for visible Hub action failures."""


class UnknownActionError(ActionError):
    """The client supplied an action id that is not registered."""


class UnsupportedActionError(ActionError):
    """No launcher is registered for the resolved action kind."""


class InvalidActionTarget(ActionError):
    """A registered action target violates its launcher policy."""


class CmuxUnavailable(ActionError):
    """cmux is not installed or its executable cannot be used."""


class CmuxLaunchError(ActionError):
    """cmux was available but did not open the requested target."""


class ActionKind(str, Enum):
    NOTION_CMUX = "notion.cmux"
    RESOURCE_CMUX = "resource.cmux"
    ARTIFACT_CMUX = "artifact.cmux"
    OBSIDIAN_NOTE = "obsidian.note"
    ZOTERO_ITEM = "zotero.item"
    CODEX_SESSION = "codex.session"


class WorkspacePolicy(str, Enum):
    """Whether the client must select a server-registered cmux workspace."""

    NONE = "none"
    REQUIRED = "required"


@dataclass(frozen=True)
class PublicAction:
    """Safe action representation that may be serialized to the Hub client."""

    id: str
    label: str
    kind: ActionKind
    workspace_policy: WorkspacePolicy = WorkspacePolicy.NONE


@dataclass(frozen=True)
class RegisteredAction:
    """Server-side action record. Never serialize this object to the client."""

    id: str
    label: str
    kind: ActionKind
    target: str
    workspace_policy: WorkspacePolicy = WorkspacePolicy.NONE

    def public_view(self) -> PublicAction:
        return PublicAction(
            id=self.id,
            label=self.label,
            kind=self.kind,
            workspace_policy=self.workspace_policy,
        )


class ActionRegistry:
    """In-process mapping from opaque action ids to trusted targets."""

    def __init__(self, id_factory: Callable[[], str] | None = None) -> None:
        self._id_factory = id_factory or self._default_id
        self._actions: dict[str, RegisteredAction] = {}

    @staticmethod
    def _default_id() -> str:
        return f"act_{secrets.token_urlsafe(24)}"

    def register(
        self,
        *,
        kind: ActionKind,
        label: str,
        target: str,
        workspace_policy: WorkspacePolicy = WorkspacePolicy.NONE,
    ) -> PublicAction:
        if not label.strip():
            raise ValueError("Action label must not be empty")
        if not target.strip():
            raise ValueError("Action target must not be empty")
        for _ in range(32):
            action_id = self._id_factory()
            if action_id and action_id not in self._actions:
                break
        else:
            raise RuntimeError("Could not allocate a unique Hub action id")
        action = RegisteredAction(
            id=action_id,
            label=label,
            kind=ActionKind(kind),
            target=target,
            workspace_policy=WorkspacePolicy(workspace_policy),
        )
        self._actions[action_id] = action
        return action.public_view()

    def resolve(self, action_id: str) -> RegisteredAction:
        try:
            return self._actions[action_id]
        except KeyError as exc:
            raise UnknownActionError(f"Unknown Hub action: {action_id}") from exc


def register_notion_actions(
    catalog: Any, registry: ActionRegistry
) -> dict[str, list[PublicAction]]:
    """Register cmux actions from trusted Notion page IDs in a HubCatalog.

    The returned view contains only opaque IDs.  URLs are constructed here and
    retained exclusively in the server-side registry.
    """
    result: dict[str, list[PublicAction]] = {}
    for resource in catalog.resources:
        page_id = resource.projections.notion_page_id
        if not page_id or not _NOTION_PAGE_ID_RE.fullmatch(page_id):
            continue
        compact = page_id.replace("-", "").lower()
        action = registry.register(
            kind=ActionKind.NOTION_CMUX,
            label="在 cmux 中打开 Notion",
            target=f"https://www.notion.so/{compact}",
            workspace_policy=WorkspacePolicy.REQUIRED,
        )
        result.setdefault(resource.resource_id, []).append(action)
    return result


def register_obsidian_actions(
    catalog: Any, registry: ActionRegistry
) -> dict[str, list[PublicAction]]:
    """Register editable Vault artifacts without exposing their paths to the client."""
    result: dict[str, list[PublicAction]] = {}
    for artifact in catalog.artifacts:
        artifact_format = getattr(artifact.format, "value", artifact.format)
        if artifact_format not in {"markdown", "canvas"}:
            continue
        action = registry.register(
            kind=ActionKind.OBSIDIAN_NOTE,
            label="在 Obsidian 中编辑",
            target=artifact.vault_path,
        )
        result.setdefault(artifact.artifact_id, []).append(action)
    return result


def register_resource_view_actions(
    catalog: Any, registry: ActionRegistry
) -> dict[str, list[PublicAction]]:
    """Register cmux PDF previews from catalog attachment keys."""
    result: dict[str, list[PublicAction]] = {}
    for resource in catalog.resources:
        attachment_key = resource.zotero.attachment_key
        if not attachment_key or not _ZOTERO_KEY_RE.fullmatch(attachment_key):
            continue
        action = registry.register(
            kind=ActionKind.RESOURCE_CMUX,
            label="在 cmux 中查看 PDF",
            target=attachment_key,
            workspace_policy=WorkspacePolicy.REQUIRED,
        )
        result.setdefault(resource.resource_id, []).append(action)
    return result


def register_artifact_view_actions(
    catalog: Any, registry: ActionRegistry
) -> dict[str, list[PublicAction]]:
    """Register cmux previews for catalog-registered Markdown and Canvas files."""
    result: dict[str, list[PublicAction]] = {}
    for artifact in catalog.artifacts:
        artifact_format = getattr(artifact.format, "value", artifact.format)
        if artifact_format not in {"markdown", "canvas"}:
            continue
        action = registry.register(
            kind=ActionKind.ARTIFACT_CMUX,
            label="在 cmux 中查看",
            target=artifact.vault_path,
            workspace_policy=WorkspacePolicy.REQUIRED,
        )
        result.setdefault(artifact.artifact_id, []).append(action)
    return result


def register_zotero_actions(
    catalog: Any, registry: ActionRegistry
) -> dict[str, list[PublicAction]]:
    """Register Zotero item actions without exposing item keys or deep links."""
    result: dict[str, list[PublicAction]] = {}
    for resource in catalog.resources:
        item_key = resource.zotero.item_key
        if not item_key or not _ZOTERO_KEY_RE.fullmatch(item_key):
            continue
        action = registry.register(
            kind=ActionKind.ZOTERO_ITEM,
            label="在 Zotero 中编辑",
            target=item_key,
        )
        result.setdefault(resource.resource_id, []).append(action)
    return result


def register_codex_action(registry: ActionRegistry) -> PublicAction:
    """Register one global blank-session action with no prompt or command target."""
    return registry.register(
        kind=ActionKind.CODEX_SESSION,
        label="在 cmux 中启动 Codex",
        target=_CODEX_BLANK_TARGET,
        workspace_policy=WorkspacePolicy.REQUIRED,
    )


class Launcher(Protocol):
    def open(self, target: str, **kwargs: Any) -> Any: ...


class ActionExecutor:
    """Resolve an opaque action and dispatch it to its allowlisted launcher."""

    def __init__(
        self,
        registry: ActionRegistry,
        launchers: Mapping[ActionKind, Launcher],
    ) -> None:
        self._registry = registry
        self._launchers = dict(launchers)

    def execute(self, action_id: str, *, workspace_id: str | None = None) -> Any:
        action = self._registry.resolve(action_id)
        launcher = self._launchers.get(action.kind)
        if launcher is None:
            raise UnsupportedActionError(f"No launcher registered for {action.kind.value}")
        if action.workspace_policy is WorkspacePolicy.REQUIRED:
            if not workspace_id:
                raise InvalidActionTarget("This action requires a cmux workspace")
            return launcher.open(action.target, workspace_id=workspace_id)
        if workspace_id is not None:
            raise InvalidActionTarget("This action does not accept a cmux workspace")
        return launcher.open(action.target)


class CatalogActionService:
    """Refresh opaque actions when the live HubCatalog revision changes.

    The catalog may change while a long-running loopback Hub remains active.  A
    refresh swaps the public view and server-side registry together, so newly
    projected Notion pages and newly registered Vault artifacts do not require a
    process restart.  Existing actions remain usable until the client fetches a
    newer action surface.
    """

    def __init__(
        self,
        catalog_provider: Any,
        launchers: Mapping[ActionKind, Launcher],
        *,
        workspace_registry: WorkspaceRegistry | None = None,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._launchers = dict(launchers)
        self._workspace_registry = workspace_registry
        self._lock = threading.RLock()
        self._revision: str | None = None
        self._public_actions: dict[str, list[PublicAction]] = {}
        self._executor: ActionExecutor | None = None

    def public_actions(self) -> dict[str, list[PublicAction]]:
        catalog = self._catalog_provider.load()
        with self._lock:
            if self._executor is None or self._revision != catalog.revision:
                registry = ActionRegistry()
                public_actions: dict[str, list[PublicAction]] = {}
                registrars = (
                    (ActionKind.RESOURCE_CMUX, register_resource_view_actions),
                    (ActionKind.NOTION_CMUX, register_notion_actions),
                    (ActionKind.ZOTERO_ITEM, register_zotero_actions),
                    (ActionKind.ARTIFACT_CMUX, register_artifact_view_actions),
                    (ActionKind.OBSIDIAN_NOTE, register_obsidian_actions),
                )
                for kind, registrar in registrars:
                    if kind not in self._launchers:
                        continue
                    for entity_id, actions in registrar(catalog, registry).items():
                        public_actions.setdefault(entity_id, []).extend(actions)
                if ActionKind.CODEX_SESSION in self._launchers:
                    public_actions["__hub__"] = [register_codex_action(registry)]
                self._executor = ActionExecutor(registry, self._launchers)
                self._public_actions = public_actions
                self._revision = catalog.revision
            return {
                entity_id: list(actions)
                for entity_id, actions in self._public_actions.items()
            }

    def public_workspaces(
        self,
        *,
        instance_token: str | None = None,
    ) -> WorkspaceListing:
        if self._workspace_registry is None:
            return WorkspaceListing(
                workspaces=(),
                capability_error="cmux workspace discovery is not configured",
            )
        return self._workspace_registry.public_workspaces(instance_token=instance_token)

    def execute(self, action_id: str, *, workspace_id: str | None = None) -> Any:
        with self._lock:
            executor = self._executor
        if executor is None:
            self.public_actions()
            with self._lock:
                executor = self._executor
        if executor is None:  # pragma: no cover - defensive impossible state
            raise UnknownActionError("Hub actions are unavailable")
        return executor.execute(action_id, workspace_id=workspace_id)


@dataclass(frozen=True)
class CmuxLaunchResult:
    opened: bool
    started_app: bool
    attempts: int


@dataclass(frozen=True)
class ObsidianLaunchResult:
    opened: bool


@dataclass(frozen=True)
class ZoteroLaunchResult:
    opened: bool


@dataclass(frozen=True)
class CodexLaunchResult:
    opened: bool


class ObsidianLauncher:
    """Open one catalog-registered Vault artifact in Obsidian."""

    def __init__(
        self,
        vault_root: Path,
        *,
        timeout: float = 5.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self._vault_root = Path(vault_root)
        self._timeout = timeout
        self._runner = runner

    def open(self, target: str) -> ObsidianLaunchResult:
        try:
            path = safe_vault_path(self._vault_root, target)
        except (VaultPathError, TypeError, ValueError) as exc:
            raise InvalidActionTarget("Obsidian target escapes the configured Vault") from exc
        if not path.is_file():
            raise InvalidActionTarget("Obsidian target is not an existing Vault file")
        uri = "obsidian://open?" + urlencode({"path": str(path)})
        argv = ["/usr/bin/open", uri]
        try:
            result = self._runner(
                argv,
                shell=False,
                timeout=self._timeout,
                env=minimal_child_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ActionError("Opening Obsidian timed out") from exc
        except OSError as exc:
            raise ActionError("Could not start Obsidian") from exc
        if result.returncode != 0:
            raise ActionError(
                f"Obsidian could not open the registered artifact "
                f"(exit {result.returncode})"
            )
        return ObsidianLaunchResult(opened=True)


class ZoteroLauncher:
    """Open one catalog-derived Zotero item deep link."""

    def __init__(
        self,
        *,
        timeout: float = 5.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = timeout
        self._runner = runner

    def open(self, target: str) -> ZoteroLaunchResult:
        if not isinstance(target, str) or not _ZOTERO_KEY_RE.fullmatch(target):
            raise InvalidActionTarget("Zotero target is not a catalog item key")
        uri = f"zotero://select/library/items/{target}"
        argv = ["/usr/bin/open", uri]
        try:
            result = self._runner(
                argv,
                shell=False,
                timeout=self._timeout,
                env=minimal_child_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ActionError("Opening Zotero timed out") from exc
        except OSError as exc:
            raise ActionError("Could not start Zotero") from exc
        if result.returncode != 0:
            raise ActionError(
                f"Zotero could not open the registered item (exit {result.returncode})"
            )
        return ZoteroLaunchResult(opened=True)


class CmuxLauncher:
    """Open an allowlisted Notion HTTPS URL in cmux, never in another browser."""

    def __init__(
        self,
        configured_path: str | Path | None = None,
        *,
        timeout: float = 5.0,
        start_if_needed: bool = True,
        retry_attempts: int = 4,
        retry_delay: float = 0.1,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        sleeper: Callable[[float], None] = time.sleep,
        control: CmuxControl | None = None,
        workspace_registry: WorkspaceRegistry | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if retry_attempts < 0 or retry_delay < 0:
            raise ValueError("retry settings must not be negative")
        self._configured_path = Path(configured_path).expanduser() if configured_path else None
        self._timeout = timeout
        self._start_if_needed = start_if_needed
        self._retry_attempts = retry_attempts
        self._retry_delay = retry_delay
        self._runner = runner
        self._sleeper = sleeper
        self._control = control
        self._workspace_registry = workspace_registry
        if (control is None) != (workspace_registry is None):
            raise ValueError("control and workspace_registry must be configured together")

    def open(
        self,
        target: str,
        *,
        workspace_id: str | None = None,
    ) -> CmuxLaunchResult:
        url = self._validate_notion_url(target)
        if self._control is not None and self._workspace_registry is not None:
            raw_workspace = _resolve_workspace(self._workspace_registry, workspace_id)
            try:
                self._control.open(url, workspace_id=raw_workspace)
            except CmuxControlError as exc:
                raise CmuxLaunchError(_redact_targets(str(exc), url)) from exc
            return CmuxLaunchResult(opened=True, started_app=False, attempts=1)
        if workspace_id is not None:
            raise InvalidActionTarget("This cmux launcher has no workspace registry")
        executable = self._resolve_executable()
        command = [str(executable), "open", url, "--focus", "true"]
        env = minimal_child_environment(include_cmux=True)

        first = self._invoke(command, env)
        if first.returncode == 0:
            return CmuxLaunchResult(opened=True, started_app=False, attempts=1)
        if not self._start_if_needed or not self._is_no_socket_failure(first):
            raise self._command_failure(first, secrets=(url,))

        starter = self._invoke(["/usr/bin/open", "-b", _CMUX_BUNDLE_ID], env)
        if starter.returncode != 0:
            detail = self._process_detail(starter)
            raise CmuxLaunchError(f"Failed to start cmux: {detail}")

        last = first
        for retry in range(1, self._retry_attempts + 1):
            self._sleeper(self._retry_delay)
            last = self._invoke(command, env)
            if last.returncode == 0:
                return CmuxLaunchResult(
                    opened=True,
                    started_app=True,
                    attempts=retry + 1,
                )
            if not self._is_no_socket_failure(last):
                raise self._command_failure(last, secrets=(url,))
        raise CmuxLaunchError(
            f"cmux did not become ready after {self._retry_attempts} retries: "
            f"{_redact_targets(self._process_detail(last), url)}"
        )

    def _resolve_executable(self) -> Path:
        if self._configured_path is not None:
            if self._is_executable(self._configured_path):
                return self._configured_path
            raise CmuxUnavailable(
                f"Configured cmux CLI is not executable: {self._configured_path}"
            )
        path_candidate = shutil.which("cmux")
        if path_candidate:
            path = Path(path_candidate)
            if self._is_executable(path):
                return path
        if self._is_executable(DEFAULT_CMUX_PATH):
            return DEFAULT_CMUX_PATH
        raise CmuxUnavailable("cmux CLI was not found")

    @staticmethod
    def _is_executable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    @staticmethod
    def _validate_notion_url(target: str) -> str:
        if not isinstance(target, str) or target != target.strip():
            raise InvalidActionTarget("Notion target must be a clean HTTPS URL")
        if any(ord(char) < 32 for char in target):
            raise InvalidActionTarget("Notion target contains control characters")
        try:
            parsed = urlsplit(target)
            _ = parsed.port
        except ValueError as exc:
            raise InvalidActionTarget("Notion target is not a valid URL") from exc
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise InvalidActionTarget("Notion target must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidActionTarget("Notion target must not contain user information")
        try:
            host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise InvalidActionTarget("Notion target has an invalid host") from exc
        if not any(host == base or host.endswith(f".{base}") for base in _NOTION_HOSTS):
            raise InvalidActionTarget("Notion target host is not allowlisted")
        return target

    def _invoke(
        self,
        argv: list[str],
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
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
            raise CmuxLaunchError(f"Command timed out after {self._timeout:g} seconds") from exc
        except OSError as exc:
            raise CmuxUnavailable(f"Could not execute {argv[0]}: {exc}") from exc

    @staticmethod
    def _is_no_socket_failure(result: subprocess.CompletedProcess[str]) -> bool:
        output = f"{result.stdout or ''}\n{result.stderr or ''}".lower()
        return any(marker in output for marker in _NO_SOCKET_MARKERS)

    @classmethod
    def _command_failure(
        cls,
        result: subprocess.CompletedProcess[str],
        *,
        secrets: tuple[str, ...] = (),
    ) -> CmuxLaunchError:
        detail = _redact_targets(cls._process_detail(result), *secrets)
        return CmuxLaunchError(f"cmux failed to open the Notion page: {detail}")

    @staticmethod
    def _process_detail(result: subprocess.CompletedProcess[str]) -> str:
        detail = (result.stderr or result.stdout or "").strip()
        return detail[:500] if detail else f"exit status {result.returncode}"


class CmuxResourceLauncher:
    """Open a catalog PDF through the fixed loopback Hub origin in cmux."""

    def __init__(
        self,
        workspace_registry: WorkspaceRegistry,
        *,
        control: CmuxControl,
        hub_origin: str = "http://127.0.0.1:23128",
    ) -> None:
        parsed = urlsplit(hub_origin)
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("hub_origin must be a plain 127.0.0.1 HTTP origin")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("hub_origin has an invalid port") from exc
        self._hub_origin = hub_origin.rstrip("/")
        self._workspace_registry = workspace_registry
        self._control = control

    def open(
        self,
        target: str,
        *,
        workspace_id: str | None = None,
    ) -> CmuxLaunchResult:
        if not isinstance(target, str) or not _ZOTERO_KEY_RE.fullmatch(target):
            raise InvalidActionTarget("Resource target is not a catalog attachment key")
        workspace = _resolve_workspace(self._workspace_registry, workspace_id)
        url = f"{self._hub_origin}/open/paper/{target}"
        try:
            self._control.open(url, workspace_id=workspace)
        except CmuxControlError as exc:
            raise CmuxLaunchError(_redact_targets(str(exc), url, target)) from exc
        return CmuxLaunchResult(opened=True, started_app=False, attempts=1)


class CmuxArtifactLauncher:
    """Open one registered Markdown or Canvas file in a cmux preview."""

    def __init__(
        self,
        vault_root: Path,
        workspace_registry: WorkspaceRegistry,
        *,
        control: CmuxControl,
    ) -> None:
        self._vault_root = Path(vault_root)
        self._workspace_registry = workspace_registry
        self._control = control

    def open(
        self,
        target: str,
        *,
        workspace_id: str | None = None,
    ) -> CmuxLaunchResult:
        try:
            path = safe_vault_path(self._vault_root, target)
        except (VaultPathError, TypeError, ValueError) as exc:
            raise InvalidActionTarget("cmux preview target escapes the configured Vault") from exc
        if path.suffix.lower() not in {".md", ".canvas"} or not path.is_file():
            raise InvalidActionTarget("cmux preview target is not a registered readable artifact")
        workspace = _resolve_workspace(self._workspace_registry, workspace_id)
        try:
            self._control.open(str(path), workspace_id=workspace)
        except CmuxControlError as exc:
            raise CmuxLaunchError(_redact_targets(str(exc), str(path), target)) from exc
        return CmuxLaunchResult(opened=True, started_app=False, attempts=1)


class CodexLauncher:
    """Start one blank native Codex session at a server-fixed trusted cwd."""

    def __init__(
        self,
        trusted_cwd: Path,
        workspace_registry: WorkspaceRegistry,
        *,
        control: CmuxControl,
    ) -> None:
        try:
            resolved = Path(trusted_cwd).resolve(strict=True)
        except OSError as exc:
            raise ValueError("trusted_cwd must be an existing directory") from exc
        if not resolved.is_dir():
            raise ValueError("trusted_cwd must be an existing directory")
        self._trusted_cwd = resolved
        self._workspace_registry = workspace_registry
        self._control = control

    def open(
        self,
        target: str,
        *,
        workspace_id: str | None = None,
    ) -> CodexLaunchResult:
        if target != _CODEX_BLANK_TARGET:
            raise InvalidActionTarget("Codex action must create a blank native session")
        workspace = _resolve_workspace(self._workspace_registry, workspace_id)
        try:
            self._control.new_codex_session(
                workspace_id=workspace,
                working_directory=self._trusted_cwd,
            )
        except CmuxControlError as exc:
            raise CmuxLaunchError(
                _redact_targets(str(exc), str(self._trusted_cwd), target)
            ) from exc
        return CodexLaunchResult(opened=True)


def _resolve_workspace(
    registry: WorkspaceRegistry,
    workspace_id: str | None,
) -> str:
    if not workspace_id:
        raise InvalidActionTarget("A cmux workspace selection is required")
    try:
        return registry.resolve(workspace_id)
    except CmuxControlError as exc:
        raise InvalidActionTarget(str(exc)) from exc


def _redact_targets(detail: str, *targets: str) -> str:
    redacted = detail
    for target in targets:
        if target:
            redacted = redacted.replace(target, "<registered target>")
    return redacted
