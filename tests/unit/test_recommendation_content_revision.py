"""Content corrections have a local history without fabricating recommendations."""
from __future__ import annotations

import copy
import json

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import (
    RecommendationStore,
    _digest,
    reading_kind,
)

ACTOR = {"kind": "agent", "name": "Synthetic content editor"}


def seeded(tmp_path, kind="blog", abstract=False):
    store = RecommendationStore(tmp_path / "pool")
    resource = {"kind": kind, "title": "Synthetic work", "url": "https://example.org/work",
                "description_original": "A short source excerpt.", "description_zh": "原来的合成摘句。",
                "links": [{"label": "Code", "url": "https://example.org/code"}]}
    if abstract:
        resource.update(abstract_original="A complete synthetic author abstract.", abstract_zh="完整的合成作者摘要。")
    payload = {"schema_version": 1, "producer": {"producer_id": "first-agent", "name": "First producer"},
               "run_id": "first-run", "items": [{"submission_id": "work", "resource": resource,
                                                   "tags": ["synthetic"]}]}
    receipt = store.submit(payload)
    return store, store.get_candidate(receipt["receipts"][0]["candidate_id"])


def summary_changes():
    return {"description_original": None, "description_zh": None,
            "summary_zh": "根据实际原文整理的合成简介，方法与结果均由输入事实支持。",
            "summary_sources": ["https://example.org/work"]}


def revise(store, row, changes=None, actor=None, revision=None):
    return store.revise_content(row["candidate_id"], row["revision"] if revision is None else revision,
                                summary_changes() if changes is None else changes, ACTOR if actor is None else actor)


def test_correction_preserves_recommendations_and_records_before_after(tmp_path):
    store, row = seeded(tmp_path)
    result = revise(store, row)
    after = result["candidate"]
    assert result["status"] == "updated" and after["revision"] == row["revision"] + 1
    assert after["recommendations"] == row["recommendations"]
    assert after["producers"] == row["producers"] and after["tags"] == row["tags"]
    assert after["resource"]["links"] == row["resource"]["links"]
    assert "description_zh" not in after["resource"]
    assert after["reading_kind"] == "summary" and after["review_required"] and after["review_available"]
    assert store.list_candidates()["total"] == 1
    history = RecommendationStore(store.state_dir).content_revision_history(row["candidate_id"])
    assert history["candidate_id"] == row["candidate_id"] and len(history["items"]) == 1
    record = history["items"][0]
    assert record == result["revision_record"]
    assert record["updated_by"] == ACTOR and record["updated_at"]
    assert record["before"]["resource"] == row["resource"]
    assert record["after"]["resource"] == after["resource"]
    assert record["changes"] == summary_changes()


def test_unchanged_content_does_not_increment_revision_or_history(tmp_path):
    store, row = seeded(tmp_path, abstract=True)
    result = revise(store, row, {"abstract_zh": row["resource"]["abstract_zh"]})
    assert result == {"status": "unchanged", "candidate": row, "revision_record": None}
    assert store.content_revision_history(row["candidate_id"])["items"] == []
    assert store.get_candidate(row["candidate_id"]) == row


@pytest.mark.parametrize("decision", ["selected", "saved", "ignored", "unread"])
def test_content_change_clears_review_and_only_pending_selection(tmp_path, decision):
    store, row = seeded(tmp_path, abstract=True)
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = store.set_decision(row["candidate_id"], decision, row["revision"])
    store.save_evaluation(row["candidate_id"], 4, "Saved human evaluation", 0, row["revision"])
    before = store.get_candidate(row["candidate_id"])
    result = revise(store, before, {"abstract_zh": "修订后的完整合成摘要。"})
    after = result["candidate"]
    assert not after["abstract_reviewed"]
    assert after["decision"] == ("unread" if decision == "selected" else decision)
    assert after["evaluation"]["score"] == 4 and after["evaluation"]["comment"] == "Saved human evaluation"
    assert after["evaluation"]["revision"] == before["evaluation"]["revision"]
    assert not after["evaluation"]["matches_current_content"]
    assert result["revision_record"]["before"]["abstract_reviewed"]
    assert not result["revision_record"]["after"]["abstract_reviewed"]


