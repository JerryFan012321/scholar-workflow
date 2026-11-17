"""Feedback delivery contracts use synthetic records and never invoke native Codex."""
from __future__ import annotations

import json
import shlex
import subprocess
import uuid

from scholar_workflow.research.recommendations.feedback import Feedback
from scholar_workflow.research.recommendations.project_tasks import pool_id
from scholar_workflow.research.recommendations.store import RecommendationStore


PREFIX = "这是用户对你的推荐的反馈，请你根据条目和对应的反馈优化你的推荐上下文，但不需要你马上推荐，推荐任务仍然由定时任务触发："


def fixture_pool(tmp_path, producers=("one", "two"), *, state_dir=None):
    store = RecommendationStore(state_dir or tmp_path / "test")
    root = tmp_path / "project"
    root.mkdir()
    project_id = str(uuid.uuid4())
    routes = {}
    with store._database(write=True, dispatch=False) as db:
        for producer in producers:
            folder = root / ".agents/context/recommendations" / producer
            folder.mkdir(parents=True)
            (folder / "context.md").write_text("# Human context\n")
            (folder / "recommended.md").write_text("# Recommended\n")
            route = {"schema_version": 2, "producer_id": producer, "project_id": project_id,
                     "project_title": "Synthetic project", "title": producer,
                     "project_root": str(root), "context_file": str((folder / "context.md").relative_to(root)),
                     "recommended_file": str((folder / "recommended.md").relative_to(root)),
                     "thread_id": str(uuid.uuid4()), "host": "local", "profile": store.profile,
                     "pool_id": pool_id(store), "revision": 1}
            routes[producer] = route
            db.execute("INSERT INTO recommendation_tasks VALUES(?,?,?)",
                       (producer, project_id, json.dumps(route)))
    for producer in producers:
        receipt = store.submit({"schema_version": 1, "producer": {"producer_id": producer, "name": producer},
                                "run_id": "run-" + producer, "items": [{"submission_id": "submission-" + producer,
                                "tags": [producer], "resource": {"kind": "blog", "title": "Shared synthetic source",
                                "url": "https://example.org/source", "summary_zh": "原始推荐说明：" + producer,
                                "summary_sources": ["https://example.org/source"]}}]})
        candidate_id = receipt["receipts"][0]["candidate_id"]
    return store, root, routes, store.get_candidate(candidate_id)


def test_human_feedback_snapshots_all_origins_and_keeps_curator_independent(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("native Codex")))
    store, root, routes, candidate = fixture_pool(tmp_path)
    store.save_evaluation(candidate["candidate_id"], 2, "原话：请少推荐这一类；不要立即推荐。", 0, candidate["revision"])
    feedback = Feedback(store)
    event = feedback.events()["items"][0]
    assert event["evaluation"]["comment"] == "原话：请少推荐这一类；不要立即推荐。"
    assert event["resource"]["url"] == candidate["resource"]["url"]
    assert {r["producer"]["producer_id"] for r in event["recommendations"]} == set(routes)
    assert {r["run_id"] for r in event["recommendations"]} == {"run-one", "run-two"}
    assert feedback.status()["curator_pending"] == 1
    assert list(store.state_dir.glob("context/inbox/*.jsonl"))
    assert sorted(p.name for p in (root / ".agents/context/recommendations/one").iterdir()) == ["context.md", "recommended.md"]
    assert {r["status"] for r in feedback.deliveries()["items"]} == {"pending"}


def test_feedback_message_locates_exact_cli_pool_and_quotes_home(tmp_path):
    home = tmp_path / "home with spaces and 'quotes' $literal"
    store, _, routes, candidate = fixture_pool(tmp_path, ("one",), state_dir=home / "recommendations/test")
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    calls = []

    def runner(args, **kwargs):
        message = args[args.index("--message") + 1]
        calls.append(message)
        return subprocess.CompletedProcess(args, 0, "Queued message located for thread " + routes["one"]["thread_id"] + ".\n", "")

    Feedback(store, runner=runner).flush()
    message = calls[0]
    payload = json.loads(message[message.index("{\n"):])
    assert payload["pool_locator"] == {"state_dir": str(store.state_dir),
                                       "scholar_workflow_home": str(home), "cli_addressable": True}
    assert "env SCHOLAR_WORKFLOW_HOME=" + shlex.quote(str(home)) + " scholar-research" in message
    assert "feedback complete --input -" in message
    assert "feedback start --input -" in message
    assert Feedback(store).events()["items"][0]["pool_state_dir"] == str(store.state_dir)


def test_queue_uses_original_route_and_does_not_resubmit_on_repeated_flush(tmp_path):
    store, _, routes, candidate = fixture_pool(tmp_path, ("one",))
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    calls = []

    def runner(args, **kwargs):
        # A database read during the subprocess proves delivery does not retain its lock.
        with store._database() as db:
            assert db.execute("SELECT count(*) FROM feedback_events").fetchone()[0] == 1
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "Queued message queue-1 for thread " + routes["one"]["thread_id"] + ".\n", "")

    feedback = Feedback(store, runner=runner)
    feedback.flush()
    feedback.flush()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[:2] == ["codex", "queue"]
    assert args[args.index("--thread") + 1] == routes["one"]["thread_id"]
    message = args[args.index("--message") + 1]
    assert message.startswith(PREFIX + "\n")
    assert str((tmp_path / "project" / routes["one"]["context_file"])) in message
    assert "feedback complete" in message
    assert "推荐任务仍然由定时任务触发" in message
    assert kwargs["shell"] is False
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert feedback.deliveries()["items"][0]["status"] == "queued"
    assert feedback.status()["curator_pending"] == 1
