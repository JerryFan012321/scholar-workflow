"""Contract tests for the disabled-by-default Hub WI-039 worker primitives."""

from __future__ import annotations

import json
import multiprocessing
import signal
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    CodexCapabilityProbe,
    CodexCommandBuilder,
    ProcessGroupReaper,
    TaskContractError,
    TaskCoordinator,
    TaskEffort,
    TaskRecipeRegistry,
    TaskRequest,
    TaskRun,
    TaskRunState,
    TaskStore,
    TaskWorker,
    extract_codex_thread_id,
)

ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 9, 22, 8, 0, tzinfo=UTC)
THREAD_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
FORK_THREAD_ID = "11111111-2222-4333-8444-555555555555"
VERIFIED_CAPABILITIES = CodexCapabilities(
    available=True,
    create=True,
    resume=True,
    fork=True,
)


def _reserve_run_in_process(store_path, run_payload, start_event, result_queue):
    """Top-level helper so the collision test also works with spawn-based runners."""

    start_event.wait(timeout=5)
    try:
        reservation = TaskStore(Path(store_path)).reserve_run(
            TaskRun.model_validate(run_payload)
        )
    except TaskContractError as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", reservation.run.run_id, ""))


class Clock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value


class Identifiers:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value:03d}"


def _registry_payload(*, model: str = "gpt-5.6-codex") -> dict:
    return {
        "schema_version": 1,
        "recipes": [
            {
                "recipe_id": "research-task",
                "title": "Research task",
                "project_required": False,
                "allowed_library_ids": ["papers", "tools"],
                "allowed_project_ids": None,
                "allowed_tool_ids": ["zotero-local"],
                "context_policy_id": "selected-only",
                "safety_policy_id": "standard-safe",
                "allowed_efforts": ["standard", "deep"],
            }
        ],
        "safety_policies": [
            {
                "policy_id": "standard-safe",
                "policy_version": 1,
                "model": model,
                "sandbox": "workspace-write",
                "approval_policy": "never",
            }
        ],
    }


def _write_registry(path: Path, *, model: str = "gpt-5.6-codex") -> None:
    path.write_text(json.dumps(_registry_payload(model=model)), encoding="utf-8")


def _harness(tmp_path: Path):
    recipe_path = tmp_path / "recipes.json"
    _write_registry(recipe_path)
    registry = TaskRecipeRegistry(recipe_path)
    store = TaskStore(tmp_path / "tasks.json")
    clock = Clock()
    builder = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        project_registry=ProjectRegistry(tmp_path / "projects.json"),
        safety_policies=registry.safety_policy_map(),
        runtime_cwd=tmp_path,
    )
    coordinator = TaskCoordinator(
        recipes=registry,
        store=store,
        commands=builder,
        clock=clock,
        identifier_factory=Identifiers(),
    )
    return recipe_path, registry, store, clock, builder, coordinator


def _request(
    *,
    key: str = "request-001",
    brief: str = "Investigate the selected paper",
    effort: TaskEffort | str = TaskEffort.STANDARD,
) -> TaskRequest:
    return TaskRequest(
        recipe_id="research-task",
        effort=effort,
        brief=brief,
        idempotency_key=key,
    )


class FakeProcess:
    def __init__(self, stdout: str, *, returncode: int = 0) -> None:
        self.pid = 4242
        self._stdout = stdout
        self._final_returncode = returncode
        self.returncode: int | None = None
        self.input: str | None = None
        self.timeout: float | None = None

    def communicate(self, *, input: str, timeout: float):
        self.input = input
        self.timeout = timeout
        self.returncode = self._final_returncode
        return self._stdout, "ignored stderr transcript"

    def poll(self):
        return self.returncode

    def wait(self, *, timeout: float):
        self.returncode = self._final_returncode
        return self.returncode


class FakePopen:
    def __init__(self, process: FakeProcess) -> None:
        self.process = process
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.process


def test_explicit_recipe_registry_and_checked_in_schema(tmp_path):
    registry_path = tmp_path / "recipes.json"
    payload = _registry_payload()
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    registry = TaskRecipeRegistry(registry_path)

    assert registry.get("research-task").allowed_tool_ids == ["zotero-local"]
    assert registry.safety_policy_map()["standard-safe"].sandbox == "workspace-write"
    with pytest.raises(TaskContractError, match="unknown task recipe"):
        registry.get("from-path-scan")

    schema = json.loads(
        (ROOT / "contracts" / "task-recipe-registry.schema.json").read_text()
    )
    jsonschema.validate(registry.load().model_dump(mode="json"), schema)
    invalid = _registry_payload()
    invalid["recipes"][0]["safety_policy_id"] = "missing-policy"
    registry_path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(TaskContractError, match="unknown safety policy"):
        registry.load()


