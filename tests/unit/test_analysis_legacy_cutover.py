"""Pure fixture checks for the combined legacy Markdown/Canvas cutover gate."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationPlan,
    inventory_legacy_canvas,
)
from scholar_workflow.analysis.legacy_cutover import (
    LegacyFieldPayloadError,
    prepare_legacy_field_payload,
    validate_legacy_cutover,
)
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationPlan,
    LegacyTarget,
    parse_legacy_fields,
)
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import AnalysisUpdateError

NOTE_STEM = "Fixture Paper分析"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _document() -> AnalysisDocument:
    return AnalysisDocument.model_validate(
        {
            "schema_version": 2,
            "artifact_id": "analysis:fixture-paper",
            "paper_title": "Fixture Paper",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": "task",
                    "role": "task",
                    "title": "Task",
                    "body": "Original task statement",
                    "evidence": {"kind": "author_stated", "anchor": "§1"},
                },
                {
                    "claim_id": "input",
                    "role": "input",
                    "title": "Input",
                    "body": "Input description",
                    "evidence": {"kind": "author_stated", "anchor": "§2"},
                },
                {
                    "claim_id": "workflow",
                    "role": "workflow",
                    "title": "Workflow",
                    "body": "Process description",
                    "order": 1,
                    "evidence": {"kind": "author_stated", "anchor": "§3"},
                },
                {
                    "claim_id": "output",
                    "role": "output",
                    "title": "Output",
                    "body": "Output description",
                    "evidence": {"kind": "author_stated", "anchor": "§4"},
                },
                {
                    "claim_id": "boundary",
                    "role": "boundary",
                    "title": "Boundary",
                    "body": "A stated limitation",
                    "evidence": {"kind": "author_stated", "anchor": "§5"},
                },
            ],
        }
    )


def _fixture() -> tuple[
    bytes,
    bytes,
    AnalysisDocument,
    AnalysisBundle,
    LegacyMigrationPlan,
    LegacyCanvasMigrationPlan,
]:
    visible = b"Original task statement"
    source_markdown = (
        visible
        + b"\n"
        + f'<!-- sw-analysis-field path="task" base_sha256="{_sha256(visible)}" -->\n'.encode()
    )
    old_field = parse_legacy_fields(source_markdown)[0]
    markdown_plan = LegacyMigrationPlan(
        source_sha256=_sha256(source_markdown),
        expected_field_count=1,
        mappings=(
            LegacyFieldMapping(
                "task",
                old_field.sha256,
                (
                    LegacyFragment(
                        0,
                        len(old_field.content),
                        old_field.sha256,
                        "copy",
                        LegacyTarget("task"),
                    ),
                ),
            ),
        ),
        split_targets={},
    )
    custom_node = {
        "id": "user-owned-note",
        "type": "text",
        "text": "Keep this personal note",
        "x": 10000,
        "y": 10000,
        "width": 400,
        "height": 200,
        "color": "4",
    }
    source_canvas = _json_bytes({"nodes": [custom_node], "edges": []})
    document = _document()
    rendered = render_analysis(document, note_stem=NOTE_STEM)
    new_canvas = deepcopy(rendered.canvas)
    new_canvas["nodes"].append(custom_node)
    bundle = AnalysisBundle(rendered.markdown, new_canvas)
    canvas_plan = LegacyCanvasMigrationPlan(
        source_sha256=_sha256(source_canvas),
        candidate_sha256=_sha256(_json_bytes(bundle.canvas)),
        mappings=tuple(
            LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
            for row in inventory_legacy_canvas(source_canvas)
        ),
    )
    return source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan


def _run(
    fixture: tuple[
        bytes,
        bytes,
        AnalysisDocument,
        AnalysisBundle,
        LegacyMigrationPlan,
        LegacyCanvasMigrationPlan,
    ],
    *,
    approved_digest: str | None = None,
):
    return validate_legacy_cutover(
        *fixture,
        note_stem=NOTE_STEM,
        approved_digest=approved_digest,
    )


def _codes(report: object) -> set[str]:
    return {finding.code for finding in report.findings}


def test_full_fixture_requires_composite_approval_then_returns_stageable_triple() -> None:
    fixture = _fixture()
    pending = _run(fixture)
    assert not pending.ok
    assert pending.artifacts is None
    assert pending.cutover_digest is not None
    assert _codes(pending) == {"approval-required"}

    approved = _run(fixture, approved_digest=pending.cutover_digest)
    assert approved.ok
    assert approved.findings == ()
    assert approved.artifacts is not None
    assert approved.artifacts.markdown == fixture[3].markdown.encode("utf-8")
    assert approved.artifacts.canvas == _json_bytes(fixture[3].canvas)
    baseline = AnalysisBaseline.model_validate_json(approved.artifacts.sidecar)
    assert baseline.artifact_id == fixture[2].artifact_id
    assert baseline.markdown_sha256 == _sha256(approved.artifacts.markdown)


def test_wrong_external_digest_returns_no_stageable_bytes() -> None:
    report = _run(_fixture(), approved_digest="0" * 64)
    assert not report.ok
    assert report.artifacts is None
    assert _codes(report) == {"approval-digest-mismatch"}


def test_missing_markdown_mapping_blocks_cutover() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    fixture = (
        source_md,
        source_canvas,
        document,
        bundle,
        replace(md_plan, mappings=()),
        canvas_plan,
    )
    report = _run(fixture)
    assert not report.ok
    assert report.artifacts is None
    assert "markdown-missing-path-mapping" in _codes(report)


def test_missing_canvas_mapping_blocks_cutover() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    fixture = (
        source_md,
        source_canvas,
        document,
        bundle,
        md_plan,
        replace(canvas_plan, mappings=()),
    )
    report = _run(fixture)
    assert not report.ok
    assert report.artifacts is None
    assert "canvas-missing-mapping" in _codes(report)


def test_losing_an_old_custom_canvas_node_blocks_even_conformant_new_bundle() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    new_canvas = deepcopy(bundle.canvas)
    new_canvas["nodes"] = [node for node in new_canvas["nodes"] if node["id"] != "user-owned-note"]
    new_bundle = AnalysisBundle(bundle.markdown, new_canvas)
    fixture = (
        source_md,
        source_canvas,
        document,
        new_bundle,
        md_plan,
        replace(canvas_plan, candidate_sha256=_sha256(_json_bytes(new_canvas))),
    )
    report = _run(fixture)
    assert not report.ok
    assert report.artifacts is None
    assert "canvas-not-preserved" in _codes(report)


def test_candidate_bundle_conformance_failure_returns_no_stageable_bytes() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    invalid_bundle = AnalysisBundle(
        bundle.markdown.replace("# Fixture Paper：论文分析", "# Wrong"), bundle.canvas
    )
    report = _run((source_md, source_canvas, document, invalid_bundle, md_plan, canvas_plan))
    assert not report.ok
    assert report.artifacts is None
    assert "bundle-markdown-paper-title-mismatch" in _codes(report)


def test_candidate_canvas_cannot_carry_old_field_markers() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    new_canvas = deepcopy(bundle.canvas)
    new_canvas["nodes"][-1]["text"] += "\n<!-- sw-analysis-field -->"
    report = _run(
        (
            source_md,
            source_canvas,
            document,
            AnalysisBundle(bundle.markdown, new_canvas),
            md_plan,
            canvas_plan,
        )
    )
    assert not report.ok
    assert report.artifacts is None
    assert _codes(report) == {"legacy-canvas-marker-retained"}


def test_baseline_creation_failure_returns_no_stageable_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_baseline(*_args: object, **_kwargs: object) -> None:
        raise AnalysisUpdateError("fixture baseline failure")

    monkeypatch.setattr("scholar_workflow.analysis.legacy_cutover.create_baseline", fail_baseline)
    report = _run(_fixture())
    assert not report.ok
    assert report.artifacts is None
    assert _codes(report) == {"baseline-invalid"}


def test_source_or_candidate_change_invalidates_composite_approval() -> None:
    source_md, source_canvas, document, bundle, md_plan, canvas_plan = _fixture()
    approved_digest = _run(_fixture()).cutover_digest
    assert approved_digest is not None
    source_changed = source_md.replace(b"Original task statement", b"Changed task statement")
    report = _run(
        (source_changed, source_canvas, document, bundle, md_plan, canvas_plan),
        approved_digest=approved_digest,
    )
    assert not report.ok and report.artifacts is None
    assert "markdown-source-changed" in _codes(report)

    changed_bundle = AnalysisBundle(bundle.markdown + "\nA human addendum\n", bundle.canvas)
    report = _run(
        (source_md, source_canvas, document, changed_bundle, md_plan, canvas_plan),
        approved_digest=approved_digest,
    )
    assert not report.ok and report.artifacts is None
    assert "approval-digest-mismatch" in _codes(report)


def _prepare_fixture(*, source_sidecar: bytes | None = None, **overrides: object):
    fixture = _fixture()
    digest = _run(fixture).cutover_digest
    assert digest is not None
    kwargs: dict[str, object] = {
        "markdown_path": f"{NOTE_STEM}.md",
        "canvas_path": f"{NOTE_STEM}.canvas",
        "sidecar_path": f"{NOTE_STEM}.analysis.json",
        "source_markdown": fixture[0],
        "source_canvas": fixture[1],
        "source_sidecar": source_sidecar,
        "document": fixture[2],
        "bundle": fixture[3],
        "markdown_plan": fixture[4],
        "canvas_plan": fixture[5],
        "note_stem": NOTE_STEM,
        "approved_cutover_digest": digest,
    }
    kwargs.update(overrides)
    return prepare_legacy_field_payload(**kwargs)


def test_field_payload_digest_binds_sidecar_absence_and_old_bytes() -> None:
    absent = _prepare_fixture()
    existing = _prepare_fixture(source_sidecar=b'{"old":true}\n')
    empty = _prepare_fixture(source_sidecar=b"")
    assert absent.cutover_digest == existing.cutover_digest == empty.cutover_digest
    assert len({absent.payload_digest, existing.payload_digest, empty.payload_digest}) == 3
    assert absent.source_sidecar_sha256 is None
    assert existing.source_sidecar_sha256 == _sha256(b'{"old":true}\n')
    assert empty.source_sidecar_sha256 == _sha256(b"")
    with pytest.raises(TypeError):
        absent.files[absent.markdown_path] = b"tamper"
    with pytest.raises(TypeError):
        absent.sources[absent.sidecar_path] = "0" * 64


def test_field_payload_digest_binds_all_three_relative_paths() -> None:
    original = _prepare_fixture()
    moved = _prepare_fixture(
        markdown_path=f"另一个领域/{NOTE_STEM}.md",
        canvas_path=f"另一个领域/{NOTE_STEM}.canvas",
        sidecar_path=f"另一个领域/{NOTE_STEM}.analysis.json",
    )
    assert original.cutover_digest == moved.cutover_digest
    assert original.payload_digest != moved.payload_digest


def test_real_pilot_analysis_to_tree_canvas_pair_is_valid_and_path_bound() -> None:
    same_stem = _prepare_fixture()
    tree_name = _prepare_fixture(canvas_path="Fixture Paper解析树.canvas")
    assert tree_name.canvas_path == "Fixture Paper解析树.canvas"
    assert tree_name.sidecar_path == "Fixture Paper分析.analysis.json"
    assert tree_name.cutover_digest == same_stem.cutover_digest
    assert tree_name.payload_digest != same_stem.payload_digest
    with pytest.raises(LegacyFieldPayloadError, match="path"):
        _prepare_fixture(canvas_path="Fixture Paper树.canvas")


def test_field_payload_blocks_pending_semantic_fragment_even_with_digest() -> None:
    fixture = _fixture()
    field = fixture[4].mappings[0]
    pending_fragment = replace(field.fragments[0], disposition="pending")
    pending_plan = replace(
        fixture[4], mappings=(replace(field, fragments=(pending_fragment,)),)
    )
    with pytest.raises(LegacyFieldPayloadError, match="markdown-pending-decision") as exc:
        _prepare_fixture(markdown_plan=pending_plan)
    assert exc.value.report is not None
    assert exc.value.report.artifacts is None


def test_field_payload_blocks_changed_canvas_source_or_candidate() -> None:
    with pytest.raises(LegacyFieldPayloadError, match="canvas-source-changed"):
        _prepare_fixture(source_canvas=b'{"nodes":[],"edges":[]}')
    original = _prepare_fixture()
    assert original.canvas
    candidate = _fixture()[3]
    changed = AnalysisBundle(candidate.markdown + "\nHuman addendum\n", candidate.canvas)
    with pytest.raises(LegacyFieldPayloadError, match="approval-digest-mismatch"):
        _prepare_fixture(bundle=changed)
