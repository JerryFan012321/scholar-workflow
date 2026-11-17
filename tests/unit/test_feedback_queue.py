"""Native queue acceptance and central completion boundaries, with no live processes."""
from __future__ import annotations

import hashlib
import json
import errno
import os
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import codex_feedback as queue
from scholar_workflow.research.recommendations import context_files as disk
from scholar_workflow.research.recommendations.feedback import Feedback
from tests.contract.test_feedback_queue import fixture_pool


def pending_feedback(tmp_path):
    store, root, routes, candidate = fixture_pool(tmp_path, ("one",))
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    return store, root, routes["one"], Feedback(store).events()["items"][0]


def accepted(route, queue_id="receipt-1"):
    def runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, f"Queued message {queue_id} for thread {route['thread_id']}.\n", "")
    return runner


@pytest.mark.parametrize("outcome,expected,attempts", [
    ("timeout", "uncertain", 1), ("unknown", "uncertain", 1),
    ("wrong-thread", "uncertain", 1), ("failure", "pending", 2),
    ("missing", "pending", 2),
])
def test_acceptance_controls_automatic_retry(tmp_path, outcome, expected, attempts):
    store, _, _, _ = pending_feedback(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(args, 20)
        if outcome == "missing":
            raise FileNotFoundError(2, "not installed")
        if outcome == "failure":
            return subprocess.CompletedProcess(args, 1, "", "explicit failure")
        stdout = ("Queued message other for thread 00000000-0000-0000-0000-000000000000.\n"
                  if outcome == "wrong-thread" else "accepted maybe")
        return subprocess.CompletedProcess(args, 0, stdout, "")

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    feedback.flush()
    receipt = feedback.deliveries()["items"][0]
    assert receipt["status"] == expected
    assert receipt["attempts"] == attempts == len(calls)
    assert receipt["error"]


def test_crash_after_claim_stays_uncertain_and_is_not_retried(tmp_path):
    store, _, _, _ = pending_feedback(tmp_path)
    calls = []

    def crash(args, **kwargs):
        calls.append(args)
        raise RuntimeError("synthetic interruption")

    feedback = Feedback(store, runner=crash)
    with pytest.raises(RuntimeError, match="synthetic"):
        feedback.flush()
    feedback.flush()
    assert len(calls) == 1
    assert feedback.deliveries()["items"][0]["status"] == "uncertain"


def test_matching_queue_receipt_prevents_retry_after_nonzero_exit(tmp_path):
    store, _, route, _ = pending_feedback(tmp_path)
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        result = accepted(route, "accepted-before-failure")(args, **kwargs)
        result.returncode = 1
        return result

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert len(calls) == delivery["attempts"] == 1
    assert delivery["status"] == "queued"
    assert delivery["queue_message_id"] == "accepted-before-failure"
    assert "status 1" in delivery["error"]


def test_large_message_remains_pending_without_partial_payload(tmp_path, monkeypatch):
    store, _, _, event = pending_feedback(tmp_path)
    monkeypatch.setattr(queue, "MAX_MESSAGE_BYTES", 1)
    feedback = Feedback(store, runner=lambda *a, **k: pytest.fail("oversize must not be sent"))
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert delivery["status"] == "pending"
    assert delivery["attempts"] == 0
    assert "without truncation" in delivery["error"]
    assert feedback.events()["items"][0] == event


def test_explicit_native_enable_still_cannot_execute_test_profile(tmp_path, monkeypatch):
    store, _, _, _ = pending_feedback(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("test profile native process"))
    feedback = Feedback(store, native_enabled=True)
    feedback.flush()
    assert feedback.deliveries()["items"][0]["status"] == "pending"
    assert feedback.deliveries()["items"][0]["attempts"] == 0


def test_profile_mismatch_cannot_bypass_test_isolation(tmp_path, monkeypatch):
    store, _, route, _ = pending_feedback(tmp_path)
    route["profile"] = "personal"
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
        delivery = json.loads(db.execute("SELECT record FROM feedback_queue_receipts").fetchone()[0])
        delivery["route"] = route
        db.execute("UPDATE feedback_queue_receipts SET record=?", (json.dumps(delivery),))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("test pool native process"))
    feedback = Feedback(store, native_enabled=True)
    feedback.flush()
    assert "another active profile" in feedback.deliveries()["items"][0]["error"]
    assert feedback.deliveries()["items"][0]["attempts"] == 0


