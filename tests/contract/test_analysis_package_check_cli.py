"""An installed-style explicit checker must not repair or trust a new baseline."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.package_check import package_check_markdown
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.cli import main

FIXTURE = Path(__file__).parents[1] / "fixtures/analysis_v5_toy.json"
STEM = "Synthetic Scalar Reader Analysis"


def _package(tmp_path: Path) -> Path:
    root = tmp_path / "package"
    root.mkdir()
    document = AnalysisDocument.model_validate_json(FIXTURE.read_text())
    pair, baseline = render_analysis_projection(document, note_stem=STEM)
    (root / f"{STEM}.md").write_text(pair.markdown, encoding="utf-8")
    (root / "Tree.canvas").write_text(json.dumps(pair.canvas), encoding="utf-8")
    (root / "Baseline.json").write_text(baseline.model_dump_json(), encoding="utf-8")
    return root


def _check(root: Path, state: Path, *extra: str, markdown: str = STEM + ".md"):
    return CliRunner().invoke(main, [
        "analysis", "check-bundle", str(root), "--markdown", markdown,
        "--canvas", "Tree.canvas", "--sidecar", "Baseline.json", *extra,
    ], env={"SCHOLAR_WORKFLOW_HOME": str(state)})


def _files(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}


def test_explicit_v5_pair_zero_writes(tmp_path):
    root = _package(tmp_path)
    before = _files(root)
    state = tmp_path / "state"
    result = _check(root, state, "--format", "json", "--require-ir", "5")
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["status"] == "conformant" and report["read_only"]
    assert report["ir_version"] == 5
    assert report["roles"] == ["abstract", "introduction", "method", "experiments", "limitation"]
    assert report["content_records"] == 38
    assert report["findings"] == []
    assert report["not_checked"] == [
        "source_fidelity", "live_reader", "human_visual_review", "canonical_registration",
    ]
    assert set(report["files"]) == set(before)
    assert _files(root) == before and not state.exists()


@pytest.mark.parametrize("case", ["prose", "source", "backlink", "alignment", "edge", "baseline"])
def test_changed_pair_fails_without_repair(tmp_path, case):
    root = _package(tmp_path)
    path = root / "Tree.canvas"
    canvas = json.loads(path.read_text())
    if case == "prose":
        md = root / f"{STEM}.md"
        md.write_text(md.read_text().replace("Estimate a scalar", "Invent a scalar"))
    elif case == "baseline":
        path = root / "Baseline.json"
        raw = json.loads(path.read_text())
        raw["markdown_sha256"] = "0" * 64
        path.write_text(json.dumps(raw))
    else:
        if case in {"source", "backlink"}:
            needle = "zotero://" if case == "source" else "[["
            node = next(n for n in canvas["nodes"] if needle in n.get("text", ""))
            node["text"] = node["text"].replace(needle, "broken:")
        elif case == "alignment":
            canvas["nodes"][1]["x"] += 1
        else:
            edge = dict(canvas["edges"][0])
            edge["id"] = "fedcba9876543210"
            edge["toNode"] = canvas["nodes"][-1]["id"]
            canvas["edges"].append(edge)
        path.write_text(json.dumps(canvas))
    before = _files(root)
    result = _check(root, tmp_path / "state", "--format", "json")
    assert result.exit_code == 7, result.output
    report = json.loads(result.output)
    assert report["status"] == "nonconformant" and report["findings"]
    if case == "baseline":
        assert report["findings"][0]["code"] == "package-baseline-mismatch"
    assert _files(root) == before


def test_backlink_filename_is_actual_filename(tmp_path):
    root = _package(tmp_path)
    (root / f"{STEM}.md").rename(root / "Wrong.md")
    result = _check(root, tmp_path / "state", "--format", "json", markdown="Wrong.md")
    assert result.exit_code == 7
    assert "markdown-backlink-filename-mismatch" in result.output


def test_version_requirement_is_explicit_not_conversion(tmp_path):
    root = _package(tmp_path)
    result = _check(root, tmp_path / "state", "--format", "json", "--require-ir", "4")
    assert result.exit_code == 7 and "required-ir-version-mismatch" in result.output
    assert json.loads(result.output)["ir_version"] == 5


def test_allowed_editor_metadata_is_not_drift(tmp_path):
    root = _package(tmp_path)
    path = root / "Tree.canvas"
    canvas = json.loads(path.read_text())
    canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {}}
    path.write_text(json.dumps(canvas))
    assert _check(root, tmp_path / "state").exit_code == 0


@pytest.mark.parametrize("name", ["../Outside.md", "/absolute.md", "a/b.md", "a\\b.md"])
def test_filename_paths_rejected(tmp_path, name):
    root = _package(tmp_path)
    result = _check(root, tmp_path / "state", markdown=name)
    assert result.exit_code == 2


@pytest.mark.parametrize("case", ["missing", "symlink", "fifo", "duplicate-json", "utf8", "oversize"])
def test_unsafe_file_shapes_rejected(tmp_path, case):
    root = _package(tmp_path)
    path = root / "Tree.canvas"
    path.unlink()
    if case == "symlink":
        path.symlink_to(root / "Baseline.json")
    elif case == "fifo":
        os.mkfifo(path)
    elif case == "duplicate-json":
        path.write_text('{"nodes":[],"nodes":[],"edges":[]}')
    elif case == "utf8":
        path.write_bytes(b"\xff")
    elif case == "oversize":
        path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
    result = _check(root, tmp_path / "state")
    assert result.exit_code == 2, result.output


def test_symlink_directory_rejected(tmp_path):
    root = _package(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    assert _check(link, tmp_path / "state").exit_code == 2


def test_changed_read_set_is_not_success(tmp_path, monkeypatch):
    root = _package(tmp_path)
    real_stat = os.stat

    def intervening_edit(path, *args, **kwargs):
        if path == "Tree.canvas" and kwargs.get("dir_fd") is not None:
            with (root / "Tree.canvas").open("a") as handle:
                handle.write(" ")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr("os.stat", intervening_edit)
    result = _check(root, tmp_path / "state")
    assert result.exit_code == 2 and "changed during inspection" in result.output


def test_human_report_is_honest_and_localized(tmp_path):
    root = _package(tmp_path)
    result = _check(root, tmp_path / "state", "--language", "zh")
    assert result.exit_code == 0, result.output
    assert "摘要 → 引言 → 方法 → 实验 → 局限" in result.output
    assert "原文是否支持论点" in result.output and "正式登记均未检查" in result.output
    assert "没有改写" in result.output and "sw-analysis-claim" not in result.output


def test_legacy_v4_is_checked_as_legacy_not_new_template(tmp_path):
    root = tmp_path / "package"
    root.mkdir()
    fixture = Path(__file__).parents[1] / "fixtures/analysis-v5-safety-inputs/v4-base.json"
    document = AnalysisDocument.model_validate_json(fixture.read_text())
    bundle, baseline = render_analysis_projection(document, note_stem=STEM)
    (root / f"{STEM}.md").write_text(bundle.markdown)
    (root / "Tree.canvas").write_text(json.dumps(bundle.canvas))
    (root / "Baseline.json").write_text(baseline.model_dump_json())
    result = _check(root, tmp_path / "state", "--format", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ir_version"] == 4
    result = _check(root, tmp_path / "state", "--require-ir", "5")
    assert result.exit_code == 7 and "required-ir-version-mismatch" in result.output


def test_metadata_cannot_inject_report_structure():
    report = {
        "status": "conformant", "paper_title": "Title\n## forged <script> [[link]]",
        "ir_version": 5, "scope": "whole", "roles": [], "content_records": 0,
        "canvas_nodes": 0, "canvas_edges": 0, "files": {}, "findings": [],
    }
    text = package_check_markdown(report, language="en")
    assert "\n## forged" not in text and "<script>" not in text and "[[link]]" not in text


def test_duplicate_selected_file_and_unknown_ir_are_rejected(tmp_path):
    root = _package(tmp_path)
    result = _check(root, tmp_path / "state", "--sidecar", "Tree.canvas")
    assert result.exit_code == 2
    result = _check(root, tmp_path / "state", "--require-ir", "6")
    assert result.exit_code == 2


def test_extra_canvas_fields_do_not_bypass_gate(tmp_path):
    root = _package(tmp_path)
    path = root / "Tree.canvas"
    canvas = json.loads(path.read_text())
    canvas["approved"] = True
    path.write_text(json.dumps(canvas))
    result = _check(root, tmp_path / "state", "--format", "json")
    assert result.exit_code == 7 and "invalid-json-canvas-contract" in result.output


def test_raw_file_hashes_are_exact_not_canvas_semantic_hash(tmp_path):
    from hashlib import sha256

    root = _package(tmp_path)
    report = json.loads(_check(root, tmp_path / "state", "--format", "json").output)
    assert report["files"] == {
        name: "sha256:" + sha256(payload).hexdigest() for name, payload in _files(root).items()
    }


def test_relative_directory_rejected_without_state_creation(tmp_path, monkeypatch):
    root = _package(tmp_path)
    monkeypatch.chdir(tmp_path)
    state = tmp_path / "state"
    result = _check(Path(root.name), state)
    assert result.exit_code == 2 and not state.exists()
