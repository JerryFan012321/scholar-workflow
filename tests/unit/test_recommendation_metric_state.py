"""Independent synthetic expectations for metric observations and reviewed summaries."""
from __future__ import annotations

import copy
import pytest
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import RecommendationStore


def payload(kind="paper", **extra):
    return {"schema_version": 1, "producer": {"producer_id": "fixture", "name": "Fixture"},
            "run_id": "fixture-run", "items": [{"submission_id": "fixture-item", "tags": ["synthetic"],
             "resource": {"kind": kind, "title": "Synthetic source", "url": "https://example.org/work",
                          **extra}}]}


def add(store, data):
    result = store.submit(data)
    assert result["receipts"][0]["status"] == "accepted", result
    return store.get_candidate(result["receipts"][0]["candidate_id"])


def observation(value=42, status="ok", time="2026-11-08T01:00:00+00:00"):
    base = {"platform": "github", "metric": "stars", "url": "https://github.com/example/model"}
    return {"observations": [{**base, "value": value, "observed_at": time}] if status == "ok" else [],
            "checks": [{**base, "status": status, "checked_at": time}]}


def test_old_candidate_metric_refresh_preserves_choice_review_and_recommendations(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = add(store, payload(abstract_original="Original abstract.", abstract_zh="完整的合成摘要。",
                             project_url="https://github.com/example/model"))
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    before = copy.deepcopy(row)
    result = store.record_metric_refresh(row["candidate_id"], row["revision"], observation(0))
    assert result["metrics"][0]["value"] == 0
    assert result["abstract_reviewed"] and result["decision"] == "selected"
    assert result["resource"] == before["resource"]
    assert result["recommendations"] == before["recommendations"]
    assert result["revision"] == before["revision"]
    assert RecommendationStore(tmp_path / "state").get_candidate(row["candidate_id"])["metrics"] == result["metrics"]


def test_failure_and_old_observation_do_not_erase_latest_success(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = add(store, payload(project_url="https://github.com/example/model"))
    store.record_metric_refresh(row["candidate_id"], row["revision"], observation(25))
    store.record_metric_refresh(row["candidate_id"], row["revision"], observation(2, time="2026-11-07T01:00:00+00:00"))
    result = store.record_metric_refresh(row["candidate_id"], row["revision"], observation(status="rate_limited", time="2026-11-09T01:00:00+00:00"))
    assert result["metrics"][0]["value"] == 25
    assert result["metric_refresh"]["checks"][0]["status"] == "rate_limited"
    assert result["metrics"][0]["observed_at"] == "2026-11-08T01:00:00+00:00"


def test_metric_refresh_rejects_stale_revision_and_undeclared_target(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = add(store, payload(project_url="https://github.com/example/model"))
    changed = store.set_decision(row["candidate_id"], "saved", row["revision"])
    with pytest.raises(ResearchError):
        store.record_metric_refresh(row["candidate_id"], row["revision"], observation())
    wrong = observation(); wrong["observations"][0]["url"] = "https://github.com/other/model"
    with pytest.raises(ResearchError):
        store.record_metric_refresh(row["candidate_id"], changed["revision"], wrong)
    assert not store.get_candidate(row["candidate_id"])["metrics"]


@pytest.mark.parametrize("kind", ["paper", "project", "blog"])
def test_sourced_summary_is_explicit_and_review_binds_current_text(tmp_path, kind):
    store = RecommendationStore(tmp_path / "state")
    data = payload(kind, summary_zh="这是根据实际正文整理的合成资料总结。", summary_sources=["https://example.org/work"],
                   links=[{"kind": "blog", "label": "Official research blog", "url": "https://example.org/blog"}])
    row = add(store, data)
    assert row["reading_kind"] == "summary" and row["review_required"] and row["review_available"]
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    with pytest.raises(ResearchError): store.prepare_handoff()
    row = store.review_candidate(row["candidate_id"], row["revision"])
    assert store.prepare_handoff()["items"][0]["abstract_reviewed"]
    data["producer"]["producer_id"] = "another"; data["items"][0]["resource"]["summary_zh"] = "正文已更新，因此总结也已改变。"
    result = store.submit(data)
    assert result["receipts"][0]["status"] == "accepted"
    row = store.get_candidate(row["candidate_id"])
    assert not row["abstract_reviewed"] and row["decision"] == "selected"
    assert row["resource"]["links"][0]["kind"] == "blog"


def test_summary_requires_valid_sources_and_cannot_bypass_missing_abstract_translation(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    result = store.submit(payload(summary_zh="无来源的总结。"))
    assert result["receipts"][0]["status"] == "invalid"
    row = add(store, payload(abstract_original="Author abstract exists.", summary_zh="不能代替译文。",
                             summary_sources=["https://example.org/work"]))
    assert not row["review_available"]
    with pytest.raises(ResearchError): store.review_candidate(row["candidate_id"], row["revision"])


def test_explicit_nonpaper_summary_is_shown_without_discarding_source_excerpt(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = add(store, payload("blog", description_original="Actual source introduction.", description_zh="原文简介译文。",
                             summary_zh="不应替换已有原文。", summary_sources=["https://example.org/work"]))
    assert row["reading_kind"] == "summary" and row["review_required"]
    assert row["resource"]["description_original"] == "Actual source introduction."