def test_changed_binding_does_not_redirect_existing_event(tmp_path):
    store, _, route, _ = pending_feedback(tmp_path)
    original = dict(route)
    route["revision"] += 1
    route["thread_id"] = "00000000-0000-0000-0000-000000000000"
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
    feedback = Feedback(store, runner=lambda *a, **k: pytest.fail("stale route must not send"))
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert delivery["status"] == "pending"
    assert delivery["route"] == original
    assert "binding changed" in delivery["error"]


def test_symlinked_context_is_not_sent_to_native_queue(tmp_path):
    store, root, route, _ = pending_feedback(tmp_path)
    context = root / route["context_file"]
    context.unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("outside context")
    context.symlink_to(outside)
    feedback = Feedback(store, runner=lambda *a, **k: pytest.fail("unsafe context must not send"))
    feedback.flush()
    assert feedback.deliveries()["items"][0]["status"] == "pending"
    assert feedback.deliveries()["items"][0]["error"]


@pytest.mark.parametrize("uncertain", [False, True])
def test_completion_checks_current_digest_and_keeps_curator_independent(tmp_path, uncertain):
    store, root, route, event = pending_feedback(tmp_path)
    runner = (lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "unknown", "")) if uncertain else accepted(route)
    feedback = Feedback(store, runner=runner)
    feedback.flush()
    with pytest.raises(ResearchError, match="current digest"):
        feedback.complete(event["event_id"], "one", "0" * 64, "Updated task context")
    context = root / route["context_file"]
    context.write_text("# Learned preference\n\nHuman prefers a narrower set.\n")
    digest = hashlib.sha256(context.read_bytes()).hexdigest()
    receipt = feedback.complete(event["event_id"], "one", digest, "Updated task context")
    assert receipt["status"] == "completed"
    assert feedback.complete(event["event_id"], "one", digest, "Updated task context") == receipt
    with pytest.raises(ResearchError, match="different receipt"):
        feedback.complete(event["event_id"], "one", digest, "A conflicting receipt")
    assert feedback.status()["curator_pending"] == 1
    assert len(feedback.batch()["items"]) == 1
    assert list(store.state_dir.glob("context/inbox/*.jsonl"))
    assert sorted(item.name for item in context.parent.iterdir()) == ["context.md", "recommended.md"]


def test_pending_and_foreign_producer_cannot_complete(tmp_path):
    store, root, route, event = pending_feedback(tmp_path)
    digest = hashlib.sha256((root / route["context_file"]).read_bytes()).hexdigest()
    feedback = Feedback(store)
    with pytest.raises(ResearchError, match="Only queued or uncertain"):
        feedback.complete(event["event_id"], "one", digest, "No delivery happened")
    with pytest.raises(ResearchError, match="No feedback delivery"):
        feedback.complete(event["event_id"], "foreign", digest, "Wrong producer")


def test_completed_during_enqueue_is_not_downgraded_to_queued(tmp_path):
    store, root, route, event = pending_feedback(tmp_path)
    digest = hashlib.sha256((root / route["context_file"]).read_bytes()).hexdigest()
    feedback = None

    def runner(args, **kwargs):
        feedback.complete(event["event_id"], "one", digest, "Context reviewed during delivery")
        return accepted(route)(args, **kwargs)

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    assert feedback.deliveries()["items"][0]["status"] == "completed"


def test_rebinding_after_enqueue_rejects_completion(tmp_path):
    store, root, route, event = pending_feedback(tmp_path)
    feedback = Feedback(store, runner=accepted(route))
    feedback.flush()
    route["revision"] += 1
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
    digest = hashlib.sha256((root / route["context_file"]).read_bytes()).hexdigest()
    with pytest.raises(ResearchError, match="binding changed"):
        feedback.complete(event["event_id"], "one", digest, "Changed binding")