def test_command_is_fixed_by_server_policy_and_continuation_order_is_valid(tmp_path):
    _, registry, _, _, builder, _ = _harness(tmp_path)
    recipe = registry.get("research-task")
    request = _request(brief="literal $(touch /tmp/never)")

    created = builder.build_new(recipe, request)
    expected_prefix = (
        "/opt/codex/bin/codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--json",
        "-C",
        str(tmp_path.resolve()),
        "-m",
        "gpt-5.6-codex",
        "-s",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-c",
        'model_reasoning_effort="medium"',
    )
    assert created.argv == expected_prefix + ("-",)
    assert created.stdin == request.brief
    assert request.brief not in created.argv

    resumed = builder.build_continuation(
        recipe,
        request,
        mode="resume",
        codex_thread_id=THREAD_ID,
    )
    assert resumed.argv == expected_prefix + ("resume", THREAD_ID, "-")
    assert resumed.argv.index("-C") < resumed.argv.index("resume")
    with pytest.raises(ValueError, match="explicit saved"):
        builder.build_continuation(
            recipe,
            request,
            mode="resume",
            codex_thread_id="--last",
        )

    unknown_policy = recipe.model_copy(update={"safety_policy_id": "unknown-policy"})
    with pytest.raises(ValueError, match="not registered"):
        builder.build_new(unknown_policy, request)


def test_capability_probe_fails_closed_when_a_builder_flag_is_missing(tmp_path):
    def incomplete_runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="--json --cd", stderr="")

    capabilities = CodexCapabilityProbe(
        Path("/opt/codex/bin/codex"),
        runner=incomplete_runner,
    ).probe()
    assert capabilities.available is False
    assert capabilities.create is False
    assert capabilities.detail is not None
    with pytest.raises(TaskContractError, match="disabled by capability probe"):
        TaskWorker(TaskStore(tmp_path / "tasks.json"), capabilities=capabilities)


