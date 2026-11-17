"""Central feedback stays durable while project context remains human-maintained."""
from __future__ import annotations

import json
import subprocess
import uuid

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.feedback import Feedback
from scholar_workflow.research.recommendations.project_tasks import ProjectTasks
from scholar_workflow.research.recommendations.ranking import RecommendationRanking
from scholar_workflow.research.recommendations.store import RecommendationStore


@pytest.fixture(autouse=True)
def no_native_processes(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Unit tests must not launch native processes")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    assert not calls, "Test-profile feedback attempted to launch a native process"


def submit(store, producer="task-one", *, item="paper"):
    result = store.submit({
        "schema_version": 1, "producer": {"producer_id": producer, "name": producer},
        "run_id": "run-" + item, "items": [{
            "submission_id": item, "tags": ["world-models"],
            "resource": {
                "kind": "paper", "title": "Synthetic paper", "authors": ["Example Author"],
                "arxiv_id": "2401.12345", "url": "https://arxiv.org/abs/2401.12345",
                "abstract_original": "The complete synthetic abstract explains the task, method and result.",
                "abstract_zh": "完整合成摘要说明任务、方法、结果及使用边界。",
            },
            "recommendation_reason": "Useful for this project's evaluation task.",
        }],
    })
    assert result["receipts"][0]["status"] == "accepted"
    return store.get_candidate(result["receipts"][0]["candidate_id"])


@pytest.fixture
def setup(tmp_path):
    store = RecommendationStore(tmp_path / "recommendations/test")
    tasks = ProjectTasks(store, "test")
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Human rules\n\nPreserve this original text.\n")
    one = tasks.bind(root, "task-one", "Evaluation papers", str(uuid.uuid4()))
    two = tasks.bind(root, "task-two", "World model progress", str(uuid.uuid4()))
    return store, tasks, root, one, two


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def project_documents(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_unprocessed_submission_creates_no_feedback_or_project_changes(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    submit(store)
    assert not Feedback(store).events()["items"]
    assert not list(store.state_dir.glob("context/inbox/*.jsonl"))
    assert project_documents(root) == before


def test_decision_records_central_feedback_without_rewriting_project_documents(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    updated = store.set_decision(row["candidate_id"], "saved", row["revision"])
    event = Feedback(store).events()["items"][0]
    daily = records(next(store.state_dir.glob("context/inbox/*.jsonl")))
    assert daily == [event]
    assert event["decision"] == "saved"
    assert event["summary"] == row["resource"]["abstract_zh"]
    assert event["processed_at"]
    assert updated["decision"] == "saved"
    assert project_documents(root) == before
    assert not list(root.rglob("feedback.jsonl"))
    assert not list(root.rglob("state.json"))


def test_one_human_event_can_address_two_tasks_without_counting_two_votes(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    submit(store, "task-two")
    row = store.get_candidate(row["candidate_id"])
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    feedback = Feedback(store)
    first = feedback.events(producer_id="task-one")["items"]
    second = feedback.events(producer_id="task-two")["items"]
    assert len(first) == len(second) == 1
    assert first[0]["event_id"] == second[0]["event_id"]
    assert {task["producer_id"] for task in first[0]["tasks"]} == {"task-one", "task-two"}
    assert feedback.status()["curator_pending"] == 1
    assert project_documents(root) == before


def test_late_task_attribution_gets_known_state_not_another_vote(setup):
    store, *_ = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    submit(store, "task-two")
    baseline = Feedback(store).events(producer_id="task-two")["items"][0]
    assert baseline["kind"] == "baseline"
    assert baseline["processed_at"] is None
    assert baseline["decision"] == "saved"
    assert Feedback(store).status()["curator_pending"] == 1


def test_quality_and_scoped_irrelevance_have_distinct_feedback(setup):
    store, *_ = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "ignored", row["revision"], "not_relevant", "My evaluation project")
    assert row["disposition"] == {"reason": "not_relevant", "scope": "My evaluation project"}
    row = store.set_decision(row["candidate_id"], "ignored", row["revision"], "not_relevant")
    assert row["disposition"] == {"reason": "not_relevant", "scope": "current_research"}
    row = store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    assert row["disposition"]["reason"] == "quality"
    row = store.set_decision(row["candidate_id"], "unread", row["revision"])
    assert row["disposition"] is None
    assert [item["decision"] for item in Feedback(store).events()["items"]] == [
        "ignored", "ignored", "ignored", "unread",
    ]


def test_evaluation_edits_clear_and_stale_revision_are_recorded(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    row = store.save_evaluation(row["candidate_id"], 5, "放入评测分类，暂时不分析。", 0, row["revision"])
    with pytest.raises(ResearchError):
        store.save_evaluation(row["candidate_id"], 1, "stale", 0, row["revision"])
    store.save_evaluation(row["candidate_id"], None, "", 1, row["revision"])
    events = Feedback(store).events()["items"]
    assert events[0]["evaluation"]["comment"] == "放入评测分类，暂时不分析。"
    assert events[0]["evaluation"]["score"] == 5
    assert events[1]["evaluation"]["score"] is None
    assert events[1]["evaluation"]["comment"] == ""
    assert project_documents(root) == before


def test_unavailable_project_never_rolls_back_a_human_decision(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    moved = root.with_name("temporarily-unavailable")
    root.rename(moved)
    saved = store.set_decision(row["candidate_id"], "saved", row["revision"])
    assert saved["decision"] == "saved"
    assert Feedback(store).events()["items"][0]["decision"] == "saved"
    moved.rename(root)
    feedback = Feedback(store, native_enabled=False)
    feedback.flush()
    feedback.flush()
    assert len(feedback.events()["items"]) == 1
    assert project_documents(root) == before


def test_curator_consumes_exact_batch_and_keeps_new_arrivals(setup):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "saved", row["revision"])
    feedback = Feedback(store)
    batch = feedback.batch()
    later = store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    payload = {"batch_id": batch["batch_id"], "content": "## Evaluation research\nPrefer reproducible evaluation evidence.\n",
               "expected_revision": 0, "updated_by": {"kind": "agent", "name": "curator"}}
    consumed = feedback.consume(**payload)
    assert consumed["status"] == "consumed"
    assert feedback.consume(**payload) == consumed
    assert feedback.status()["curator_pending"] == 1
    pending = records(next(store.state_dir.glob("context/inbox/*.jsonl")))
    assert len(pending) == 1 and pending[0]["decision"] == "ignored"
    assert (store.state_dir / "context/PREFERENCES.md").read_text() == payload["content"]
    assert later["decision"] == "ignored"
    assert len(feedback.events()["items"]) == 2
    assert project_documents(root) == before


def test_curator_revision_conflict_keeps_pending_files(setup):
    store, *_ = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    feedback = Feedback(store)
    batch = feedback.batch()
    RecommendationRanking(store).save_context("Another editor's preferences", 0, {"kind": "human", "name": "reader"})
    with pytest.raises(ResearchError):
        feedback.consume(batch["batch_id"], "stale", 0, {"kind": "agent", "name": "curator"})
    assert feedback.status()["curator_pending"] == 1
    assert list(store.state_dir.glob("context/inbox/*.jsonl"))


def test_last_consumed_daily_file_is_removed_but_history_stays(setup):
    store, *_ = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    feedback = Feedback(store)
    first, overlapping = feedback.batch(), feedback.batch()
    feedback.consume(first["batch_id"], "## Domain\nPreferences", 0, {"kind": "agent", "name": "curator"})
    assert not list(store.state_dir.glob("context/inbox/*.jsonl"))
    assert len(feedback.events()["items"]) == 1
    with pytest.raises(ResearchError):
        feedback.consume(overlapping["batch_id"], "Cannot consume it twice", 1, {"kind": "agent", "name": "curator"})


def test_task_guide_observes_human_document_edits_without_checkpoint(setup):
    _, tasks, root, one, _ = setup
    before = tasks.guide("task-one", include_context=True)
    context = root / one["context_file"]
    recommended = root / one["recommended_file"]
    context.write_text("# Research context\nOnly retain evaluations of closed-loop driving.\n")
    recommended.write_text("# Recommended\nAlready considered this work; keep its exact reason.\n")
    after = tasks.guide("task-one", include_context=True)
    assert after["context"] == context.read_text()
    assert after["recommended"] == recommended.read_text()
    assert after["context_revision"] != before["context_revision"]
    assert after["recommended_revision"] != before["recommended_revision"]
    assert "checkpoint" not in after
    assert not list(root.rglob("state.json"))


def test_task_event_pagination_is_scoped_and_uses_sequence_not_date(setup):
    store, *_ = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "saved", row["revision"])
    store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    first = Feedback(store).events(producer_id="task-one", limit=1)
    second = Feedback(store).events(producer_id="task-one", after=first["next_sequence"], limit=1,
                                    expected_pool=first["pool_id"])
    with pytest.raises(ResearchError):
        Feedback(store).events(producer_id="task-one", after=first["next_sequence"], limit=1,
                               expected_pool="another-pool")
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["event_id"] != second["items"][0]["event_id"]
    assert not Feedback(store).events(producer_id="task-two")["items"]


@pytest.mark.parametrize("reason", ["quality", "not_relevant", "other"])
def test_processed_reason_is_recorded_without_machine_project_files(setup, reason):
    store, _, root, *_ = setup
    before = project_documents(root)
    row = submit(store)
    store.set_decision(row["candidate_id"], "ignored", row["revision"], reason)
    task_record = Feedback(store).events(producer_id="task-one")["items"][-1]
    central = [record for path in (store.state_dir / "context/inbox").glob("*.jsonl") for record in records(path)]
    assert task_record["disposition"]["reason"] == reason
    assert central[-1]["event_id"] == task_record["event_id"]
    assert central[-1]["disposition"] == task_record["disposition"]
    assert project_documents(root) == before