def test_legacy_task_projection_is_retired_without_touching_old_files(tmp_path):
    store, root, route, candidate = fixture_pool(tmp_path, ("one",))
    route["schema_version"] = 1
    old = root / "feedback.jsonl"
    old.write_text("human retained legacy content\n")
    route["feedback_file"] = str(old.relative_to(root))
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    feedback = Feedback(store, runner=lambda *a, **k: pytest.fail("legacy route must never dispatch"))
    feedback.flush()
    assert feedback.deliveries()["items"] == []
    assert old.read_text() == "human retained legacy content\n"
    assert feedback.status()["curator_pending"] == 1


def test_multi_producer_feedback_dispatches_once_per_origin(tmp_path):
    store, _, routes, candidate = fixture_pool(tmp_path)
    store.save_evaluation(candidate["candidate_id"], 1, "Preserve verbatim feedback", 0, candidate["revision"])
    calls = []

    def runner(args, **kwargs):
        thread = args[args.index("--thread") + 1]
        message = args[args.index("--message") + 1]
        producer = next(key for key, route in routes.items() if route["thread_id"] == thread)
        assert f'"run_id": "run-{producer}"' in message
        other = "two" if producer == "one" else "one"
        assert f'"run_id": "run-{other}"' not in message
        assert "Preserve verbatim feedback" in message
        calls.append(thread)
        return accepted(routes[producer])(args, **kwargs)

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    feedback.flush()
    assert set(calls) == {route["thread_id"] for route in routes.values()}
    assert len(calls) == 2


def test_edited_human_tags_and_snapshot_identity_are_in_queue_payload(tmp_path):
    store, _, route, previous = pending_feedback(tmp_path)
    candidate = store.get_candidate(previous["candidate_id"])
    updated = store.edit_tags(candidate["candidate_id"], candidate["revision"], ["human-tag", "人工偏好"])
    feedback = Feedback(store)
    event = feedback.events()["items"][-1]
    message = queue.message_for(event, route)
    payload = json.loads(message[message.index("{\n"):])
    assert payload["human_feedback"]["kind"] == "tags"
    assert payload["human_feedback"]["tags"] == updated["tags"] == event["tags"]
    assert payload["candidate_revision"] == event["candidate_revision"]
    assert payload["resource_digest"] == event["resource_digest"]


def test_late_producer_baseline_keeps_original_snapshot_and_does_not_add_curator_vote(tmp_path):
    store, root, route, original_event = pending_feedback(tmp_path)
    route = dict(route, producer_id="two", title="two", thread_id=str(uuid.uuid4()))
    folder = root / ".agents/context/recommendations/two"
    folder.mkdir()
    for field, name in (("context_file", "context.md"), ("recommended_file", "recommended.md")):
        (folder / name).write_text("# Synthetic second producer\n")
        route[field] = str((folder / name).relative_to(root))
    with store._database(write=True, dispatch=False) as db:
        db.execute("INSERT INTO recommendation_tasks VALUES(?,?,?)", ("two", route["project_id"], json.dumps(route)))
    submission = store.submit({"schema_version": 1, "producer": {"producer_id": "two", "name": "two"},
                  "run_id": "later-run", "items": [{"submission_id": "later-item", "tags": ["two"], "resource": {
                      "kind": "blog", "title": "Shared synthetic source", "url": "https://example.org/source",
                      "summary_zh": "后加入来源的原始推荐说明", "summary_sources": ["https://example.org/source"]}}]})
    assert submission["status"] == "complete", submission
    feedback = Feedback(store)
    events = feedback.events()["items"]
    assert events[0] == original_event
    assert len(events) == 2
    assert events[1]["kind"] == "baseline"
    assert len(events[1]["recommendations"]) == 2
    assert feedback.status()["curator_pending"] == 1
    assert len(feedback.deliveries(producer_id="two")["items"]) == 1


def test_uncertain_retry_requires_review_and_only_restores_pending(tmp_path):
    store, _, route, event = pending_feedback(tmp_path)
    calls = []

    def unknown(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "acceptance unknown", "")

    feedback = Feedback(store, runner=unknown)
    feedback.flush()
    previous = feedback.deliveries()["items"][0]
    receipt = feedback.retry(event["event_id"], "one", 1, True)
    assert receipt["status"] == "pending"
    assert receipt["attempts"] == 1
    assert len(calls) == 1
    assert receipt["route"] == route
    assert receipt["retry_reviews"][-1]["confirmed_not_queued"] is True
    assert receipt["retry_reviews"][-1]["previous"] == {
        key: previous.get(key) for key in ("status", "attempts", "error", "updated_at", "queue_message_id")}
    assert receipt["retry_reviews"][-1]["reviewed_at"]
    assert feedback.events()["items"][0] == event
    assert feedback.status()["curator_pending"] == 1
    Feedback(store, runner=accepted(route)).flush()
    assert feedback.deliveries()["items"][0]["attempts"] == 2
    assert feedback.deliveries()["items"][0]["status"] == "queued"


