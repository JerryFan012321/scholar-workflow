"""Public task binding and central feedback contracts, without native services."""
from __future__ import annotations

import json
import subprocess
import uuid

import pytest
from click.testing import CliRunner

from scholar_workflow.research.recommendations.cli import recommendations


@pytest.fixture(autouse=True)
def no_native_processes(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Contract tests must not launch native processes")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    yield
    assert not calls, "Test-profile feedback attempted to launch a native process"


def invoke(runner, *args, input=None):
    result = runner.invoke(recommendations, ["--profile", "test", *args], input=input)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def submission(*, target=None):
    producer = {"producer_id": "synthetic", "name": "Synthetic research"}
    if target is not None:
        producer["feedback_target"] = target
    return {
        "schema_version": 1,
        "producer": producer,
        "run_id": "one",
        "items": [{"submission_id": "one", "tags": ["evaluation"], "resource": {
            "kind": "blog", "title": "Synthetic blog", "url": "https://example.org/blog",
            "summary_zh": "这份合成资料说明任务、方法、结果与使用边界。",
            "summary_sources": ["https://example.org/blog"],
        }}],
    }


def test_task_binding_needs_no_project_layout_and_only_creates_two_documents(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    rules = b"# My project rules\n"
    (root / "AGENTS.md").write_bytes(rules)
    runner = CliRunner()
    spec = {"project_root": str(root), "producer_id": "evaluation", "title": "Evaluation research",
            "thread_id": str(uuid.uuid4()), "expected_revision": 0}
    task = invoke(runner, "tasks", "bind", "--input", "-", input=json.dumps(spec))
    assert task["schema_version"] == 2
    assert task["revision"] == 1
    assert (root / "AGENTS.md").read_bytes() == rules
    assert not (root / "project-layout.json").exists()
    base = root / ".agents/context/recommendations/evaluation"
    assert {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()} == {
        "AGENTS.md", ".agents/context/recommendations/evaluation/context.md",
        ".agents/context/recommendations/evaluation/recommended.md",
    }
    guide = invoke(runner, "tasks", "guide", "evaluation")
    assert guide["project_root"] == str(root)
    assert "context" not in guide and "recommended" not in guide and "checkpoint" not in guide
    expanded = invoke(runner, "tasks", "guide", "evaluation", "--read-context")
    assert expanded["context"] == (base / "context.md").read_text()
    assert expanded["recommended"] == (base / "recommended.md").read_text()
    assert expanded["context_revision"] and expanded["recommended_revision"]
    assert "checkpoint" not in expanded
    assert invoke(runner, "tasks", "list")["tasks"] == [task]
    assert not invoke(runner, "intake", "target")["enabled"]


def test_routed_submission_binds_task_and_returns_document_locators(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    runner = CliRunner()
    payload = submission(target={"project_root": str(root), "thread_id": str(uuid.uuid4()), "host": "local"})
    result = invoke(runner, "submit", "--input", "-", input=json.dumps(payload))
    receipt = result["receipts"][0]
    assert receipt["status"] == "accepted"
    expected = {"context_file": str(root / ".agents/context/recommendations/synthetic/context.md"),
                "recommended_file": str(root / ".agents/context/recommendations/synthetic/recommended.md")}
    assert receipt["task_files"] == expected
    repeated = invoke(runner, "submit", "--input", "-", input=json.dumps(payload))
    assert repeated["receipts"][0]["status"] == "duplicate"
    assert repeated["receipts"][0]["task_files"] == expected
    assert len(invoke(runner, "tasks", "list")["tasks"]) == 1
    assert not (root / ".agents/context/recommendations/synthetic/feedback.jsonl").exists()


def test_invalid_routed_item_does_not_bind_a_task(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    payload = submission(target={"project_root": str(root), "thread_id": str(uuid.uuid4())})
    del payload["items"][0]["resource"]["title"]
    runner = CliRunner()
    result = runner.invoke(recommendations, ["--profile", "test", "submit", "--input", "-"],
                           input=json.dumps(payload))
    assert result.exit_code == 2
    assert json.loads(result.output)["receipts"][0]["status"] == "invalid"
    assert not invoke(runner, "tasks", "list")["tasks"]
    assert not (root / ".agents").exists()


def test_cli_human_action_preserves_central_feedback_without_project_projection(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    runner = CliRunner()
    submitted = invoke(runner, "submit", "--input", "-", input=json.dumps(submission()))
    receipt = submitted["receipts"][0]
    assert "task_files" not in receipt
    result = invoke(runner, "feedback", "decision", "--input", "-", input=json.dumps({
        "candidate_id": receipt["candidate_id"], "decision": "ignored", "expected_revision": 1,
        "reason": "not_relevant"}))
    assert result["disposition"] == {"reason": "not_relevant", "scope": "current_research"}
    assert list((home / "recommendations/test/context/inbox").glob("*.jsonl"))
    batch = invoke(runner, "curator", "batch")
    invoke(runner, "curator", "consume", "--input", "-", input=json.dumps({
        "batch_id": batch["batch_id"], "content": "## Evaluation\nThis source is for another direction.",
        "expected_revision": 0, "updated_by": {"kind": "agent", "name": "curator"}}))
    assert not invoke(runner, "feedback", "status")["curator_pending"]
    assert not list((home / "recommendations/test/context/inbox").glob("*.jsonl"))


@pytest.mark.parametrize("args", [
    ["projects", "enable"], ["tasks", "register"], ["tasks", "save-context"],
])
def test_retired_project_context_commands_are_not_exposed(tmp_path, monkeypatch, args):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(recommendations, ["--profile", "test", *args])
    assert result.exit_code == 2


def test_browser_style_path_fields_cannot_be_used_as_task_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    result = CliRunner().invoke(recommendations, ["--profile", "test", "tasks", "guide", "../../outside"])
    assert result.exit_code == 2
    assert not (tmp_path / "outside").exists()
