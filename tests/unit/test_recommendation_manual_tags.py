"""Manual tags preserve producer attribution and exact-record filtering."""
import copy

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.store import RecommendationStore


def payload(producer="a", tags=None):
    return {"schema_version": 1, "producer": {"producer_id": producer, "name": producer},
            "run_id": producer, "items": [{"submission_id": producer, "tags": tags or ["代码世界模型"],
                "resource": {"kind": "paper", "title": "Synthetic paper", "url": "https://arxiv.org/abs/2501.00001"}}]}


def seed(tmp_path):
    store = RecommendationStore(tmp_path / "pool")
    result = store.submit(payload())
    return store, store.get_candidate(result["receipts"][0]["candidate_id"])


def test_edit_persist_and_reset_preserve_originals(tmp_path):
    store, row = seed(tmp_path)
    original = copy.deepcopy(row["recommendations"])
    edited = store.edit_tags(row["candidate_id"], row["revision"], [" 场景编排 ", "场景编排"])
    assert edited["tags"] == ["场景编排"]
    assert edited["recommendations"] == original
    assert edited["resource"] == row["resource"] and edited["decision"] == row["decision"]
    assert RecommendationStore(store.state_dir).get_candidate(row["candidate_id"])["tags"] == ["场景编排"]
    assert store.list_candidates(tag="代码世界模型")["total"] == 0
    assert store.list_candidates(tag="场景编排", producer_id="a")["total"] == 1
    assert store.edit_tags(row["candidate_id"], edited["revision"], ["场景编排"])["revision"] == edited["revision"]
    with pytest.raises(ResearchError):
        store.edit_tags(row["candidate_id"], row["revision"], [])
    restored = store.edit_tags(row["candidate_id"], edited["revision"], reset=True)
    assert restored["tags"] == ["代码世界模型"] and restored["recommendations"] == original


def test_later_agent_cannot_restore_removed_tag_or_cross_join(tmp_path):
    store, row = seed(tmp_path)
    store.edit_tags(row["candidate_id"], row["revision"], [])
    store.submit(payload("b", ["代码世界模型", "多模态基础模型"]))
    latest = store.get_candidate(row["candidate_id"])
    assert latest["tags"] == ["多模态基础模型"]
    assert store.list_candidates(tag="多模态基础模型", producer_id="a")["total"] == 0
    assert store.list_candidates(tag="多模态基础模型", producer_id="b")["total"] == 1
    assert len(latest["recommendations"]) == 2


@pytest.mark.parametrize("tags", [None, "text", [""], ["x" * 121], [42], ["api_key=secret-value-here"]])
def test_invalid_tag_updates_do_not_write(tmp_path, tags):
    store, row = seed(tmp_path)
    with pytest.raises(ResearchError):
        store.edit_tags(row["candidate_id"], row["revision"], tags)
    assert store.get_candidate(row["candidate_id"]) == row


def test_authenticated_tag_http_route(tmp_path):
    import http.client
    import json
    import threading
    from scholar_workflow.research.recommendations.server import create_server
    store, row = seed(tmp_path)
    token = "synthetic-tag-token-" + "a" * 32
    server = create_server(store.state_dir, "test", token)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_port
        connection = http.client.HTTPConnection("127.0.0.1", port)
        body = json.dumps({"candidate_id": row["candidate_id"], "expected_revision": row["revision"], "tags": ["场景编排"]})
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}", "Authorization": f"Bearer {token}"}
        connection.request("POST", "/api/tags", body, headers)
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["tags"] == ["场景编排"]
        connection.close()
        connection = http.client.HTTPConnection("127.0.0.1", port)
        headers.pop("Authorization")
        connection.request("POST", "/api/tags", body, headers)
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        connection.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_tag_cli_uses_same_profile_and_revision(tmp_path, monkeypatch):
    import json
    from click.testing import CliRunner
    from scholar_workflow.research.runner import main
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    def call(*args, body=None):
        result = runner.invoke(main, ["recommendations", "--profile", "test", *args],
                               input=json.dumps(body) if body is not None else None)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)
    receipt = call("submit", "--input", "-", body=payload())
    candidate_id = receipt["receipts"][0]["candidate_id"]
    edited = call("tags", "set", "--input", "-", body={
        "candidate_id": candidate_id, "expected_revision": 1, "tags": ["场景编排"]})
    assert edited["tags"] == ["场景编排"]
    restored = call("tags", "reset", candidate_id, "--expected-revision", str(edited["revision"]))
    assert restored["tags"] == ["代码世界模型"]
