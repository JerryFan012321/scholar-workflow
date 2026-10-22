"""Independent v5 aspect-advisory expectations; no real library or reader writes."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.audit import audit_analysis_pairs
from scholar_workflow.analysis.batch import (
    AnalysisBatchRunner,
    AnalysisBatchStore,
    _validate_targeted_repair,
)
from scholar_workflow.analysis.complete_reference import render_complete_analysis
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisAuditTarget,
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisDocument,
    AnalysisState,
    ConformanceFinding,
    ConformanceReport,
)
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import create_baseline, plan_analysis_update
from scholar_workflow.cli import main

FIXTURE = Path(__file__).parents[1] / "fixtures/analysis_v5_toy.json"
STEM = "Synthetic Scalar Reader Analysis"


def _document(*, dense: bool = False) -> AnalysisDocument:
    raw = json.loads(FIXTURE.read_text())
    if dense:
        evidence = {"kind": "not_applicable", "detail": "Synthetic layout input only."}
        raw["claims"].extend({
            "claim_id": f"extra-{index}", "role": "method", "title": f"Synthetic module {index}",
            "outline_path": f"method/modules/extra-{index}",
            "container": True, "body": "", "evidence": evidence,
            "points": [{
                "point_id": slot, "text": f"Synthetic {slot} entry {index}; no scientific claim.",
                "evidence": evidence,
            } for slot in ("motivation", "method", "why-it-works", "technical-advantage")],
        } for index in range(20))
    return AnalysisDocument.model_validate(raw)


def _stretched(document: AnalysisDocument, *, axis: str = "tall", note_stem: str = STEM) -> AnalysisBundle:
    bundle = render_analysis(document, note_stem=note_stem)
    canvas = deepcopy(bundle.canvas)
    for node in canvas["nodes"]:
        if axis == "tall":
            # Stretch centers, not tops, so differing card heights cannot reorder ports.
            node["y"] = 5 * node["y"] + 2 * node["height"]
        else:
            node["x"] *= 10
    return AnalysisBundle(markdown=bundle.markdown, canvas=canvas)


def _assert_warning(findings):
    assert len(findings) == 1
    warning = findings[0]
    assert (warning.code, warning.path) == ("canvas-aspect-limit", "canvas/geometry")
    assert warning.severity == "warning" and not warning.repairable


def _request(document: AnalysisDocument) -> AnalysisBatchRequest:
    return AnalysisBatchRequest(batch_id="aspect-advisory", items=[AnalysisBatchItem(
        item_id="synthetic", zotero_item_key="SYNTH001", note_stem=STEM, document=document,
    )])


@pytest.mark.parametrize("axis", ["tall", "wide"])
def test_v5_aspect_only_keeps_every_record_edge_and_five_branches(axis):
    document = _document()
    original = render_analysis(document, note_stem=STEM)
    bundle = _stretched(document, axis=axis)
    report = validate_bundle(document, bundle, note_stem=STEM)
    assert report.ok
    _assert_warning(report.findings)
    assert bundle.markdown == original.markdown
    assert bundle.canvas["edges"] == original.canvas["edges"]
    assert [{k: v for k, v in n.items() if k not in {"x", "y"}} for n in bundle.canvas["nodes"]] == [
        {k: v for k, v in n.items() if k not in {"x", "y"}} for n in original.canvas["nodes"]
    ]
    assert [role.value for role in document.profile.roles] == [
        "abstract", "introduction", "method", "experiments", "limitation",
    ]


def test_direct_renderer_returns_a_complete_dense_candidate_without_aspect_exception():
    document = _document(dense=True)
    complete = render_complete_analysis(document, note_stem=STEM)
    assert complete == render_complete_analysis(document, note_stem=STEM, enforce_limits=False)
    report = validate_bundle(document, complete, note_stem=STEM)
    assert report.ok
    _assert_warning(report.findings)
    for claim in document.claims:
        for point in claim.points:
            assert point.text in complete.markdown
            assert any(point.text in node["text"] for node in complete.canvas["nodes"])


@pytest.mark.parametrize("case,code", [
    ("height", "canvas-node-height-limit"),
    ("overlap", "overlapping-canvas-nodes"),
    ("backlink", "canvas-managed-content-mismatch"),
    ("alignment", "canvas-level-alignment"),
    ("route", "canvas-edge-routing-mismatch"),
])
def test_aspect_warning_never_masks_a_hard_error(case, code):
    document = _document()
    bundle = _stretched(document)
    nodes = bundle.canvas["nodes"]
    if case == "height":
        nodes[-1]["height"] = 421
    elif case == "overlap":
        nodes[-1].update(x=nodes[-2]["x"], y=nodes[-2]["y"])
    elif case == "backlink":
        node = next(n for n in nodes if "[[" in n["text"])
        node["text"] = node["text"].replace("[[", "broken:")
    elif case == "alignment":
        nodes[-1]["x"] += 1
    else:
        bundle.canvas["edges"][0]["styleAttributes"]["pathfindingMethod"] = "direct"
    report = validate_bundle(document, bundle, note_stem=STEM)
    assert not report.ok
    assert any(f.code == code and f.severity == "error" for f in report.findings)
    _assert_warning([f for f in report.findings if f.severity == "warning"])


def test_batch_warning_survives_reopen_without_repair_or_reexecution(tmp_path):
    request = _request(_document())
    database = tmp_path / "batch.db"
    store = AnalysisBatchStore(database)
    calls = []

    def renderer(document, note_stem):
        calls.append(document)
        return _stretched(document, note_stem=note_stem)

    def forbidden_repair(*args):
        pytest.fail("A warning must not spend the repair budget")

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    first = runner.run(request, repair=forbidden_repair)
    assert first.state == "completed"
    item = first.items[0]
    assert item.state is AnalysisState.VALIDATED and item.repair_count == 0
    _assert_warning(item.diagnostics)
    assert {p.name for p in Path(item.stage_path).iterdir()} == {
        "analysis.md", "analysis.canvas", "analysis.baseline.json",
    }
    assert runner.run(request, repair=forbidden_repair) == first
    assert len(calls) == 1
    store.close()
    reopened = AnalysisBatchStore(database, readonly=True)
    assert reopened.get_item(request.batch_id, item.item_id) == item
    reopened.close()


@pytest.mark.parametrize("deferred", [False, True])
def test_warning_cannot_block_the_one_permitted_hard_error_repair(tmp_path, deferred):
    request = _request(_document())
    calls = []
    repairs = []

    def renderer(document, note_stem):
        bundle = _stretched(document, note_stem=note_stem)
        if not calls:
            node = next(n for n in bundle.canvas["nodes"] if "[[" in n["text"])
            node["text"] = node["text"].replace("[[", "broken:")
        calls.append(document)
        return bundle

    def repair(document, report):
        repairs.append(report)
        assert {f.severity for f in report.findings} == {"error", "warning"}
        return document

    store = AnalysisBatchStore(tmp_path / "batch.db")
    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=renderer)
    if deferred:
        failed = runner.run(request).items[0]
        assert failed.state is AnalysisState.FAILED and failed.repair_count == 0
        assert failed.stage_path is None
    result = runner.run(request, repair=repair).items[0]
    assert result.state is AnalysisState.REPAIRED and result.repair_count == 1
    _assert_warning(result.diagnostics)
    assert len(repairs) == 1 and len(calls) == 2
    store.close()


def test_warning_alone_cannot_reopen_a_stored_failure_or_erase_history(tmp_path):
    request = _request(_document())
    store = AnalysisBatchStore(tmp_path / "batch.db")
    store.ensure_batch(request)
    store.ensure_item(request.batch_id, request.items[0])
    warning = ConformanceFinding(
        code="canvas-aspect-limit", path="canvas/geometry", message="Synthetic stored warning.",
        severity="warning", repairable=True,
    )
    store.update_item(request.batch_id, "synthetic", AnalysisState.FAILED, diagnostics=[warning], stage_path=None)
    before = store.get_item(request.batch_id, "synthetic")

    def forbidden(*args):
        pytest.fail("A stored failure needs an error finding to claim repair")

    runner = AnalysisBatchRunner(store=store, stage_root=tmp_path / "stage", renderer=forbidden)
    assert runner.run(request, repair=forbidden).items[0] == before
    assert store.get_item(request.batch_id, "synthetic") == before
    store.close()


@pytest.mark.parametrize("path", ["canvas/geometry", "canvas/claims/a-t"])
@pytest.mark.parametrize("field", ["body", "canvas_summary"])
def test_warning_cannot_authorize_claim_or_summary_rewrites(path, field):
    original = _document()
    raw = original.model_dump(mode="json")
    raw["claims"][0][field] = "Unapproved replacement."
    repaired = AnalysisDocument.model_validate(raw)
    report = ConformanceReport(ok=True, findings=[ConformanceFinding(
        code="canvas-aspect-limit", path=path, message="Advisory only.",
        severity="warning", repairable=True,
    )])
    with pytest.raises(ValueError, match="outside reported findings"):
        _validate_targeted_repair(original, repaired, report)


def test_legacy_error_aspect_repair_keeps_its_existing_summary_only_authority():
    original = _document()
    raw = original.model_dump(mode="json")
    raw["claims"][0]["canvas_summary"] = "Faithful shorter display."
    repaired = AnalysisDocument.model_validate(raw)
    report = ConformanceReport(ok=False, findings=[ConformanceFinding(
        code="canvas-aspect-limit", path="canvas/geometry", message="Historical error.",
    )])
    _validate_targeted_repair(original, repaired, report)
    raw["claims"][0]["body"] = "Unauthorized prose edit."
    with pytest.raises(ValueError, match="outside reported findings"):
        _validate_targeted_repair(original, AnalysisDocument.model_validate(raw), report)


def test_warning_pair_update_audit_and_cli_are_readonly_and_preserve_manual_layout(tmp_path):
    document = _document()
    bundle = _stretched(document)
    baseline = create_baseline(document, bundle, note_stem=STEM)
    plan = plan_analysis_update(current=bundle, baseline=baseline, update=document, note_stem=STEM)
    assert plan.status == "ready" and plan.conflicts == () and plan.proposed == bundle
    package = tmp_path / "package"
    package.mkdir()
    (package / f"{STEM}.md").write_text(bundle.markdown)
    (package / "Tree.canvas").write_text(json.dumps(bundle.canvas))
    (package / "Baseline.json").write_text(baseline.model_dump_json())
    before = {p.name: p.read_bytes() for p in package.iterdir()}
    report = audit_analysis_pairs(package, [AnalysisAuditTarget(
        item_id="synthetic", note_stem=STEM, markdown_path=f"{STEM}.md",
        canvas_path="Tree.canvas", sidecar_path="Baseline.json", document=document,
    )])
    assert report.ok and len(report.findings) == 1 and report.findings[0].severity == "warning"
    assert report.findings[0].path == "items/synthetic/canvas/geometry"
    state = tmp_path / "state"
    args = ["analysis", "check-bundle", str(package), "--markdown", f"{STEM}.md",
            "--canvas", "Tree.canvas", "--sidecar", "Baseline.json", "--require-ir", "5"]
    cli = CliRunner()
    result = cli.invoke(main, [*args, "--format", "json"], env={"SCHOLAR_WORKFLOW_HOME": str(state)})
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["status"] == "conformant" and output["findings"][0]["severity"] == "warning"
    assert "human_visual_review" in output["not_checked"]
    for language, label in [("en", "Warning"), ("zh", "提醒")]:
        result = cli.invoke(main, [*args, "--language", language], env={"SCHOLAR_WORKFLOW_HOME": str(state)})
        assert result.exit_code == 0 and label in result.output
    assert {p.name: p.read_bytes() for p in package.iterdir()} == before
    assert not state.exists()
