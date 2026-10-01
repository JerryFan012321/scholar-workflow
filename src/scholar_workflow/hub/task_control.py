"""Production Hub v3 task control with separate routing and authorization.

The public browser contract contains only an opaque action, destination, target,
bounded brief, effort, and idempotency key.  This service maps the action to a
registered recipe, resolves the target to a trusted cwd, resolves the destination
to a live raw cmux workspace, and queues the durable task for a long-lived terminal
worker.  Neither host paths nor server-owned Codex configuration cross the public
boundary.
"""

from __future__ import annotations

import hashlib
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from scholar_workflow.hub.cmux import CmuxControl, CmuxControlError
from scholar_workflow.hub.destinations import DestinationRegistry
from scholar_workflow.hub.directory import EntityRef, ProjectRegistry
from scholar_workflow.knowledge.fields import FieldService, KnowledgeSourceRegistry
from scholar_workflow.knowledge.catalog_models import HubModel
from scholar_workflow.hub.routing import (
    ExecutionTargetError,
    ExecutionTargetRegistry,
    TaskActionRequest,
)
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    CodexCapabilityProbe,
    LogicalTask,
    TaskContractError,
    TaskCoordinator,
    TaskEffort,
    TaskRecipe,
    TaskRecipeRegistry,
    TaskRequest,
    TaskRun,
    TaskStore,
    TaskSubmission,
)
from scholar_workflow.hub.terminal_worker import (
    TerminalTaskBroker,
    TerminalWorkerError,
    TerminalWorkerState,
    build_terminal_worker_command,
)


class PublicExecutionTarget(HubModel):
    """Browser-safe execution target metadata without its registered root."""

    target_id: str
    title: str = "Execution target"
    kind: str
    registered_root_id: str | None = None
    source_id: str | None = None
    field_id: str | None = None
    project_id: str | None = None
    capabilities: list[str]
    available: bool
    reason: str | None = None


class PublicTaskAction(HubModel):
    """An opaque action backed by exactly one server-owned TaskRecipe."""

    action_id: str
    title: str
    allowed_efforts: list[TaskEffort]
    allowed_target_ids: list[str]
    allowed_model_profile_ids: list[str] = Field(default_factory=list)
    destination_required: bool = True
    available: bool
    reason: str | None = None


class PublicTaskRun(HubModel):
    """Durable task-run state with no prompt, argv, cwd, PID, or thread ID."""

    task_id: str
    run_id: str
    state: str
    mode: str
    cancel_requested: bool
    terminal_routed: bool = True


class PublicTask(HubModel):
    """Logical task status without configuration fingerprints or private identity."""

    task_id: str
    action_id: str
    title: str
    effort: TaskEffort
    model_profile_id: str | None = None
    model_title: str | None = None
    reasoning_effort: str | None = None
    archived: bool
    thread_available: bool
    runs: list[PublicTaskRun]


class TaskDispatchResult(PublicTaskRun):
    """Immediate result of a create, resume, or fork reservation."""

    reused: bool


class TaskActionRegistry:
    """Derive stable opaque actions from the explicit recipe registry."""

    def __init__(self, recipes: TaskRecipeRegistry) -> None:
        self._recipes = recipes

    @staticmethod
    def action_id(recipe_id: str) -> str:
        digest = hashlib.sha256(f"task-recipe\0{recipe_id}".encode()).hexdigest()
        return f"task:{digest[:32]}"

    def mappings(self) -> dict[str, TaskRecipe]:
        result: dict[str, TaskRecipe] = {}
        for recipe in self._recipes.load().recipes:
            action_id = self.action_id(recipe.recipe_id)
            if action_id in result:
                raise TaskContractError("task action identity collision")
            result[action_id] = recipe
        return result

    def resolve(self, action_id: str) -> TaskRecipe:
        try:
            return self.mappings()[action_id]
        except KeyError:
            raise KeyError("unknown task action") from None


