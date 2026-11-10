"""The installed-style CLI edits reading content, never resubmits a recommendation."""
from __future__ import annotations

import json

from click.testing import CliRunner

from scholar_workflow.research.runner import main


def call(tmp_path, *args, payload=None):
    return CliRunner().invoke(main, ["recommendations", "--profile", "test", *args],
        input=json.dumps(payload) if payload is not None else None,
        env={"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "state")})


def seeded(tmp_path):
    result = call(tmp_path, "submit", "--input", "-", payload={
        "schema_version":1, "producer":{"producer_id":"producer","name":"Synthetic producer"},
        "run_id":"one", "items":[{"submission_id":"one","tags":["synthetic"],
        "resource":{"kind":"blog","title":"Original synthetic work","url":"https://example.org/work",
                    "description_original":"A teaser.","description_zh":"摘句。"}}]})
    assert result.exit_code == 0, result.output
    key = json.loads(result.output)["receipts"][0]["candidate_id"]
    return {"candidate_id":key,"expected_revision":1,"updated_by":{"kind":"agent","name":"Editor"},
            "changes":{"summary_zh":"根据已核实正文整理的合成简介。","summary_sources":["https://example.org/work"],
                       "description_original":None,"description_zh":None}}


def test_revise_and_read_history_work_without_browser_or_http(tmp_path, monkeypatch):
    from scholar_workflow.research.recommendations import lifecycle
    def forbidden(*args, **kwargs):
        raise AssertionError("Content correction must not launch a service")
    monkeypatch.setattr(lifecycle, "start", forbidden)
    payload = seeded(tmp_path)
    result = call(tmp_path, "revise-content", "--input", "-", payload=payload)
    assert result.exit_code == 0, result.output
    updated = json.loads(result.output)
    assert updated["status"] == "updated"
    assert len(updated["candidate"]["recommendations"]) == 1
    history = call(tmp_path, "content-history", "--candidate-id", payload["candidate_id"])
    assert history.exit_code == 0, history.output
    record = json.loads(history.output)["items"][0]
    assert record["updated_by"] == payload["updated_by"]
    assert record["before"]["resource"]["description_zh"] == "摘句。"
    assert record["after"]["resource"]["summary_zh"] == payload["changes"]["summary_zh"]
    assert call(tmp_path, "revise-content", "--input", "-", payload=payload).exit_code == 5
    payload["expected_revision"] = 2
    repeated = call(tmp_path, "revise-content", "--input", "-", payload=payload)
    assert repeated.exit_code == 0 and json.loads(repeated.output)["status"] == "unchanged"
    assert len(json.loads(call(tmp_path, "content-history", "--candidate-id", payload["candidate_id"]).output)["items"]) == 1
    listing = json.loads(call(tmp_path, "list", "--format", "json").output)
    assert listing["total"] == 1 and len(listing["items"][0]["recommendations"]) == 1
    assert json.loads(call(tmp_path, "status").output)["status"] == "stopped"


def test_content_revision_cli_refuses_unknown_top_fields_without_state(tmp_path):
    result = call(tmp_path, "revise-content", "--input", "-", payload={"command":"whoami"})
    assert result.exit_code == 2
    assert not (tmp_path / "state").exists()


def test_content_revision_cannot_change_identity_or_human_choices(tmp_path):
    payload = seeded(tmp_path)
    payload["changes"]["decision"] = "selected"
    result = call(tmp_path, "revise-content", "--input", "-", payload=payload)
    assert result.exit_code == 2
    history = call(tmp_path, "content-history", "--candidate-id", payload["candidate_id"])
    assert history.exit_code == 0 and json.loads(history.output)["items"] == []
