"""Behavioral checks for project task isolation and code-only human feedback delivery."""
from __future__ import annotations

import json
import uuid

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.feedback import Feedback
from scholar_workflow.research.recommendations.project_tasks import ProjectTasks
from scholar_workflow.research.recommendations.ranking import RecommendationRanking
from scholar_workflow.research.recommendations.store import RecommendationStore


def project(path):
    path.mkdir()
    identifier = str(uuid.uuid4())
    (path / "project-layout.json").write_text(json.dumps({"schema_version": 2, "project_id": identifier}))
    (path / "AGENTS.md").write_text("# Human rules\n\nPreserve this original text.\n")
    return identifier


def submit(store, producer="task-one", *, title="Synthetic paper", item="paper", kind="paper"):
    resource = {"kind": kind, "title": title, "url": "https://example.org/" + item,
                "authors": ["Example Author"]}
    if kind == "paper":
        resource.update(arxiv_id="2401.12345", url="https://arxiv.org/abs/2401.12345",
                        abstract_original="The complete synthetic abstract explains the task, method and result.",
                        abstract_zh="完整合成摘要说明任务、方法、结果及使用边界。")
    else:
        resource.update(summary_zh="这份合成资料介绍研究任务、采用的方案与已公开结果，并说明尚未披露的细节。",
                        summary_sources=[resource["url"]])
    result = store.submit({"schema_version": 1, "producer": {"producer_id": producer, "name": producer},
                           "run_id": "run-" + item, "items": [{"submission_id": item, "tags": ["world-models"],
                                                               "resource": resource, "recommendation_reason": "Useful for this project's evaluation task."}]})
    assert result["receipts"][0]["status"] == "accepted"
    return store.get_candidate(result["receipts"][0]["candidate_id"])


@pytest.fixture
def setup(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    tasks = ProjectTasks(store, "test")
    root = tmp_path / "project"
    project_id = project(root)
    tasks.enable(root)
    one = tasks.register(project_id, "task-one", "Evaluation papers")
    two = tasks.register(project_id, "task-two", "World model progress")
    return store, tasks, root, project_id, one, two


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_enable_preserves_human_rules_and_discovers_multiple_equal_tasks(setup):
    store, tasks, root, project_id, *_ = setup
    before = (root / "AGENTS.md").read_bytes()
    tasks.enable(root)
    assert (root / "AGENTS.md").read_bytes() == before
    assert before.startswith(b"# Human rules\n\nPreserve this original text.\n")
    assert len(tasks.list(project_id)["tasks"]) == 2
    assert "context" not in tasks.guide("task-one")
    assert "context" in tasks.guide("task-one", include_context=True)
    assert not Feedback(store).events()["items"]


def test_unprocessed_submission_creates_no_feedback(setup):
    store, _, root, _, one, _ = setup
    submit(store)
    assert not Feedback(store).events()["items"]
    assert not (root / one["feedback_file"]).exists()
    assert not list(store.state_dir.glob("context/inbox/*.jsonl"))


def test_decision_writes_project_and_daily_files_without_agent(setup):
    store, _, root, _, one, two = setup
    row = submit(store)
    updated = store.set_decision(row["candidate_id"], "saved", row["revision"])
    delivered = records(root / one["feedback_file"])
    daily = records(next(store.state_dir.glob("context/inbox/*.jsonl")))
    assert delivered == daily
    assert delivered[0]["decision"] == "saved"
    assert delivered[0]["summary"] == row["resource"]["abstract_zh"]
    assert delivered[0]["processed_at"]
    assert not (root / two["feedback_file"]).exists()
    assert updated["decision"] == "saved"
    assert not Feedback(store).status()["pending_deliveries"]


def test_one_human_event_is_delivered_to_two_tasks_but_not_counted_twice(setup):
    store, _, root, _, one, two = setup
    row = submit(store)
    submit(store, "task-two")
    row = store.get_candidate(row["candidate_id"])
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    first, second = records(root / one["feedback_file"]), records(root / two["feedback_file"])
    assert len(first) == len(second) == 1
    assert first[0]["event_id"] == second[0]["event_id"]
    assert Feedback(store).status()["curator_pending"] == 1


def test_late_task_attribution_gets_known_state_not_another_vote(setup):
    store, _, root, _, _, two = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    submit(store, "task-two")
    baseline = records(root / two["feedback_file"])[0]
    assert baseline["kind"] == "baseline"
    assert baseline["processed_at"] is None
    assert baseline["decision"] == "saved"
    assert Feedback(store).status()["curator_pending"] == 1


def test_quality_and_scoped_irrelevance_have_distinct_feedback(setup):
    store, *_ = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "ignored", row["revision"], "not_relevant", "My evaluation project")
    assert row["disposition"] == {"reason": "not_relevant", "scope": "My evaluation project"}
    with pytest.raises(ResearchError):
        store.set_decision(row["candidate_id"], "ignored", row["revision"], "not_relevant")
    row = store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    assert row["disposition"]["reason"] == "quality"
    row = store.set_decision(row["candidate_id"], "unread", row["revision"])
    assert row["disposition"] is None
    assert [i["decision"] for i in Feedback(store).events()["items"]] == ["ignored", "ignored", "unread"]