class TaskControlService:
    """Route validated Hub task actions to private long-lived cmux workers."""

    def __init__(
        self,
        *,
        recipes: TaskRecipeRegistry,
        targets: ExecutionTargetRegistry,
        store: TaskStore,
        coordinator: TaskCoordinator,
        destinations: DestinationRegistry,
        cmux: CmuxControl,
        worker_state: TerminalWorkerState,
        worker_generation: str,
        python_executable: Path = Path(sys.executable),
        broker: TerminalTaskBroker | None = None,
        probe_factory: Callable[[Path], CodexCapabilityProbe] = CodexCapabilityProbe,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        worker_start_timeout: float = 5.0,
        worker_poll_interval: float = 0.05,
        context_resolver: Callable[[EntityRef], bool] | None = None,
    ) -> None:
        if worker_start_timeout <= 0 or worker_poll_interval <= 0:
            raise ValueError("worker startup timing must be positive")
        self._recipes = recipes
        self._actions = TaskActionRegistry(recipes)
        self._targets = targets
        self._store = store
        self._coordinator = coordinator
        self._destinations = destinations
        self._cmux = cmux
        self._worker_state = worker_state
        self._worker_generation = worker_generation
        self._python_executable = Path(python_executable)
        self._broker = broker
        self._probe_factory = probe_factory
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._worker_start_timeout = worker_start_timeout
        self._worker_poll_interval = worker_poll_interval
        self._launch_lock = threading.RLock()
        self._context_resolver = context_resolver
        self._capabilities = CodexCapabilities(
            available=False,
            create=False,
            resume=False,
            fork=False,
            detail="Codex task execution has not been checked",
        )
        self._available = False
        self._unavailable_reason: str | None = "Codex task execution is unavailable"
        self.refresh_availability()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    @property
    def capabilities(self) -> CodexCapabilities:
        """Return only feature booleans and a sanitized diagnostic."""

        return self._capabilities

    def refresh_availability(self) -> bool:
        """Validate registries, private runtime, broker, and the full Codex probe."""

        try:
            recipe_document = self._recipes.load()
        except (TaskContractError, OSError, ValueError):
            return self._set_unavailable("Task recipe registry is unavailable")
        if not recipe_document.recipes:
            return self._set_unavailable("No registered task recipes are available")

        try:
            target_document = self._targets.load()
        except (ExecutionTargetError, OSError, ValueError):
            return self._set_unavailable("Execution target registry is unavailable")
        if not target_document.targets:
            return self._set_unavailable("No registered execution targets are available")

        try:
            config = self._worker_state.load_runtime(
                generation=self._worker_generation
            )
            executable = config.resolved_codex_executable()
        except (TerminalWorkerError, OSError, ValueError):
            return self._set_unavailable("Codex worker runtime is unavailable")

        expected_paths = (
            (config.recipe_registry_path, self._recipes.path),
            (config.task_store_path, self._store.path),
            (config.execution_target_registry_path, self._targets.path),
            (config.project_registry_path, self._targets.project_registry_path),
            (config.source_registry_path, self._targets.source_registry_path),
        )
        if any(
            configured.resolve(strict=False) != expected.resolve(strict=False)
            for configured, expected in expected_paths
        ):
            return self._set_unavailable("Codex worker runtime does not match Hub registries")

        try:
            broker = self._broker or TerminalTaskBroker(
                self._worker_state,
                generation=self._worker_generation,
            )
        except (TerminalWorkerError, TaskContractError, OSError, ValueError):
            return self._set_unavailable("Codex task broker is unavailable")
        if broker.config.generation != self._worker_generation:
            return self._set_unavailable("Codex task broker generation is stale")

        try:
            capabilities = self._probe_factory(executable).probe()
        except (OSError, RuntimeError, ValueError):
            return self._set_unavailable("Configured Codex capability probe failed")
        if not (
            capabilities.available
            and capabilities.create
            and capabilities.resume
            and capabilities.fork
        ):
            self._capabilities = CodexCapabilities(
                available=False,
                create=capabilities.create,
                resume=capabilities.resume,
                fork=capabilities.fork,
                detail="Configured Codex lacks required task capabilities",
            )
            return self._set_unavailable(
                "Configured Codex lacks required task capabilities",
                reset_capabilities=False,
            )

        available_targets = self._available_target_ids(target_document.targets)
        if not available_targets:
            return self._set_unavailable("No execution target currently allows Codex tasks")
        if not any(
            set(recipe.allowed_target_ids or ()) & available_targets
            for recipe in recipe_document.recipes
        ):
            return self._set_unavailable(
                "No task recipe has an available allowlisted execution target"
            )

        self._broker = broker
        self._capabilities = capabilities.model_copy(update={"detail": None})
        self._available = True
        self._unavailable_reason = None
        return True

    def public_targets(self) -> list[PublicExecutionTarget]:
        try:
            targets = self._targets.load().targets
        except (ExecutionTargetError, OSError, ValueError):
            return []
        public: list[PublicExecutionTarget] = []
        try:
            projects = {
                row.project_id: row
                for row in ProjectRegistry(self._targets.project_registry_path).load()
            }
            sources = KnowledgeSourceRegistry(self._targets.source_registry_path).load_document()
        except (OSError, RuntimeError, ValueError):
            projects = {}
            sources = None
        for target in sorted(targets, key=lambda row: row.target_id):
            folder = next((row for row in sources.folders if row.folder_id == target.registered_root_id), None) if sources else None
            title = (
                projects[target.registered_root_id].display_name
                if target.kind == "project" and target.registered_root_id in projects
                else folder.root.name if folder else target.target_id
            )
            if target.field_id and folder:
                try:
                    manifest = FieldService._load_manifest(folder.root)
                    title = next(row.title for row in manifest.fields if row.field_id == target.field_id)
                except (OSError, RuntimeError, ValueError, StopIteration):
                    pass
            available = False
            if "codex" in target.capabilities:
                try:
                    self._targets.resolve(target.target_id, capability="codex")
                except (ExecutionTargetError, OSError, ValueError):
                    pass
                else:
                    available = True
            public.append(
                PublicExecutionTarget(
                    target_id=target.target_id,
                    title=title,
                    kind=target.kind,
                    registered_root_id=target.registered_root_id,
                    field_id=target.field_id,
                    project_id=target.registered_root_id if target.kind == "project" else None,
                    source_id=target.source_id or next(
                        (row.source_id for row in sources.sources if row.folder_id == target.registered_root_id and row.enabled),
                        None,
                    ) if sources is not None and target.kind == "vault" else None,
                    capabilities=[
                        capability
                        for capability in target.capabilities
                        if capability == "codex"
                    ],
                    available=available,
                    reason=None if available else "Execution target is unavailable",
                )
            )
        return public

    def public_actions(self) -> list[PublicTaskAction]:
        try:
            mappings = self._actions.mappings()
        except (TaskContractError, OSError, ValueError):
            return []
        available_targets = {
            row.target_id for row in self.public_targets() if row.available
        }
        public: list[PublicTaskAction] = []
        for action_id, recipe in sorted(mappings.items()):
            allowed = sorted(
                set(recipe.allowed_target_ids or ()) & available_targets
            )
            available = self.available and bool(allowed)
            reason = None
            if not self.available:
                reason = self.unavailable_reason
            elif not allowed:
                reason = "No allowlisted execution target is available"
            public.append(
                PublicTaskAction(
                    action_id=action_id,
                    title=recipe.title,
                    allowed_efforts=recipe.allowed_efforts,
                    allowed_target_ids=allowed,
                    allowed_model_profile_ids=recipe.allowed_model_profile_ids or [],
                    available=available,
                    reason=reason,
                )
            )
        return public

    def public_options(self) -> dict[str, Any]:
        """Expose only explicitly approved model profiles to the task page."""

        try:
            document = self._recipes.load()
        except (TaskContractError, OSError, ValueError):
            return {"model_profiles": [], "default_profile_id": None, "available": False,
                    "reason": "Task recipe registry is unavailable"}
        return {
            "model_profiles": [row.public() for row in document.model_profiles],
            "default_profile_id": next((row.profile_id for row in document.model_profiles if row.is_default), None),
            "available": self.available,
            "reason": self.unavailable_reason,
        }

    def create(self, request: TaskActionRequest) -> TaskDispatchResult:
        recipe, task_request, raw_workspace, fingerprint, cwd = self._prepare(request)
        return self._dispatch(
            request=request,
            task_request=task_request,
            raw_workspace=raw_workspace,
            fingerprint=fingerprint,
            cwd=cwd,
            operation=lambda: self._coordinator.create(
                task_request,
                title=recipe.title,
            ),
        )

    def resume(
        self, task_id: str, request: TaskActionRequest
    ) -> TaskDispatchResult:
        task = self._store.get_task(task_id)
        _recipe, task_request, raw_workspace, fingerprint, cwd = self._prepare(request, pinned_task=task)
        return self._dispatch(
            request=request,
            task_request=task_request,
            raw_workspace=raw_workspace,
            fingerprint=fingerprint,
            cwd=cwd,
            operation=lambda: self._coordinator.resume(task_id, task_request),
        )

    def fork(self, task_id: str, request: TaskActionRequest) -> TaskDispatchResult:
        recipe, task_request, raw_workspace, fingerprint, cwd = self._prepare(request)
        return self._dispatch(
            request=request,
            task_request=task_request,
            raw_workspace=raw_workspace,
            fingerprint=fingerprint,
            cwd=cwd,
            operation=lambda: self._coordinator.fork(
                task_id,
                task_request,
                title=recipe.title,
            ),
        )

    def task_status(self, task_id: str) -> PublicTask:
        try:
            task = self._store.get_task(task_id)
            document = self._store.snapshot()
            runs = [run for run in document.runs if run.task_id == task.task_id]
        except (TaskContractError, OSError, ValueError):
            raise KeyError("unknown logical task") from None
        return self._public_task(task, runs)

    def run_status(self, run_id: str) -> PublicTaskRun:
        try:
            run = self._store.get_run(run_id)
        except (TaskContractError, OSError, ValueError):
            raise KeyError("unknown task run") from None
        return self._public_run(run)

    def cancel(self, run_id: str) -> PublicTaskRun:
        try:
            run = self._store.request_cancel(run_id, now=self._clock())
        except (TaskContractError, OSError, ValueError):
            raise KeyError("unknown task run") from None
        return self._public_run(run)

    def _prepare(
        self, request: TaskActionRequest, *, pinned_task: LogicalTask | None = None,
    ) -> tuple[TaskRecipe, TaskRequest, str, str, Path]:
        if not self.available:
            raise RuntimeError(
                self.unavailable_reason or "Codex task execution is unavailable"
            )
        recipe = self._actions.resolve(request.action_id)
        if request.target_id not in (recipe.allowed_target_ids or ()):
            raise ValueError(
                "Selected execution target is not allowed for this task action"
            )
        if TaskEffort(request.effort) not in recipe.allowed_efforts:
            raise ValueError("Selected effort is not allowed for this task action")
        if request.model_profile_id is not None:
            if request.model_profile_id not in (recipe.allowed_model_profile_ids or ()):
                raise ValueError("Selected model profile is not allowed for this task action")
            profile = self._recipes.model_profile_map().get(request.model_profile_id)
            pinned = pinned_task is not None and pinned_task.model_profile_id == request.model_profile_id
            if profile is None or (
                not pinned and request.reasoning_effort is not None
                and request.reasoning_effort not in profile.supported_reasoning_efforts
            ):
                raise ValueError("Selected reasoning effort is not supported by this model")
        elif request.reasoning_effort is not None:
            raise ValueError("Select an approved model profile before choosing reasoning effort")
        for reference in request.entity_refs:
            if (
                reference.provider_id not in recipe.allowed_provider_ids
                and reference.provider_id.split(":", 1)[0] not in recipe.allowed_provider_ids
            ):
                raise ValueError("Selected context provider is not allowed for this task action")
            if self._context_resolver is None or not self._context_resolver(reference):
                raise ValueError("Selected task context is unavailable")
        try:
            resolved_target = self._targets.resolve(
                request.target_id,
                capability="codex",
            )
        except (ExecutionTargetError, OSError, ValueError):
            raise ValueError("Selected execution target is unavailable") from None
        if request.destination_id is None:
            raise ValueError("A live cmux destination is required for Codex tasks")
        try:
            opaque_workspace, fingerprint = (
                self._destinations.resolve_with_instance(request.destination_id)
            )
            raw_workspace = self._destinations.workspaces.resolve(opaque_workspace)
            if self._destinations.workspaces.instance_fingerprint() != fingerprint:
                raise CmuxControlError("cmux instance changed")
        except (CmuxControlError, OSError, ValueError):
            raise ValueError("Selected cmux destination is unavailable") from None
        task_request = TaskRequest(
            recipe_id=recipe.recipe_id,
            target_id=request.target_id,
            effort=request.effort,
            model_profile_id=request.model_profile_id,
            reasoning_effort=request.reasoning_effort,
            entity_refs=request.entity_refs,
            brief=request.brief,
            idempotency_key=request.idempotency_key,
        )
        return recipe, task_request, raw_workspace, fingerprint, resolved_target.cwd

    def _dispatch(
        self,
        *,
        request: TaskActionRequest,
        task_request: TaskRequest,
        raw_workspace: str,
        fingerprint: str,
        cwd: Path,
        operation: Callable[[], TaskSubmission],
    ) -> TaskDispatchResult:
        try:
            submission = operation()
        except (TaskContractError, ValueError) as exc:
            raise ValueError(self._public_task_conflict(exc)) from None
        except (OSError, RuntimeError):
            raise RuntimeError("Task state is unavailable") from None

        if submission.reused:
            return self._dispatch_result(submission)
        invocation = submission.invocation
        if invocation is None or invocation.cwd.resolve(strict=False) != cwd.resolve(
            strict=False
        ):
            self._fail_reserved_run(
                submission.run.run_id,
                "Task target validation failed before terminal routing",
            )
            raise RuntimeError("Task target validation failed")

        slot_id = self._slot_id(
            raw_workspace=raw_workspace,
            fingerprint=fingerprint,
            target_id=task_request.target_id or "missing-target",
        )
        try:
            self._ensure_worker(
                slot_id=slot_id,
                raw_workspace=raw_workspace,
                fingerprint=fingerprint,
                cwd=cwd,
            )
            assert self._broker is not None
            self._broker.enqueue(
                slot_id=slot_id,
                submission=submission,
                request=task_request,
            )
        except (CmuxControlError, TerminalWorkerError, TaskContractError, OSError, ValueError):
            self._fail_reserved_run(
                submission.run.run_id,
                "Codex terminal routing failed before execution",
            )
            raise RuntimeError("Could not route the task to a Codex terminal") from None
        return self._dispatch_result(submission)

    def _ensure_worker(
        self, *, slot_id: str, raw_workspace: str, fingerprint: str, cwd: Path
    ) -> None:
        with self._launch_lock:
            if self._destinations.workspaces.instance_fingerprint() != fingerprint:
                raise CmuxControlError("cmux instance changed")
            if self._worker_state.worker_alive(
                slot_id=slot_id,
                generation=self._worker_generation,
            ):
                return
            self._worker_state.clear_stop(
                slot_id=slot_id,
                generation=self._worker_generation,
            )
            command = build_terminal_worker_command(
                python_executable=self._python_executable,
                state_root=self._worker_state.root,
                slot_id=slot_id,
                generation=self._worker_generation,
            )
            self._cmux.new_terminal_worker(
                workspace_id=raw_workspace,
                working_directory=cwd,
                command=command,
            )
            deadline = self._monotonic() + self._worker_start_timeout
            while self._monotonic() < deadline:
                if self._worker_state.worker_alive(
                    slot_id=slot_id,
                    generation=self._worker_generation,
                ):
                    return
                self._sleep(self._worker_poll_interval)
            raise TerminalWorkerError("terminal worker did not acquire its private lease")

    def _available_target_ids(self, targets: list[Any]) -> set[str]:
        result: set[str] = set()
        for target in targets:
            if "codex" not in target.capabilities:
                continue
            try:
                self._targets.resolve(target.target_id, capability="codex")
            except (ExecutionTargetError, OSError, ValueError):
                continue
            result.add(target.target_id)
        return result

    def _public_task(self, task: LogicalTask, runs: list[TaskRun]) -> PublicTask:
        action_id = TaskActionRegistry.action_id(task.recipe_id)
        return PublicTask(
            task_id=task.task_id,
            action_id=action_id,
            title=task.title,
            effort=task.effort,
            model_profile_id=task.model_profile_id,
            model_title=task.resolved_model,
            reasoning_effort=task.reasoning_effort,
            archived=task.archived,
            thread_available=task.codex_thread_id is not None,
            runs=[
                self._public_run(run)
                for run in sorted(runs, key=lambda row: row.created_at)
            ],
        )

    @staticmethod
    def _public_run(run: TaskRun) -> PublicTaskRun:
        return PublicTaskRun(
            task_id=run.task_id,
            run_id=run.run_id,
            state=run.state.value,
            mode=run.mode,
            cancel_requested=run.cancel_requested_at is not None,
        )

    @classmethod
    def _dispatch_result(cls, submission: TaskSubmission) -> TaskDispatchResult:
        run = cls._public_run(submission.run)
        return TaskDispatchResult(
            **run.model_dump(),
            reused=submission.reused,
        )

    def _fail_reserved_run(self, run_id: str, reason: str) -> None:
        try:
            self._store.fail_queued(run_id, now=self._clock(), reason=reason)
        except (TaskContractError, OSError, ValueError):
            pass

    def _set_unavailable(
        self,
        reason: str,
        *,
        reset_capabilities: bool = True,
    ) -> bool:
        self._available = False
        self._unavailable_reason = reason
        if reset_capabilities:
            self._capabilities = CodexCapabilities(
                available=False,
                create=False,
                resume=False,
                fork=False,
                detail=reason,
            )
        return False

    @staticmethod
    def _public_task_conflict(error: Exception) -> str:
        detail = str(error).lower()
        if "idempotency" in detail:
            return "Idempotency key conflicts with an existing task request"
        if "archived" in detail:
            return "Archived tasks cannot be resumed"
        if "saved codex thread" in detail or "source task has no" in detail:
            return "The task has no resumable Codex thread"
        if "configuration" in detail:
            return "Task continuation cannot change its registered configuration"
        if "active run" in detail:
            return "The task already has an active continuation"
        return "Task request conflicts with the registered task policy"

    def _slot_id(
        self, *, raw_workspace: str, fingerprint: str, target_id: str
    ) -> str:
        digest = hashlib.sha256(
            (
                f"{self._worker_generation}\0{fingerprint}\0{raw_workspace}\0{target_id}"
            ).encode()
        ).hexdigest()
        return f"slot-{digest[:32]}"


__all__ = [
    "PublicExecutionTarget",
    "PublicTask",
    "PublicTaskAction",
    "PublicTaskRun",
    "TaskActionRegistry",
    "TaskControlService",
    "TaskDispatchResult",
]