def test_completed_ingestion_receipt_is_retained_and_marked_old(tmp_path):
    store, row = seeded(tmp_path, abstract=True)
    record = {"plan_id": "synthetic-plan", "status": "completed", "resource_digest": _digest(row["resource"]),
              "receipt": {"item_key": "ITEM1234"}}
    with store._database(write=True) as database:
        database.execute("INSERT INTO ingestion_plans VALUES(?,?,?)",
                         (record["plan_id"], row["candidate_id"], json.dumps(record)))
    before = store.get_candidate(row["candidate_id"])
    assert before["ingestion"]["matches_current_content"]
    after = revise(store, before)["candidate"]
    assert after["ingestion"]["status"] == "completed"
    assert after["ingestion"]["receipt"] == record["receipt"]
    assert not after["ingestion"]["matches_current_content"]


def test_active_ingestion_refuses_even_noop_content_edit(tmp_path):
    store, row = seeded(tmp_path, abstract=True)
    with store._database(write=True) as database:
        database.execute("INSERT INTO ingestion_plans VALUES(?,?,?)",
                         ("synthetic-plan", row["candidate_id"], '{"status":"in_progress"}'))
    for changes in [summary_changes(), {"abstract_zh": row["resource"]["abstract_zh"]}]:
        with pytest.raises(ResearchError) as error:
            revise(store, row, changes)
        assert error.value.exit_code == 5
    assert store.content_revision_history(row["candidate_id"])["items"] == []


def test_stale_revision_refuses_before_any_correction(tmp_path):
    store, row = seeded(tmp_path)
    revise(store, row)
    with pytest.raises(ResearchError) as error:
        revise(store, row)
    assert error.value.exit_code == 5
    assert len(store.content_revision_history(row["candidate_id"])["items"]) == 1


@pytest.mark.parametrize("changes", [{}, {"title":"New title"}, {"url":"https://example.org/other"},
    {"kind":"paper"}, {"decision":"selected"}, {"evaluation":{"score":5}},
    {"summary_zh":"Unsupported summary"}, {"summary_sources":["https://example.org/work"]},
    {"description_original":"Only another excerpt", "description_zh":"仍只是摘句。"},
    {"summary_zh":"Text", "summary_sources":["file:///private/secret"]},
    {"summary_zh":"Text", "summary_sources":["http://127.0.0.1:1/"]},
    {"summary_zh":"   ", "summary_sources":["https://example.org/work"]}])
def test_rejects_out_of_scope_or_incomplete_content(tmp_path, changes):
    store, row = seeded(tmp_path)
    with pytest.raises(ResearchError):
        revise(store, row, changes)
    assert store.get_candidate(row["candidate_id"]) == row
    assert store.content_revision_history(row["candidate_id"])["items"] == []


@pytest.mark.parametrize("actor", [{}, {"kind":"unknown","name":"Editor"},
    {"kind":"agent","name":""}, {"kind":"agent","name":"Editor","token":"secret"}, {"kind":[],"name":"Editor"}])
def test_actor_is_explicit_nonsecret_and_bounded(tmp_path, actor):
    store, row = seeded(tmp_path)
    with pytest.raises(ResearchError):
        revise(store, row, actor=actor)
    assert store.get_candidate(row["candidate_id"]) == row


@pytest.mark.parametrize("kind", ["paper", "project", "blog"])
def test_author_abstract_is_preferred_for_every_resource_kind(tmp_path, kind):
    store, row = seeded(tmp_path, kind=kind)
    row = revise(store, row, {"abstract_original":"A complete author abstract.",
                             "abstract_zh":"完整的作者摘要。", **summary_changes()})["candidate"]
    assert row["reading_kind"] == "abstract" and row["review_available"] and row["review_required"]
    row = store.review_candidate(row["candidate_id"], row["revision"])
    assert row["abstract_reviewed"]
    reopened = RecommendationStore(store.state_dir).get_candidate(row["candidate_id"])
    assert reopened["abstract_reviewed"]
    untranslatable = copy.deepcopy(row["resource"])
    untranslatable.pop("abstract_zh")
    assert reading_kind(untranslatable) == "unavailable"
    with pytest.raises(ResearchError):
        revise(store, row, {"abstract_original":"Changed author abstract without a new translation."})
    assert store.get_candidate(row["candidate_id"]) == row