def test_store_persists_hashes_not_brief_or_transcript_and_idempotency_is_durable(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    brief = "PRIVATE BRIEF THAT MUST NOT BE STORED"
    request = _request(brief=brief)
    submission = coordinator.create(request, title="Paper investigation")
    replay = coordinator.create(request, title="Paper investigation")

    assert submission.reused is False
    assert replay.reused is True
    assert replay.invocation is None
    assert replay.run.run_id == submission.run.run_id
    persisted = (tmp_path / "tasks.json").read_text(encoding="utf-8")
    assert brief not in persisted
    assert "brief_hash" in persisted
    assert "transcript" not in persisted

    with pytest.raises(TaskContractError, match="different request"):
        coordinator.create(
            _request(brief="changed", key=request.idempotency_key),
            title="Paper investigation",
        )

    schema = json.loads((ROOT / "contracts" / "task-store.schema.json").read_text())
    jsonschema.validate(store.snapshot().model_dump(mode="json"), schema)


def test_lockfile_symlink_fails_closed(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    coordinator.create(_request(), title="Creates lock")
    store.lock_path.unlink()
    target = tmp_path / "attacker-lock"
    target.write_text("", encoding="utf-8")
    store.lock_path.symlink_to(target)

    with pytest.raises(TaskContractError, match="lockfile cannot be a symlink"):
        store.snapshot()


def test_worker_uses_shell_false_stdin_and_extracts_only_explicit_thread_jsonl(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    brief = "stdin only; ; $(not-a-command)"
    submission = coordinator.create(_request(brief=brief), title="Safe launch")
    transcript = (
        json.dumps({"type": "thread.started", "thread_id": THREAD_ID})
        + "\n"
        + json.dumps({"type": "item.completed", "text": "PRIVATE TRANSCRIPT"})
        + "\n"
    )
    process = FakeProcess(transcript)
    popen = FakePopen(process)

    result = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=popen,
    ).execute(
        submission,
        timeout_seconds=30,
    )

    assert result.state == TaskRunState.SUCCEEDED
    assert result.codex_thread_id == THREAD_ID
    assert store.get_task(submission.task.task_id).codex_thread_id == THREAD_ID
    argv, kwargs = popen.calls[0]
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert process.input == brief
    assert brief not in argv
    persisted = (tmp_path / "tasks.json").read_text(encoding="utf-8")
    assert brief not in persisted
    assert "PRIVATE TRANSCRIPT" not in persisted

    assert extract_codex_thread_id(transcript) == THREAD_ID
    with pytest.raises(TaskContractError, match="exactly one"):
        extract_codex_thread_id(json.dumps({"type": "done"}))
    with pytest.raises(TaskContractError, match="invalid explicit"):
        extract_codex_thread_id(json.dumps({"thread_id": "--last"}))
    with pytest.raises(TaskContractError, match="invalid explicit"):
        extract_codex_thread_id(json.dumps({"thread_id": "friendly-thread-name"}))
    with pytest.raises(TaskContractError, match="exactly one"):
        extract_codex_thread_id(
            json.dumps({"thread_id": THREAD_ID})
            + "\n"
            + json.dumps({"thread_id": FORK_THREAD_ID})
        )


def test_thread_identity_cannot_be_owned_by_two_logical_tasks(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    first = coordinator.create(_request(), title="First owner")
    second = coordinator.create(
        _request(key="request-second", brief="second task"),
        title="Second owner",
    )
    output = json.dumps({"type": "thread.started", "thread_id": THREAD_ID})
    first_result = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(FakeProcess(output)),
    ).execute(first, timeout_seconds=30)
    second_result = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(FakeProcess(output)),
    ).execute(second, timeout_seconds=30)

    assert first_result.state == TaskRunState.SUCCEEDED
    assert second_result.state == TaskRunState.FAILED
    assert store.get_task(second.task.task_id).codex_thread_id is None


def test_two_processes_cannot_reserve_the_same_thread(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    created = coordinator.create(_request(), title="Thread owner")
    TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": THREAD_ID}))
        ),
    ).execute(created, timeout_seconds=30)
    task = store.get_task(created.task.task_id)
    base = {
        "task_id": task.task_id,
        "state": "queued",
        "mode": "resume",
        "configuration_fingerprint": task.configuration_fingerprint,
        "source_thread_id": THREAD_ID,
        "codex_thread_id": None,
        "result_summary": None,
        "result_summary_hash": None,
        "created_at": NOW.isoformat(),
        "started_at": None,
        "heartbeat_at": None,
        "timeout_at": None,
        "cancel_requested_at": None,
        "completed_at": None,
    }
    run_a = base | {
        "run_id": "run-process-a",
        "idempotency_key": "process-key-a",
        "request_fingerprint": "sha256:" + "a" * 64,
    }
    run_b = base | {
        "run_id": "run-process-b",
        "idempotency_key": "process-key-b",
        "request_fingerprint": "sha256:" + "b" * 64,
    }
    context = multiprocessing.get_context("fork")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_reserve_run_in_process,
            args=(str(store.path), payload, start_event, result_queue),
        )
        for payload in (run_a, run_b)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = [result_queue.get(timeout=5) for _ in processes]
    for process in processes:
        process.join(timeout=5)
        assert process.exitcode == 0

    assert sorted(result[0] for result in results) == ["error", "ok"]
    assert any("active run" in result[2] for result in results if result[0] == "error")
    queued = [run for run in store.snapshot().runs if run.state == TaskRunState.QUEUED]
    assert len(queued) == 1


def test_corrupt_success_record_is_rejected_on_read(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    created = coordinator.create(_request(), title="Corruption check")
    TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": THREAD_ID}))
        ),
    ).execute(created, timeout_seconds=30)
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    payload["runs"][0]["completed_at"] = None
    store.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TaskContractError, match="invalid task store"):
        store.snapshot()


