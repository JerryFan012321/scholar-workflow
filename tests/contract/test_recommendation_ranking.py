"""External agents share context and return order; the application runs no model."""
from __future__ import annotations

import copy
import http.client
import json
import threading

import pytest
from click.testing import CliRunner

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.cli import recommendations
from scholar_workflow.research.recommendations.ranking import RecommendationRanking
from scholar_workflow.research.recommendations.server import create_server
from scholar_workflow.research.recommendations.store import RecommendationStore


def fixture(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    receipt = store.submit({"schema_version": 1, "producer": {"producer_id": "specialist", "name": "Synthetic agent"},
        "run_id": "first", "items": [
            {"submission_id": name, "tags": ["synthetic"], "recommendation_reason": "有助于比较数据条件。",
             "resource": {"kind": "blog", "title": name, "url": "https://example.org/" + name,
                          "project_url": "https://github.com/example/synthetic",
                          "summary_zh": "合成总结", "summary_sources": ["https://example.org/" + name]},
             "metrics": [{"platform": "github", "metric": "stars", "value": 10,
                          "url": "https://github.com/example/synthetic", "observed_at": "2026-11-10T00:00:00Z"}]}
            for name in ["first", "second"]]})
    assert receipt["status"] == "complete"
    return store, RecommendationRanking(store), [r["candidate_id"] for r in receipt["receipts"]]


def ranking_payload(service, ids, run_id="ranking-one"):
    snapshot = service.snapshot()
    return {"schema_version": 1, "producer": {"producer_id": "curator", "name": "Synthetic external agent"},
        "run_id": run_id, "context_digest": snapshot["context_digest"],
        "expected_revision": snapshot["ranking"]["revision"], "rationale": "合成测试，优先比较当前问题。",
        "items": [{"candidate_id": key, "reason": "合成排序理由，不表示科学质量结论。"} for key in ids]}


def test_snapshot_assembles_live_facts_and_context_does_not_duplicate_them(tmp_path):
    store, service, ids = fixture(tmp_path)
    assert service.context()["context"]["content"] == ""
    before = service.snapshot()
    assert before["candidates"][0]["recommendations"][0]["recommendation_reason"] == "有助于比较数据条件。"
    store.save_evaluation(ids[0], 4, "人类的合成评价", 0, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    assert service.snapshot()["context_digest"] != before["context_digest"]
    saved = service.save_context("当前关注成本；这些是合成输入。", 0, {"kind": "agent", "name": "curator"})
    assert saved["context"]["revision"] == 1 and saved["candidate_count"] == 2
    with pytest.raises(ResearchError):
        service.save_context("stale overwrite", 0, {"kind": "human", "name": "Synthetic"})
    reopened = RecommendationRanking(RecommendationStore(store.state_dir))
    assert reopened.context()["context"] == saved["context"]
    assert reopened.snapshot()["candidates"][0]["evaluation"]["score"] in {4, None}


def test_ranking_preserves_content_membership_and_supports_idempotent_retry(tmp_path):
    store, service, ids = fixture(tmp_path)
    before = {r["candidate_id"]: r for r in store.list_candidates()["items"]}
    payload = ranking_payload(service, ids[::-1])
    receipt = service.submit(payload)
    assert receipt["status"] == "accepted" and receipt["revision"] == 1
    listed = store.list_candidates(sort="agent")
    assert listed["ranking"]["status"] == "current"
    assert [r["candidate_id"] for r in listed["items"]] == ids[::-1]
    for row in listed["items"]:
        for field in ("resource", "revision", "decision", "abstract_reviewed", "recommendations", "evaluation"):
            assert row[field] == before[row["candidate_id"]][field]
    store.save_evaluation(ids[0], 1, "之后的新判断", 0, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    assert service.submit(payload)["status"] == "duplicate"
    assert store.list_candidates(sort="agent")["ranking"]["status"] == "stale"
    assert len(service.history()["items"]) == 1
    with pytest.raises(ResearchError):
        service.submit({**payload, "rationale": "same run conflicting input"})


@pytest.mark.parametrize("change", ["feedback", "metric", "content", "context", "requirement"])
def test_input_changes_reject_stale_agent_result(tmp_path, change):
    store, service, ids = fixture(tmp_path)
    payload = ranking_payload(service, ids)
    if change == "feedback":
        store.save_evaluation(ids[0], 2, "new", 0, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    elif change == "metric":
        row = store.get_candidate(ids[0])
        store.record_metric_refresh(ids[0], row["revision"], {"observations": [], "checks": [
            {"platform": "github", "metric": "stars", "url": "https://github.com/example/synthetic",
             "status": "unavailable", "checked_at": "2026-11-10T01:00:00Z"}]})
    elif change == "content":
        row = store.get_candidate(ids[0])
        store.set_decision(ids[0], "saved", row["revision"])
    elif change == "context":
        service.save_context("new focus", 0, {"kind": "human", "name": "Synthetic"})
    else:
        store.save_requirement("synthetic-requirement", "Synthetic", "Current source requirements", True, 0,
                               {"kind": "human", "name": "Synthetic"})
    with pytest.raises(ResearchError, match="changed"):
        service.submit(payload)
    assert service.context()["ranking"]["status"] == "empty"


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "missing", "extra", "false_revision"])
def test_invalid_order_or_fields_cannot_remove_candidates(tmp_path, mutation):
    store, service, ids = fixture(tmp_path)
    payload = ranking_payload(service, ids)
    if mutation == "unknown":
        payload["items"][0]["candidate_id"] = "candidate-" + "f" * 64
    elif mutation == "duplicate":
        payload["items"][1] = copy.deepcopy(payload["items"][0])
    elif mutation == "missing":
        payload["items"].pop()
    elif mutation == "extra":
        payload["shell"] = "not-an-executor"
    else:
        payload["expected_revision"] = True
    with pytest.raises(ResearchError):
        service.submit(payload)
    assert store.list_candidates()["total"] == 2


def test_known_evaluation_history_is_preserved_for_context_without_inventing_older_data(tmp_path):
    store, service, ids = fixture(tmp_path)
    store.save_evaluation(ids[0], 4, "first judgment", 0, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    store.save_evaluation(ids[0], 2, "revised judgment", 1, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    store.save_evaluation(ids[0], None, "", 2, expected_candidate_revision=store.get_candidate(ids[0])["revision"])
    row = next(r for r in service.snapshot()["candidates"] if r["candidate_id"] == ids[0])
    assert [r["score"] for r in row["evaluation_history"]] == [4, 2, None]
    assert row["evaluation"]["score"] is None


def test_cli_exposes_context_and_ranking_without_provider_or_agent_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
    store = RecommendationStore(tmp_path / "recommendations/test")
    receipt = store.submit({"schema_version": 1, "producer": {"producer_id": "one", "name": "Synthetic"},
        "run_id": "one", "items": [{"submission_id": "one", "tags": [], "resource": {
            "kind": "blog", "title": "Synthetic", "url": "https://example.org/cli"}}]})
    runner = CliRunner()
    result = runner.invoke(recommendations, ["--profile", "test", "context", "snapshot"])
    assert result.exit_code == 0, result.output
    snapshot = json.loads(result.output)
    payload = ranking_payload(RecommendationRanking(store), [receipt["receipts"][0]["candidate_id"]])
    assert payload["context_digest"] == snapshot["context_digest"]
    result = runner.invoke(recommendations, ["--profile", "test", "ranking", "submit", "--input", "-"], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "accepted"


def test_http_context_editor_auth_cas_and_agent_sort_share_cli_store(tmp_path):
    store, ranking, ids = fixture(tmp_path)
    token = "synthetic-ranking-context-session-0123456789"
    server = create_server(store.state_dir, "test", token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(method, path, payload=None, authenticated=True):
        connection = http.client.HTTPConnection(*server.server_address, timeout=3)
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        connection.request(method, path, None if payload is None else json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    try:
        assert request("GET", "/api/ranking/context", authenticated=False)[0] == 401
        assert request("GET", "/api/ranking/context")[1]["context"]["revision"] == 0
        payload = {"content": "真实记录之外的合成测试关注点", "expected_revision": 0}
        assert request("POST", "/api/ranking/context", {**payload, "command": "not-an-executor"})[0] == 400
        assert request("POST", "/api/ranking/context", payload)[0] == 200
        assert request("POST", "/api/ranking/context", payload)[0] == 409
        assert ranking.context()["context"]["updated_by"]["kind"] == "human"
        ranking.submit(ranking_payload(ranking, ids[::-1]))
        status, listed = request("GET", "/api/candidates?sort=agent")
        assert status == 200 and [r["candidate_id"] for r in listed["items"]] == ids[::-1]
        assert listed["ranking"]["status"] == "current"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()
