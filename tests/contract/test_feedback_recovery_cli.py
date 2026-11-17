"""Explicit queue recovery never invokes a native process in the test profile."""
from __future__ import annotations

import json
import subprocess

import pytest
from click.testing import CliRunner

from scholar_workflow.research.recommendations.cli import recommendations
from scholar_workflow.research.recommendations.feedback import Feedback
from tests.contract.test_feedback_queue import fixture_pool


@pytest.fixture
def uncertain_delivery(tmp_path, monkeypatch):
    home = tmp_path / "home"
    base = home / "recommendations"
    base.mkdir(parents=True)
    store, root, routes, candidate = fixture_pool(base, ("one",))
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    store.set_decision(candidate["candidate_id"], "saved", candidate["revision"])
    feedback = Feedback(store, runner=lambda args, **kwargs:
                        subprocess.CompletedProcess(args, 0, "unknown acceptance", ""))
    feedback.flush()
    delivery = feedback.deliveries()["items"][0]
    assert delivery["status"] == "uncertain"
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        pytest.fail("Recovery CLI must not invoke a real Codex chat"))
    return feedback, delivery


def retry(runner, payload):
    return runner.invoke(recommendations, ["--profile", "test", "feedback", "retry", "--input", "-"],
                         input=json.dumps(payload))


def test_reviewed_uncertain_recovery_is_pending_until_sync(uncertain_delivery):
    feedback, delivery = uncertain_delivery
    payload = {"event_id": delivery["event_id"], "producer_id": "one",
               "expected_attempts": delivery["attempts"], "confirmed_not_queued": True}
    result = retry(CliRunner(), payload)
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "pending"
    assert receipt["attempts"] == delivery["attempts"]
    assert feedback.status()["curator_pending"] == 1
    # The same review must not revive a newer attempt or clear its history.
    repeated = retry(CliRunner(), payload)
    assert repeated.exit_code in {0, 5}, repeated.output
    assert feedback.deliveries()["items"][0]["attempts"] == delivery["attempts"]


def test_started_receipt_is_idempotent_and_blocks_not_queued_retry(uncertain_delivery):
    feedback, delivery = uncertain_delivery
    payload = {"event_id": delivery["event_id"], "producer_id": "one"}
    runner = CliRunner()
    args = ["--profile", "test", "feedback", "start", "--input", "-"]
    result = runner.invoke(recommendations, args, input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    started = json.loads(result.output)
    assert started["started_at"]
    assert started["status"] == "uncertain"
    repeated = runner.invoke(recommendations, args, input=json.dumps(payload))
    assert repeated.exit_code == 0, repeated.output
    assert json.loads(repeated.output)["started_at"] == started["started_at"]
    retry_result = retry(runner, {**payload, "expected_attempts": delivery["attempts"],
                                 "confirmed_not_queued": True})
    assert retry_result.exit_code == 5, retry_result.output
    assert feedback.status()["curator_pending"] == 1


@pytest.mark.parametrize("changes", [
    {"confirmed_not_queued": False}, {"confirmed_not_queued": "true"},
    {"expected_attempts": 0}, {"unexpected": "not allowed"},
])
def test_retry_rejects_unreviewed_or_stale_requests(uncertain_delivery, changes):
    feedback, delivery = uncertain_delivery
    payload = {"event_id": delivery["event_id"], "producer_id": "one",
               "expected_attempts": delivery["attempts"], "confirmed_not_queued": True, **changes}
    result = retry(CliRunner(), payload)
    assert result.exit_code in {2, 5}, result.output
    assert feedback.deliveries()["items"][0] == delivery
