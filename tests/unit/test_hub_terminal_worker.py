"""Private cmux terminal worker queue and execution tests."""

from __future__ import annotations

import io
import json
import os
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from scholar_workflow.hub.directory import (
    ProjectRegistration,
    ProjectRegistry,
    ProjectRegistryDocument,
)
from scholar_workflow.hub.fields import (
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.routing import (
    ExecutionTarget,
    ExecutionTargetRegistry,
    ExecutionTargetRegistryDocument,
)
from scholar_workflow.hub.tasks import (
    CodexCapabilities,
    CodexCommandBuilder,
    TaskCoordinator,
    TaskRecipe,
    TaskRecipeRegistry,
    TaskRecipeRegistryDocument,
    TaskRequest,
    TaskRunState,
    TaskSafetyPolicy,
    TaskStore,
)
from scholar_workflow.hub.terminal_worker import (
    TerminalSlotWorker,
    TerminalTaskBroker,
    TerminalWorkerError,
    TerminalWorkerRuntimeConfig,
    TerminalWorkerState,
    build_terminal_worker_command,
)

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
THREAD_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
CAPABILITIES = CodexCapabilities(
    available=True,
    create=True,
    resume=True,
    fork=True,
)


def _write_registry(path: Path, document) -> None:
    path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _runtime(tmp_path: Path, *, brief: str = "private approved brief"):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "project-layout.json").write_text(
        json.dumps({"schema_version": 2, "project_id": PROJECT_ID}),
        encoding="utf-8",
    )
    project_registry_path = tmp_path / "projects.json"
    _write_registry(
        project_registry_path,
        ProjectRegistryDocument(
            projects=[
                ProjectRegistration(
                    project_id=PROJECT_ID,
                    display_name="Project",
                    root=project_root,
                    capabilities=["codex"],
                )
            ]
        ),
    )
    source_registry_path = tmp_path / "sources.json"
    KnowledgeSourceRegistry(source_registry_path).save(
        KnowledgeSourceRegistryDocument()
    )
    target_registry_path = tmp_path / "targets.json"
    targets = ExecutionTargetRegistry(
        target_registry_path,
        project_registry=ProjectRegistry(project_registry_path),
        source_registry=KnowledgeSourceRegistry(source_registry_path),
    )
    targets.save(
        ExecutionTargetRegistryDocument(
            targets=[
                ExecutionTarget(
                    target_id="project-target",
                    kind="project",
                    registered_root_id=PROJECT_ID,
                    capabilities=["codex"],
                )
            ]
        )
    )

    recipes_path = tmp_path / "recipes.json"
    recipe = TaskRecipe(
        recipe_id="research-task",
        title="Research task",
        allowed_target_ids=["project-target"],
        safety_policy_id="standard-safe",
        allowed_efforts=["standard"],
    )
    policy = TaskSafetyPolicy(
        policy_id="standard-safe",
        policy_version=1,
        model="gpt-test",
        sandbox="workspace-write",
    )
    _write_registry(
        recipes_path,
        TaskRecipeRegistryDocument(recipes=[recipe], safety_policies=[policy]),
    )
    recipes = TaskRecipeRegistry(recipes_path)

    fake_codex = tmp_path / "codex"
    fake_codex.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "brief = sys.stdin.read()\n"
        f"assert brief == {brief!r}\n"
        f"assert {brief!r} not in sys.argv\n"
        f"print(json.dumps({{'type': 'thread.started', 'thread_id': {THREAD_ID!r}}}))\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)

    task_store_path = tmp_path / "tasks.json"
    store = TaskStore(task_store_path)
    builder = CodexCommandBuilder(
        codex_executable=fake_codex,
        target_registry=targets,
        safety_policies=recipes.safety_policy_map(),
    )
    coordinator = TaskCoordinator(recipes=recipes, store=store, commands=builder)
    request = TaskRequest(
        recipe_id="research-task",
        target_id="project-target",
        effort="standard",
        brief=brief,
        idempotency_key="request-001",
    )
    submission = coordinator.create(request, title="Research task")

    state = TerminalWorkerState(tmp_path / "terminal-state")
    state.save_runtime(
        TerminalWorkerRuntimeConfig(
            generation="generation-001",
            codex_executable=fake_codex,
            recipe_registry_path=recipes_path,
            task_store_path=task_store_path,
            execution_target_registry_path=target_registry_path,
            project_registry_path=project_registry_path,
            source_registry_path=source_registry_path,
            timeout_seconds=30,
            heartbeat_interval_seconds=1,
            poll_interval_seconds=0.01,
        )
    )
    return {
        "state": state,
        "store": store,
        "coordinator": coordinator,
        "request": request,
        "submission": submission,
        "project_root": project_root,
        "fake_codex": fake_codex,
    }


