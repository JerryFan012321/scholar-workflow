"""Recommendation entrypoint with synthetic state and no personal integrations."""
from __future__ import annotations

import json

from click.testing import CliRunner

from scholar_workflow.research.runner import main


def batch():
    return {
        "schema_version": 1,
        "producer": {"producer_id": "world-models-daily", "name": "世界模型每日推荐"},
        "run_id": "run-one",
        "items": [{
            "submission_id": "paper-one",
            "resource": {"kind": "paper", "title": "Synthetic Paper",
                         "url": "https://arxiv.org/abs/2601.00001v2",
                         "abstract_original": "A complete synthetic abstract.",
                         "abstract_zh": "这是一段完整的合成摘要，用于验证推荐入口。"},
            "tags": ["世界模型"],
        }],
    }


def invoke(tmp_path, *args, input=None):
    return CliRunner().invoke(main, ["recommendations", *args], input=input,
                              env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "home")})


def test_schema_without_initializing_state(tmp_path):
    result = invoke(tmp_path, "schema")
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert schema["properties"]["schema_version"]["const"] == 1
    assert not (tmp_path / "home").exists()


def test_submit_stdin_replay_and_isolated_profiles(tmp_path):
    payload = json.dumps(batch(), ensure_ascii=False)
    first = invoke(tmp_path, "--profile", "test", "submit", "--input", "-", input=payload)
    assert first.exit_code == 0, first.output
    assert json.loads(first.output)["receipts"][0]["status"] == "accepted"
    second = invoke(tmp_path, "--profile", "test", "submit", "--input", "-", input=payload)
    assert second.exit_code == 0, second.output
    assert json.loads(second.output)["receipts"][0]["status"] == "duplicate"
    listed = invoke(tmp_path, "--profile", "test", "list", "--format", "json")
    assert json.loads(listed.output)["total"] == 1
    personal = invoke(tmp_path, "list", "--format", "json")
    assert json.loads(personal.output)["total"] == 0


def test_duplicate_keys_rejected_before_state(tmp_path):
    result = invoke(tmp_path, "--profile", "test", "submit", "--input", "-",
                    input='{"schema_version":1,"schema_version":1}')
    assert result.exit_code == 2, result.output
    assert not (tmp_path / "home").exists()


def test_status_and_stop_are_read_only_when_stopped(tmp_path):
    for command in ("status", "stop"):
        result = invoke(tmp_path, "--profile", "test", command)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["status"] == "stopped"
    assert not (tmp_path / "home").exists()


def test_handoff_empty_is_explicit(tmp_path):
    result = invoke(tmp_path, "--profile", "test", "handoff")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["items"] == []
    assert json.loads(result.output)["profile"] == "test"
    assert json.loads(result.output)["pool_id"].startswith("pool-")


def test_submission_identity_conflict_is_nonzero(tmp_path):
    payload = batch()
    original = invoke(tmp_path, "--profile", "test", "submit", "--input", "-",
                      input=json.dumps(payload))
    assert original.exit_code == 0, original.output
    payload["items"][0]["resource"]["title"] = "Conflicting title"
    result = invoke(tmp_path, "--profile", "test", "submit", "--input", "-",
                    input=json.dumps(payload))
    assert result.exit_code == 5, result.output


def test_symlink_spec_is_refused(tmp_path):
    target = tmp_path / "spec.json"
    target.write_text(json.dumps(batch()))
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    result = invoke(tmp_path, "--profile", "test", "submit", "--input", str(link))
    assert result.exit_code == 7, result.output


def test_owned_service_starts_reuses_and_stops_without_losing_candidates(tmp_path):
    submitted = invoke(tmp_path, "--profile", "test", "submit", "--input", "-",
                       input=json.dumps(batch()))
    assert submitted.exit_code == 0, submitted.output
    try:
        started = invoke(tmp_path, "--profile", "test", "start")
        assert started.exit_code == 0, started.output
        status = json.loads(started.output)
        assert status["status"] == "running"
        assert status["current_build"]
        reused = invoke(tmp_path, "--profile", "test", "start")
        assert reused.exit_code == 0, reused.output
        assert json.loads(reused.output)["pid"] == status["pid"]
        opened = invoke(tmp_path, "--profile", "test", "open", "--no-browser")
        assert opened.exit_code == 0, opened.output
        assert opened.output.strip() == f"http://127.0.0.1:{status['port']}/"
    finally:
        stopped = invoke(tmp_path, "--profile", "test", "stop")
    assert stopped.exit_code == 0, stopped.output
    assert json.loads(stopped.output)["status"] == "stopped"
    assert json.loads(invoke(tmp_path, "--profile", "test", "list", "--format", "json").output)["total"] == 1
    assert json.loads(invoke(tmp_path, "--profile", "test", "stop").output)["status"] == "stopped"


def test_refresh_metrics_uses_current_registered_candidate_without_resubmitting(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import cli as module
    original = invoke(tmp_path, "--profile", "test", "submit", "--input", "-", input=json.dumps(batch()))
    candidate_id = json.loads(original.output)["receipts"][0]["candidate_id"]
    calls = []
    def refresh(store, identifier, expected_revision=None):
        row = store.get_candidate(identifier); calls.append(identifier)
        return {**row, "metric_refresh": {"checks": []}}
    monkeypatch.setattr(module, "refresh_candidate_metrics", refresh)
    result = invoke(tmp_path, "--profile", "test", "refresh-metrics", "--candidate-id", candidate_id)
    assert result.exit_code == 0, result.output
    assert calls == [candidate_id]
    listing = json.loads(invoke(tmp_path, "--profile", "test", "list", "--format", "json").output)
    assert listing["total"] == 1 and len(listing["items"][0]["recommendations"]) == 1


def test_producer_and_curator_work_with_no_browser_or_http(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import lifecycle
    def forbidden(*args, **kwargs):
        raise AssertionError("Headless data operations must not start HTTP or a browser")
    monkeypatch.setattr(lifecycle, "start", forbidden)
    payload = batch()
    for producer in ["domain-agent", "project-agent"]:
        payload["producer"]["producer_id"] = producer
        result = invoke(tmp_path, "--profile", "test", "submit", "--input", "-", input=json.dumps(payload))
        assert result.exit_code == 0, result.output
    snapshot = invoke(tmp_path, "--profile", "test", "context", "snapshot")
    assert snapshot.exit_code == 0, snapshot.output
    result = invoke(tmp_path, "--profile", "test", "context", "save", "--input", "-", input=json.dumps({
        "content":"Synthetic curator context", "expected_revision":0,
        "updated_by":{"kind":"agent", "name":"curator"}}))
    assert result.exit_code == 0, result.output
    assert json.loads(invoke(tmp_path, "--profile", "test", "list", "--format", "json").output)["total"] == 1
    assert json.loads(invoke(tmp_path, "--profile", "test", "status").output)["status"] == "stopped"
