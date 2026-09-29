"""The Field adapter must expose only an approved, byte-bound analysis triple."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from scholar_workflow.analysis.legacy_canvas_migration import LegacyCanvasMigrationPlan
from scholar_workflow.analysis.legacy_cutover import (
    LegacyFieldPayloadError,
    LegacyFieldProposalError,
    parse_legacy_field_proposal,
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
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis

NOTE_STEM = "JEPA分析"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fixture():
    document = AnalysisDocument.model_validate(
        {
            "schema_version": 1,
            "artifact_id": "analysis:fixture-jepa",
            "paper_title": "JEPA",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": role,
                    "role": role,
                    "title": role,
                    "body": body,
                    "order": 1 if role == "workflow" else None,
                    "evidence": {"kind": "author_stated", "anchor": "§1"},
                }
                for role, body in (
                    ("task", "Original task statement"),
                    ("input", "Input statement"),
                    ("workflow", "Workflow statement"),
                    ("output", "Output statement"),
                    ("boundary", "Boundary statement"),
                )
            ],
        }
    )
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    visible = b"Original task statement"
    source_markdown = (
        visible
        + b"\n"
        + f'<!-- sw-analysis-field path="task" base_sha256="{_sha256(visible)}" -->\n'.encode()
    )
    field = parse_legacy_fields(source_markdown)[0]
    markdown_plan = LegacyMigrationPlan(
        source_sha256=_sha256(source_markdown),
        expected_field_count=1,
        mappings=(
            LegacyFieldMapping(
                "task",
                field.sha256,
                (
                    LegacyFragment(
                        0,
                        len(field.content),
                        field.sha256,
                        "copy",
                        LegacyTarget("task"),
                    ),
                ),
            ),
        ),
        split_targets={},
    )
    source_canvas = json.dumps({"nodes": [], "edges": []}).encode()
    candidate_canvas = (
        json.dumps(bundle.canvas, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    canvas_plan = LegacyCanvasMigrationPlan(
        source_sha256=_sha256(source_canvas),
        candidate_sha256=_sha256(candidate_canvas),
        mappings=(),
    )
    return source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan


def test_prepared_field_payload_requires_cutover_approval_and_binds_three_paths() -> None:
    source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan = _fixture()
    pending = validate_legacy_cutover(
        source_markdown,
        source_canvas,
        document,
        bundle,
        markdown_plan,
        canvas_plan,
        note_stem=NOTE_STEM,
    )
    assert pending.cutover_digest is not None
    assert pending.artifacts is None
    kwargs = {
        "markdown_path": f"{NOTE_STEM}.md",
        "canvas_path": f"{NOTE_STEM}.canvas",
        "sidecar_path": f"{NOTE_STEM}.analysis.json",
        "source_markdown": source_markdown,
        "source_canvas": source_canvas,
        "source_sidecar": None,
        "document": document,
        "bundle": bundle,
        "markdown_plan": markdown_plan,
        "canvas_plan": canvas_plan,
        "note_stem": NOTE_STEM,
    }
    with pytest.raises(LegacyFieldPayloadError, match="approval-required"):
        prepare_legacy_field_payload(**kwargs, approved_cutover_digest=None)

    prepared = prepare_legacy_field_payload(
        **kwargs, approved_cutover_digest=pending.cutover_digest
    )
    assert prepared.cutover_digest == pending.cutover_digest
    assert prepared.source_markdown_sha256 == _sha256(source_markdown)
    assert prepared.source_canvas_sha256 == _sha256(source_canvas)
    assert prepared.source_sidecar_sha256 is None
    assert set(prepared.files) == {
        f"{NOTE_STEM}.md",
        f"{NOTE_STEM}.canvas",
        f"{NOTE_STEM}.analysis.json",
    }
    assert prepared.files[f"{NOTE_STEM}.md"] == bundle.markdown.encode()
    assert prepared.payload_digest != pending.cutover_digest


@pytest.mark.parametrize(
    "overrides",
    [
        {"markdown_path": "../JEPA分析.md"},
        {"markdown_path": ".hidden/JEPA分析.md"},
        {"canvas_path": "另一领域/JEPA分析.canvas"},
        {"sidecar_path": "other.analysis.json"},
        {"markdown_path": "other.md"},
    ],
)
def test_field_payload_rejects_unsafe_or_mismatched_paths(overrides: dict[str, str]) -> None:
    source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan = _fixture()
    pending = validate_legacy_cutover(
        source_markdown,
        source_canvas,
        document,
        bundle,
        markdown_plan,
        canvas_plan,
        note_stem=NOTE_STEM,
    )
    kwargs = {
        "markdown_path": f"{NOTE_STEM}.md",
        "canvas_path": f"{NOTE_STEM}.canvas",
        "sidecar_path": f"{NOTE_STEM}.analysis.json",
        "source_markdown": source_markdown,
        "source_canvas": source_canvas,
        "source_sidecar": None,
        "document": document,
        "bundle": bundle,
        "markdown_plan": markdown_plan,
        "canvas_plan": canvas_plan,
        "note_stem": NOTE_STEM,
        "approved_cutover_digest": pending.cutover_digest,
    }
    kwargs.update(overrides)
    with pytest.raises(LegacyFieldPayloadError, match="path"):
        prepare_legacy_field_payload(**kwargs)


def _proposal() -> dict[str, object]:
    source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan = _fixture()
    assert source_markdown and source_canvas
    proposal = {
        "schema_version": 1,
        "markdown_path": f"{NOTE_STEM}.md",
        "canvas_path": "JEPA解析树.canvas",
        "sidecar_path": f"{NOTE_STEM}.analysis.json",
        "document": document.model_dump(mode="json"),
        "bundle": {"markdown": bundle.markdown, "canvas": bundle.canvas},
        "markdown_plan": asdict(markdown_plan),
        "canvas_plan": asdict(canvas_plan),
    }
    return json.loads(json.dumps(proposal, ensure_ascii=False, allow_nan=False))


def test_strict_json_proposal_parser_builds_typed_candidate_without_source_bytes() -> None:
    raw = json.dumps(_proposal(), ensure_ascii=False, allow_nan=False).encode("utf-8")
    parsed = parse_legacy_field_proposal(raw)
    assert parsed.note_stem == NOTE_STEM
    assert parsed.canvas_path == "JEPA解析树.canvas"
    assert isinstance(parsed.document, AnalysisDocument)
    assert parsed.markdown_plan.expected_field_count == 1
    assert parsed.canvas_plan.mappings == ()
    assert not hasattr(parsed, "source_markdown")


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update({"source_markdown": "untrusted old bytes"}),
        lambda value: value.update({"schema_version": True}),
        lambda value: value.update({"markdown_path": "/tmp/JEPA分析.md"}),
        lambda value: value["bundle"].update({"unexpected": 1}),
        lambda value: value["markdown_plan"].update({"expected_field_count": True}),
        lambda value: value["markdown_plan"]["mappings"][0].update({"unexpected": 1}),
        lambda value: value["markdown_plan"]["mappings"][0]["fragments"][0].update(
            {"disposition": "silently_drop"}
        ),
        lambda value: value["canvas_plan"].update({"source_sha256": "wrong"}),
    ],
)
def test_proposal_parser_rejects_unsafe_keys_types_and_paths(change) -> None:
    payload = _proposal()
    change(payload)
    with pytest.raises(LegacyFieldProposalError):
        parse_legacy_field_proposal(payload)


def test_proposal_parser_rejects_duplicate_json_keys_nonfinite_and_oversize() -> None:
    raw = json.dumps(_proposal(), ensure_ascii=False).encode("utf-8")
    with pytest.raises(LegacyFieldProposalError, match="duplicate"):
        parse_legacy_field_proposal(raw.replace(b'"schema_version": 1,', b'"schema_version": 1, "schema_version": 1,', 1))
    with pytest.raises(LegacyFieldProposalError, match="finite"):
        parse_legacy_field_proposal(raw.replace(b'"schema_version": 1,', b'"schema_version": NaN,', 1))
    with pytest.raises(LegacyFieldProposalError, match="too large"):
        parse_legacy_field_proposal(b" " * (8 * 1024 * 1024 + 1))
    with pytest.raises(LegacyFieldProposalError, match="valid UTF-8 JSON"):
        parse_legacy_field_proposal(b'{"schema_version":' + b"9" * 5000 + b"}")
    invalid_text = _proposal()
    invalid_text["markdown_path"] = "\ud800"
    with pytest.raises(LegacyFieldProposalError, match="invalid UTF-8 text"):
        parse_legacy_field_proposal(invalid_text)
