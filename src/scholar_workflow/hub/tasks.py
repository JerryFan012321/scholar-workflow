"""Server-owned Hub task contracts and an internal, disabled-by-default worker.

Nothing in this module is an HTTP entry point.  The server may expose task execution only
after a separately reviewed worker integration enables it.  Until then these types provide
the durable WI-039 contract, including safe command construction, idempotency, explicit
thread identity, cancellation, timeouts, and stale-run recovery.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Literal, Self

from pydantic import Field, field_validator, model_validator

from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.models import HubModel

MAX_BRIEF_BYTES = 8 * 1024
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")
_THREAD_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class TaskContractError(ValueError):
    """A task request conflicts with a registered or persisted contract."""


class ProcessRecoveryError(TaskContractError):
    """A worker could not prove that a spawned process group has stopped."""


def _now() -> datetime:
    return datetime.now(UTC)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_text(value: str) -> str:
    return _digest_bytes(value.encode("utf-8"))


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest_bytes(encoded)


def _validate_digest(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError("value must be a sha256 digest")
    return value


class TaskEffort(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class TaskRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    RECOVERY_REQUIRED = "recovery_required"


class TaskRecipe(HubModel):
    recipe_id: str
    title: str = Field(min_length=1, max_length=200)
    project_required: bool = True
    allowed_library_ids: list[str] = Field(default_factory=list)
    allowed_project_ids: list[str] | None = None
    allowed_tool_ids: list[str] = Field(default_factory=list)
    context_policy_id: str = "selected-only"
    safety_policy_id: str = "default"
    allowed_efforts: list[TaskEffort] = Field(
        default_factory=lambda: [TaskEffort.STANDARD]
    )

    @field_validator("recipe_id")
    @classmethod
    def _recipe_id(cls, value: str) -> str:
        if not _TASK_ID.fullmatch(value):
            raise ValueError("recipe_id must be a portable registered identifier")
        return value

    @field_validator("allowed_library_ids")
    @classmethod
    def _libraries(cls, values: list[str]) -> list[str]:
        allowed = {"papers", "projects", "tools"}
        if len(values) != len(set(values)) or any(value not in allowed for value in values):
            raise ValueError("invalid or duplicate allowed library")
        return values

    @field_validator(
        "allowed_project_ids",
        "allowed_tool_ids",
        "context_policy_id",
        "safety_policy_id",
    )
    @classmethod
    def _portable_policy_ids(cls, value: list[str] | str | None) -> list[str] | str | None:
        values = value if isinstance(value, list) else [value] if value is not None else []
        if len(values) != len(set(values)) or any(
            not isinstance(item, str) or not _TASK_ID.fullmatch(item) for item in values
        ):
            raise ValueError("recipe scope and policy identifiers must be portable and unique")
        return value

    @field_validator("allowed_efforts")
    @classmethod
    def _efforts(cls, values: list[TaskEffort]) -> list[TaskEffort]:
        if not values or len(values) != len(set(values)):
            raise ValueError("allowed_efforts must contain unique values")
        return values


class TaskSafetyPolicy(HubModel):
    """Server-owned Codex configuration; clients can select it only through a recipe."""

    policy_id: str
    policy_version: int = Field(ge=1)
    model: str = Field(min_length=1, max_length=100)
    sandbox: Literal["read-only", "workspace-write"]
    approval_policy: Literal["never"] = "never"

    @field_validator("policy_id", "model")
    @classmethod
    def _clean_values(cls, value: str) -> str:
        if not _TASK_ID.fullmatch(value):
            raise ValueError("task safety policy values must be portable identifiers")
        return value


class TaskRequest(HubModel):
    recipe_id: str
    project_id: str | None = None
    entity_refs: list[dict[str, str]] = Field(default_factory=list, max_length=32)
    effort: TaskEffort
    brief: str = Field(min_length=1)
    idempotency_key: str

    @field_validator("recipe_id", "project_id", "idempotency_key")
    @classmethod
    def _ids(cls, value: str | None) -> str | None:
        if value is not None and not _TASK_ID.fullmatch(value):
            raise ValueError("task request identifiers must be portable")
        return value

    @field_validator("brief")
    @classmethod
    def _bounded_brief(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("brief must not have leading or trailing whitespace")
        if len(value.encode("utf-8")) > MAX_BRIEF_BYTES:
            raise ValueError(f"brief exceeds {MAX_BRIEF_BYTES} bytes")
        if "\x00" in value:
            raise ValueError("brief contains a null byte")
        return value

    @field_validator("entity_refs")
    @classmethod
    def _entity_refs(cls, values: list[dict[str, str]]) -> list[dict[str, str]]:
        expected = {"library_id", "item_type", "item_id"}
        seen: set[tuple[str, str, str]] = set()
        for value in values:
            if set(value) != expected:
                raise ValueError("entity refs must contain typed reference fields only")
            if value["library_id"] not in {"papers", "projects", "tools"}:
                raise ValueError("unknown entity reference library")
            identity = (value["library_id"], value["item_type"], value["item_id"])
            if identity in seen:
                raise ValueError("duplicate entity reference")
            seen.add(identity)
            if any(
                not isinstance(part, str)
                or not part
                or part != part.strip()
                or any(ord(character) < 32 for character in part)
                for part in identity
            ):
                raise ValueError("entity reference values must be clean text")
        return values


class LogicalTask(HubModel):
    task_id: str
    recipe_id: str
    title: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    effort: TaskEffort
    configuration_fingerprint: str
    approved_summary: str | None = Field(default=None, max_length=2000)
    brief_hash: str
    codex_thread_id: str | None = None
    archived: bool = False
    created_at: datetime
    updated_at: datetime

    @field_validator("task_id", "recipe_id")
    @classmethod
    def _portable_ids(cls, value: str) -> str:
        if not _TASK_ID.fullmatch(value):
            raise ValueError("task identifiers must be portable")
        return value

    @field_validator("configuration_fingerprint", "brief_hash")
    @classmethod
    def _digests(cls, value: str) -> str:
        return _validate_digest(value)

    @field_validator("codex_thread_id")
    @classmethod
    def _thread(cls, value: str | None) -> str | None:
        if value is not None and (value == "--last" or not _THREAD_ID.fullmatch(value)):
            raise ValueError("task thread identity must be an explicit Codex thread ID")
        return value


class TaskRun(HubModel):
    run_id: str
    task_id: str
    state: TaskRunState
    mode: str
    idempotency_key: str
    request_fingerprint: str
    configuration_fingerprint: str
    source_thread_id: str | None = None
    codex_thread_id: str | None = None
    result_summary: str | None = Field(default=None, max_length=2000)
    result_summary_hash: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    timeout_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        if value not in {"create", "resume", "fork"}:
            raise ValueError("task run mode must be create, resume, or fork")
        return value

    @model_validator(mode="after")
    def _thread_required_for_continuation(self) -> Self:
        if self.mode in {"resume", "fork"} and not self.source_thread_id:
            raise ValueError("resume and fork require an explicit codex_thread_id")
        if self.mode == "create" and self.source_thread_id is not None:
            raise ValueError("create runs cannot have a source thread")
        if (self.result_summary is None) != (self.result_summary_hash is None):
            raise ValueError("result summary and hash must be present together")
        if (
            self.result_summary is not None
            and self.result_summary_hash != _digest_text(self.result_summary)
        ):
            raise ValueError("result summary hash does not match its content")
        if self.state == TaskRunState.QUEUED:
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.heartbeat_at,
                    self.timeout_at,
                    self.completed_at,
                    self.codex_thread_id,
                )
            ):
                raise ValueError("queued runs cannot contain execution or completion fields")
        elif self.state in {TaskRunState.RUNNING, TaskRunState.RECOVERY_REQUIRED}:
            if any(
                value is None
                for value in (self.started_at, self.heartbeat_at, self.timeout_at)
            ):
                raise ValueError("active runs require start, heartbeat, and timeout timestamps")
            if self.completed_at is not None or self.codex_thread_id is not None:
                raise ValueError("active runs cannot contain completion fields")
        else:
            if self.completed_at is None:
                raise ValueError("terminal runs require a completion timestamp")
            if self.state == TaskRunState.SUCCEEDED and self.codex_thread_id is None:
                raise ValueError("successful runs require an explicit Codex thread ID")
            if self.state != TaskRunState.SUCCEEDED and self.codex_thread_id is not None:
                raise ValueError("unsuccessful runs cannot claim a Codex thread ID")
        return self

    @field_validator("run_id", "task_id", "idempotency_key")
    @classmethod
    def _portable_ids(cls, value: str) -> str:
        if not _TASK_ID.fullmatch(value):
            raise ValueError("run identifiers must be portable")
        return value

    @field_validator(
        "request_fingerprint",
        "configuration_fingerprint",
        "result_summary_hash",
    )
    @classmethod
    def _optional_digests(cls, value: str | None) -> str | None:
        return _validate_digest(value) if value is not None else None

    @field_validator("source_thread_id", "codex_thread_id")
    @classmethod
    def _threads(cls, value: str | None) -> str | None:
        if value is not None and (value == "--last" or not _THREAD_ID.fullmatch(value)):
            raise ValueError("run thread identity must be an explicit Codex thread ID")
        return value


class CodexInvocation(HubModel):
    argv: tuple[str, ...]
    stdin: str
    cwd: Path
    recipe_id: str
    effort: TaskEffort


class CodexCommandBuilder:
    """Map an allowlisted recipe/request to argv; never accept browser argv."""

    _EFFORT_MAP: ClassVar[dict[TaskEffort, str]] = {
        TaskEffort.FAST: "minimal",
        TaskEffort.STANDARD: "medium",
        TaskEffort.DEEP: "high",
    }

    def __init__(
        self,
        *,
        codex_executable: Path,
        project_registry: ProjectRegistry,
        safety_policies: dict[str, TaskSafetyPolicy],
        runtime_cwd: Path | None = None,
    ) -> None:
        executable = Path(codex_executable)
        if not executable.is_absolute():
            raise ValueError("codex_executable must be an explicit absolute path")
        self._executable = executable
        self._projects = project_registry
        if not safety_policies or any(
            identifier != policy.policy_id
            for identifier, policy in safety_policies.items()
        ):
            raise ValueError("safety policies must be an explicit keyed registry")
        self._safety_policies = dict(safety_policies)
        self._runtime_cwd = Path(runtime_cwd).resolve() if runtime_cwd is not None else None

    def build_new(self, recipe: TaskRecipe, request: TaskRequest) -> CodexInvocation:
        self._validate_recipe_request(recipe, request)
        cwd = self._trusted_cwd(recipe, request)
        effort = self._EFFORT_MAP[request.effort]
        policy = self.policy_for(recipe)
        return CodexInvocation(
            argv=self._base_argv(cwd=cwd, policy=policy, effort=effort) + (
                "-",
            ),
            stdin=request.brief,
            cwd=cwd,
            recipe_id=recipe.recipe_id,
            effort=request.effort,
        )

    def build_continuation(
        self,
        recipe: TaskRecipe,
        request: TaskRequest,
        *,
        mode: str,
        codex_thread_id: str,
    ) -> CodexInvocation:
        self._validate_recipe_request(recipe, request)
        if mode not in {"resume", "fork"}:
            raise ValueError("continuation mode must be resume or fork")
        if codex_thread_id == "--last" or not _THREAD_ID.fullmatch(codex_thread_id):
            raise ValueError("an explicit saved Codex thread ID is required")
        cwd = self._trusted_cwd(recipe, request)
        effort = self._EFFORT_MAP[request.effort]
        policy = self.policy_for(recipe)
        return CodexInvocation(
            argv=self._base_argv(cwd=cwd, policy=policy, effort=effort) + (
                mode,
                codex_thread_id,
                "-",
            ),
            stdin=request.brief,
            cwd=cwd,
            recipe_id=recipe.recipe_id,
            effort=request.effort,
        )

    def policy_for(self, recipe: TaskRecipe) -> TaskSafetyPolicy:
        try:
            return self._safety_policies[recipe.safety_policy_id]
        except KeyError:
            raise ValueError(
                f"recipe safety policy is not registered: {recipe.safety_policy_id}"
            ) from None

    def _base_argv(
        self,
        *,
        cwd: Path,
        policy: TaskSafetyPolicy,
        effort: str,
    ) -> tuple[str, ...]:
        return (
            str(self._executable),
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--strict-config",
            "--json",
            "-C",
            str(cwd),
            "-m",
            policy.model,
            "-s",
            policy.sandbox,
            "-c",
            f'approval_policy="{policy.approval_policy}"',
            "-c",
            f'model_reasoning_effort="{effort}"',
        )

    def _validate_recipe_request(self, recipe: TaskRecipe, request: TaskRequest) -> None:
        if request.recipe_id != recipe.recipe_id:
            raise ValueError("request does not match the registered recipe")
        if request.effort not in recipe.allowed_efforts:
            raise ValueError("effort is not allowlisted by the recipe")
        if recipe.project_required and request.project_id is None:
            raise ValueError("recipe requires a registered project")
        if not recipe.project_required and request.project_id is not None:
            raise ValueError("recipe does not accept a project")
        if (
            recipe.allowed_project_ids is not None
            and request.project_id not in recipe.allowed_project_ids
        ):
            raise ValueError("project is not allowlisted by the recipe")
        if any(
            reference["library_id"] not in recipe.allowed_library_ids
            for reference in request.entity_refs
        ):
            raise ValueError("entity reference library is not allowlisted by the recipe")
        if any(
            reference["library_id"] == "tools"
            and reference["item_id"] not in recipe.allowed_tool_ids
            for reference in request.entity_refs
        ):
            raise ValueError("tool reference is not allowlisted by the recipe")

    def _trusted_cwd(self, recipe: TaskRecipe, request: TaskRequest) -> Path:
        if recipe.project_required:
            assert request.project_id is not None
            return self._projects.resolve(request.project_id, capability="codex").root
        if self._runtime_cwd is None or not self._runtime_cwd.is_dir():
            raise ValueError("runtime recipe has no trusted server cwd")
        return self._runtime_cwd


class CodexCapabilities(HubModel):
    available: bool
    create: bool
    resume: bool
    fork: bool
    detail: str | None = None


class CodexCapabilityProbe:
    """Probe configured Codex features without executing a task or relying on a version."""

    _EXEC_FLAGS: ClassVar[tuple[str, ...]] = (
        "--config",
        "--strict-config",
        "--model",
        "--sandbox",
        "--cd",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
    )

    def __init__(
        self,
        executable: Path,
        *,
        timeout: float = 5.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        path = Path(executable)
        if not path.is_absolute():
            raise ValueError("Codex capability probe needs an explicit absolute executable")
        self._executable = str(path)
        self._timeout = timeout
        self._runner = runner

    def probe(self) -> CodexCapabilities:
        results: list[bool] = []
        commands = (
            [self._executable, "exec", "--help"],
            [self._executable, "exec", "resume", "--help"],
            [self._executable, "exec", "fork", "--help"],
        )
        for index, argv in enumerate(commands):
            try:
                result = self._runner(
                    argv,
                    shell=False,
                    timeout=self._timeout,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                results.append(False)
            else:
                supported = result.returncode == 0
                if index == 0:
                    supported = supported and all(
                        flag in result.stdout for flag in self._EXEC_FLAGS
                    )
                else:
                    mode = "resume" if index == 1 else "fork"
                    supported = (
                        supported
                        and "--json" in result.stdout
                        and f"codex exec {mode}" in result.stdout
                    )
                results.append(supported)
        available = all(results)
        return CodexCapabilities(
            available=available,
            create=results[0],
            resume=results[1],
            fork=results[2],
            detail=None if available else "Configured Codex lacks required exec capabilities",
        )


class TaskRecipeRegistryDocument(HubModel):
    """Checked host configuration; recipes are never inferred from PATH or executables."""

    schema_version: int = 1
    recipes: list[TaskRecipe] = Field(default_factory=list)
    safety_policies: list[TaskSafetyPolicy] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported task recipe registry schema")
        return value

    @model_validator(mode="after")
    def _unique_recipes(self) -> Self:
        identifiers = [recipe.recipe_id for recipe in self.recipes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate task recipe ID")
        policy_ids = [policy.policy_id for policy in self.safety_policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("duplicate task safety policy ID")
        unknown = {
            recipe.safety_policy_id for recipe in self.recipes
        } - set(policy_ids)
        if unknown:
            raise ValueError("task recipe references an unknown safety policy")
        return self


class TaskRecipeRegistry:
    """Load an explicit recipe registry from one configured JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> TaskRecipeRegistryDocument:
        if self.path.is_symlink() or not self.path.is_file():
            raise TaskContractError("task recipe registry must be a regular non-symlink file")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return TaskRecipeRegistryDocument.model_validate(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TaskContractError(f"invalid task recipe registry: {exc}") from None

    def get(self, recipe_id: str) -> TaskRecipe:
        for recipe in self.load().recipes:
            if recipe.recipe_id == recipe_id:
                return recipe
        raise TaskContractError(f"unknown task recipe: {recipe_id}")

    def safety_policy_map(self) -> dict[str, TaskSafetyPolicy]:
        return {policy.policy_id: policy for policy in self.load().safety_policies}


class IdempotencyRecord(HubModel):
    idempotency_key: str
    request_fingerprint: str
    run_id: str

    @field_validator("idempotency_key", "run_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        if not _TASK_ID.fullmatch(value):
            raise ValueError("idempotency records require portable identifiers")
        return value

    @field_validator("request_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        return _validate_digest(value)


class TaskStoreDocument(HubModel):
    """Durable task metadata.  Briefs and transcripts are deliberately absent."""

    schema_version: int = 1
    tasks: list[LogicalTask] = Field(default_factory=list)
    runs: list[TaskRun] = Field(default_factory=list)
    idempotency: list[IdempotencyRecord] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported task store schema")
        return value

    @model_validator(mode="after")
    def _consistent_references(self) -> Self:
        task_ids = [task.task_id for task in self.tasks]
        run_ids = [run.run_id for run in self.runs]
        keys = [record.idempotency_key for record in self.idempotency]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("duplicate logical task ID")
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("duplicate task run ID")
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate idempotency key")
        task_set = set(task_ids)
        run_set = set(run_ids)
        if any(run.task_id not in task_set for run in self.runs):
            raise ValueError("task run references an unknown logical task")
        if any(record.run_id not in run_set for record in self.idempotency):
            raise ValueError("idempotency record references an unknown task run")
        idempotency_by_run = {record.run_id: record for record in self.idempotency}
        if set(idempotency_by_run) != run_set:
            raise ValueError("every task run requires exactly one idempotency record")
        for run in self.runs:
            if idempotency_by_run[run.run_id].request_fingerprint != run.request_fingerprint:
                raise ValueError("idempotency fingerprint does not match its task run")

        successful_threads: dict[str, str] = {}
        threads_by_task: dict[str, set[str]] = {}
        for run in self.runs:
            if run.state != TaskRunState.SUCCEEDED:
                continue
            assert run.codex_thread_id is not None
            if run.mode == "resume" and run.codex_thread_id != run.source_thread_id:
                raise ValueError("persisted resume run changed Codex thread identity")
            if run.mode == "fork" and run.codex_thread_id == run.source_thread_id:
                raise ValueError("persisted fork run reused its source thread identity")
            owner = successful_threads.setdefault(run.codex_thread_id, run.task_id)
            if owner != run.task_id:
                raise ValueError("Codex thread identity has multiple logical task owners")
            threads_by_task.setdefault(run.task_id, set()).add(run.codex_thread_id)
        for task in self.tasks:
            produced = threads_by_task.get(task.task_id, set())
            if len(produced) > 1:
                raise ValueError("logical task has multiple Codex thread identities")
            if task.codex_thread_id is None and produced:
                raise ValueError("logical task omits its successful Codex thread identity")
            if task.codex_thread_id is not None and produced != {task.codex_thread_id}:
                raise ValueError("logical task thread identity lacks a matching successful run")

        active_threads: set[str] = set()
        for run in self.runs:
            if run.state not in _ACTIVE_STATES or run.source_thread_id is None:
                continue
            if run.source_thread_id in active_threads:
                raise ValueError("Codex thread has multiple active task runs")
            active_threads.add(run.source_thread_id)
        return self


class TaskReservation(HubModel):
    task: LogicalTask
    run: TaskRun
    reused: bool


_ACTIVE_STATES = {
    TaskRunState.QUEUED,
    TaskRunState.RUNNING,
    TaskRunState.RECOVERY_REQUIRED,
}
_TERMINAL_STATES = {
    TaskRunState.SUCCEEDED,
    TaskRunState.FAILED,
    TaskRunState.INTERRUPTED,
    TaskRunState.CANCELLED,
    TaskRunState.TIMED_OUT,
}


class TaskStore:
    """Atomic local JSON store for task metadata and idempotency reservations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self._lock = threading.RLock()

    @contextmanager
    def _locked_transaction(self) -> Iterator[None]:
        """Serialize every read and read-modify-write across worker processes."""

        with self._lock:
            parent = self.path.parent
            parent.mkdir(parents=True, exist_ok=True)
            if parent.is_symlink() or not parent.is_dir():
                raise TaskContractError("task store parent cannot be a symlink")
            if self.lock_path.is_symlink():
                raise TaskContractError("task store lockfile cannot be a symlink")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(self.lock_path, flags, 0o600)
            except OSError as exc:
                raise TaskContractError(f"cannot open task store lockfile: {exc}") from None
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise TaskContractError("task store lockfile must be a regular file")
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            except OSError as exc:
                raise TaskContractError(f"task store lock failed: {exc}") from None
            finally:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(descriptor)

    def snapshot(self) -> TaskStoreDocument:
        with self._locked_transaction():
            return self._read()

    def get_task(self, task_id: str) -> LogicalTask:
        with self._locked_transaction():
            document = self._read()
            return self._find_task(document, task_id)

    def get_run(self, run_id: str) -> TaskRun:
        with self._locked_transaction():
            document = self._read()
            return self._find_run(document, run_id)

    def reserve(self, task: LogicalTask, run: TaskRun) -> TaskReservation:
        """Reserve an idempotency key and thread before a worker can launch."""

        with self._locked_transaction():
            document = self._read()
            existing = next(
                (
                    record
                    for record in document.idempotency
                    if record.idempotency_key == run.idempotency_key
                ),
                None,
            )
            if existing is not None:
                if existing.request_fingerprint != run.request_fingerprint:
                    raise TaskContractError(
                        "idempotency key was already used for a different request"
                    )
                existing_run = self._find_run(document, existing.run_id)
                return TaskReservation(
                    task=self._find_task(document, existing_run.task_id),
                    run=existing_run,
                    reused=True,
                )

            if any(item.task_id == task.task_id for item in document.tasks):
                raise TaskContractError(f"logical task already exists: {task.task_id}")
            if any(item.run_id == run.run_id for item in document.runs):
                raise TaskContractError(f"task run already exists: {run.run_id}")
            locked_thread = run.source_thread_id
            if locked_thread is not None:
                for existing_run in document.runs:
                    if (
                        existing_run.state in _ACTIVE_STATES
                        and existing_run.source_thread_id == locked_thread
                    ):
                        raise TaskContractError(
                            f"Codex thread already has an active run: {locked_thread}"
                        )

            document.tasks.append(task)
            document.runs.append(run)
            document.idempotency.append(
                IdempotencyRecord(
                    idempotency_key=run.idempotency_key,
                    request_fingerprint=run.request_fingerprint,
                    run_id=run.run_id,
                )
            )
            self._write(document)
            return TaskReservation(task=task, run=run, reused=False)

    def reserve_run(self, run: TaskRun) -> TaskReservation:
        """Reserve a continuation run for an existing logical task."""

        with self._locked_transaction():
            document = self._read()
            task = self._find_task(document, run.task_id)
            existing = next(
                (
                    record
                    for record in document.idempotency
                    if record.idempotency_key == run.idempotency_key
                ),
                None,
            )
            if existing is not None:
                if existing.request_fingerprint != run.request_fingerprint:
                    raise TaskContractError(
                        "idempotency key was already used for a different request"
                    )
                existing_run = self._find_run(document, existing.run_id)
                return TaskReservation(
                    task=self._find_task(document, existing_run.task_id),
                    run=existing_run,
                    reused=True,
                )
            if run.configuration_fingerprint != task.configuration_fingerprint:
                raise TaskContractError("resume cannot silently change task configuration")
            assert run.source_thread_id is not None
            for existing_run in document.runs:
                if (
                    existing_run.state in _ACTIVE_STATES
                    and existing_run.source_thread_id == run.source_thread_id
                ):
                    raise TaskContractError(
                        f"Codex thread already has an active run: {run.source_thread_id}"
                    )
            document.runs.append(run)
            document.idempotency.append(
                IdempotencyRecord(
                    idempotency_key=run.idempotency_key,
                    request_fingerprint=run.request_fingerprint,
                    run_id=run.run_id,
                )
            )
            self._write(document)
            return TaskReservation(task=task, run=run, reused=False)

    def start(self, run_id: str, *, now: datetime, timeout_seconds: float) -> TaskRun:
        if timeout_seconds <= 0:
            raise TaskContractError("task timeout must be positive")
        with self._locked_transaction():
            document = self._read()
            index, run = self._run_with_index(document, run_id)
            if run.state != TaskRunState.QUEUED:
                raise TaskContractError("only a queued task run can start")
            updated = run.model_copy(
                update={
                    "state": TaskRunState.RUNNING,
                    "started_at": now,
                    "heartbeat_at": now,
                    "timeout_at": now + timedelta(seconds=timeout_seconds),
                }
            )
            document.runs[index] = updated
            self._write(document)
            return updated

    def heartbeat(self, run_id: str, *, now: datetime) -> TaskRun:
        with self._locked_transaction():
            document = self._read()
            index, run = self._run_with_index(document, run_id)
            if run.state != TaskRunState.RUNNING:
                raise TaskContractError("only a running task can heartbeat")
            updated = run.model_copy(update={"heartbeat_at": now})
            document.runs[index] = updated
            self._write(document)
            return updated

    def request_cancel(self, run_id: str, *, now: datetime) -> TaskRun:
        with self._locked_transaction():
            document = self._read()
            index, run = self._run_with_index(document, run_id)
            if run.state in _TERMINAL_STATES:
                return run
            updates: dict[str, object] = {"cancel_requested_at": now}
            if run.state == TaskRunState.QUEUED:
                updates.update(state=TaskRunState.CANCELLED, completed_at=now)
            updated = run.model_copy(update=updates)
            document.runs[index] = updated
            self._write(document)
            return updated

    def finish(
        self,
        run_id: str,
        *,
        state: TaskRunState,
        now: datetime,
        codex_thread_id: str | None = None,
        result_summary: str | None = None,
    ) -> TaskRun:
        if state not in _TERMINAL_STATES:
            raise TaskContractError("finish requires a terminal task state")
        if result_summary is not None and len(result_summary) > 2000:
            raise TaskContractError("result summary exceeds 2000 characters")
        if codex_thread_id is not None and (
            codex_thread_id == "--last" or not _THREAD_ID.fullmatch(codex_thread_id)
        ):
            raise TaskContractError("invalid explicit Codex thread ID")
        with self._locked_transaction():
            document = self._read()
            index, run = self._run_with_index(document, run_id)
            if run.state in _TERMINAL_STATES:
                return run
            if run.state not in {
                TaskRunState.RUNNING,
                TaskRunState.RECOVERY_REQUIRED,
            }:
                raise TaskContractError("only an active task can finish")
            if state == TaskRunState.SUCCEEDED and codex_thread_id is None:
                raise TaskContractError("successful task runs require a Codex thread ID")
            if run.mode == "resume" and codex_thread_id != run.source_thread_id:
                raise TaskContractError("resume returned a different Codex thread ID")
            if run.mode == "fork" and codex_thread_id == run.source_thread_id:
                raise TaskContractError("fork must return a new Codex thread ID")
            if state == TaskRunState.SUCCEEDED:
                for task in document.tasks:
                    if (
                        task.task_id != run.task_id
                        and task.codex_thread_id == codex_thread_id
                    ):
                        raise TaskContractError(
                            "Codex thread identity already belongs to another logical task"
                        )
            updated = run.model_copy(
                update={
                    "state": state,
                    "codex_thread_id": codex_thread_id,
                    "result_summary": result_summary,
                    "result_summary_hash": (
                        _digest_text(result_summary) if result_summary is not None else None
                    ),
                    "completed_at": now,
                }
            )
            document.runs[index] = updated
            if state == TaskRunState.SUCCEEDED:
                task_index, task = self._task_with_index(document, run.task_id)
                document.tasks[task_index] = task.model_copy(
                    update={"codex_thread_id": codex_thread_id, "updated_at": now}
                )
            self._write(document)
            return updated

    def mark_recovery_required(
        self,
        run_id: str,
        *,
        now: datetime,
        reason: str,
    ) -> TaskRun:
        if not reason or len(reason) > 2000:
            raise TaskContractError("recovery reason must be concise")
        with self._locked_transaction():
            document = self._read()
            index, run = self._run_with_index(document, run_id)
            if run.state in _TERMINAL_STATES:
                return run
            if run.state not in {
                TaskRunState.RUNNING,
                TaskRunState.RECOVERY_REQUIRED,
            }:
                raise TaskContractError("only an active task can require recovery")
            updated = run.model_copy(
                update={
                    "state": TaskRunState.RECOVERY_REQUIRED,
                    "heartbeat_at": now,
                    "result_summary": reason,
                    "result_summary_hash": _digest_text(reason),
                }
            )
            document.runs[index] = updated
            self._write(document)
            return updated

    def stale_runs(self, *, now: datetime, stale_after: timedelta) -> list[TaskRun]:
        """Return stale candidates without claiming their processes have stopped."""

        if stale_after <= timedelta(0):
            raise TaskContractError("stale interval must be positive")
        with self._locked_transaction():
            document = self._read()
            stale: list[TaskRun] = []
            for run in document.runs:
                if run.state not in {
                    TaskRunState.RUNNING,
                    TaskRunState.RECOVERY_REQUIRED,
                } or run.heartbeat_at is None:
                    continue
                if now - run.heartbeat_at <= stale_after:
                    continue
                stale.append(run)
            return stale

    def _read(self) -> TaskStoreDocument:
        if not self.path.exists():
            return TaskStoreDocument()
        if self.path.is_symlink() or not self.path.is_file():
            raise TaskContractError("task store must be a regular non-symlink file")
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return TaskStoreDocument.model_validate(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TaskContractError(f"invalid task store: {exc}") from None

    def _write(self, document: TaskStoreDocument) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        if parent.is_symlink() or not parent.is_dir() or self.path.is_symlink():
            raise TaskContractError("task store path cannot use a symlink")
        try:
            checked = TaskStoreDocument.model_validate(document.model_dump(mode="json"))
        except ValueError as exc:
            raise TaskContractError(f"refusing invalid task store update: {exc}") from None
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(checked.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _find_task(document: TaskStoreDocument, task_id: str) -> LogicalTask:
        for task in document.tasks:
            if task.task_id == task_id:
                return task
        raise TaskContractError(f"unknown logical task: {task_id}")

    @staticmethod
    def _find_run(document: TaskStoreDocument, run_id: str) -> TaskRun:
        for run in document.runs:
            if run.run_id == run_id:
                return run
        raise TaskContractError(f"unknown task run: {run_id}")

    @staticmethod
    def _task_with_index(
        document: TaskStoreDocument, task_id: str
    ) -> tuple[int, LogicalTask]:
        for index, task in enumerate(document.tasks):
            if task.task_id == task_id:
                return index, task
        raise TaskContractError(f"unknown logical task: {task_id}")

    @staticmethod
    def _run_with_index(document: TaskStoreDocument, run_id: str) -> tuple[int, TaskRun]:
        for index, run in enumerate(document.runs):
            if run.run_id == run_id:
                return index, run
        raise TaskContractError(f"unknown task run: {run_id}")


class TaskSubmission(HubModel):
    task: LogicalTask
    run: TaskRun
    invocation: CodexInvocation | None
    reused: bool


def task_configuration_fingerprint(
    recipe: TaskRecipe,
    request: TaskRequest,
    *,
    safety_policy: TaskSafetyPolicy,
) -> str:
    """Hash immutable continuation configuration without retaining the brief."""

    return _canonical_digest(
        {
            "recipe": recipe.model_dump(mode="json"),
            "safety_policy": safety_policy.model_dump(mode="json"),
            "project_id": request.project_id,
            "entity_refs": request.entity_refs,
            "effort": request.effort.value,
        }
    )


def task_request_fingerprint(
    request: TaskRequest,
    *,
    mode: str,
    task_id: str | None = None,
    source_task_id: str | None = None,
    title: str | None = None,
) -> str:
    """Bind an idempotency key to one exact request while storing only its digest."""

    return _canonical_digest(
        {
            "request": request.model_dump(mode="json", exclude={"idempotency_key"}),
            "mode": mode,
            "task_id": task_id,
            "source_task_id": source_task_id,
            "title": title,
        }
    )


def _new_identifier(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


class TaskCoordinator:
    """Prepare durable runs; it cannot launch a process by itself."""

    def __init__(
        self,
        *,
        recipes: TaskRecipeRegistry,
        store: TaskStore,
        commands: CodexCommandBuilder,
        clock: Callable[[], datetime] = _now,
        identifier_factory: Callable[[str], str] = _new_identifier,
    ) -> None:
        self._recipes = recipes
        self._store = store
        self._commands = commands
        self._clock = clock
        self._identifier_factory = identifier_factory

    def create(self, request: TaskRequest, *, title: str) -> TaskSubmission:
        recipe = self._recipes.get(request.recipe_id)
        configuration = task_configuration_fingerprint(
            recipe,
            request,
            safety_policy=self._commands.policy_for(recipe),
        )
        now = self._clock()
        task = LogicalTask(
            task_id=self._identifier_factory("task"),
            recipe_id=recipe.recipe_id,
            title=title,
            project_id=request.project_id,
            effort=request.effort,
            configuration_fingerprint=configuration,
            brief_hash=_digest_text(request.brief),
            created_at=now,
            updated_at=now,
        )
        run = TaskRun(
            run_id=self._identifier_factory("run"),
            task_id=task.task_id,
            state=TaskRunState.QUEUED,
            mode="create",
            idempotency_key=request.idempotency_key,
            request_fingerprint=task_request_fingerprint(
                request, mode="create", title=title
            ),
            configuration_fingerprint=configuration,
            created_at=now,
        )
        reservation = self._store.reserve(task, run)
        return TaskSubmission(
            task=reservation.task,
            run=reservation.run,
            invocation=(
                None if reservation.reused else self._commands.build_new(recipe, request)
            ),
            reused=reservation.reused,
        )

    def resume(self, task_id: str, request: TaskRequest) -> TaskSubmission:
        task = self._store.get_task(task_id)
        if task.archived:
            raise TaskContractError("archived tasks cannot be resumed")
        if task.codex_thread_id is None:
            raise TaskContractError("task has no saved Codex thread ID")
        recipe = self._recipes.get(request.recipe_id)
        configuration = task_configuration_fingerprint(
            recipe,
            request,
            safety_policy=self._commands.policy_for(recipe),
        )
        if configuration != task.configuration_fingerprint:
            raise TaskContractError("resume cannot silently change task configuration")
        now = self._clock()
        run = TaskRun(
            run_id=self._identifier_factory("run"),
            task_id=task.task_id,
            state=TaskRunState.QUEUED,
            mode="resume",
            idempotency_key=request.idempotency_key,
            request_fingerprint=task_request_fingerprint(
                request, mode="resume", task_id=task.task_id
            ),
            configuration_fingerprint=configuration,
            source_thread_id=task.codex_thread_id,
            created_at=now,
        )
        reservation = self._store.reserve_run(run)
        return TaskSubmission(
            task=reservation.task,
            run=reservation.run,
            invocation=(
                None
                if reservation.reused
                else self._commands.build_continuation(
                    recipe,
                    request,
                    mode="resume",
                    codex_thread_id=task.codex_thread_id,
                )
            ),
            reused=reservation.reused,
        )

    def fork(
        self,
        source_task_id: str,
        request: TaskRequest,
        *,
        title: str,
    ) -> TaskSubmission:
        source = self._store.get_task(source_task_id)
        if source.codex_thread_id is None:
            raise TaskContractError("source task has no saved Codex thread ID")
        recipe = self._recipes.get(request.recipe_id)
        configuration = task_configuration_fingerprint(
            recipe,
            request,
            safety_policy=self._commands.policy_for(recipe),
        )
        now = self._clock()
        task = LogicalTask(
            task_id=self._identifier_factory("task"),
            recipe_id=recipe.recipe_id,
            title=title,
            project_id=request.project_id,
            effort=request.effort,
            configuration_fingerprint=configuration,
            brief_hash=_digest_text(request.brief),
            created_at=now,
            updated_at=now,
        )
        run = TaskRun(
            run_id=self._identifier_factory("run"),
            task_id=task.task_id,
            state=TaskRunState.QUEUED,
            mode="fork",
            idempotency_key=request.idempotency_key,
            request_fingerprint=task_request_fingerprint(
                request, mode="fork", source_task_id=source.task_id, title=title
            ),
            configuration_fingerprint=configuration,
            source_thread_id=source.codex_thread_id,
            created_at=now,
        )
        reservation = self._store.reserve(task, run)
        return TaskSubmission(
            task=reservation.task,
            run=reservation.run,
            invocation=(
                None
                if reservation.reused
                else self._commands.build_continuation(
                    recipe,
                    request,
                    mode="fork",
                    codex_thread_id=source.codex_thread_id,
                )
            ),
            reused=reservation.reused,
        )


def extract_codex_thread_id(jsonl: str) -> str:
    """Extract the one explicit thread ID emitted by ``codex exec --json``."""

    identifiers: set[str] = set()
    for line_number, raw_line in enumerate(jsonl.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TaskContractError(f"invalid Codex JSONL at line {line_number}: {exc.msg}") from None
        if not isinstance(event, dict):
            raise TaskContractError(f"invalid Codex JSONL object at line {line_number}")
        thread_id = event.get("thread_id")
        if thread_id is None:
            continue
        if not isinstance(thread_id, str) or thread_id == "--last" or not _THREAD_ID.fullmatch(
            thread_id
        ):
            raise TaskContractError("Codex returned an invalid explicit thread ID")
        identifiers.add(thread_id)
    if len(identifiers) != 1:
        raise TaskContractError("Codex JSONL must contain exactly one explicit thread ID")
    return identifiers.pop()


class ProcessGroupReaper:
    """Terminate the complete process group started for one task run."""

    def __init__(
        self,
        *,
        getpgid: Callable[[int], int] = os.getpgid,
        killpg: Callable[[int, int], None] = os.killpg,
        grace_seconds: float = 2.0,
    ) -> None:
        self._getpgid = getpgid
        self._killpg = killpg
        self._grace_seconds = grace_seconds

    def reap(self, process: Any) -> None:
        if self._stopped(process):
            return
        try:
            process_group = self._getpgid(process.pid)
            self._killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            self._require_stopped(process)
            return
        except Exception as exc:
            raise ProcessRecoveryError("cannot signal Codex process group") from exc
        try:
            process.wait(timeout=self._grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                self._killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                self._require_stopped(process)
                return
            except Exception as exc:
                raise ProcessRecoveryError("cannot kill Codex process group") from exc
            try:
                process.wait(timeout=self._grace_seconds)
            except Exception as exc:
                raise ProcessRecoveryError("Codex process group did not stop") from exc
        except Exception as exc:
            raise ProcessRecoveryError("cannot wait for Codex process group") from exc
        self._require_stopped(process)

    @staticmethod
    def _stopped(process: Any) -> bool:
        try:
            return process.poll() is not None
        except Exception as exc:
            raise ProcessRecoveryError("cannot inspect Codex process state") from exc

    def _require_stopped(self, process: Any) -> None:
        if not self._stopped(process):
            raise ProcessRecoveryError("Codex process group stop is unconfirmed")


class TaskWorker:
    """Internal worker primitive.  The production Hub does not instantiate it yet."""

    def __init__(
        self,
        store: TaskStore,
        *,
        capabilities: CodexCapabilities,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        reaper: ProcessGroupReaper | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        if not (
            capabilities.available
            and capabilities.create
            and capabilities.resume
            and capabilities.fork
        ):
            raise TaskContractError("Codex task worker is disabled by capability probe")
        self._store = store
        self._popen_factory = popen_factory
        self._reaper = reaper or ProcessGroupReaper()
        self._clock = clock
        self._active: dict[str, Any] = {}
        self._active_lock = threading.RLock()
        self._reap_lock = threading.RLock()

    def execute(self, submission: TaskSubmission, *, timeout_seconds: float) -> TaskRun:
        if submission.reused or submission.invocation is None:
            raise TaskContractError("an idempotency replay cannot launch another process")
        run = self._store.start(
            submission.run.run_id,
            now=self._clock(),
            timeout_seconds=timeout_seconds,
        )
        invocation = submission.invocation
        try:
            process = self._popen_factory(
                list(invocation.argv),
                cwd=str(invocation.cwd),
                shell=False,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except Exception:  # noqa: BLE001 - process boundary must fail closed
            return self._store.finish(
                run.run_id,
                state=TaskRunState.FAILED,
                now=self._clock(),
                result_summary="Codex process could not start",
            )

        with self._active_lock:
            self._active[run.run_id] = process
        try:
            current = self._store.get_run(run.run_id)
            if current.cancel_requested_at is not None or current.state == TaskRunState.CANCELLED:
                recovery = self._reap_or_recovery(
                    run.run_id,
                    process,
                    reason="Cancellation recovery requires process-group cleanup",
                )
                if recovery is not None:
                    return recovery
                return self._finish_cancelled_if_needed(run.run_id)
            if current.state == TaskRunState.RECOVERY_REQUIRED:
                recovery = self._reap_or_recovery(
                    run.run_id,
                    process,
                    reason="Worker recovery requires process-group cleanup",
                )
                if recovery is not None:
                    return recovery
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.INTERRUPTED,
                    now=self._clock(),
                    result_summary="Worker entered recovery before execution",
                )
            try:
                stdout, _stderr = process.communicate(
                    input=invocation.stdin,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                recovery = self._reap_or_recovery(
                    run.run_id,
                    process,
                    reason="Timeout recovery requires process-group cleanup",
                )
                if recovery is not None:
                    return recovery
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.TIMED_OUT,
                    now=self._clock(),
                    result_summary="Codex run exceeded its timeout",
                )
            except Exception:  # noqa: BLE001 - process boundary must retain/reap handles
                recovery = self._reap_or_recovery(
                    run.run_id,
                    process,
                    reason="Worker I/O failed before process-group cleanup completed",
                )
                if recovery is not None:
                    return recovery
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary="Codex worker I/O failed",
                )

            current = self._store.get_run(run.run_id)
            if current.state in _TERMINAL_STATES:
                if process.poll() is None:
                    recovery = self._reap_or_recovery(
                        run.run_id,
                        process,
                        reason="Terminal task still has an unconfirmed process group",
                    )
                    if recovery is not None:
                        raise ProcessRecoveryError(
                            "terminal task has a live process group"
                        )
                return current
            if current.cancel_requested_at is not None:
                if process.poll() is None:
                    recovery = self._reap_or_recovery(
                        run.run_id,
                        process,
                        reason="Cancellation recovery requires process-group cleanup",
                    )
                    if recovery is not None:
                        return recovery
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.CANCELLED,
                    now=self._clock(),
                    result_summary="Codex run cancelled",
                )
            if process.returncode != 0:
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary=f"Codex exited with status {process.returncode}",
                )
            try:
                thread_id = extract_codex_thread_id(stdout)
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.SUCCEEDED,
                    now=self._clock(),
                    codex_thread_id=thread_id,
                )
            except TaskContractError:
                return self._store.finish(
                    run.run_id,
                    state=TaskRunState.FAILED,
                    now=self._clock(),
                    result_summary="Codex output did not contain a valid thread identity",
                )
        finally:
            self._forget_if_stopped(run.run_id, process)

    def heartbeat(self, run_id: str) -> TaskRun:
        return self._store.heartbeat(run_id, now=self._clock())

    def cancel(self, run_id: str) -> TaskRun:
        run = self._store.request_cancel(run_id, now=self._clock())
        if run.state == TaskRunState.CANCELLED:
            return run
        with self._active_lock:
            process = self._active.get(run_id)
        if process is not None:
            recovery = self._reap_or_recovery(
                run_id,
                process,
                reason="Cancellation recovery requires process-group cleanup",
            )
            if recovery is not None:
                return recovery
            return self._finish_cancelled_if_needed(run_id)
        return self._store.mark_recovery_required(
            run_id,
            now=self._clock(),
            reason="Cancellation requested but the process handle is unavailable",
        )

    def interrupt_stale(self, *, stale_after: timedelta) -> list[TaskRun]:
        candidates = self._store.stale_runs(
            now=self._clock(),
            stale_after=stale_after,
        )
        interrupted: list[TaskRun] = []
        for run in candidates:
            with self._active_lock:
                process = self._active.get(run.run_id)
            if process is None:
                self._store.mark_recovery_required(
                    run.run_id,
                    now=self._clock(),
                    reason="Stale worker has no local process handle",
                )
                continue
            recovery = self._reap_or_recovery(
                run.run_id,
                process,
                reason="Stale worker process-group cleanup is incomplete",
            )
            if recovery is not None:
                continue
            interrupted.append(
                self._store.finish(
                    run.run_id,
                    state=TaskRunState.INTERRUPTED,
                    now=self._clock(),
                    result_summary="Worker heartbeat expired",
                )
            )
        return interrupted

    def active_run_ids(self) -> tuple[str, ...]:
        """Expose opaque run IDs for diagnostics without exposing process handles."""

        with self._active_lock:
            return tuple(sorted(self._active))

    def _reap_or_recovery(
        self,
        run_id: str,
        process: Any,
        *,
        reason: str,
    ) -> TaskRun | None:
        try:
            with self._reap_lock:
                self._reaper.reap(process)
            if not self._process_stopped(process):
                raise ProcessRecoveryError("process-group reaper returned before stop")
        except Exception:  # noqa: BLE001 - injected reapers are an isolation boundary
            if self._process_stopped(process):
                self._forget_if_stopped(run_id, process)
                return None
            return self._store.mark_recovery_required(
                run_id,
                now=self._clock(),
                reason=reason,
            )
        self._forget_if_stopped(run_id, process)
        return None

    @staticmethod
    def _process_stopped(process: Any) -> bool:
        try:
            return process.poll() is not None
        except Exception:  # noqa: BLE001 - an uninspectable process is treated as live
            return False

    def _forget_if_stopped(self, run_id: str, process: Any) -> None:
        if not self._process_stopped(process):
            return
        with self._active_lock:
            if self._active.get(run_id) is process:
                self._active.pop(run_id, None)

    def _finish_cancelled_if_needed(self, run_id: str) -> TaskRun:
        run = self._store.get_run(run_id)
        if run.state in _TERMINAL_STATES:
            return run
        return self._store.finish(
            run_id,
            state=TaskRunState.CANCELLED,
            now=self._clock(),
            result_summary="Codex run cancelled",
        )


__all__ = [
    "MAX_BRIEF_BYTES",
    "CodexCapabilities",
    "CodexCapabilityProbe",
    "CodexCommandBuilder",
    "CodexInvocation",
    "IdempotencyRecord",
    "LogicalTask",
    "ProcessGroupReaper",
    "ProcessRecoveryError",
    "TaskContractError",
    "TaskCoordinator",
    "TaskEffort",
    "TaskRecipe",
    "TaskRecipeRegistry",
    "TaskRecipeRegistryDocument",
    "TaskRequest",
    "TaskReservation",
    "TaskRun",
    "TaskRunState",
    "TaskSafetyPolicy",
    "TaskStore",
    "TaskStoreDocument",
    "TaskSubmission",
    "TaskWorker",
    "extract_codex_thread_id",
    "task_configuration_fingerprint",
    "task_request_fingerprint",
]