def _make_blocking_codex(path: Path, *, brief: str, delay: float = 5.0) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        "brief = sys.stdin.read()\n"
        f"assert brief == {brief!r}\n"
        f"print(json.dumps({{'type': 'thread.started', 'thread_id': {THREAD_ID!r}}}), flush=True)\n"
        f"time.sleep({delay!r})\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _update_timing(
    state: TerminalWorkerState,
    *,
    timeout: float,
    heartbeat: float,
    poll: float = 0.01,
) -> None:
    current = state.load_runtime(generation="generation-001")
    state.save_runtime(
        current.model_copy(
            update={
                "timeout_seconds": timeout,
                "heartbeat_interval_seconds": heartbeat,
                "poll_interval_seconds": poll,
            }
        )
    )


def test_worker_command_contains_only_fixed_runtime_coordinates(tmp_path: Path):
    state_root = tmp_path / "private state"
    state_root.mkdir(mode=0o700)
    command = build_terminal_worker_command(
        python_executable=Path(sys.executable),
        state_root=state_root,
        slot_id="slot-001",
        generation="generation-001",
    )

    assert command.startswith(str(Path(sys.executable).resolve()))
    assert "-m scholar_workflow.hub.terminal_worker" in command
    assert "--slot slot-001" in command
    assert "--generation generation-001" in command
    assert "private approved brief" not in command
    assert "gpt-test" not in command
    assert "project-target" not in command


def test_private_ticket_is_consumed_and_jsonl_is_not_persisted(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    broker = TerminalTaskBroker(state, generation="generation-001")
    receipt = broker.enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )

    ticket_path = (
        state.slots_path
        / "slot-001"
        / "queue"
        / f"{runtime['submission'].run.run_id}.json"
    )
    payload = json.loads(ticket_path.read_text(encoding="utf-8"))
    assert receipt.queued is True
    assert payload["submission"]["invocation"] is None
    assert payload["request"]["brief"] == "private approved brief"
    assert stat.S_IMODE(state.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(ticket_path.stat().st_mode) == 0o600

    terminal = io.StringIO()
    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=terminal,
        stderr=io.StringIO(),
    )
    assert worker.run_once() is True

    run = runtime["store"].get_run(runtime["submission"].run.run_id)
    assert run.state == TaskRunState.SUCCEEDED
    assert run.codex_thread_id == THREAD_ID
    assert THREAD_ID in terminal.getvalue()
    assert "private approved brief" not in terminal.getvalue()
    assert not ticket_path.exists()
    assert list((state.slots_path / "slot-001" / "active").iterdir()) == []
    persisted = runtime["store"].path.read_text(encoding="utf-8")
    assert THREAD_ID in persisted
    assert "private approved brief" not in persisted
    assert "thread.started" not in persisted


