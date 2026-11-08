"""Synthetic recommendation identities, submissions and human review boundaries."""
from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import (
    RecommendationStore,
    load_submission_schema,
)


def submission(producer="world-models", submission_id="item-1", **resource_changes):
    resource = {
        "kind": "paper", "title": "A synthetic paper",
        "url": "https://arxiv.org/abs/2601.12345v1", "arxiv_id": "2601.12345v1",
        "abstract_original": "A complete abstract. " * 40,
        "abstract_zh": "这是一段完整的合成摘要。" * 40,
    }
    resource.update(resource_changes)
    return {
        "schema_version": 1,
        "producer": {"producer_id": producer, "name": producer}, "run_id": "run-1",
        "items": [{"submission_id": submission_id, "resource": resource,
                   "tags": ["world-models"], "channels": [], "metrics": []}],
    }


def submit_in_process(root, producer):
    return RecommendationStore(root).submit(submission(producer))


def candidate(store, payload=None):
    result = store.submit(payload or submission())
    return store.get_candidate(result["receipts"][0]["candidate_id"])


def test_schema_is_packaged_and_strict():
    schema = load_submission_schema()
    assert schema["properties"]["schema_version"]["const"] == 1
    assert schema["additionalProperties"] is False


def test_latest_recommendation_sort_uses_recommendation_not_human_edits(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import store as module
    clock = iter(["2026-11-01T00:00:00+00:00", "2026-11-02T00:00:00+00:00",
                  "2026-11-03T00:00:00+00:00", "2026-11-04T00:00:00+00:00"])
    monkeypatch.setattr(module, "_now", lambda: next(clock))
    store = RecommendationStore(tmp_path / "state")
    first = candidate(store)
    second = candidate(store, submission(submission_id="other-paper", arxiv_id="2601.99999",
                                         url="https://arxiv.org/abs/2601.99999"))
    candidate(store, submission("another-agent"))
    store.set_decision(second["candidate_id"], "saved", second["revision"])
    assert store.list_candidates(sort="newest")["items"][0]["candidate_id"] == first["candidate_id"]


def test_duplicate_retry_is_idempotent_and_conflicting_retry_is_not_lost(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    payload = submission()
    first = store.submit(payload)
    assert first["receipts"][0]["status"] == "accepted"
    assert store.submit(payload)["receipts"][0]["status"] == "duplicate"
    changed = copy.deepcopy(payload)
    changed["items"][0]["resource"]["title"] = "Changed under the same submission"
    assert store.submit(changed)["receipts"][0]["status"] == "conflict"
    assert store.list_candidates()["total"] == 1


def test_cross_agent_arxiv_versions_share_one_candidate_and_complete_abstract(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    first = candidate(store)
    second = submission("3dgs", url="https://arxiv.org/pdf/2601.12345v2.pdf",
                        arxiv_id="2601.12345v2")
    second["items"][0]["tags"] = ["3dgs"]
    result = candidate(store, second)
    assert result["candidate_id"] == first["candidate_id"]
    assert len(result["recommendations"]) == 2
    assert len(result["resource"]["abstract_original"]) > 280
    assert store.list_candidates(producer_id="world-models", tag="3dgs")["total"] == 0
    assert store.list_candidates(producer_id="3dgs", tag="3dgs")["total"] == 1


def test_url_arxiv_identity_and_explicit_identifier_must_agree(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    invalid = submission(arxiv_id="2601.99999")
    assert store.submit(invalid)["receipts"][0]["status"] == "invalid"
    assert store.list_candidates()["total"] == 0


def test_types_remain_distinct_and_same_title_does_not_merge(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    for index, (kind, url) in enumerate([
        ("paper", "https://example.org/work"),
        ("project", "https://example.org/work"),
        ("blog", "https://example.org/work"),
        ("blog", "https://example.org/another"),
    ]):
        payload = submission(submission_id=f"item-{index}", kind=kind, url=url)
        payload["items"][0]["resource"].pop("arxiv_id")
        candidate(store, payload)
    assert store.list_candidates()["total"] == 4


def test_invalid_item_isolated_and_unsafe_url_refused(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    payload = submission()
    invalid = copy.deepcopy(payload["items"][0])
    invalid["submission_id"] = "bad"
    invalid["resource"]["project_url"] = "https://127.0.0.1/private"
    payload["items"].append(invalid)
    result = store.submit(payload)
    assert result["status"] == "partial"
    assert [row["status"] for row in result["receipts"]] == ["accepted", "invalid"]
    assert store.list_candidates()["total"] == 1


@pytest.mark.parametrize("extra", [{"unknown": 1}, {"schema_version": 2}])
def test_invalid_envelope_writes_nothing(tmp_path, extra):
    store = RecommendationStore(tmp_path / "state")
    payload = submission()
    payload.update(extra)
    with pytest.raises(ResearchError):
        store.submit(payload)
    assert not (tmp_path / "state").exists()


def test_decision_cas_and_refresh_preserve_human_state(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = candidate(store)
    selected = store.set_decision(row["candidate_id"], "selected", row["revision"])
    with pytest.raises(ResearchError) as error:
        store.set_decision(row["candidate_id"], "ignored", row["revision"])
    assert error.value.exit_code == 5
    refreshed = candidate(store, submission("another-agent"))
    assert refreshed["decision"] == "selected"
    assert refreshed["revision"] >= selected["revision"]


def test_review_binds_abstract_but_not_metric_refresh_and_handoff_gates(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = candidate(store)
    row = store.set_decision(row["candidate_id"], "selected", row["revision"])
    with pytest.raises(ResearchError):
        store.prepare_handoff()
    row = store.review_candidate(row["candidate_id"], row["revision"])
    assert row["abstract_reviewed"]
    metric_refresh = submission("another-agent")
    metric_refresh["items"][0]["metrics"] = [{
        "platform": "github", "metric": "stars", "value": 123,
        "url": "https://github.com/example/model", "observed_at": "2026-11-08T12:00:00Z",
    }]
    row = candidate(store, metric_refresh)
    assert row["abstract_reviewed"]
    assert store.prepare_handoff()["items"][0]["candidate_id"] == row["candidate_id"]
    row = candidate(store, submission("third-agent", abstract_zh="摘要内容已经改变。"))
    assert row["decision"] == "selected"
    assert not row["abstract_reviewed"]
    with pytest.raises(ResearchError):
        store.prepare_handoff()


def test_missing_translation_is_visible_and_cannot_be_reviewed(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    payload = submission()
    payload["items"][0]["resource"].pop("abstract_zh")
    row = candidate(store, payload)
    assert not row["abstract_reviewed"]
    with pytest.raises(ResearchError) as error:
        store.review_candidate(row["candidate_id"], row["revision"])
    assert error.value.exit_code == 7


def test_metadata_only_refresh_retains_abstract_and_changed_original_clears_stale_translation(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = candidate(store)
    row = store.review_candidate(row["candidate_id"], row["revision"])
    payload = submission("metadata-agent")
    del payload["items"][0]["resource"]["abstract_original"]
    del payload["items"][0]["resource"]["abstract_zh"]
    row = candidate(store, payload)
    assert row["abstract_reviewed"]
    payload = submission("new-original", abstract_original="A revised original abstract.")
    del payload["items"][0]["resource"]["abstract_zh"]
    row = candidate(store, payload)
    assert "abstract_zh" not in row["resource"]
    assert not row["abstract_reviewed"]


def test_date_filter_runs_before_pagination_and_unknown_dates_are_not_fabricated(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    candidate(store, submission(published_at="2026-11-01"))
    candidate(store, submission("second", submission_id="different", arxiv_id="2601.12346",
                                url="https://arxiv.org/abs/2601.12346", published_at="2026-11-08"))
    result = store.list_candidates(since="2026-11-07", limit=1)
    assert result["total"] == 1
    assert result["items"][0]["resource"]["published_at"] == "2026-11-08"


def test_late_older_version_keeps_newer_body_and_preserves_source_snapshot(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    latest = submission("latest", arxiv_id="2601.12345v3",
                        url="https://arxiv.org/abs/2601.12345v3",
                        abstract_original="The latest original.", abstract_zh="新版摘要。")
    row = candidate(store, latest)
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = candidate(store, submission("late-old-agent"))
    assert row["resource"]["abstract_zh"] == "新版摘要。"
    assert row["abstract_reviewed"]
    assert row["recommendations"][-1]["resource"]["arxiv_id"] == "2601.12345v1"


def test_unversioned_metadata_keeps_known_version_before_late_older_body(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    latest = submission("latest", arxiv_id="2601.12345v2",
                        url="https://arxiv.org/abs/2601.12345v2",
                        abstract_original="The version two original.", abstract_zh="第二版摘要。")
    row = candidate(store, latest)
    row = store.review_candidate(row["candidate_id"], row["revision"])
    metadata = submission("unversioned-metadata", arxiv_id="2601.12345",
                          url="https://arxiv.org/abs/2601.12345",
                          project_url="https://example.org/project")
    del metadata["items"][0]["resource"]["abstract_original"]
    del metadata["items"][0]["resource"]["abstract_zh"]
    row = candidate(store, metadata)
    assert row["resource"]["arxiv_id"] == "2601.12345v2"
    assert row["resource"]["url"] == latest["items"][0]["resource"]["url"]
    assert row["resource"]["project_url"] == "https://example.org/project"
    assert row["abstract_reviewed"]
    row = candidate(store, submission("late-version-one"))
    assert row["resource"]["arxiv_id"] == "2601.12345v2"
    assert row["resource"]["abstract_zh"] == "第二版摘要。"
    assert row["abstract_reviewed"]
    assert len(row["recommendations"]) == 3
    assert row["recommendations"][1]["resource"]["arxiv_id"] == "2601.12345"
    assert row["recommendations"][2]["resource"]["arxiv_id"] == "2601.12345v1"


def test_unversioned_body_cannot_replace_known_version_but_keeps_source_record(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = candidate(store, submission("latest", arxiv_id="2601.12345v2",
                                      url="https://arxiv.org/abs/2601.12345v2"))
    row = store.review_candidate(row["candidate_id"], row["revision"])
    previous_resource = row["resource"]
    row = candidate(store, submission("unclear-version", arxiv_id="2601.12345",
                                      url="https://arxiv.org/abs/2601.12345",
                                      abstract_original="A changed body without an identified version.",
                                      abstract_zh="未确认版本的另一段摘要。"))
    assert row["resource"] == previous_resource
    assert row["abstract_reviewed"]
    assert row["recommendations"][-1]["resource"]["abstract_zh"] == "未确认版本的另一段摘要。"


def test_explicit_url_version_is_not_lost_when_arxiv_field_has_base_id(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    row = candidate(store, submission("latest", arxiv_id="2601.12345v2",
                                      url="https://arxiv.org/abs/2601.12345v2"))
    row = store.review_candidate(row["candidate_id"], row["revision"])
    row = candidate(store, submission("version-three", arxiv_id="2601.12345",
                                      url="https://arxiv.org/abs/2601.12345v3",
                                      abstract_original="The identified version three abstract.",
                                      abstract_zh="有明确版本的第三版摘要。"))
    assert row["resource"]["arxiv_id"] == "2601.12345v3"
    assert row["resource"]["abstract_zh"] == "有明确版本的第三版摘要。"
    assert not row["abstract_reviewed"]


def test_multiple_processes_preserve_all_recommendations(tmp_path):
    state = tmp_path / "state"
    with ProcessPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(submit_in_process, [state] * 6, [f"agent-{n}" for n in range(6)]))
    assert all(row["receipts"][0]["status"] == "accepted" for row in results)
    store = RecommendationStore(state)
    assert store.list_candidates()["total"] == 1
    assert len(store.list_candidates()["items"][0]["recommendations"]) == 6


def test_private_state_and_symlink_refusal(tmp_path):
    state = tmp_path / "state"
    candidate(RecommendationStore(state))
    assert (state / "recommendations.sqlite3").stat().st_mode & 0o777 == 0o600
    other = tmp_path / "other"
    other.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(other, target_is_directory=True)
    with pytest.raises(ResearchError) as error:
        RecommendationStore(link).submit(submission())
    assert error.value.exit_code == 7
    assert not list(other.iterdir())


def test_metrics_are_raw_and_invalid_values_are_not_coerced(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    payload = submission()
    metric = {"platform": "github", "metric": "stars", "value": 0,
              "url": "https://github.com/example/model", "observed_at": "2026-11-08T12:00:00Z"}
    payload["items"][0]["metrics"] = [metric]
    row = candidate(store, payload)
    assert row["metrics"] == [metric]
    assert "score" not in row
    changed = submission("other-agent")
    changed["items"][0]["metrics"] = [dict(metric, value=True)]
    assert store.submit(changed)["receipts"][0]["status"] == "invalid"
