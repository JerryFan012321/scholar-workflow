"""Prepared CLI acceptance for one synthetic project; run only after approval."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow import cli

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "project-context"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Project context attempted a service, config, or external execution")

    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    monkeypatch.setattr(cli, "_zotero_adapter", forbidden)
    monkeypatch.setattr(cli, "_field_hub_request", forbidden)
    monkeypatch.setattr(cli, "_managed_field_hub_record", forbidden)
    monkeypatch.setattr(cli, "_hub_snapshot_path", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli.webbrowser, "open", forbidden)
    return root


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def _invoke(root: Path, command: str, *options: str):
    return CliRunner().invoke(
        cli.main, ["project", command, "--project-root", str(root), *options],
    )


def test_overview_matches_independently_prepared_output(project: Path) -> None:
    before = _snapshot(project)
    result = _invoke(project, "overview")
    assert result.exit_code == 0, result.output
    assert result.output == (project / "EXPECTED-OVERVIEW.md").read_text(encoding="utf-8")
    assert _snapshot(project) == before
    assert str(project) not in result.output and "11111111-1111-4111" not in result.output


@pytest.mark.parametrize("language", ["en", "zh"])
def test_empty_template_is_stdout_only(project: Path, language: str) -> None:
    before = _snapshot(project)
    result = _invoke(project, "context-template", "--language", language)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["project_id"] == "11111111-1111-4111-8111-111111111111"
    assert payload["entries"] == []
    assert payload["language"] == language
    assert _snapshot(project) == before


def test_validate_reports_only_declaration_validity(project: Path) -> None:
    before = _snapshot(project)
    result = _invoke(project, "validate-context")
    assert result.exit_code == 0, result.output
    assert "明确声明了 7 项" in result.output
    assert "尚未核验资料可用性或科学内容" in result.output
    assert _snapshot(project) == before


def test_language_override_does_not_rewrite_inventory(project: Path) -> None:
    before = _snapshot(project)
    result = _invoke(project, "overview", "--language", "en")
    assert result.exit_code == 0, result.output
    assert "## Code" in result.output and "Purpose:" in result.output
    assert "## 代码" not in result.output and "用途:" not in result.output
    assert _snapshot(project) == before


def test_json_keeps_references_and_honest_per_item_state(project: Path) -> None:
    before = _snapshot(project)
    result = _invoke(project, "overview", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    entries = {entry["entry_id"]: entry for entry in payload["entries"]}
    assert len(entries) == 7
    assert entries["code"]["state"] == "available"
    assert entries["paper"]["state"] == "unverified"
    assert entries["missing"]["state"] == "missing"
    assert entries["paper"]["ref"]["resource_id"] == "synthetic-paper-only"
    assert _snapshot(project) == before


@pytest.mark.parametrize("command", ["validate-context", "overview"])
def test_missing_inventory_is_input_error_without_creation(project: Path, command: str) -> None:
    (project / "project-context.json").unlink()
    before = _snapshot(project)
    result = _invoke(project, command)
    assert result.exit_code == 2
    assert "project-context.json" in result.output
    assert _snapshot(project) == before


def test_identity_mismatch_does_not_repair_inventory(project: Path) -> None:
    path = project / "project-context.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["project_id"] = "22222222-2222-4222-8222-222222222222"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = _snapshot(project)
    result = _invoke(project, "overview")
    assert result.exit_code == 2
    assert "identity does not match" in result.output
    assert _snapshot(project) == before


def test_command_uri_is_rejected_without_launch(project: Path) -> None:
    path = project / "project-context.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][1]["ref"] = {
        "kind": "external-resource", "provider": "obsidian", "resource_id": "test-only",
        "uri": "obsidian://advanced-uri?vault=test&commandid=run",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = _snapshot(project)
    result = _invoke(project, "overview")
    assert result.exit_code == 2
    assert _snapshot(project) == before
