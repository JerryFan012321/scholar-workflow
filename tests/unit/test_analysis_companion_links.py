"""Exact companion targets are display routes, never file authorization."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument, AnalysisProfile
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/analysis_v5_toy.json"
NOTE_STEM = "Synthetic analysis"
NOTE_PATH = "Examples/Source/resources/papers/toy/Synthetic analysis.md"


def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def with_target():
    value = payload()
    value["profile"]["canvas_note_path"] = NOTE_PATH
    return value


@pytest.mark.parametrize("images", [False, True])
def test_explicit_target_replaces_all_claim_point_and_image_backlinks_only(images):
    value = payload()
    if images:
        for claim_id, point_id, kind in (
            ("m-1", "method", "process_diagram"),
            ("e-a", "components", "experimental_table"),
        ):
            claim = next(c for c in value["claims"] if c["claim_id"] == claim_id)
            point = next(p for p in claim["points"] if p["point_id"] == point_id)
            source = deepcopy(point["evidence"]["source_spans"][0])
            source.pop("quote", None)
            point["canvas_image"] = {
                "kind": kind, "asset_id": "asset:" + claim_id,
                "image_path": "attachments/" + claim_id + ".png", "sha256": "a" * 64,
                "pixel_width": 1200, "pixel_height": 360,
                "caption": "Synthetic source visual", "source": source,
            }
    before = AnalysisDocument.model_validate(value)
    value["profile"]["canvas_note_path"] = NOTE_PATH
    after = AnalysisDocument.model_validate(value)
    old = render_analysis(before, note_stem=NOTE_STEM)
    new = render_analysis(after, note_stem=NOTE_STEM)
    old_links = [n["text"] for n in old.canvas["nodes"] if "↩ [[" in n.get("text", "")]
    new_links = [n["text"] for n in new.canvas["nodes"] if "↩ [[" in n.get("text", "")]
    assert len(old_links) == len(new_links) > 0
    assert sum("![" in text for text in new_links) == (2 if images else 0)
    expected = [s.replace(f"[[{NOTE_STEM}#^", f"[[{NOTE_PATH[:-3]}#^") for s in old_links]
    assert new_links == expected
    assert new.markdown == old.markdown
    assert new.canvas["edges"] == old.canvas["edges"]
    assert [{k: v for k, v in n.items() if k != "text"} for n in new.canvas["nodes"]] == [
        {k: v for k, v in n.items() if k != "text"} for n in old.canvas["nodes"]
    ]
    assert validate_bundle(after, new, note_stem=NOTE_STEM).ok


def test_omitted_route_retains_old_serialization_and_projection():
    document = AnalysisDocument.model_validate(payload())
    assert "canvas_note_path" not in document.profile.model_dump(mode="json")
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    assert any(f"[[{NOTE_STEM}#^" in n.get("text", "") for n in bundle.canvas["nodes"])


@pytest.mark.parametrize("path", [
    "", "/absolute/Note.md", "../Note.md", "a/../Note.md", "a//Note.md", "./Note.md",
    "https://example.org/Note.md", "a\\Note.md", "a/Note.pdf", "a/Note#bad.md",
    "a/Note|bad.md", "a/[Note].md", "a/Note^bad.md", "a/Note\n.md", "a/Note\x00.md",
    None, 42, " Note.md", "a/Note.md ", "a/Note\x7f.md", "a/Note.md\n",
])
def test_unsafe_target_is_rejected(path):
    value = payload()
    value["profile"]["canvas_note_path"] = path
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(value)


@pytest.mark.parametrize("framework", ["legacy", "reference_tree"])
def test_explicit_route_requires_v5(framework):
    with pytest.raises(ValidationError):
        AnalysisProfile(kind="whole", framework=framework, canvas_note_path=NOTE_PATH)


def test_route_basename_must_be_the_paired_markdown():
    document = AnalysisDocument.model_validate(with_target())
    with pytest.raises(ValueError, match="filename"):
        render_analysis(document, note_stem="A different analysis")


def test_whole_binding_preserves_layout_and_focused_updates_cannot_remove_it():
    old = AnalysisDocument.model_validate(payload())
    bundle, baseline = render_analysis_projection(old, note_stem=NOTE_STEM)
    plan = plan_analysis_update(current=bundle, baseline=baseline,
        update=AnalysisDocument.model_validate(with_target()), note_stem=NOTE_STEM)
    assert plan.status == "ready"
    assert plan.proposed.markdown == bundle.markdown
    assert plan.proposed.canvas["edges"] == bundle.canvas["edges"]
    assert [{k: v for k, v in n.items() if k != "text"} for n in plan.proposed.canvas["nodes"]] == [
        {k: v for k, v in n.items() if k != "text"} for n in bundle.canvas["nodes"]
    ]
    value = plan.document.model_dump(mode="json")
    value["profile"].update(kind="focused", roles=["method"])
    value["claims"] = [c for c in value["claims"] if c["role"] == "method"]
    focused = plan_analysis_update(current=plan.proposed, baseline=plan.baseline,
        update=AnalysisDocument.model_validate(value), note_stem=NOTE_STEM)
    assert focused.status == "ready" and focused.proposed == plan.proposed
    value["profile"].pop("canvas_note_path")
    with pytest.raises(AnalysisUpdateError, match="whole analysis update"):
        plan_analysis_update(current=plan.proposed, baseline=plan.baseline,
            update=AnalysisDocument.model_validate(value), note_stem=NOTE_STEM)


def test_canonical_binding_is_checked_against_trusted_source(tmp_path, monkeypatch):
    from scholar_workflow.adapters.obsidian_registry import ObsidianReaderBinding, ZotFlowError
    from scholar_workflow.analysis import commit
    vault = tmp_path / "Vault"
    source = vault / "Examples/Source"
    source.mkdir(parents=True)
    document = AnalysisDocument.model_validate(with_target())
    request = SimpleNamespace(document=document,
        paths=SimpleNamespace(markdown="resources/papers/toy/Synthetic analysis.md"))
    monkeypatch.setattr(commit, "resolve_obsidian_reader", lambda root:
        ObsidianReaderBinding(source_root=root, vault_root=vault, vault_id="0123456789abcdef"))
    commit._assert_canvas_note_binding(source, request)
    wrong = deepcopy(with_target())
    wrong["profile"]["canvas_note_path"] = "Other/Source/Synthetic analysis.md"
    request.document = AnalysisDocument.model_validate(wrong)
    with pytest.raises(commit.AnalysisCommitSafetyError, match="companion"):
        commit._assert_canvas_note_binding(source, request)
    def unavailable(_):
        raise ZotFlowError("unavailable")
    monkeypatch.setattr(commit, "resolve_obsidian_reader", unavailable)
    with pytest.raises(commit.AnalysisCommitSafetyError, match="companion"):
        commit._assert_canvas_note_binding(source, request)


def test_reproduction_does_not_mark_moved_same_vault_companion_matched(tmp_path, monkeypatch):
    from scholar_workflow.adapters import obsidian_registry
    from scholar_workflow.workflows.knowledge_reproduction import _reader_checks
    vault = tmp_path / "Vault"
    original = vault / "Examples/Source"
    original.mkdir(parents=True)
    document = AnalysisDocument.model_validate(with_target())
    _, baseline = render_analysis_projection(document, note_stem=NOTE_STEM)
    baselines = {document.artifact_id: (
        "resources/papers/toy/analysis.baseline.json", baseline)}
    monkeypatch.setattr(obsidian_registry, "resolve_obsidian_reader", lambda root:
        obsidian_registry.ObsidianReaderBinding(source_root=root, vault_root=vault,
            vault_id="0123456789abcdef"))
    matched = _reader_checks(original, baselines)[0]
    assert matched["canvas_note_binding"] == "binding-matched"
    moved = _reader_checks(vault / "Copied/Source", baselines)[0]
    assert moved["canvas_note_binding"] == "rebinding-required"
    assert moved["reader_launch_verified"] is False