def test_resume_accepts_new_brief_but_keeps_the_saved_thread(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    broker = TerminalTaskBroker(state, generation="generation-001")
    terminal = io.StringIO()
    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=terminal,
        stderr=io.StringIO(),
    )
    broker.enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    assert worker.run_once() is True

    followup_brief = "Continue with a different question"
    runtime["fake_codex"].write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"assert sys.stdin.read() == {followup_brief!r}\n"
        f"print(json.dumps({{'type': 'thread.started', 'thread_id': {THREAD_ID!r}}}))\n",
        encoding="utf-8",
    )
    runtime["fake_codex"].chmod(0o700)
    request = TaskRequest(
        recipe_id="research-task",
        target_id="project-target",
        effort="standard",
        brief=followup_brief,
        idempotency_key="request-resume-001",
    )
    submission = runtime["coordinator"].resume(
        runtime["submission"].task.task_id,
        request,
    )
    assert broker.enqueue(
        slot_id="slot-001",
        submission=submission,
        request=request,
    ).queued
    assert worker.run_once() is True
    resumed = runtime["store"].get_run(submission.run.run_id)
    assert resumed.state == TaskRunState.SUCCEEDED
    assert resumed.codex_thread_id == THREAD_ID
    assert followup_brief not in terminal.getvalue()