def test_resume_configuration_is_immutable_thread_is_mutexed_and_fork_is_new_task(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    created = coordinator.create(_request(), title="Long task")
    TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": THREAD_ID}))
        ),
    ).execute(created, timeout_seconds=30)

    with pytest.raises(TaskContractError, match="cannot silently change"):
        coordinator.resume(
            created.task.task_id,
            _request(key="request-deep", brief="continue", effort="deep"),
        )

    resume = coordinator.resume(
        created.task.task_id,
        _request(key="request-resume", brief="continue"),
    )
    with pytest.raises(TaskContractError, match="active run"):
        coordinator.resume(
            created.task.task_id,
            _request(key="request-concurrent", brief="also continue"),
        )
    resumed = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": THREAD_ID}))
        ),
    ).execute(resume, timeout_seconds=30)
    assert resumed.state == TaskRunState.SUCCEEDED

    fork = coordinator.fork(
        created.task.task_id,
        _request(key="request-fork", brief="new direction", effort="deep"),
        title="Forked task",
    )
    assert fork.task.task_id != created.task.task_id
    assert fork.run.source_thread_id == THREAD_ID
    assert fork.invocation is not None
    assert fork.invocation.argv[-3:] == ("fork", THREAD_ID, "-")
    forked = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": FORK_THREAD_ID}))
        ),
    ).execute(fork, timeout_seconds=30)
    assert forked.codex_thread_id == FORK_THREAD_ID
    assert store.get_task(fork.task.task_id).codex_thread_id == FORK_THREAD_ID


def test_policy_change_invalidates_resume_configuration(tmp_path):
    registry_path, _, store, _, _, coordinator = _harness(tmp_path)
    created = coordinator.create(_request(), title="Long task")
    TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(
            FakeProcess(json.dumps({"type": "thread.started", "thread_id": THREAD_ID}))
        ),
    ).execute(created, timeout_seconds=30)

    _write_registry(registry_path, model="gpt-6-codex")
    changed_registry = TaskRecipeRegistry(registry_path)
    changed_builder = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        project_registry=ProjectRegistry(tmp_path / "projects.json"),
        safety_policies=changed_registry.safety_policy_map(),
        runtime_cwd=tmp_path,
    )
    changed = TaskCoordinator(
        recipes=changed_registry,
        store=store,
        commands=changed_builder,
        identifier_factory=Identifiers(),
    )
    with pytest.raises(TaskContractError, match="cannot silently change"):
        changed.resume(
            created.task.task_id,
            _request(key="request-resume", brief="continue"),
        )


class TimeoutProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__("")
        self.wait_calls = 0

    def communicate(self, *, input: str, timeout: float):
        self.input = input
        raise subprocess.TimeoutExpired(["codex"], timeout)

    def wait(self, *, timeout: float):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise subprocess.TimeoutExpired(["codex"], timeout)
        self.returncode = -signal.SIGKILL
        return self.returncode


def test_timeout_reaps_process_group_and_cancel_has_explicit_state(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    timed = coordinator.create(_request(), title="Timed task")
    process = TimeoutProcess()
    signals: list[tuple[int, int]] = []
    reaper = ProcessGroupReaper(
        getpgid=lambda pid: 9001,
        killpg=lambda pgid, sig: signals.append((pgid, sig)),
        grace_seconds=0.01,
    )
    result = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,
    ).execute(timed, timeout_seconds=1)

    assert result.state == TaskRunState.TIMED_OUT
    assert signals == [(9001, signal.SIGTERM), (9001, signal.SIGKILL)]

    queued = coordinator.create(
        _request(key="request-cancel", brief="cancel me"),
        title="Cancelled task",
    )
    cancelled = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
    ).cancel(queued.run.run_id)
    assert cancelled.state == TaskRunState.CANCELLED
    assert cancelled.cancel_requested_at is not None


def test_process_start_failure_is_sanitized_and_persisted(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Cannot start")

    def fail_to_start(*_args, **_kwargs):
        raise OSError("PRIVATE HOST ERROR")

    result = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=fail_to_start,
    ).execute(
        submission,
        timeout_seconds=30,
    )
    assert result.state == TaskRunState.FAILED
    assert result.result_summary == "Codex process could not start"
    assert "PRIVATE HOST ERROR" not in (tmp_path / "tasks.json").read_text()


class BlockingProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__("")
        self.started = threading.Event()
        self.released = threading.Event()

    def communicate(self, *, input: str, timeout: float):
        self.input = input
        self.started.set()
        assert self.released.wait(timeout=2)
        return "", ""


class ReleasingReaper:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def reap(self, process: BlockingProcess) -> None:
        self.calls.append(process.pid)
        process.returncode = -signal.SIGTERM
        process.released.set()


def test_running_cancel_reaps_active_group_and_finishes_cancelled(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Running cancel")
    process = BlockingProcess()
    reaper = ReleasingReaper()
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,  # type: ignore[arg-type]
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(worker.execute(submission, timeout_seconds=30))
    )
    thread.start()
    assert process.started.wait(timeout=2)
    cancelled = worker.cancel(submission.run.run_id)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert cancelled.state == TaskRunState.CANCELLED
    assert results[0].state == TaskRunState.CANCELLED
    assert reaper.calls == [process.pid]


