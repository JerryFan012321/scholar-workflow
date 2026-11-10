"""Review withdrawal is reversible local state, never Zotero deletion."""
from __future__ import annotations

import http.client
import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.server import create_server
from scholar_workflow.research.recommendations.store import RecommendationStore, _digest

TOKEN = "synthetic-review-exit-token-0123456789"


def selected(tmp_path, kind="paper"):
    store = RecommendationStore(tmp_path / "pool")
    resource = {"kind": kind, "title": "Synthetic review", "url": "https://example.org/review"}
    resource.update({"abstract_original": "Complete synthetic abstract.", "abstract_zh": "完整合成摘要。"}
                    if kind == "paper" else {"summary_zh": "有来源的合成总结。", "summary_sources": [resource["url"]]})
    receipt = store.submit({"schema_version": 1, "producer": {"producer_id": "test", "name": "Synthetic"},
                            "run_id": "one", "items": [{"submission_id": "one", "tags": [], "resource": resource}]})
    row = store.get_candidate(receipt["receipts"][0]["candidate_id"])
    row = store.review_candidate(row["candidate_id"], row["revision"])
    return store, store.set_decision(row["candidate_id"], "selected", row["revision"])


def plan(store, row):
    return store.create_ingestion_plan({"candidate_id": row["candidate_id"], "candidate_revision": row["revision"],
        "resource_digest": _digest(row["resource"]), "collection_key": "ABCD1234",
        "provider_identity": "synthetic", "collection_version": 1,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(), "metadata": {"title": "Synthetic"}})


@pytest.mark.parametrize("kind", ["paper", "blog"])
def test_review_can_be_withdrawn_and_confirmed_again_without_touching_content(tmp_path, kind):
    store, row = selected(tmp_path, kind)
    pending = plan(store, row)
    updated = store.revoke_review(row["candidate_id"], row["revision"])
    assert not updated["abstract_reviewed"] and updated["decision"] == "unread"
    assert updated["resource"] == row["resource"] and updated["recommendations"] == row["recommendations"]
    assert store.prepare_handoff()["items"] == []
    with pytest.raises(ResearchError):
        store.claim_ingestion_plan(pending["plan_id"])
    with pytest.raises(ResearchError):
        store.revoke_review(row["candidate_id"], row["revision"])
    confirmed = store.review_candidate(updated["candidate_id"], updated["revision"])
    assert confirmed["abstract_reviewed"] and confirmed["decision"] == "unread"


@pytest.mark.parametrize("decision", ["saved", "ignored"])
def test_withdrawal_keeps_other_explicit_decisions(tmp_path, decision):
    store, row = selected(tmp_path)
    row = store.set_decision(row["candidate_id"], decision, row["revision"])
    assert store.revoke_review(row["candidate_id"], row["revision"])["decision"] == decision


def test_active_write_is_protected_and_completed_receipt_is_retained(tmp_path):
    store, row = selected(tmp_path)
    pending = plan(store, row)
    store.claim_ingestion_plan(pending["plan_id"])
    with pytest.raises(ResearchError):
        store.revoke_review(row["candidate_id"], row["revision"])
    assert store.get_candidate(row["candidate_id"])["abstract_reviewed"]
    store.finish_ingestion_plan(pending["plan_id"], {"status": "completed", "item_key": "ITEM1234", "collection_key": "ABCD1234"})
    before = store.ingestion_history()
    updated = store.revoke_review(row["candidate_id"], row["revision"])
    assert not updated["abstract_reviewed"] and updated["ingestion"]["status"] == "completed"
    assert store.ingestion_history() == before


def test_http_revoke_requires_session_origin_and_current_revision(tmp_path):
    store, row = selected(tmp_path)
    service = create_server(store.state_dir, "test", TOKEN)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()

    def request(payload, token=TOKEN, origin=True):
        connection = http.client.HTTPConnection(*service.server_address, timeout=3)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{service.server_port}"
        connection.request("POST", "/api/reviews/revoke", json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    try:
        body = {"candidate_id": row["candidate_id"], "expected_revision": row["revision"]}
        assert request(body, token=None)[0] == 401
        assert request(body, origin=False)[0] == 403
        assert request({**body, "command": "not-an-executor"})[0] == 400
        status, result = request(body)
        assert status == 200 and not result["abstract_reviewed"] and result["decision"] == "unread"
        assert request(body)[0] == 409
    finally:
        service.shutdown()
        service.server_close()
        thread.join(3)
        assert not thread.is_alive()
