"""Fixture-only tests for legacy JSON Canvas conservation before human cutover."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from scholar_workflow.analysis.legacy_canvas_migration import (
    LegacyCanvasElementMapping,
    LegacyCanvasMigrationError,
    LegacyCanvasMigrationPlan,
    inventory_legacy_canvas,
    validate_legacy_canvas_migration,
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canvas(value: dict[str, object]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _marked(text: str, path: str) -> str:
    baseline = _sha256(text.encode("utf-8"))
    return f'{text}\n<!-- sw-analysis-field path="{path}" base_sha256="{baseline}" -->'


def _node(node_id: str, text: str, *, color: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "id": node_id,
        "type": "text",
        "text": text,
        "x": 0,
        "y": 0,
        "width": 400,
        "height": 200,
    }
    if color is not None:
        result["color"] = color
    return result


def _fixture() -> bytes:
    generated_edge_id = _sha256(b"edge\nroot\ntask")[:16]
    return _canvas(
        {
            "nodes": [
                _node("root", _marked("# Root", "root")),
                _node("task", _marked("# Task", "task")),
                _node("human-note", "My untouched note", color="4"),
            ],
            "edges": [
                {"id": generated_edge_id, "fromNode": "root", "toNode": "task"},
                {"id": "human-edge", "fromNode": "root", "toNode": "human-note"},
            ],
        }
    )


def _plan(
    source: bytes,
    candidate: bytes,
    mappings: tuple[LegacyCanvasElementMapping, ...] | None = None,
) -> LegacyCanvasMigrationPlan:
    if mappings is None:
        mappings = tuple(
            LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
            for row in inventory_legacy_canvas(source)
        )
    return LegacyCanvasMigrationPlan(_sha256(source), _sha256(candidate), mappings)


def _codes(report: object) -> set[str]:
    return {finding.code for finding in report.findings}


def test_inventory_classifies_marked_nodes_and_deterministic_edges() -> None:
    rows = inventory_legacy_canvas(_fixture())
    assert len(rows) == 5
    assert {(row.kind, row.element_id, row.ownership) for row in rows} == {
        ("node", "root", "generated"),
        ("node", "task", "generated"),
        ("node", "human-note", "custom"),
        ("edge", _sha256(b"edge\nroot\ntask")[:16], "generated"),
        ("edge", "human-edge", "custom"),
    }
    assert all(len(row.payload_sha256) == 64 for row in rows)


def test_exact_preservation_passes_without_review() -> None:
    source = _fixture()
    report = validate_legacy_canvas_migration(source, source, _plan(source, source))
    assert report.ok
    assert not report.review_required


def test_custom_payload_and_edge_changes_cannot_silently_pass_preserve() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"][2]["color"] = "5"
    candidate_value["edges"][1]["toSide"] = "left"
    candidate = _canvas(candidate_value)
    report = validate_legacy_canvas_migration(source, candidate, _plan(source, candidate))
    assert not report.ok
    assert "not-preserved" in _codes(report)
    assert sum(row.code == "not-preserved" for row in report.findings) == 2


def test_custom_rewrite_and_retirement_require_external_review_digest() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"][2]["text"] = "Reviewed replacement"
    candidate_value["edges"] = candidate_value["edges"][:1]
    candidate = _canvas(candidate_value)
    source_rows = inventory_legacy_canvas(source)
    candidate_rows = {(row.kind, row.element_id): row for row in inventory_legacy_canvas(candidate)}
    mappings = []
    for row in source_rows:
        if row.element_id == "human-note":
            mappings.append(
                LegacyCanvasElementMapping(
                    row.kind,
                    row.element_id,
                    row.payload_sha256,
                    "reviewed_rewrite",
                    target_id=row.element_id,
                    target_payload_sha256=candidate_rows[(row.kind, row.element_id)].payload_sha256,
                )
            )
        elif row.element_id == "human-edge":
            mappings.append(
                LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "retire")
            )
        else:
            mappings.append(
                LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
            )
    plan = _plan(source, candidate, tuple(mappings))
    pending = validate_legacy_canvas_migration(source, candidate, plan)
    assert not pending.ok
    assert pending.review_required
    assert _codes(pending) == {"human-review-required"}
    approved = validate_legacy_canvas_migration(
        source, candidate, plan, approved_review_digest=pending.plan_digest
    )
    assert approved.ok


def test_generated_nodes_and_edges_cannot_disappear_without_explicit_mapping_and_review() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"] = [node for node in candidate_value["nodes"] if node["id"] != "task"]
    candidate_value["edges"] = [
        edge for edge in candidate_value["edges"] if edge["toNode"] != "task"
    ]
    candidate = _canvas(candidate_value)
    base = _plan(source, candidate)
    missing = replace(base, mappings=base.mappings[1:])
    assert "missing-mapping" in _codes(validate_legacy_canvas_migration(source, candidate, missing))
    retired = tuple(
        replace(row, disposition="retire")
        if row.source_id in {"task", _sha256(b"edge\nroot\ntask")[:16]}
        else row
        for row in base.mappings
    )
    plan = replace(base, mappings=retired)
    pending = validate_legacy_canvas_migration(source, candidate, plan)
    assert _codes(pending) == {"human-review-required"}
    assert validate_legacy_canvas_migration(
        source, candidate, plan, approved_review_digest=pending.plan_digest
    ).ok


def test_rewrite_target_must_exist_with_its_planned_complete_payload() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"][1]["text"] = "# Reviewed task"
    candidate = _canvas(candidate_value)
    base = _plan(source, candidate)
    bad = replace(
        base.mappings[1],
        disposition="reviewed_rewrite",
        target_id="task",
        target_payload_sha256="0" * 64,
    )
    plan = replace(base, mappings=(base.mappings[0], bad, *base.mappings[2:]))
    initial = validate_legacy_canvas_migration(source, candidate, plan)
    report = validate_legacy_canvas_migration(
        source, candidate, plan, approved_review_digest=initial.plan_digest
    )
    assert "rewrite-target-changed" in _codes(report)


def test_duplicate_unknown_pending_and_wrong_payload_mappings_fail_closed() -> None:
    source = _fixture()
    plan = _plan(source, source)
    duplicate = replace(plan, mappings=(*plan.mappings, plan.mappings[0]))
    assert "duplicate-mapping" in _codes(
        validate_legacy_canvas_migration(source, source, duplicate)
    )
    unknown = replace(
        plan,
        mappings=(
            *plan.mappings,
            LegacyCanvasElementMapping("node", "absent", "0" * 64, "preserve"),
        ),
    )
    assert "unknown-source" in _codes(validate_legacy_canvas_migration(source, source, unknown))
    pending = replace(
        plan, mappings=(replace(plan.mappings[0], disposition="pending"), *plan.mappings[1:])
    )
    assert "pending-decision" in _codes(validate_legacy_canvas_migration(source, source, pending))
    stale = replace(
        plan,
        mappings=(replace(plan.mappings[0], source_payload_sha256="0" * 64), *plan.mappings[1:]),
    )
    assert "source-payload-changed" in _codes(
        validate_legacy_canvas_migration(source, source, stale)
    )


def test_digest_binds_full_source_candidate_bytes_and_mapping() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"][2]["text"] = "Reviewed replacement"
    candidate = _canvas(candidate_value)
    rows = inventory_legacy_canvas(source)
    changed_row = next(
        row for row in inventory_legacy_canvas(candidate) if row.element_id == "human-note"
    )
    mappings = tuple(
        LegacyCanvasElementMapping(
            row.kind,
            row.element_id,
            row.payload_sha256,
            "reviewed_rewrite",
            target_id=row.element_id,
            target_payload_sha256=changed_row.payload_sha256,
        )
        if row.element_id == "human-note"
        else LegacyCanvasElementMapping(row.kind, row.element_id, row.payload_sha256, "preserve")
        for row in rows
    )
    plan = _plan(source, candidate, mappings)
    pending = validate_legacy_canvas_migration(source, candidate, plan)
    source_changed = source.replace(b"My untouched note", b"My edited note")
    report = validate_legacy_canvas_migration(
        source_changed, candidate, plan, approved_review_digest=pending.plan_digest
    )
    assert {"source-changed", "source-payload-changed", "human-review-required"}.issubset(
        _codes(report)
    )
    candidate_reformatted = json.dumps(json.loads(candidate), indent=2).encode()
    report = validate_legacy_canvas_migration(
        source, candidate_reformatted, plan, approved_review_digest=pending.plan_digest
    )
    assert {"candidate-changed", "human-review-required"}.issubset(_codes(report))
    remapped = replace(
        plan, mappings=(replace(plan.mappings[0], disposition="retire"), *plan.mappings[1:])
    )
    report = validate_legacy_canvas_migration(
        source, candidate, remapped, approved_review_digest=pending.plan_digest
    )
    assert "human-review-required" in _codes(report)


@pytest.mark.parametrize(
    "content",
    [
        b'{"nodes":[],"nodes":[],"edges":[]}',
        b'{"nodes":[],"edges":[],"extra":1}',
        b'{"nodes":[],"edges":[],"extra":NaN}',
        b'{"nodes":[],"edges":[],"extra":1e309}',
        b"not JSON",
    ],
)
def test_malformed_json_canvas_is_not_inventoried(content: bytes) -> None:
    with pytest.raises(LegacyCanvasMigrationError):
        inventory_legacy_canvas(content)


def test_duplicate_ids_cross_type_collision_and_dangling_edges_are_rejected() -> None:
    source = json.loads(_fixture())
    source["nodes"].append(dict(source["nodes"][0]))
    with pytest.raises(LegacyCanvasMigrationError):
        inventory_legacy_canvas(_canvas(source))
    source = json.loads(_fixture())
    source["nodes"][0]["type"] = []
    with pytest.raises(LegacyCanvasMigrationError):
        inventory_legacy_canvas(_canvas(source))
    source = json.loads(_fixture())
    source["edges"][0]["id"] = "root"
    with pytest.raises(LegacyCanvasMigrationError, match="collide"):
        inventory_legacy_canvas(_canvas(source))
    source = json.loads(_fixture())
    source["edges"][0]["toNode"] = "missing"
    with pytest.raises(LegacyCanvasMigrationError):
        inventory_legacy_canvas(_canvas(source))


def test_duplicate_generated_paths_are_rejected() -> None:
    source = json.loads(_fixture())
    source["nodes"][1]["text"] = _marked("# Duplicate", "root")
    with pytest.raises(LegacyCanvasMigrationError, match="duplicate generated"):
        inventory_legacy_canvas(_canvas(source))


def test_retired_old_id_cannot_be_reused_as_a_different_element_kind() -> None:
    source = _fixture()
    candidate_value = json.loads(source)
    candidate_value["nodes"] = [
        node for node in candidate_value["nodes"] if node["id"] != "human-note"
    ]
    candidate_value["edges"] = [
        edge for edge in candidate_value["edges"] if edge["id"] != "human-edge"
    ]
    candidate_value["edges"].append({"id": "human-note", "fromNode": "root", "toNode": "task"})
    candidate = _canvas(candidate_value)
    base = _plan(source, candidate)
    retired = tuple(
        replace(row, disposition="retire") if row.source_id in {"human-note", "human-edge"} else row
        for row in base.mappings
    )
    plan = replace(base, mappings=retired)
    pending = validate_legacy_canvas_migration(source, candidate, plan)
    report = validate_legacy_canvas_migration(
        source, candidate, plan, approved_review_digest=pending.plan_digest
    )
    assert "not-retired" in _codes(report)
