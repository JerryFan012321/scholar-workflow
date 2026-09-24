"""Hub v3 execution-target and durable task-runtime contracts."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.routing import (
    ExecutionTarget,
    ExecutionTargetError,
    ExecutionTargetRegistry,
    ExecutionTargetRegistryDocument,
    TaskActionRequest,
)
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    CodexCapabilityProbe,
    CodexCommandBuilder,
    TaskContractError,
    TaskCoordinator,
    TaskRecipeRegistry,
    TaskRequest,
    TaskRunState,
    TaskRuntimeManager,
    TaskSafetyPolicy,
    TaskStore,
    TaskWorker,
    task_request_from_action,
)

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
SOURCE_ID = "22222222-2222-4222-8222-222222222222"
THREAD_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
FORK_THREAD_ID = "11111111-2222-4333-8444-555555555555"
CAPABILITIES = CodexCapabilities(
    available=True,
    create=True,
    resume=True,
    fork=True,
)
ROOT = Path(__file__).parents[2]


def _target_registry(tmp_path: Path) -> tuple[ExecutionTargetRegistry, dict[str, Path]]:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True)
    (project_root / "project-layout.json").write_text(
        json.dumps({"schema_version": 2, "project_id": PROJECT_ID}),
        encoding="utf-8",
    )
    project_path = tmp_path / "projects.json"
    project_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "projects": [
                    {
                        "project_id": PROJECT_ID,
                        "display_name": "Project",
                        "root": str(project_root),
                        "enabled": True,
                        "capabilities": ["codex"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    vault_root = tmp_path / "vault"
    folder_root = tmp_path / "folder"
    vault_root.mkdir()
    folder_root.mkdir()
    source_registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    source_registry.save(
        KnowledgeSourceRegistryDocument(
            folders=[
                FolderRegistration(
                    folder_id="vault-root",
                    root=vault_root,
                    capabilities=["read", "codex"],
                ),
                FolderRegistration(
                    folder_id="folder-root",
                    root=folder_root,
                    capabilities=["read", "codex"],
                ),
            ],
            sources=[
                KnowledgeSourceRegistration(
                    source_id=SOURCE_ID,
                    folder_id="vault-root",
                    capabilities=["read"],
                )
            ],
        )
    )
    registry = ExecutionTargetRegistry(
        tmp_path / "execution-targets.json",
        project_registry=ProjectRegistry(project_path),
        source_registry=source_registry,
    )
    registry.save(
        ExecutionTargetRegistryDocument(
            targets=[
                ExecutionTarget(
                    target_id="project-target",
                    kind="project",
                    registered_root_id=PROJECT_ID,
                    capabilities=["codex"],
                ),
                ExecutionTarget(
                    target_id="vault-target",
                    kind="vault",
                    registered_root_id="vault-root",
                    capabilities=["codex"],
                ),
                ExecutionTarget(
                    target_id="folder-target",
                    kind="folder",
                    registered_root_id="folder-root",
                    capabilities=["codex"],
                ),
            ]
        )
    )
    return registry, {
        "project-target": project_root.resolve(),
        "vault-target": vault_root.resolve(),
        "folder-target": folder_root.resolve(),
    }


def _recipe_registry(path: Path) -> TaskRecipeRegistry:
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "recipes": [
                    {
                        "recipe_id": "research-task",
                        "title": "Research task",
                        "project_required": True,
                        "allowed_provider_ids": [],
                        "allowed_project_ids": None,
                        "allowed_target_ids": ["project-target"],
                        "allowed_tool_ids": [],
                        "context_policy_id": "selected-only",
                        "safety_policy_id": "standard-safe",
                        "allowed_efforts": ["standard"],
                    }
                ],
                "safety_policies": [
                    {
                        "policy_id": "standard-safe",
                        "policy_version": 1,
                        "model": "gpt-5.6-codex",
                        "sandbox": "workspace-write",
                        "approval_policy": "never",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return TaskRecipeRegistry(path)


class _FakeProcess:
    def __init__(self, thread_id: str) -> None:
        self.pid = 4242
        self.returncode: int | None = None
        self._stdout = json.dumps({"thread_id": thread_id})

    def communicate(self, *, input: str, timeout: float):
        self.returncode = 0
        return self._stdout, ""

    def poll(self):
        return self.returncode

    def wait(self, *, timeout: float):
        self.returncode = 0
        return 0


class _SequencePopen:
    def __init__(self, *thread_ids: str) -> None:
        self._thread_ids = list(thread_ids)
        self.calls: list[tuple[list[str], dict]] = []
        self._lock = threading.Lock()

    def __call__(self, argv, **kwargs):
        with self._lock:
            self.calls.append((list(argv), kwargs))
            return _FakeProcess(self._thread_ids.pop(0))


class _BlockingProcess(_FakeProcess):
    def __init__(self) -> None:
        super().__init__(THREAD_ID)
        self.started = threading.Event()
        self.released = threading.Event()

    def communicate(self, *, input: str, timeout: float):
        self.started.set()
        assert self.released.wait(timeout=2)
        return self._stdout, ""


class _ReleasingReaper:
    def reap(self, process: _BlockingProcess) -> None:
        process.returncode = -15
        process.released.set()


def _runtime(
    tmp_path: Path,
    *,
    popen,
    reaper=None,
) -> tuple[TaskRuntimeManager, TaskStore]:
    targets, _roots = _target_registry(tmp_path)
    recipes = _recipe_registry(tmp_path / "recipes.json")
    store = TaskStore(tmp_path / "tasks.json")
    builder = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        target_registry=targets,
        safety_policies=recipes.safety_policy_map(),
    )
    coordinator = TaskCoordinator(
        recipes=recipes,
        store=store,
        commands=builder,
    )
    worker = TaskWorker(
        store,
        capabilities=CAPABILITIES,
        popen_factory=popen,
        reaper=reaper,
    )
    return (
        TaskRuntimeManager(
            coordinator=coordinator,
            store=store,
            capabilities=CAPABILITIES,
            worker=worker,
            timeout_seconds=30,
        ),
        store,
    )


def _request(key: str, *, brief: str = "Inspect the registered target") -> TaskRequest:
    return TaskRequest(
        recipe_id="research-task",
        target_id="project-target",
        effort="standard",
        brief=brief,
        idempotency_key=key,
    )


def test_execution_targets_resolve_only_registered_root_ids(tmp_path: Path):
    registry, roots = _target_registry(tmp_path)

    schema = json.loads(
        (ROOT / "contracts" / "execution-target-registry.schema.json").read_text()
    )
    jsonschema.validate(registry.load().model_dump(mode="json"), schema)

    for target_id, expected in roots.items():
        resolved = registry.resolve(target_id, capability="codex")
        assert resolved.cwd == expected
        assert resolved.target.registered_root_id != str(expected)
    assert (registry.path.stat().st_mode & 0o777) == 0o600

    document = registry.load()
    document.targets.append(
        ExecutionTarget(
            target_id="unknown-target",
            kind="folder",
            registered_root_id="not-registered",
            capabilities=["codex"],
        )
    )
    registry.save(document)
    with pytest.raises(ExecutionTargetError, match="unknown folder"):
        registry.resolve("unknown-target", capability="codex")


def test_task_action_is_strict_utf8_bounded_and_destination_never_changes_cwd(tmp_path: Path):
    registry, roots = _target_registry(tmp_path)
    policy = TaskSafetyPolicy(
        policy_id="standard-safe",
        policy_version=1,
        model="gpt-5.6-codex",
        sandbox="workspace-write",
    )
    builder = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        target_registry=registry,
        safety_policies={policy.policy_id: policy},
    )
    recipe = _recipe_registry(tmp_path / "recipes.json").get("research-task")
    first = TaskActionRequest(
        action_id="run-research",
        destination_id="destination-one",
        target_id="project-target",
        brief="Inspect the project",
        effort="standard",
        idempotency_key="request-one",
    )
    second = first.model_copy(update={"destination_id": "destination-two"})
    first_task = task_request_from_action(first, recipe_id=recipe.recipe_id)
    second_task = task_request_from_action(second, recipe_id=recipe.recipe_id)

    assert first_task == second_task
    assert builder.build_new(recipe, first_task).cwd == roots["project-target"]
    assert builder.build_new(recipe, second_task).cwd == roots["project-target"]
    assert "destination-one" not in builder.build_new(recipe, first_task).argv

    for forbidden in ("url", "command", "cwd", "model", "sandbox", "environment"):
        with pytest.raises(ValidationError):
            TaskActionRequest.model_validate(
                {**first.model_dump(mode="json"), forbidden: "untrusted"}
            )
    with pytest.raises(ValidationError, match="clean bounded text"):
        TaskActionRequest.model_validate(
            {**first.model_dump(mode="json"), "brief": "界" * 2731}
        )


def test_runtime_manager_create_resume_fork_status_and_idempotency(tmp_path: Path):
    popen = _SequencePopen(THREAD_ID, THREAD_ID, FORK_THREAD_ID)
    manager, store = _runtime(tmp_path, popen=popen)

    created = manager.create(_request("create-key"), title="Research")
    created = manager.wait(created.run.run_id, timeout=2)
    assert created.run.state == TaskRunState.SUCCEEDED
    assert created.task.codex_thread_id == THREAD_ID

    replay = manager.create(_request("create-key"), title="Research")
    assert replay.reused is True
    assert replay.run.run_id == created.run.run_id
    assert len(popen.calls) == 1

    resumed = manager.resume(
        created.task.task_id,
        _request("resume-key", brief="Continue explicitly"),
    )
    resumed = manager.wait(resumed.run.run_id, timeout=2)
    assert resumed.run.state == TaskRunState.SUCCEEDED
    assert popen.calls[1][0][-3:] == ["resume", THREAD_ID, "-"]
    assert "--last" not in popen.calls[1][0]

    forked = manager.fork(
        created.task.task_id,
        _request("fork-key", brief="Explore a new branch"),
        title="Forked research",
    )
    forked = manager.wait(forked.run.run_id, timeout=2)
    assert forked.run.state == TaskRunState.SUCCEEDED
    assert forked.task.task_id != created.task.task_id
    assert forked.task.codex_thread_id == FORK_THREAD_ID
    assert popen.calls[2][0][-3:] == ["fork", THREAD_ID, "-"]
    assert len(manager.task_status(created.task.task_id)) == 2
    assert len(store.snapshot().idempotency) == 3


def test_runtime_manager_cancel_and_capability_probe_fail_closed(tmp_path: Path):
    process = _BlockingProcess()
    manager, _store = _runtime(
        tmp_path,
        popen=lambda *args, **kwargs: process,
        reaper=_ReleasingReaper(),
    )
    running = manager.create(_request("cancel-key"), title="Cancelable")
    assert process.started.wait(timeout=2)
    cancelled = manager.cancel(running.run.run_id)
    assert cancelled.run.state == TaskRunState.CANCELLED
    assert manager.wait(running.run.run_id, timeout=2).run.state == TaskRunState.CANCELLED

    targets, _roots = _target_registry(tmp_path / "disabled")
    recipes = _recipe_registry(tmp_path / "disabled-recipes.json")
    disabled_store = TaskStore(tmp_path / "disabled-tasks.json")
    builder = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        target_registry=targets,
        safety_policies=recipes.safety_policy_map(),
    )
    coordinator = TaskCoordinator(
        recipes=recipes,
        store=disabled_store,
        commands=builder,
    )

    def incomplete_help(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="codex exec", stderr="")

    disabled = TaskRuntimeManager.from_probe(
        coordinator=coordinator,
        store=disabled_store,
        probe=CodexCapabilityProbe(
            Path("/opt/codex/bin/codex"),
            runner=incomplete_help,
        ),
    )
    assert disabled.capabilities.available is False
    with pytest.raises(TaskContractError, match="lacks required exec capabilities"):
        disabled.create(_request("disabled-key"), title="Disabled")
    assert disabled_store.snapshot().runs == []