def test_evaluation_edits_clear_and_stale_revision_are_recorded(setup):
    store, _, root, _, one, _ = setup
    row = submit(store)
    row = store.save_evaluation(row["candidate_id"], 5, "放入评测分类，暂时不分析。", 0, row["revision"])
    with pytest.raises(ResearchError):
        store.save_evaluation(row["candidate_id"], 1, "stale", 0, row["revision"])
    store.save_evaluation(row["candidate_id"], None, "", 1, row["revision"])
    feedback = records(root / one["feedback_file"])
    assert feedback[0]["evaluation"]["comment"] == "放入评测分类，暂时不分析。"
    assert feedback[0]["evaluation"]["score"] == 5
    assert feedback[1]["evaluation"]["score"] is None
    assert feedback[1]["evaluation"]["comment"] == ""


def test_unavailable_project_preserves_decision_and_retries_idempotently(setup):
    store, _, root, _, one, _ = setup
    row = submit(store)
    moved = root.with_name("temporarily-unavailable")
    root.rename(moved)
    saved = store.set_decision(row["candidate_id"], "saved", row["revision"])
    assert saved["decision"] == "saved"
    assert Feedback(store).status()["pending_deliveries"]
    moved.rename(root)
    assert not Feedback(store).flush()["pending_deliveries"]
    Feedback(store).flush()
    assert len(records(root / one["feedback_file"])) == 1


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "edited", "nonobject"])
def test_feedback_projection_never_overwrites_unsafe_or_edited_file(setup, tmp_path, attack):
    store, _, root, _, one, _ = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "saved", row["revision"])
    target = root / one["feedback_file"]
    other = tmp_path / "outside.txt"
    other.write_text("human original")
    if attack == "symlink":
        target.unlink(); target.symlink_to(other)
    elif attack == "hardlink":
        target.unlink(); target.hardlink_to(other)
    elif attack == "nonobject":
        target.write_text("42\n")
    else:
        target.write_text('{"event_id":"unknown","human":"keep"}\n')
    store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    assert other.read_text() == "human original"
    assert Feedback(store).status()["pending_deliveries"]
    if attack == "edited":
        assert "keep" in target.read_text()


def test_profile_or_cross_project_task_rebinding_is_rejected(setup, tmp_path):
    store, tasks, root, _, *_ = setup
    with pytest.raises(ResearchError):
        ProjectTasks(RecommendationStore(tmp_path / "other-pool"), "personal").enable(root)
    second = tmp_path / "second-project"
    second_id = project(second)
    tasks.enable(second)
    with pytest.raises(ResearchError):
        tasks.register(second_id, "task-one", "Wrong project", expected_revision=1)


def test_enable_does_not_shadow_existing_legacy_human_rules(tmp_path):
    root = tmp_path / "legacy"
    project(root)
    (root / "AGENTS.md").rename(root / "AGENT.md")
    tasks = ProjectTasks(RecommendationStore(tmp_path / "state"), "test")
    with pytest.raises(ResearchError):
        tasks.enable(root)
    assert not (root / "AGENTS.md").exists()
    assert not (root / ".agents/context/recommendations").exists()
    assert "Preserve this original text." in (root / "AGENT.md").read_text()


def test_curator_consumes_exact_batch_and_keeps_new_arrivals(setup):
    store, _, root, _, one, _ = setup
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
    assert len(records(root / one["feedback_file"])) == 2
    assert (store.state_dir / "context/PREFERENCES.md").read_text() == payload["content"]
    assert later["decision"] == "ignored"
    assert len(feedback.events()["items"]) == 2


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


def test_task_context_save_is_revision_checked_and_separate_from_delivery(setup):
    store, tasks, _, _, *_ = setup
    row = submit(store)
    store.set_decision(row["candidate_id"], "saved", row["revision"])
    guide = tasks.guide("task-one", include_context=True)
    event_id = Feedback(store).events(producer_id="task-one")["items"][0]["event_id"]
    assert guide["checkpoint"]["consumed_event_ids"] == []
    result = tasks.save_context("task-one", "# Task\nRefined project requirements.\n", guide["context_revision"], [event_id])
    assert result["checkpoint"]["consumed_event_ids"] == [event_id]
    with pytest.raises(ResearchError):
        tasks.save_context("task-one", "stale", guide["context_revision"], [])
    wrong = tasks.guide("task-two", include_context=True)
    with pytest.raises(ResearchError):
        tasks.save_context("task-two", "wrong", wrong["context_revision"], [event_id])


def test_task_event_pagination_is_scoped_and_uses_sequence_not_date(setup):
    store, *_ = setup
    row = submit(store)
    row = store.set_decision(row["candidate_id"], "saved", row["revision"])
    store.set_decision(row["candidate_id"], "ignored", row["revision"], "quality")
    first = Feedback(store).events(producer_id="task-one", limit=1)
    second = Feedback(store).events(producer_id="task-one", after=first["next_sequence"], limit=1, expected_pool=first["pool_id"])
    with pytest.raises(ResearchError):
        Feedback(store).events(producer_id="task-one", after=first["next_sequence"], limit=1, expected_pool="another-pool")
    assert first["has_more"] and not second["has_more"]
    assert first["items"][0]["event_id"] != second["items"][0]["event_id"]
    assert not Feedback(store).events(producer_id="task-two")["items"]