def test_worker_revalidates_ticket_and_fails_tampered_brief(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    ticket_path = next((state.slots_path / "slot-001" / "queue").iterdir())
    payload = json.loads(ticket_path.read_text(encoding="utf-8"))
    payload["request"]["brief"] = "tampered brief"
    ticket_path.write_text(json.dumps(payload), encoding="utf-8")
    ticket_path.chmod(0o600)

    called = False

    def forbidden_popen(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("invalid ticket must not launch Codex")

    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        popen_factory=forbidden_popen,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert worker.run_once() is True
    run = runtime["store"].get_run(runtime["submission"].run.run_id)
    assert run.state == TaskRunState.FAILED
    assert run.result_summary == "Terminal worker rejected the queued task"
    assert called is False


def test_worker_re_resolves_target_before_launch(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    (runtime["project_root"] / "project-layout.json").unlink()

    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        popen_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("untrusted target must not launch Codex")
        ),
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert worker.run_once() is True
    assert (
        runtime["store"].get_run(runtime["submission"].run.run_id).state
        == TaskRunState.FAILED
    )


def test_public_slot_status_exposes_only_opaque_run_identity(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )

    status = state.public_status(slot_id="slot-001", generation="generation-001")
    payload = status.model_dump(mode="json")
    assert status.state == "idle"
    assert status.queued_run_ids == [runtime["submission"].run.run_id]
    encoded = json.dumps(payload)
    assert "private approved brief" not in encoded
    assert str(tmp_path) not in encoded
    assert "gpt-test" not in encoded
    assert "pid" not in encoded.lower()

    state.request_stop(slot_id="slot-001", generation="generation-001")
    assert (
        state.public_status(slot_id="slot-001", generation="generation-001").state
        == "stopping"
    )
    assert stat.S_IMODE((state.slots_path / "slot-001" / "stop.json").stat().st_mode) == 0o600


def test_runtime_config_and_queue_files_are_owner_only(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )

    for path in [state.root, *state.root.rglob("*")]:
        expected = 0o700 if path.is_dir() else 0o600
        assert stat.S_IMODE(path.stat().st_mode) == expected
    assert os.getuid() == state.runtime_path.stat().st_uid


def test_long_running_terminal_task_refreshes_heartbeat(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_blocking_codex(
        runtime["fake_codex"],
        brief=runtime["request"].brief,
        delay=0.15,
    )
    _update_timing(runtime["state"], timeout=2, heartbeat=0.03)
    TerminalTaskBroker(runtime["state"], generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    worker = TerminalSlotWorker(
        state=runtime["state"],
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    assert worker.run_once() is True
    run = runtime["store"].get_run(runtime["submission"].run.run_id)
    assert run.state == TaskRunState.SUCCEEDED
    assert run.started_at is not None
    assert run.heartbeat_at is not None
    assert run.heartbeat_at > run.started_at


def test_cancel_reaps_terminal_process_group(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_blocking_codex(
        runtime["fake_codex"],
        brief=runtime["request"].brief,
    )
    _update_timing(runtime["state"], timeout=5, heartbeat=0.05)
    TerminalTaskBroker(runtime["state"], generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    worker = TerminalSlotWorker(
        state=runtime["state"],
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    run_id = runtime["submission"].run.run_id
    deadline = time.monotonic() + 2
    while runtime["store"].get_run(run_id).state == TaskRunState.QUEUED:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    runtime["store"].request_cancel(run_id, now=runtime["store"].get_run(run_id).started_at)
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert runtime["store"].get_run(run_id).state == TaskRunState.CANCELLED


def test_timeout_reaps_terminal_process_group(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_blocking_codex(
        runtime["fake_codex"],
        brief=runtime["request"].brief,
    )
    _update_timing(runtime["state"], timeout=0.12, heartbeat=0.03)
    TerminalTaskBroker(runtime["state"], generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    worker = TerminalSlotWorker(
        state=runtime["state"],
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )

    started = time.monotonic()
    assert worker.run_once() is True
    elapsed = time.monotonic() - started
    run = runtime["store"].get_run(runtime["submission"].run.run_id)
    assert run.state == TaskRunState.TIMED_OUT
    assert elapsed < 2


def test_signal_stop_path_reaps_terminal_process_group(tmp_path: Path):
    runtime = _runtime(tmp_path)
    _make_blocking_codex(
        runtime["fake_codex"],
        brief=runtime["request"].brief,
    )
    _update_timing(runtime["state"], timeout=5, heartbeat=0.05)
    TerminalTaskBroker(runtime["state"], generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    worker = TerminalSlotWorker(
        state=runtime["state"],
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    thread = threading.Thread(target=worker.run_once)
    thread.start()
    run_id = runtime["submission"].run.run_id
    deadline = time.monotonic() + 2
    while runtime["store"].get_run(run_id).state == TaskRunState.QUEUED:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    worker.request_stop()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert runtime["store"].get_run(run_id).state == TaskRunState.INTERRUPTED


def test_worker_alive_requires_generation_marker_and_kernel_lease(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert state.worker_alive(slot_id="slot-001", generation="generation-001") is False

    thread = threading.Thread(target=worker.run_forever)
    thread.start()
    deadline = time.monotonic() + 2
    while not state.worker_alive(slot_id="slot-001", generation="generation-001"):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert (
        state.public_status(slot_id="slot-001", generation="generation-001").worker_alive
        is True
    )

    state.request_stop(slot_id="slot-001", generation="generation-001")
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert state.worker_alive(slot_id="slot-001", generation="generation-001") is False


def test_stale_generation_worker_exits_without_reusing_slot(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    worker = TerminalSlotWorker(
        state=state,
        slot_id="slot-001",
        generation="generation-001",
        capabilities=CAPABILITIES,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    thread = threading.Thread(target=worker.run_forever)
    thread.start()
    deadline = time.monotonic() + 2
    while not state.worker_alive(slot_id="slot-001", generation="generation-001"):
        assert time.monotonic() < deadline
        time.sleep(0.01)

    current = state.load_runtime(generation="generation-001")
    state.save_runtime(current.model_copy(update={"generation": "generation-002"}))
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert state.worker_alive(slot_id="slot-001", generation="generation-002") is False


def test_sigkill_after_claim_recovers_without_replaying_brief(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    run_id = runtime["submission"].run.run_id
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from scholar_workflow.hub.terminal_worker import TerminalWorkerState\n"
        "state = TerminalWorkerState(Path(sys.argv[1]))\n"
        "with state.worker_lease(slot_id='slot-001', generation='generation-001'):\n"
        "    state.mark_worker_ready(slot_id='slot-001', generation='generation-001')\n"
        "    assert state.claim_next(slot_id='slot-001', generation='generation-001')\n"
        "    time.sleep(30)\n"
    )
    old_worker = subprocess.Popen(
        [sys.executable, "-c", script, str(state.root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    marker = state.slots_path / "slot-001" / "active" / f"{run_id}.json"
    try:
        deadline = time.monotonic() + 3
        while not marker.exists():
            assert old_worker.poll() is None
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert state.worker_alive(slot_id="slot-001", generation="generation-001")
        os.kill(old_worker.pid, signal.SIGKILL)
        old_worker.wait(timeout=3)
        assert not state.worker_alive(slot_id="slot-001", generation="generation-001")
        current = state.load_runtime(generation="generation-001")
        state.save_runtime(current.model_copy(update={"generation": "generation-002"}))

        worker = TerminalSlotWorker(
            state=state,
            slot_id="slot-001",
            generation="generation-002",
            capabilities=CAPABILITIES,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        replacement = threading.Thread(target=worker.run_forever)
        replacement.start()
        deadline = time.monotonic() + 3
        while runtime["store"].get_run(run_id).state == TaskRunState.QUEUED:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        state.request_stop(slot_id="slot-001", generation="generation-002")
        replacement.join(timeout=3)

        assert not replacement.is_alive()
        assert runtime["store"].get_run(run_id).state == TaskRunState.FAILED
        assert not marker.exists()
        assert list((state.slots_path / "slot-001" / "queue").iterdir()) == []
    finally:
        if old_worker.poll() is None:
            os.kill(old_worker.pid, signal.SIGKILL)
            old_worker.wait(timeout=3)


def test_stale_running_marker_waits_for_process_group_death(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    run_id = runtime["submission"].run.run_id
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    assert state.claim_next(slot_id="slot-001", generation="generation-001")
    runtime["store"].start(run_id, now=runtime["submission"].run.created_at,
                           timeout_seconds=30)
    state.mark_launching(slot_id="slot-001", generation="generation-001", run_id=run_id)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    marker = state.slots_path / "slot-001" / "active" / f"{run_id}.json"
    try:
        state.mark_running(
            slot_id="slot-001",
            generation="generation-001",
            run_id=run_id,
            process_group_id=process.pid,
        )
        with state.worker_lease(slot_id="slot-001", generation="generation-001"):
            assert not state.worker_alive(
                slot_id="slot-001", generation="generation-001"
            )
            with pytest.raises(TerminalWorkerError, match="not proven stopped"):
                state.recover_stale_active(
                    slot_id="slot-001",
                    generation="generation-001",
                    store=runtime["store"],
                )
            assert marker.exists()
            assert runtime["store"].get_run(run_id).state == TaskRunState.RECOVERY_REQUIRED
            assert not state.worker_alive(
                slot_id="slot-001", generation="generation-001"
            )
            assert process.poll() is None

            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
            state.recover_stale_active(
                slot_id="slot-001",
                generation="generation-001",
                store=runtime["store"],
            )
        assert runtime["store"].get_run(run_id).state == TaskRunState.INTERRUPTED
        assert not marker.exists()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


def test_unknown_spawn_window_keeps_marker_and_blocks_replay(tmp_path: Path):
    runtime = _runtime(tmp_path)
    state = runtime["state"]
    run_id = runtime["submission"].run.run_id
    TerminalTaskBroker(state, generation="generation-001").enqueue(
        slot_id="slot-001",
        submission=runtime["submission"],
        request=runtime["request"],
    )
    assert state.claim_next(slot_id="slot-001", generation="generation-001")
    runtime["store"].start(
        run_id,
        now=runtime["submission"].run.created_at,
        timeout_seconds=30,
    )
    state.mark_launching(slot_id="slot-001", generation="generation-001", run_id=run_id)
    marker = state.slots_path / "slot-001" / "active" / f"{run_id}.json"

    with (
        state.worker_lease(slot_id="slot-001", generation="generation-001"),
        pytest.raises(TerminalWorkerError, match="not proven stopped"),
    ):
        state.recover_stale_active(
            slot_id="slot-001",
            generation="generation-001",
            store=runtime["store"],
        )
    assert marker.exists()
    assert runtime["store"].get_run(run_id).state == TaskRunState.RECOVERY_REQUIRED
    with pytest.raises(TerminalWorkerError, match="unfinished active run"):
        state.claim_next(slot_id="slot-001", generation="generation-001")
