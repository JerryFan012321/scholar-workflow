"""Reviewed local Codex setup and approved model options for Hub tasks.

Detection examines configured and fixed installer locations only. Catalog probes
use Codex's own authentication through a short-lived app-server; this module
never opens auth files or serializes process output into public diagnostics.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import queue
import re
import secrets
import signal
import stat
import subprocess
import tempfile
import threading
import time
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from scholar_workflow.hub.cmux import minimal_child_environment
from scholar_workflow.hub.directory import ProjectRegistry, ToolDefinition, ToolRegistry
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.hub.models import HubModel
from scholar_workflow.hub.routing import ExecutionTarget, ExecutionTargetRegistry, ExecutionTargetRegistryDocument
from scholar_workflow.hub.tasks import (
    CodexCapabilityProbe,
    CodexModelProfile,
    TaskEffort,
    TaskRecipe,
    TaskRecipeRegistry,
    TaskRecipeRegistryDocument,
    TaskRunState,
    TaskSafetyPolicy,
    TaskStore,
)
from scholar_workflow.hub.terminal_worker import (
    TerminalWorkerRuntimeConfig,
    TerminalWorkerState,
)

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_RECIPE_ID = "general-research"
_POLICY_ID = "default-safe"
_MAX_CATALOG_BYTES = 1024 * 1024


class CodexSetupError(ValueError):
    """A reviewed setup choice is unavailable, stale, or invalid."""


class CodexSetupConfirmRequest(HubModel):
    candidate_id: str
    model_profile_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=64)
    sandbox: Literal["read-only", "workspace-write"] = "workspace-write"

    @field_validator("candidate_id", "model_profile_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        if not _ID.fullmatch(value):
            raise ValueError("setup choices must be reviewed opaque identifiers")
        return value

    @field_validator("target_ids")
    @classmethod
    def _targets(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)) or any(not _ID.fullmatch(value) for value in values):
            raise ValueError("setup targets must be unique registered identifiers")
        return values


def _profile_id(model: str) -> str:
    return "model-" + hashlib.sha256(model.encode("utf-8")).hexdigest()[:24]


def _config_defaults(config_home: Path) -> tuple[str | None, str | None]:
    """Read only the two root scalar settings, never auth or provider sections."""

    path = config_home / "config.toml"
    if path.is_symlink() or not path.is_file():
        return None, None
    values: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("["):
                    break
                match = re.match(r"^(model|model_reasoning_effort)\s*=", stripped)
                if match is None or len(line) > 1024:
                    continue
                try:
                    value = tomllib.loads(stripped).get(match.group(1))
                except tomllib.TOMLDecodeError:
                    continue
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", value):
                    values[match.group(1)] = value
    except (OSError, UnicodeError):
        return None, None
    return values.get("model"), values.get("model_reasoning_effort")


class CodexModelCatalog:
    """Bounded JSON-RPC model/list probe with deadline and process cleanup."""

    def __init__(
        self, *, timeout: float = 8.0,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout = timeout
        self._popen = popen_factory
        self._monotonic = monotonic

    def load(self, executable: Path) -> list[dict[str, Any]]:
        env = minimal_child_environment()
        if os.environ.get("CODEX_HOME"):
            env["CODEX_HOME"] = os.environ["CODEX_HOME"]
        process = self._popen(
            [str(executable), "app-server"], shell=False, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env=env, start_new_session=True, bufsize=1,
        )
        events: queue.Queue[str | None | Exception] = queue.Queue(maxsize=128)
        deadline = self._monotonic() + self.timeout

        def read_stdout() -> None:
            consumed = 0
            try:
                assert process.stdout is not None
                while True:
                    line = process.stdout.readline(_MAX_CATALOG_BYTES + 1)
                    if not line:
                        events.put_nowait(None)
                        return
                    consumed += len(line.encode("utf-8"))
                    if consumed > _MAX_CATALOG_BYTES:
                        events.put_nowait(CodexSetupError("Codex model catalog exceeded its response limit"))
                        return
                    events.put_nowait(line)
            except (OSError, ValueError, queue.Full):
                try:
                    events.put_nowait(CodexSetupError("Codex model catalog could not be read"))
                except queue.Full:
                    pass

        reader = threading.Thread(target=read_stdout, name="codex-model-catalog", daemon=True)
        reader.start()

        def send(payload: dict[str, Any]) -> None:
            assert process.stdin is not None
            process.stdin.write(json.dumps(payload) + "\n")
            process.stdin.flush()

        def response(identifier: int) -> dict[str, Any]:
            while True:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise CodexSetupError("Codex model catalog timed out")
                try:
                    line = events.get(timeout=remaining)
                except queue.Empty:
                    raise CodexSetupError("Codex model catalog timed out") from None
                if line is None or isinstance(line, Exception):
                    raise CodexSetupError("Codex model catalog is unavailable")
                try:
                    payload = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(payload, dict) or payload.get("id") != identifier:
                    continue
                if "error" in payload or not isinstance(payload.get("result"), dict):
                    raise CodexSetupError("Codex model catalog request was refused")
                return payload["result"]

        try:
            send({"id": 1, "method": "initialize", "params": {
                "clientInfo": {"name": "scholar-workflow", "version": "1"},
                "capabilities": {"experimentalApi": False},
            }})
            response(1)
            send({"method": "initialized"})
            rows: list[dict[str, Any]] = []
            cursor: str | None = None
            seen_cursors: set[str] = set()
            for identifier in range(2, 12):
                send({"id": identifier, "method": "model/list", "params": {
                    "cursor": cursor, "limit": 100, "includeHidden": False,
                }})
                payload = response(identifier)
                data = payload.get("data", [])
                if not isinstance(data, list):
                    raise CodexSetupError("Codex model catalog returned an invalid list")
                rows.extend(row for row in data if isinstance(row, dict))
                cursor = payload.get("nextCursor")
                if cursor is None:
                    return rows
                if not isinstance(cursor, str) or cursor in seen_cursors:
                    raise CodexSetupError("Codex model catalog returned an invalid cursor")
                seen_cursors.add(cursor)
            raise CodexSetupError("Codex model catalog exceeded its page limit")
        finally:
            if process.stdin is not None:
                process.stdin.close()
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, OSError):
                        process.kill()
                    process.wait(timeout=1)
            if process.stdout is not None:
                process.stdout.close()
            reader.join(timeout=0.2)


@dataclass
class _ReviewedCandidate:
    executable: Path
    identity: tuple[int, int, int, int]
    profiles: list[CodexModelProfile]
    target_ids: set[str]
    targets_revision: str
    recipes_revision: str
    sources_revision: str
    target_suggestions: dict[str, ExecutionTarget]
    manifest_revisions: dict[str, str]
    expires_at: float


class CodexSetupService:
    """Preview installed Codex, then persist only reviewed local choices."""

    def __init__(
        self, root: Path, *, project_registry: ProjectRegistry,
        source_registry: KnowledgeSourceRegistry,
        target_registry: ExecutionTargetRegistry | None = None,
        probe_factory: Callable[[Path], CodexCapabilityProbe] = CodexCapabilityProbe,
        catalog_loader: Callable[[Path], list[dict[str, Any]]] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        user_home: Path | None = None, config_home: Path | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = Path(root)
        self.recipes = TaskRecipeRegistry(self.root / "task-recipes.json")
        self._projects = project_registry
        self._sources = source_registry
        self.targets = target_registry or ExecutionTargetRegistry(
            self.root / "execution-targets.json", project_registry=project_registry,
            source_registry=source_registry,
        )
        self._probe_factory = probe_factory
        self._catalog_loader = catalog_loader or CodexModelCatalog().load
        self._runner = runner
        self._home = user_home or Path.home()
        self._config_home = config_home or Path(os.environ.get("CODEX_HOME", str(self._home / ".codex")))
        self._clock = monotonic
        self._previews: dict[str, _ReviewedCandidate] = {}
        self._lock = threading.RLock()

    def public_targets(self) -> list[dict[str, Any]]:
        try:
            targets = self.targets.load().targets
            projects = {row.project_id: row for row in self._projects.load()}
            sources = self._sources.load_document()
        except (OSError, RuntimeError, ValueError):
            return []
        rows = []
        for target in targets:
            source = next((row for row in sources.sources if row.enabled and row.folder_id == target.registered_root_id), None)
            folder = next((row for row in sources.folders if row.folder_id == target.registered_root_id), None)
            project = projects.get(target.registered_root_id) if target.kind == "project" else None
            title = project.display_name if project else folder.root.name if folder else target.target_id
            if target.field_id and folder:
                try:
                    manifest = FieldService._load_manifest(folder.root)
                    title = next(row.title for row in manifest.fields if row.field_id == target.field_id)
                except (OSError, RuntimeError, ValueError, StopIteration):
                    pass
            available = False
            try:
                self.targets.resolve(target.target_id, capability="codex")
            except (OSError, RuntimeError, ValueError):
                pass
            else:
                available = True
            rows.append({
                "target_id": target.target_id,
                "title": title,
                "kind": target.kind, "registered_root_id": target.registered_root_id,
                "source_id": target.source_id or (source.source_id if source and target.kind == "vault" else None),
                "field_id": target.field_id,
                "project_id": target.registered_root_id if project else None,
                "capabilities": [cap for cap in target.capabilities if cap == "codex"],
                "available": available,
                "reason": None if available else "Execution target does not currently allow Codex tasks",
            })
        return rows

    def public_options(self) -> dict[str, Any]:
        try:
            profiles = self.recipes.load().model_profiles
        except (OSError, RuntimeError, ValueError):
            profiles = []
        default_profile_id = next((row.profile_id for row in profiles if row.is_default), None)
        selected = next((row for row in profiles if row.profile_id == default_profile_id), None)
        try:
            path = self.root / "task-preferences.json"
            if not path.is_symlink() and path.is_file():
                preference = json.loads(path.read_text(encoding="utf-8"))
                profile = next((row for row in profiles if row.profile_id == preference.get("model_profile_id")), None)
                if profile and preference.get("reasoning_effort") in profile.supported_reasoning_efforts:
                    selected = profile
                    selected_effort = preference["reasoning_effort"]
                else:
                    selected_effort = selected.default_reasoning_effort if selected else None
            else:
                selected_effort = selected.default_reasoning_effort if selected else None
        except (OSError, ValueError, AttributeError):
            selected_effort = selected.default_reasoning_effort if selected else None
        return {
            "model_profiles": [row.public() for row in profiles],
            "default_profile_id": default_profile_id,
            "selected_model_profile_id": selected.profile_id if selected else None,
            "selected_reasoning_effort": selected_effort,
            "available": bool(profiles),
            "reason": None if profiles else "Configure Codex to approve model choices",
        }

    def save_preferences(self, profile_id: str, reasoning_effort: str) -> dict[str, Any]:
        profile = self.recipes.model_profile_map().get(profile_id)
        if profile is None or reasoning_effort not in profile.supported_reasoning_efforts:
            raise CodexSetupError("Select an approved model profile and supported reasoning effort")
        with self._lock, self._write_guard():
            self._save_preferences_locked(profile_id, reasoning_effort)
        return self.public_options()

    def _save_preferences_locked(self, profile_id: str, reasoning_effort: str) -> None:
        path = self.root / "task-preferences.json"
        if path.is_symlink():
            raise CodexSetupError("Task preferences cannot use a symlink")
        descriptor, name = tempfile.mkstemp(prefix=".task-preferences.", dir=self.root)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"model_profile_id": profile_id, "reasoning_effort": reasoning_effort}, handle)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def preview(self) -> dict[str, Any]:
        targets, target_suggestions = self._suggested_targets()
        sandbox = "workspace-write"
        selected_targets: set[str] = set()
        try:
            current = self.recipes.load()
            recipe = next((row for row in current.recipes if row.recipe_id == _RECIPE_ID), None)
            if recipe is not None:
                selected_targets = set(recipe.allowed_target_ids or ())
                policy = next((row for row in current.safety_policies if row.policy_id == recipe.safety_policy_id), None)
                if policy is not None:
                    sandbox = policy.sandbox
        except (OSError, RuntimeError, ValueError):
            pass
        for target in targets:
            target["selected"] = target["target_id"] in selected_targets
        manifest_revisions = self._source_manifest_revisions()
        available_targets = {row["target_id"] for row in targets if row["available"]}
        candidates: list[dict[str, Any]] = []
        with self._lock:
            self._previews = {key: value for key, value in self._previews.items() if value.expires_at > self._clock()}
            for path in self._candidate_paths():
                token = "candidate-" + secrets.token_hex(16)
                try:
                    capabilities = self._probe_factory(path).probe()
                    available = capabilities.available and capabilities.create and capabilities.resume and capabilities.fork
                except (OSError, RuntimeError, ValueError):
                    available = False
                profiles = self._profiles(path) if available else []
                available = available and bool(profiles)
                row = {
                    "candidate_id": token, "title": "Codex", "version": self._version(path),
                    "available": available,
                    "reason": None if available else "Required Codex capabilities or confirmed model settings are unavailable",
                    "model_profiles": [profile.public() for profile in profiles],
                    "default_profile_id": next((profile.profile_id for profile in profiles if profile.is_default), None),
                }
                candidates.append(row)
                if available:
                    self._previews[token] = _ReviewedCandidate(
                        executable=path, identity=self._identity(path), profiles=profiles,
                        target_ids=available_targets, targets_revision=self.targets.revision(),
                        recipes_revision=self._recipe_revision(), expires_at=self._clock() + 600,
                        sources_revision=self._sources.revision(), target_suggestions=target_suggestions,
                        manifest_revisions=manifest_revisions,
                    )
        recommended = next((row for row in candidates if row["available"]), None)
        options = self.public_options()
        return {
            "configured": bool(options["model_profiles"]), "candidates": candidates,
            "model_profiles": recommended["model_profiles"] if recommended else [],
            "default_profile_id": recommended["default_profile_id"] if recommended else None,
            "targets": targets, "sandbox_options": [
                {"value": "workspace-write", "label": "Read and write the selected target"},
                {"value": "read-only", "label": "Read the selected target"},
            ],
            "sandbox": sandbox,
            "reason": None if recommended else "No supported local Codex installation was found",
            "catalog_note": "Listed models are choices reported by Codex; account access is confirmed only by a successful run",
        }

    def confirm(self, payload: dict[str, Any] | CodexSetupConfirmRequest) -> dict[str, Any]:
        request = CodexSetupConfirmRequest.model_validate(payload)
        with self._lock, self._write_guard():
            candidate = self._previews.get(request.candidate_id)
            if candidate is None or candidate.expires_at <= self._clock():
                raise CodexSetupError("Codex setup preview expired; preview the choices again")
            if self._identity(candidate.executable) != candidate.identity:
                raise CodexSetupError("Codex installation changed after preview")
            if (
                self.targets.revision() != candidate.targets_revision
                or self._recipe_revision() != candidate.recipes_revision
                or self._sources.revision() != candidate.sources_revision
                or self._source_manifest_revisions() != candidate.manifest_revisions
            ):
                raise CodexSetupError("Codex configuration or targets changed after preview")
            if not set(request.target_ids) <= candidate.target_ids:
                raise CodexSetupError("Select only available targets shown in the setup preview")
            profile = next((row for row in candidate.profiles if row.profile_id == request.model_profile_id), None)
            if profile is None:
                raise CodexSetupError("Select a model profile shown in the setup preview")
            self._require_idle(TerminalWorkerState(self.root / "task-worker"))
            rollback = self._register_selected_targets(candidate, request.target_ids)
            try:
                result = self._register(
                    candidate.executable, profiles=candidate.profiles, selected_profile=profile,
                    target_ids=request.target_ids, sandbox=request.sandbox,
                )
            except (OSError, RuntimeError, ValueError):
                rollback()
                raise
            self._previews.pop(request.candidate_id, None)
            return result

    def register_explicit(
        self, *, executable: Path, model: str, sandbox: Literal["read-only", "workspace-write"],
        target_ids: list[str], reasoning_effort: str = "medium",
    ) -> dict[str, Any]:
        """CLI fallback: explicitly approve one model while retaining other choices."""

        path = Path(executable)
        if not path.is_absolute():
            raise CodexSetupError("Codex executable must be an absolute local path")
        path = path.resolve(strict=True)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise CodexSetupError("Codex executable is unavailable")
        capabilities = self._probe_factory(path).probe()
        if not (capabilities.available and capabilities.create and capabilities.resume and capabilities.fork):
            raise CodexSetupError("Configured Codex lacks required task capabilities")
        try:
            known_profile = next((row for row in self.recipes.load().model_profiles if row.model == model and not row.is_default), None)
        except (OSError, RuntimeError, ValueError):
            known_profile = None
        profile = CodexModelProfile(
            profile_id=_profile_id(model), title=model, model=model,
            supported_reasoning_efforts=[reasoning_effort], default_reasoning_effort=reasoning_effort,
            source="explicit",
        )
        if known_profile is not None:
            profile = known_profile.model_copy(update={
                "default_reasoning_effort": reasoning_effort
                if reasoning_effort in known_profile.supported_reasoning_efforts else known_profile.default_reasoning_effort,
            })
        default = profile.model_copy(update={"profile_id": "default", "title": f"Default · {model}", "is_default": True})
        with self._lock, self._write_guard():
            for target_id in target_ids:
                self.targets.resolve(target_id, capability="codex")
            return self._register(path, profiles=[profile, default], selected_profile=default, target_ids=target_ids, sandbox=sandbox)

    def _register(
        self, executable: Path, *, profiles: list[CodexModelProfile], selected_profile: CodexModelProfile,
        target_ids: list[str], sandbox: Literal["read-only", "workspace-write"],
    ) -> dict[str, Any]:
        worker = TerminalWorkerState(self.root / "task-worker")
        self._require_idle(worker)
        existing = self.recipes.load() if self.recipes.path.exists() else TaskRecipeRegistryDocument()
        approved = {row.profile_id: row for row in existing.model_profiles}
        approved.update({row.profile_id: row for row in profiles})
        default = selected_profile.model_copy(update={"profile_id": "default", "title": f"Default · {selected_profile.model}", "is_default": True})
        approved["default"] = default
        for identifier, row in tuple(approved.items()):
            if identifier != "default" and row.is_default:
                approved[identifier] = row.model_copy(update={"is_default": False})
        policy = TaskSafetyPolicy(policy_id=_POLICY_ID, policy_version=1, model=selected_profile.model, sandbox=sandbox)
        recipe = TaskRecipe(
            recipe_id=_RECIPE_ID, title="General research task", project_required=True,
            allowed_provider_ids=["field-manifest", "obsidian", "zotflow", "project-registry", "tool-registry", "zotero"],
            allowed_target_ids=sorted(target_ids), allowed_tool_ids=["codex"],
            allowed_model_profile_ids=sorted(approved), safety_policy_id=_POLICY_ID,
            allowed_efforts=[TaskEffort.FAST, TaskEffort.STANDARD, TaskEffort.DEEP],
        )
        recipe_document = TaskRecipeRegistryDocument(
            recipes=[row for row in existing.recipes if row.recipe_id != _RECIPE_ID] + [recipe],
            safety_policies=[row for row in existing.safety_policies if row.policy_id != _POLICY_ID] + [policy],
            model_profiles=list(approved.values()),
        )
        generation = "worker_" + secrets.token_urlsafe(24)
        runtime = TerminalWorkerRuntimeConfig(
            generation=generation, codex_executable=executable,
            recipe_registry_path=self.recipes.path.resolve(), task_store_path=(self.root / "tasks.json").resolve(),
            execution_target_registry_path=self.targets.path.resolve(),
            project_registry_path=self._projects.path.resolve(), source_registry_path=self._sources.path.resolve(),
        )
        tools = ToolRegistry(self.root / "tools.json")
        other_tools = [row for row in tools.load() if row.tool_id != "codex"]
        tool_rows = [*other_tools, ToolDefinition(
            tool_id="codex", display_name="Codex", source="host-registration", tool_type="codex",
            capabilities=["task.execute"], recipe_ids=[_RECIPE_ID], healthcheck="codex.exec", enabled=True,
        )]
        paths = [self.recipes.path, worker.runtime_path, tools.path, self.root / "task-preferences.json"]
        before: dict[Path, bytes | None] = {}
        changed: dict[Path, str] = {}
        for path in paths:
            if path.is_symlink():
                raise CodexSetupError("Codex configuration cannot use a symlink")
            before[path] = path.read_bytes() if path.exists() else None
        try:
            self.recipes.save(recipe_document)
            changed[self.recipes.path] = self._file_digest(self.recipes.path)
            worker.save_runtime(runtime)
            changed[worker.runtime_path] = self._file_digest(worker.runtime_path)
            tools.save(tool_rows)
            changed[tools.path] = self._file_digest(tools.path)
            self._save_preferences_locked("default", default.default_reasoning_effort)
            changed[paths[-1]] = self._file_digest(paths[-1])
        except (OSError, RuntimeError, ValueError):
            for path, expected in reversed(tuple(changed.items())):
                self._restore_file(path, before[path], expected)
            raise
        return {"configured": True, "generation": generation, "restart_required": False,
                "model_profile_id": "default", "target_ids": sorted(target_ids),
                "sandbox": sandbox, **self.public_options()}

    @staticmethod
    def _file_digest(path: Path) -> str:
        if path.is_symlink():
            raise CodexSetupError("Codex configuration cannot use a symlink")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def _restore_file(cls, path: Path, content: bytes | None, expected: str) -> None:
        if cls._file_digest(path) != expected:
            raise CodexSetupError("Codex setup failed and a concurrent configuration change prevents rollback")
        if content is None:
            path.unlink()
            return
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.recovery.", dir=path.parent)
        temporary = Path(name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _suggested_targets(self) -> tuple[list[dict[str, Any]], dict[str, ExecutionTarget]]:
        rows = self.public_targets()
        existing_roots = {(row["kind"], row["registered_root_id"], row.get("field_id")) for row in rows}
        suggestions: dict[str, ExecutionTarget] = {}
        sources = self._sources.load_document()
        folders = {row.folder_id: row for row in sources.folders}
        for source in sources.sources:
            folder = folders.get(source.folder_id)
            if not source.enabled or folder is None or not folder.enabled:
                continue
            try:
                root = self._sources.resolve(source.source_id, capability="read")
                manifest = FieldService._load_manifest(root)
                if manifest.source_id != source.source_id:
                    continue
                fields = manifest.fields
            except (OSError, RuntimeError, ValueError):
                fields = []
            options = [(field.field_id, field.title, field.relative_root) for field in fields]
            if not options:
                options = [(None, folder.root.name, ".")]
            for field_id, title, relative_root in options:
                if ("vault", source.folder_id, field_id) in existing_roots:
                    continue
                target_id = "target-" + hashlib.sha256(f"vault\0{source.folder_id}\0{field_id or ''}".encode()).hexdigest()[:24]
                field_root = folder.root / relative_root
                available = field_root.is_dir() and not folder.root.is_symlink() and not field_root.is_symlink()
                target = ExecutionTarget(target_id=target_id, kind="vault", registered_root_id=source.folder_id,
                                         source_id=source.source_id, field_id=field_id, capabilities=["codex"])
                suggestions[target_id] = target
                rows.append({"target_id": target_id, "title": title, "kind": "vault",
                             "registered_root_id": source.folder_id, "source_id": source.source_id,
                             "field_id": field_id, "project_id": None, "available": available,
                             "capabilities": ["codex"], "registration_required": True,
                             "permission_note": "Confirming authorizes Codex in this selected Field or Vault folder",
                             "reason": None if available else "Registered knowledge folder is unavailable"})
        for project in self._projects.load():
            if not project.enabled or ("project", project.project_id, None) in existing_roots:
                continue
            target_id = "target-" + hashlib.sha256(f"project\0{project.project_id}".encode()).hexdigest()[:24]
            available = "codex" in project.capabilities and project.root.is_dir() and not project.root.is_symlink()
            target = ExecutionTarget(target_id=target_id, kind="project", registered_root_id=project.project_id, capabilities=["codex"])
            suggestions[target_id] = target
            rows.append({"target_id": target_id, "title": project.display_name, "kind": "project",
                         "registered_root_id": project.project_id, "source_id": None,
                         "project_id": project.project_id, "available": available, "capabilities": ["codex"],
                         "registration_required": True,
                         "reason": None if available else "Register the project's Codex capability before selecting it"})
        return rows, suggestions

    def _register_selected_targets(self, candidate: _ReviewedCandidate, target_ids: list[str]) -> Callable[[], None]:
        selected = [candidate.target_suggestions[value] for value in target_ids if value in candidate.target_suggestions]
        if not selected:
            for target_id in target_ids:
                self.targets.resolve(target_id, capability="codex")
            return lambda: None
        source_before = self._sources.load_document()
        targets_before = self.targets.load()
        folder_grants: dict[str, set[str]] = {}
        for target in selected:
            if target.kind == "vault":
                folder_grants.setdefault(target.registered_root_id, set()).add(
                    f"codex.field:{target.field_id}" if target.field_id is not None else "codex"
                )
        updated_sources = source_before.model_copy(update={"folders": [
            row.model_copy(update={"capabilities": sorted(set(row.capabilities) | folder_grants[row.folder_id])})
            if row.folder_id in folder_grants else row for row in source_before.folders
        ]})
        source_changed = any(
            row.folder_id in folder_grants
            and not folder_grants[row.folder_id].issubset(row.capabilities)
            for row in source_before.folders
        )
        if source_changed:
            self._sources.save(updated_sources, expected_revision=candidate.sources_revision)
        source_after_revision = self._sources.revision()
        try:
            self.targets.save(ExecutionTargetRegistryDocument(
                targets=[*targets_before.targets, *selected],
            ), expected_revision=candidate.targets_revision)
        except (OSError, RuntimeError, ValueError):
            if source_changed:
                self._sources.save(source_before, expected_revision=source_after_revision)
            raise
        target_after_revision = self.targets.revision()

        def rollback() -> None:
            self.targets.save(targets_before, expected_revision=target_after_revision)
            if source_changed:
                self._sources.save(source_before, expected_revision=source_after_revision)

        for target_id in target_ids:
            try:
                self.targets.resolve(target_id, capability="codex")
            except (OSError, RuntimeError, ValueError):
                rollback()
                raise
        return rollback

    def _require_idle(self, worker: TerminalWorkerState) -> None:
        store_path = self.root / "tasks.json"
        if store_path.exists():
            if any(row.state in {TaskRunState.QUEUED, TaskRunState.RUNNING, TaskRunState.RECOVERY_REQUIRED} for row in TaskStore(store_path).snapshot().runs):
                raise CodexSetupError("Codex configuration cannot change while a run is active or queued")
        if worker.runtime_path.exists():
            config = worker.current_runtime()
            if worker.slots_path.is_dir():
                for path in worker.slots_path.iterdir():
                    if not path.is_dir() or path.is_symlink():
                        continue
                    status = worker.public_status(slot_id=path.name, generation=config.generation)
                    if status.active_run_id or status.queued_run_ids:
                        raise CodexSetupError("Codex configuration cannot change while a worker is busy")
                    if status.worker_alive:
                        worker.request_stop(slot_id=status.slot_id, generation=config.generation)

    def _candidate_paths(self) -> list[Path]:
        paths: list[Path] = []
        worker = TerminalWorkerState(self.root / "task-worker")
        if worker.runtime_path.is_file():
            try:
                paths.append(worker.current_runtime().codex_executable)
            except (OSError, RuntimeError, ValueError):
                pass
        paths.extend([
            self._home / ".local/bin/codex", self._home / ".npm-global/bin/codex",
            Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex"),
            Path("/Applications/Codex.app/Contents/Resources/codex"),
        ])
        found: list[Path] = []
        for path in paths:
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if resolved not in found and resolved.is_file() and os.access(resolved, os.X_OK):
                found.append(resolved)
        return found

    def _profiles(self, executable: Path) -> list[CodexModelProfile]:
        model, effort = _config_defaults(self._config_home)
        profiles: list[CodexModelProfile] = []
        default_model: str | None = None
        try:
            catalog = self._catalog_loader(executable)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            catalog = []
        for row in catalog:
            if row.get("hidden"):
                continue
            raw_model = row.get("model") or row.get("id")
            efforts = row.get("supportedReasoningEfforts", [])
            supported = [item.get("reasoningEffort") if isinstance(item, dict) else item for item in efforts]
            try:
                profile = CodexModelProfile(
                    profile_id=_profile_id(raw_model), title=row.get("displayName") or raw_model,
                    model=raw_model, supported_reasoning_efforts=supported,
                    default_reasoning_effort=row.get("defaultReasoningEffort"), source="codex-catalog",
                )
            except (TypeError, ValueError, AttributeError):
                continue
            if profile.profile_id in {item.profile_id for item in profiles}:
                continue
            profiles.append(profile)
            if row.get("isDefault"):
                default_model = profile.model
        if profiles:
            default = next((row for row in profiles if row.model == model), None)
            default = default or next((row for row in profiles if row.model == default_model), profiles[0])
            if effort in default.supported_reasoning_efforts:
                default = default.model_copy(update={"default_reasoning_effort": effort})
        else:
            try:
                existing_document = self.recipes.load()
                existing = existing_document.model_profiles
            except (OSError, RuntimeError, ValueError):
                existing = []
                existing_document = None
            if model is None:
                default = next((row for row in existing if row.is_default), None)
                if default is None and existing_document is not None:
                    policy = next((row for row in existing_document.safety_policies if row.policy_id == _POLICY_ID), None)
                    if policy is not None:
                        default = CodexModelProfile(
                            profile_id=_profile_id(policy.model), title=policy.model, model=policy.model,
                            supported_reasoning_efforts=["medium"], default_reasoning_effort="medium", source="explicit",
                        )
                        existing = [default]
                if default is None:
                    return []
                profiles = existing
            else:
                default = CodexModelProfile(
                    profile_id=_profile_id(model), title=model, model=model,
                    supported_reasoning_efforts=[effort or "medium"], default_reasoning_effort=effort or "medium",
                    source="local-config",
                )
                profiles = [default]
        alias = default.model_copy(update={"profile_id": "default", "title": f"Default · {default.title}", "is_default": True})
        return [alias, *[row.model_copy(update={"is_default": False}) for row in profiles if row.profile_id != "default"]]

    def _version(self, executable: Path) -> str | None:
        try:
            result = self._runner([str(executable), "--version"], shell=False, timeout=3,
                                  capture_output=True, text=True, env=minimal_child_environment(), check=False)
            if result.returncode == 0:
                match = re.search(r"\b\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?\b", result.stdout[:500])
                return match.group(0) if match else None
        except (OSError, subprocess.SubprocessError):
            pass
        return None

    def _recipe_revision(self) -> str:
        if self.recipes.path.is_symlink():
            raise CodexSetupError("Task recipe registry cannot use a symlink")
        try:
            content = self.recipes.path.read_bytes()
        except FileNotFoundError:
            return "absent"
        return "sha256:" + hashlib.sha256(content).hexdigest()

    def _source_manifest_revisions(self) -> dict[str, str]:
        revisions = {}
        for source in self._sources.load_document().sources:
            if not source.enabled:
                continue
            try:
                root = self._sources.resolve(source.source_id, capability="read")
                revisions[source.source_id] = FieldService._manifest_hash(root)
            except (OSError, RuntimeError, ValueError):
                revisions[source.source_id] = "unavailable"
        return revisions

    @staticmethod
    def _identity(path: Path) -> tuple[int, int, int, int]:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode) or not os.access(path, os.X_OK):
            raise CodexSetupError("Detected Codex executable is no longer available")
        return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns

    @contextmanager
    def _write_guard(self) -> Iterator[None]:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.is_symlink():
            raise CodexSetupError("Codex setup state cannot use a symlink")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.root / ".codex-setup.lock", flags, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise CodexSetupError("Codex setup lock must be a regular file")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


__all__ = ["CodexModelCatalog", "CodexSetupConfirmRequest", "CodexSetupError", "CodexSetupService"]
