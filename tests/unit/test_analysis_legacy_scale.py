"""Synthetic legacy-scale conservation checks without user Vault material."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationPlan,
    inventory_legacy_canvas,
)
from scholar_workflow.analysis.legacy_cutover import validate_legacy_cutover
from scholar_workflow.analysis.legacy_migration import (
    LegacyFieldMapping,
    LegacyFragment,
    LegacyMigrationPlan,
    LegacyTarget,
    LegacyUnmarkedDecision,
    parse_legacy_analysis,
)
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle, canvas_node_id, render_analysis

_ROLES = ("task", "input", "workflow", "output", "boundary")
_NOTE_STEM = "Synthetic Paper分析"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


@dataclass(frozen=True)
class _OldRow:
    path: str
    text: str
    role: str
    disposition: str
    point_id: str | None = None


@dataclass(frozen=True)
class _Case:
    source_markdown: bytes
    source_canvas: bytes
    document: AnalysisDocument
    bundle: AnalysisBundle
    markdown_plan: LegacyMigrationPlan
    canvas_plan: LegacyCanvasMigrationPlan

    def review(self, *, approved_digest: str | None = None):
        return validate_legacy_cutover(
            self.source_markdown,
            self.source_canvas,
            self.document,
            self.bundle,
            self.markdown_plan,
            self.canvas_plan,
            note_stem=_NOTE_STEM,
            approved_digest=approved_digest,
        )


def _rows() -> list[_OldRow]:
    rows = [
        _OldRow(
            f"{_ROLES[index % len(_ROLES)]}/item-{index:03d}",
            f"Synthetic legacy statement {index:03d}.",
            _ROLES[index % len(_ROLES)],
            "copy",
        )
        for index in range(1, 165)
    ]
    rows.extend(
        _OldRow(
            f"workflow/step-{index:03d}/evidence",
            f"Synthetic detached evidence {index:03d}.",
            "workflow",
            "rewrite",
            f"evidence-{index:03d}",
        )
        for index in range(1, 26)
    )
    rows.extend(
        _OldRow(
            f"workflow/challenge-{index:03d}",
            f"对应挑战／贡献：合成占位 {index:03d}。",
            "workflow",
            "retire",
        )
        for index in range(1, 6)
    )
    assert len(rows) == 194
    return rows


def _case() -> _Case:
    # Scale and conservation only: synthetic prose and a matching digest are not human approval.
    rows = _rows()
    markdown = bytearray(b"# Synthetic legacy prelude\n\n")
    old_nodes: list[dict[str, object]] = []
    old_edges: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        visible = row.text.encode()
        marker = f'<!-- sw-analysis-field path="{row.path}" base_sha256="{_sha256(visible)}" -->'
        markdown.extend(visible + b"\n" + marker.encode() + b"\n")
        node_id = _sha256(f"legacy\n{row.path}".encode())[:16]
        old_nodes.append(
            {
                "id": node_id,
                "type": "text",
                "x": (index % 3) * 500,
                "y": (index // 3) * 240,
                "width": 400,
                "height": 180,
                "text": f"{row.text}\n{marker}",
            }
        )
        if index:
            previous = rows[index - 1]
            old_edges.append(
                {
                    "id": _sha256(f"edge\n{previous.path}\n{row.path}".encode())[:16],
                    "fromNode": old_nodes[index - 1]["id"],
                    "toNode": node_id,
                    "toEnd": "arrow",
                }
            )
    source_markdown = bytes(markdown)
    source_canvas = _json_bytes({"nodes": old_nodes, "edges": old_edges})
    inventory = parse_legacy_analysis(source_markdown)
    assert len(inventory.fields) == 194
    assert len(inventory.unmarked) == 1
    assert len(inventory_legacy_canvas(source_canvas)) == 387

    bodies = {
        role: " ".join(row.text for row in rows if row.role == role and row.disposition == "copy")
        for role in _ROLES
    }
    points = [
        {
            "point_id": row.point_id,
            "text": f"Reviewed synthetic attribution for {row.text}",
            "evidence": {"kind": "author_stated", "anchor": f"Fixture §E{index}"},
        }
        for index, row in enumerate((row for row in rows if row.point_id is not None), start=1)
    ]
    document = AnalysisDocument.model_validate(
        {
            "schema_version": 2,
            "artifact_id": "analysis:synthetic-legacy-scale",
            "paper_title": "Synthetic Paper",
            "profile": {"kind": "whole"},
            "claims": [
                {
                    "claim_id": role,
                    "role": role,
                    "title": "Method step" if role == "workflow" else role.title(),
                    "body": bodies[role],
                    "canvas_summary": f"Synthetic {role} overview for the fixture.",
                    "evidence": {
                        "kind": "analysis_inference",
                        "detail": "Synthetic grouping; not a paper claim.",
                    },
                    "points": points if role == "workflow" else [],
                    "order": 1 if role == "workflow" else None,
                }
                for role in _ROLES
            ],
        }
    )
    bundle = render_analysis(document, note_stem=_NOTE_STEM)
    fields_by_path = {field.path: field for field in inventory.fields}
    mappings = []
    for row in rows:
        field = fields_by_path[row.path]
        target = None if row.disposition == "retire" else LegacyTarget(row.role, row.point_id)
        mappings.append(
            LegacyFieldMapping(
                row.path,
                field.sha256,
                (
                    LegacyFragment(
                        0,
                        len(field.content),
                        field.sha256,
                        row.disposition,
                        target,
                    ),
                ),
            )
        )
    unmarked = inventory.unmarked[0]
    markdown_plan = LegacyMigrationPlan(
        source_sha256=_sha256(source_markdown),
        expected_field_count=194,
        mappings=tuple(mappings),
        split_targets={},
        unmarked=(LegacyUnmarkedDecision(unmarked.location, unmarked.sha256, "rewrite"),),
    )

    candidate_canvas = _json_bytes(bundle.canvas)
    candidate_elements = {
        (item.kind, item.element_id): item for item in inventory_legacy_canvas(candidate_canvas)
    }
    canvas_mappings = []
    for index, item in enumerate(inventory_legacy_canvas(source_canvas)):
        if item.kind == "edge" or rows[index].disposition == "retire":
            canvas_mappings.append(
                LegacyCanvasElementMapping(
                    item.kind, item.element_id, item.payload_sha256, "retire"
                )
            )
            continue
        row = rows[index]
        target_id = canvas_node_id(document.artifact_id, f"role/{row.role}/{row.role}")
        target = candidate_elements[("node", target_id)]
        canvas_mappings.append(
            LegacyCanvasElementMapping(
                item.kind,
                item.element_id,
                item.payload_sha256,
                "reviewed_rewrite",
                target_id,
                target.payload_sha256,
            )
        )
    canvas_plan = LegacyCanvasMigrationPlan(
        source_sha256=_sha256(source_canvas),
        candidate_sha256=_sha256(candidate_canvas),
        mappings=tuple(canvas_mappings),
    )
    return _Case(source_markdown, source_canvas, document, bundle, markdown_plan, canvas_plan)


def _finding_codes(report: object) -> set[str]:
    return {finding.code for finding in report.findings}


def test_synthetic_legacy_scale_requires_review_then_conserves_all_objects() -> None:
    case = _case()
    pending = case.review()
    assert pending.ok is False
    assert pending.artifacts is None
    assert pending.cutover_digest is not None
    assert _finding_codes(pending) == {"approval-required"}

    approved = case.review(approved_digest=pending.cutover_digest)
    assert approved.ok is True
    assert approved.artifacts is not None
    assert len(case.bundle.canvas["nodes"]) == 11
    assert b"sw-analysis-field" not in approved.artifacts.markdown
    assert b"sw-analysis-field" not in approved.artifacts.canvas
    assert "对应挑战／贡献" not in approved.artifacts.markdown.decode()
    assert (
        len(AnalysisBaseline.model_validate_json(approved.artifacts.sidecar).document.claims) == 5
    )


def test_synthetic_legacy_scale_fails_closed_for_unmapped_field_edge_and_prelude() -> None:
    case = _case()
    missing_field = replace(case.markdown_plan, mappings=case.markdown_plan.mappings[:-1])
    field_report = replace(case, markdown_plan=missing_field).review()
    assert field_report.artifacts is None
    assert "markdown-missing-path-mapping" in _finding_codes(field_report)

    missing_edge = replace(case.canvas_plan, mappings=case.canvas_plan.mappings[:-1])
    edge_report = replace(case, canvas_plan=missing_edge).review()
    assert edge_report.artifacts is None
    assert "canvas-missing-mapping" in _finding_codes(edge_report)

    missing_prelude = replace(case.markdown_plan, unmarked=())
    prelude_report = replace(case, markdown_plan=missing_prelude).review()
    assert prelude_report.artifacts is None
    assert "markdown-missing-unmarked-decision" in _finding_codes(prelude_report)


def test_synthetic_legacy_scale_rejects_detached_evidence_and_pending_challenge() -> None:
    case = _case()
    evidence_index = next(
        index
        for index, mapping in enumerate(case.markdown_plan.mappings)
        if mapping.path.endswith("/evidence")
    )
    mappings = list(case.markdown_plan.mappings)
    evidence = mappings[evidence_index]
    mappings[evidence_index] = replace(
        evidence,
        fragments=(replace(evidence.fragments[0], disposition="copy"),),
    )
    evidence_report = replace(
        case, markdown_plan=replace(case.markdown_plan, mappings=tuple(mappings))
    ).review()
    assert evidence_report.artifacts is None
    assert "markdown-evidence-unmapped" in _finding_codes(evidence_report)

    challenge_index = next(
        index
        for index, mapping in enumerate(case.markdown_plan.mappings)
        if "challenge" in mapping.path
    )
    mappings = list(case.markdown_plan.mappings)
    challenge = mappings[challenge_index]
    mappings[challenge_index] = replace(
        challenge,
        fragments=(replace(challenge.fragments[0], disposition="pending"),),
    )
    challenge_report = replace(
        case, markdown_plan=replace(case.markdown_plan, mappings=tuple(mappings))
    ).review()
    assert challenge_report.artifacts is None
    assert "markdown-pending-decision" in _finding_codes(challenge_report)
