"""Independent candidate input; no real project, provider, Git, or application access."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow import cli

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "project-context"
CANDIDATE = "project-context-candidate.json"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    draft = json.loads((root / "project-context.json").read_text())
    draft["title"] = "候选资料清单"
    draft["entries"] = [draft["entries"][0], draft["entries"][1]]
    (root / CANDIDATE).write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        pytest.fail("Candidate preview attempted config, external execution, or a provider")

    for name in ("_load_cfg", "_zotero_adapter", "_field_hub_request", "_hub_snapshot_path"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli.webbrowser, "open", forbidden)
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def invoke(root: Path, command: str = "overview", *args: str):
    return CliRunner().invoke(cli.main, [
        "project", command, "--project-root", str(root), "--context-file", CANDIDATE, *args,
    ])


def test_preview_has_selected_material_and_keeps_both_inventories(project: Path) -> None:
    before = snapshot(project)
    result = invoke(project)
    assert result.exit_code == 0, result.output
    assert "候选预览" in result.output and "尚未替换" in result.output
    assert "# 候选资料清单" in result.output
    assert "未查询外部对象" in result.output
    assert "## 实验" not in result.output
    assert snapshot(project) == before


def test_json_marks_preview_and_keeps_typed_refs(project: Path) -> None:
    before = snapshot(project)
    result = invoke(project, "overview", "--json")
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value["preview"] is True and value["context_file"] == CANDIDATE
    assert value["title"] == "候选资料清单" and len(value["entries"]) == 2
    assert [x["state"] for x in value["entries"]] == ["available", "unverified"]
    assert snapshot(project) == before


def test_validation_marks_candidate_without_applying(project: Path) -> None:
    before = snapshot(project)
    result = invoke(project, "validate-context")
    assert result.exit_code == 0, result.output
    assert "候选" in result.output and "2 项" in result.output
    assert snapshot(project) == before


def test_explicit_candidate_does_not_need_active_inventory(project: Path) -> None:
    (project / "project-context.json").unlink()
    before = snapshot(project)
    result = invoke(project)
    assert result.exit_code == 0, result.output
    assert snapshot(project) == before


def test_language_override_only_changes_presentation(project: Path) -> None:
    before = snapshot(project)
    result = invoke(project, "overview", "--language", "en")
    assert result.exit_code == 0, result.output
    assert "Candidate preview" in result.output and "has not been replaced" in result.output
    assert "## Code" in result.output and "Purpose:" in result.output
    assert snapshot(project) == before


@pytest.mark.parametrize("command", ["overview", "validate-context"])
@pytest.mark.parametrize("name", ["../outside.json", "/tmp/outside.json", "docs/candidate.json"])
def test_unsafe_candidate_selector_is_rejected(project: Path, command: str, name: str) -> None:
    before = snapshot(project)
    result = CliRunner().invoke(cli.main, [
        "project", command, "--project-root", str(project), "--context-file", name,
    ])
    assert result.exit_code == 2
    assert "No such option" not in result.output
    assert "root-level JSON filename" in result.output
    assert snapshot(project) == before


@pytest.mark.parametrize("bad", ["missing", "malformed", "duplicate", "identity", "uri", "oversize"])
def test_invalid_candidate_has_no_fallback_or_writes(project: Path, bad: str) -> None:
    path = project / CANDIDATE
    draft = json.loads(path.read_text())
    if bad == "missing":
        path.unlink()
    elif bad == "malformed":
        path.write_text("{broken")
    elif bad == "duplicate":
        path.write_text('{"schema_version":1,"schema_version":1}')
    elif bad == "oversize":
        path.write_text(" " * (2 * 1024 * 1024))
    else:
        if bad == "identity":
            draft["project_id"] = "22222222-2222-4222-8222-222222222222"
        else:
            draft["entries"][1]["ref"]["uri"] = "obsidian://new?vault=test&file=x&content=bad"
        path.write_text(json.dumps(draft))
    before = snapshot(project)
    result = invoke(project)
    assert result.exit_code == 2, result.output
    assert "No such option" not in result.output
    assert "候选资料清单" not in result.output
    assert snapshot(project) == before


def test_symlink_candidate_is_not_followed(project: Path, tmp_path: Path) -> None:
    path = project / CANDIDATE
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    before = snapshot(project)
    result = invoke(project)
    assert result.exit_code == 2 and "unsafe" in result.output
    assert snapshot(project) == before


def test_candidate_directory_is_rejected(project: Path) -> None:
    path = project / CANDIDATE
    path.unlink()
    path.mkdir()
    before = snapshot(project)
    result = invoke(project)
    assert result.exit_code == 2 and "regular file" in result.output
    assert snapshot(project) == before