@pytest.mark.parametrize("attempts,confirmed", [(1, False), (1, "true"), (True, True), (2, True)])
def test_uncertain_retry_rejects_unconfirmed_or_stale_review(tmp_path, attempts, confirmed):
    store, _, _, event = pending_feedback(tmp_path)
    feedback = Feedback(store, runner=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "unknown", ""))
    feedback.flush()
    before = feedback.deliveries()["items"][0]
    with pytest.raises(ResearchError):
        feedback.retry(event["event_id"], "one", attempts, confirmed)
    assert feedback.deliveries()["items"][0] == before


def test_uncertain_retry_rejects_changed_original_route(tmp_path):
    store, _, route, event = pending_feedback(tmp_path)
    feedback = Feedback(store, runner=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "unknown", ""))
    feedback.flush()
    route["revision"] += 1
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
    with pytest.raises(ResearchError, match="binding changed"):
        feedback.retry(event["event_id"], "one", 1, True)
    assert feedback.deliveries()["items"][0]["status"] == "uncertain"


def test_retry_cannot_reset_an_inflight_queue_attempt(tmp_path):
    store, _, route, event = pending_feedback(tmp_path)
    running, release, reviewing = threading.Event(), threading.Event(), threading.Event()

    def runner(args, **kwargs):
        running.set()
        assert release.wait(5)
        return accepted(route)(args, **kwargs)

    feedback = Feedback(store, runner=runner)

    def review():
        reviewing.set()
        return Feedback(store).retry(event["event_id"], "one", 1, True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        flush = executor.submit(feedback.flush)
        assert running.wait(5)
        retry = executor.submit(review)
        assert reviewing.wait(5)
        try:
            with pytest.raises(FutureTimeout):
                retry.result(timeout=0.1)
        finally:
            release.set()
        flush.result(timeout=5)
        with pytest.raises(ResearchError, match="Only uncertain"):
            retry.result(timeout=5)
    assert feedback.deliveries()["items"][0]["status"] == "queued"


def test_non_cli_pool_locator_is_explicit_and_native_dispatch_is_refused(tmp_path, monkeypatch):
    calls = []

    def blocked_native(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "", "synthetic refusal")

    monkeypatch.setattr(subprocess, "run", blocked_native)
    store, _, routes, candidate = fixture_pool(tmp_path, ("one",), state_dir=tmp_path / "custom/personal")
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    event = Feedback(store).events()["items"][0]
    message = queue.message_for(event, routes["one"])
    payload = json.loads(message[message.index("{\n"):])
    assert payload["pool_locator"] == {"state_dir": str(store.state_dir),
                                       "scholar_workflow_home": None, "cli_addressable": False}
    assert "No CLI feedback complete command" in message
    feedback = Feedback(store, native_enabled=True)
    feedback.flush()
    assert feedback.deliveries()["items"][0]["status"] == "pending"
    assert "CLI-addressable" in feedback.deliveries()["items"][0]["error"]
    assert calls == []


def test_start_records_a_separate_idempotent_receipt_without_completing(tmp_path):
    store, _, route, event = pending_feedback(tmp_path)
    feedback = Feedback(store, runner=accepted(route))
    feedback.flush()
    receipt = feedback.start(event["event_id"], "one")
    assert receipt["status"] == "queued"
    assert receipt["started_at"]
    assert "completed_at" not in receipt
    assert feedback.start(event["event_id"], "one") == receipt
    assert feedback.status()["curator_pending"] == 1


def test_started_receipt_survives_unknown_queue_result_and_prevents_retry(tmp_path):
    store, _, _, event = pending_feedback(tmp_path)
    feedback = None

    def runner(args, **kwargs):
        feedback.start(event["event_id"], "one")
        return subprocess.CompletedProcess(args, 0, "unknown acceptance", "")

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert delivery["status"] == "uncertain"
    assert delivery["started_at"]
    with pytest.raises(ResearchError, match="already started"):
        feedback.retry(event["event_id"], "one", 1, True)


def test_agent_start_prevents_retry_after_nonzero_queue_exit_without_receipt(tmp_path):
    store, _, _, event = pending_feedback(tmp_path)
    feedback, calls = None, []

    def runner(args, **kwargs):
        calls.append(args)
        feedback.start(event["event_id"], "one")
        return subprocess.CompletedProcess(args, 1, "", "synthetic failure after agent acceptance")

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert len(calls) == 1
    assert delivery["status"] == "uncertain"
    assert delivery["started_at"]
    assert "status 1" in delivery["error"]
    with pytest.raises(ResearchError, match="already started"):
        feedback.retry(event["event_id"], "one", 1, True)


def test_start_rejects_pending_or_changed_route(tmp_path):
    store, _, route, event = pending_feedback(tmp_path)
    feedback = Feedback(store, runner=accepted(route))
    with pytest.raises(ResearchError, match="Only queued or uncertain"):
        feedback.start(event["event_id"], "one")
    feedback.flush()
    route["revision"] += 1
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE recommendation_tasks SET record=? WHERE producer_id='one'", (json.dumps(route),))
    with pytest.raises(ResearchError, match="binding changed"):
        feedback.start(event["event_id"], "one")


def test_curator_projection_does_not_lose_concurrent_consumption_notification(tmp_path, monkeypatch):
    store, _, _, event = pending_feedback(tmp_path)
    feedback = Feedback(store)
    batch = feedback.batch()
    with store._database(write=True, dispatch=False) as db:
        db.execute("UPDATE feedback_deliveries SET delivered=0 WHERE recipient='curator'")
    original_flush, original_project = Feedback.flush, disk.project_jsonl
    consuming, consumed = False, False

    def no_recursive_projection(self):
        return self.status() if consuming else original_flush(self)

    def project_then_consume(*args, **kwargs):
        nonlocal consuming, consumed
        result = original_project(*args, **kwargs)
        if not consumed:
            consuming = True
            try:
                feedback.consume(batch["batch_id"], "Narrow the shared recommendation scope.", 0,
                                 {"kind": "agent", "name": "test-curator"})
                consumed = True
            finally:
                consuming = False
        return result

    monkeypatch.setattr(Feedback, "flush", no_recursive_projection)
    monkeypatch.setattr(disk, "project_jsonl", project_then_consume)
    feedback.flush()
    with store._database() as db:
        assert db.execute("SELECT delivered FROM feedback_deliveries WHERE recipient='curator'").fetchone()[0] == 0
    feedback.flush()
    assert not list(store.state_dir.glob("context/inbox/*.jsonl"))
    assert feedback.events()["items"] == [event]
    assert feedback.status()["curator_pending"] == 0


def test_native_runner_finds_standard_bin_with_minimal_background_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    lookups, calls = [], []

    def which(program, path=None):
        lookups.append((program, path))
        if path is None:
            return None
        assert path.split(os.pathsep) == [str(queue.Path.home() / ".local/bin"),
                                         "/opt/homebrew/bin", "/usr/local/bin"]
        return "/opt/homebrew/bin/codex"

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "synthetic receipt", "")

    monkeypatch.setattr(queue.shutil, "which", which)
    monkeypatch.setattr(subprocess, "run", run)
    args = ["codex", "queue", "--thread", "synthetic-thread", "--message", "synthetic message"]
    options = {"shell": False, "stdin": subprocess.DEVNULL, "capture_output": True,
               "text": True, "timeout": 20, "check": False}
    result = queue.native_runner(args, **options)
    assert result.returncode == 0
    assert calls == [(["/opt/homebrew/bin/codex", *args[1:]], options)]
    assert args[0] == "codex"
    assert lookups[0] == ("codex", None)


def test_native_runner_reports_missing_executable_without_starting_process(monkeypatch):
    monkeypatch.setattr(queue.shutil, "which", lambda *args, **kwargs: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("missing executable must not run"))
    with pytest.raises(FileNotFoundError) as caught:
        queue.native_runner(["codex", "queue"], shell=False)
    assert caught.value.errno == errno.ENOENT