def test_heartbeat_refresh_and_stale_without_local_handle_requires_recovery(tmp_path):
    _, _, store, clock, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Heartbeat task")
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        clock=clock,
    )
    store.start(submission.run.run_id, now=clock(), timeout_seconds=300)

    clock.value += timedelta(seconds=20)
    heartbeat = worker.heartbeat(submission.run.run_id)
    assert heartbeat.heartbeat_at == clock.value
    clock.value += timedelta(seconds=29)
    assert worker.interrupt_stale(stale_after=timedelta(seconds=30)) == []
    clock.value += timedelta(seconds=2)
    interrupted = worker.interrupt_stale(stale_after=timedelta(seconds=30))
    assert interrupted == []
    assert store.get_run(submission.run.run_id).state == TaskRunState.RECOVERY_REQUIRED


def test_stale_active_process_is_reaped_before_interrupted_is_persisted(tmp_path):
    _, _, store, clock, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Stale active task")
    process = BlockingProcess()
    reaper = ReleasingReaper()
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,  # type: ignore[arg-type]
        clock=clock,
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(worker.execute(submission, timeout_seconds=300))
    )
    thread.start()
    assert process.started.wait(timeout=2)
    clock.value += timedelta(seconds=31)

    interrupted = worker.interrupt_stale(stale_after=timedelta(seconds=30))
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert [run.run_id for run in interrupted] == [submission.run.run_id]
    assert results[0].state == TaskRunState.INTERRUPTED
    assert reaper.calls == [process.pid]
    assert worker.active_run_ids() == ()


class FailingReaper:
    def __init__(self) -> None:
        self.calls = 0

    def reap(self, process) -> None:
        self.calls += 1
        raise RuntimeError("injected reaper failure")


def test_timeout_reaper_failure_keeps_live_handle_and_nonterminal_recovery_state(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Recovery task")
    process = TimeoutProcess()
    reaper = FailingReaper()
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,  # type: ignore[arg-type]
    )

    result = worker.execute(submission, timeout_seconds=1)

    assert result.state == TaskRunState.RECOVERY_REQUIRED
    assert result.completed_at is None
    assert worker.active_run_ids() == (submission.run.run_id,)
    assert reaper.calls == 1


def test_stale_reaper_failure_does_not_write_interrupted_or_drop_handle(tmp_path):
    _, _, store, clock, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="Stale recovery task")
    process = BlockingProcess()
    reaper = FailingReaper()
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,  # type: ignore[arg-type]
        clock=clock,
    )
    results = []
    thread = threading.Thread(
        target=lambda: results.append(worker.execute(submission, timeout_seconds=300))
    )
    thread.start()
    assert process.started.wait(timeout=2)
    clock.value += timedelta(seconds=31)

    assert worker.interrupt_stale(stale_after=timedelta(seconds=30)) == []
    recovery = store.get_run(submission.run.run_id)
    assert recovery.state == TaskRunState.RECOVERY_REQUIRED
    assert recovery.completed_at is None
    assert worker.active_run_ids() == (submission.run.run_id,)

    process.returncode = -signal.SIGTERM
    process.released.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert results[0].state == TaskRunState.FAILED
    assert worker.active_run_ids() == ()


class CommunicationErrorProcess(FakeProcess):
    def communicate(self, *, input: str, timeout: float):
        self.input = input
        raise ValueError("injected communicate failure")


class StoppingReaper:
    def __init__(self) -> None:
        self.calls = 0

    def reap(self, process) -> None:
        self.calls += 1
        process.returncode = -signal.SIGTERM


def test_communicate_exception_reaps_then_records_failed_and_drops_stopped_handle(tmp_path):
    _, _, store, _, _, coordinator = _harness(tmp_path)
    submission = coordinator.create(_request(), title="I/O failure task")
    process = CommunicationErrorProcess("")
    reaper = StoppingReaper()
    worker = TaskWorker(
        store,
        capabilities=VERIFIED_CAPABILITIES,
        popen_factory=FakePopen(process),
        reaper=reaper,  # type: ignore[arg-type]
    )

    result = worker.execute(submission, timeout_seconds=30)

    assert result.state == TaskRunState.FAILED
    assert result.result_summary == "Codex worker I/O failed"
    assert reaper.calls == 1
    assert worker.active_run_ids() == ()
