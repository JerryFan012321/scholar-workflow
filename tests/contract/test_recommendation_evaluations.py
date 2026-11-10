"""Human evaluations persist independently from recommendation and ingestion state."""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.server import create_server
from scholar_workflow.research.recommendations.store import RecommendationStore

TOKEN = "synthetic-evaluation-session-token-0123456789"


def submit(store, kind="paper", producer="one", summary="合成摘要"):
    resource = {"kind": kind, "title": "Synthetic evaluation", "url": "https://example.org/evaluation"}
    if kind == "paper":
        resource.update(abstract_original="Synthetic abstract.", abstract_zh=summary)
    else:
        resource.update(summary_zh=summary, summary_sources=[resource["url"]])
    receipt = store.submit({"schema_version": 1, "producer": {"producer_id": producer, "name": producer},
                            "run_id": "one", "items": [{"submission_id": "one", "tags": [], "resource": resource}]})
    return store.get_candidate(receipt["receipts"][0]["candidate_id"])


@pytest.mark.parametrize("kind", ["paper", "project", "blog"])
def test_save_edit_clear_and_reopen_without_changing_review_or_selection(tmp_path, kind):
    store = RecommendationStore(tmp_path / "pool")
    original = submit(store, kind)
    assert original["evaluation"]["revision"] == 0
    saved = store.save_evaluation(original["candidate_id"], 4, "方法有参考价值。\n需要关注成本。", 0, expected_candidate_revision=store.get_candidate(original["candidate_id"])["revision"])
    assert saved["evaluation"]["score"] == 4
    assert saved["evaluation"]["revision"] == 1
    assert saved["evaluation"]["matches_current_content"]
    assert saved["revision"] == original["revision"]
    assert saved["decision"] == original["decision"] and not saved["abstract_reviewed"]
    reopened = RecommendationStore(store.state_dir).get_candidate(original["candidate_id"])
    assert reopened == saved
    comment_only = store.save_evaluation(original["candidate_id"], None, "只记文字评价。", 1, expected_candidate_revision=store.get_candidate(original["candidate_id"])["revision"])
    assert comment_only["evaluation"]["score"] is None
    assert comment_only["evaluation"]["comment"] == "只记文字评价。"
    cleared = store.save_evaluation(original["candidate_id"], None, "", 2, expected_candidate_revision=store.get_candidate(original["candidate_id"])["revision"])
    assert cleared["evaluation"]["revision"] == 3
    assert cleared["evaluation"]["score"] is None and cleared["evaluation"]["comment"] == ""
    with pytest.raises(ResearchError, match="changed"):
        store.save_evaluation(original["candidate_id"], 5, "stale edit", 1, expected_candidate_revision=store.get_candidate(original["candidate_id"])["revision"])


def test_agent_resubmission_keeps_human_evaluation_and_marks_changed_content(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    row = submit(store)
    saved = store.save_evaluation(row["candidate_id"], 3, "个人判断", 0, expected_candidate_revision=store.get_candidate(row["candidate_id"])["revision"])
    same = submit(store, producer="two")
    assert same["evaluation"] == saved["evaluation"]
    changed = submit(store, producer="three", summary="已更新的合成摘要")
    assert changed["evaluation"]["score"] == 3 and changed["evaluation"]["comment"] == "个人判断"
    assert not changed["evaluation"]["matches_current_content"]
    assert store.list_candidates()["items"][0]["evaluation"] == changed["evaluation"]


def test_evaluation_of_old_content_cannot_be_bound_to_a_new_summary(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    original = submit(store)
    submit(store, producer="updated-agent", summary="新正文")
    with pytest.raises(ResearchError, match="changed"):
        store.save_evaluation(original["candidate_id"], 4, "针对旧正文的评价", 0,
                              expected_candidate_revision=original["revision"])
    assert store.get_candidate(original["candidate_id"])["evaluation"]["revision"] == 0


@pytest.mark.parametrize("score,comment,revision", [
    (0, "", 0), (6, "", 0), (True, "", 0), (2.5, "", 0), ("5", "", 0),
    (4, None, 0), (4, "x" * 4001, 0), (4, "bad\x00text", 0),
    (4, "", -1), (4, "", True), (4, "", "0"),
])
def test_invalid_evaluation_is_rejected_atomically(tmp_path, score, comment, revision):
    store = RecommendationStore(tmp_path / "pool")
    row = submit(store)
    with pytest.raises(ResearchError):
        store.save_evaluation(row["candidate_id"], score, comment, revision, expected_candidate_revision=store.get_candidate(row["candidate_id"])["revision"])
    assert store.get_candidate(row["candidate_id"]) == row


def test_evaluation_cas_is_independent_from_candidate_and_ingestion_revision(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    row = submit(store)
    reviewed = store.review_candidate(row["candidate_id"], row["revision"])
    saved = store.save_evaluation(row["candidate_id"], 5, "", 0, expected_candidate_revision=store.get_candidate(row["candidate_id"])["revision"])
    assert saved["revision"] == reviewed["revision"] and saved["abstract_reviewed"]
    selected = store.set_decision(row["candidate_id"], "selected", reviewed["revision"])
    assert selected["evaluation"] == saved["evaluation"]
    other = RecommendationStore(tmp_path / "different-pool")
    assert submit(other)["evaluation"]["revision"] == 0


def test_legacy_pool_reads_without_mutation_and_adds_evaluation_on_explicit_save(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    row = submit(store)
    with store._database(write=True) as database:
        database.execute("DROP TABLE IF EXISTS candidate_evaluations")
    path = store.state_dir / "recommendations.sqlite3"
    before = path.read_bytes()
    assert store.get_candidate(row["candidate_id"])["evaluation"]["revision"] == 0
    assert path.read_bytes() == before
    assert store.save_evaluation(row["candidate_id"], 2, "", 0, expected_candidate_revision=store.get_candidate(row["candidate_id"])["revision"])["evaluation"]["score"] == 2


def test_http_evaluation_requires_auth_origin_exact_fields_and_its_own_revision(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    row = submit(store)
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
        connection.request("POST", "/api/evaluations", json.dumps(payload), headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    try:
        body = {"candidate_id": row["candidate_id"], "score": 4, "comment": "个人评价", "expected_revision": 0, "expected_candidate_revision": row["revision"]}
        assert request(body, token=None)[0] == 401
        assert request(body, origin=False)[0] == 403
        assert request({**body, "command": "not-an-executor"})[0] == 400
        assert request({**body, "candidate_id": "candidate-" + "f" * 64})[0] == 400
        status, saved = request(body)
        assert status == 200 and saved["evaluation"]["score"] == 4
        assert request(body)[0] == 409
        assert request({**body, "score": None, "comment": "", "expected_revision": 1})[0] == 200
    finally:
        service.shutdown()
        service.server_close()
        thread.join(3)
        assert not thread.is_alive()
