"""Public project-context and feedback CLI contracts, without native services."""
from __future__ import annotations

import json
import uuid

from click.testing import CliRunner

from scholar_workflow.research.recommendations.cli import recommendations


def invoke(runner, *args, input=None):
    result = runner.invoke(recommendations, ["--profile", "test", *args], input=input)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_project_registration_context_and_feedback_are_discoverable_headlessly(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    root = tmp_path / "project"
    root.mkdir()
    identifier = str(uuid.uuid4())
    (root / "project-layout.json").write_text(json.dumps({"schema_version": 2, "project_id": identifier}))
    (root / "AGENTS.md").write_text("# My project rules\n")
    runner = CliRunner()
    enabled = invoke(runner, "projects", "enable", "--project-root", str(root))
    assert enabled["project_id"] == identifier
    task = invoke(runner, "tasks", "register", "--input", "-", input=json.dumps({
        "project_id": identifier, "producer_id": "evaluation", "title": "Evaluation research", "expected_revision": 0}))
    assert task["revision"] == 1
    guide = invoke(runner, "tasks", "guide", "evaluation")
    assert "context" not in guide
    expanded = invoke(runner, "tasks", "guide", "evaluation", "--read-context")
    assert expanded["checkpoint"]["consumed_event_ids"] == []
    assert "My project rules" in (root / "AGENTS.md").read_text()
    assert invoke(runner, "feedback", "status")["curator_pending"] == 0
    assert not invoke(runner, "intake", "target")["enabled"]


def test_cli_human_action_persists_files_without_a_page_or_agent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    runner = CliRunner()
    submitted = invoke(runner, "submit", "--input", "-", input=json.dumps({
        "schema_version": 1, "producer": {"producer_id": "synthetic", "name": "Synthetic"}, "run_id": "one",
        "items": [{"submission_id": "one", "tags": ["evaluation"], "resource": {
            "kind": "blog", "title": "Synthetic blog", "url": "https://example.org/blog",
            "summary_zh": "这份合成资料说明任务、方法、结果与使用边界。", "summary_sources": ["https://example.org/blog"]}}]}))
    candidate_id = submitted["receipts"][0]["candidate_id"]
    result = invoke(runner, "feedback", "decision", "--input", "-", input=json.dumps({
        "candidate_id": candidate_id, "decision": "ignored", "expected_revision": 1,
        "reason": "not_relevant"}))
    assert result["disposition"] == {"reason": "not_relevant", "scope": "current_research"}
    assert list((home / "recommendations/test/context/inbox").glob("*.jsonl"))
    batch = invoke(runner, "curator", "batch")
    invoke(runner, "curator", "consume", "--input", "-", input=json.dumps({
        "batch_id": batch["batch_id"], "content": "## Evaluation\nThis source is for another direction.",
        "expected_revision": 0, "updated_by": {"kind": "agent", "name": "curator"}}))
    assert not invoke(runner, "feedback", "status")["curator_pending"]
    assert not list((home / "recommendations/test/context/inbox").glob("*.jsonl"))


def test_browser_style_path_fields_cannot_be_used_as_task_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(recommendations, ["--profile", "test", "tasks", "guide", "../../outside"])
    assert result.exit_code == 2
    assert not (tmp_path / "outside").exists()
