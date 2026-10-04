"""Explicit capacity boundaries; synthetic inputs, no real Vault operations."""

import json
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.batch import _validate_targeted_repair
from scholar_workflow.analysis.complete_reference import TemplateNode, _layout_tree
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument, ConformanceReport
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_v5_toy.json"
SCHEMA = Path(__file__).resolve().parents[2] / "contracts" / "analysis-ir.schema.json"


@pytest.mark.parametrize("leaf_height,expected_height,expected_gutter", [(135, 9144, 340), (136, 9208, 344)])
def test_dense_aligned_gutter_remains_bounded(leaf_height, expected_height, expected_gutter):
    # Independent geometry: 64 equal leaves, 63 eight-pixel gaps, five layers.
    widths = [200, 400, 400, 440, 432]
    root = TemplateNode("root", "Synthetic", "root", None, "Synthetic", widths[0], 50)
    chain = [root]
    for depth, width in enumerate(widths[1:], 1):
        node = TemplateNode(f"layer-{depth}", "Label", "group", None, "Label", width, 50)
        chain[-1].children = [node]
        chain.append(node)
    chain[-1].children = [
        TemplateNode(f"leaf-{i}", "Synthetic", "point", None, "Synthetic", 1000, leaf_height)
        for i in range(64)
    ]
    _layout_tree(root, expanded=True)
    leaves = chain[-1].children
    expected_width = 2872 + 5 * expected_gutter
    assert {node.x for node in leaves} == {expected_width - 1000}
    assert max(node.x + node.width for node in leaves) == expected_width
    assert min(node.y for node in leaves) == 0
    assert max(node.y + node.height for node in leaves) == expected_height
    assert all(node.height == leaf_height for node in leaves)
    assert all(right.y - (left.y + left.height) == 8 for left, right in pairwise(leaves))
    assert all(right.x - (left.x + left.width) == expected_gutter for left, right in pairwise(chain))
    assert (expected_height / expected_width <= 2) == (leaf_height == 135)


@pytest.mark.parametrize("leaf_height,expected_height,expected_gutter", [(135, 9144, 341), (136, 9208, 344)])
def test_four_interval_dense_geometry(leaf_height, expected_height, expected_gutter):
    widths = [200, 568, 440, 1000]
    root = TemplateNode("root", "Synthetic", "root", None, "Synthetic", widths[0], 50)
    chain = [root]
    for depth, width in enumerate(widths[1:], 1):
        node = TemplateNode(f"layer-{depth}", "Label", "group", None, "Label", width, 50)
        chain[-1].children = [node]
        chain.append(node)
    leaves = [
        TemplateNode(f"leaf-{i}", "Synthetic", "point", None, "Synthetic", 1000, leaf_height)
        for i in range(64)
    ]
    chain[-1].children = leaves
    _layout_tree(root, expanded=True)
    expected_width = 3208 + 4 * expected_gutter
    assert {node.x for node in leaves} == {expected_width - 1000}
    assert max(node.y + node.height for node in leaves) == expected_height
    assert min(node.y for node in leaves) == 0
    assert all(node.height == leaf_height for node in leaves)
    assert all(right.y - left.y - left.height == 8 for left, right in pairwise(leaves))
    assert (expected_height / expected_width <= 2) == (leaf_height == 135)


def capacity_input(count, capacity=None):
    payload = json.loads(FIXTURE.read_text())
    payload["claims"] = [
        {
            "claim_id": f"limit-{i}",
            "role": "limitation",
            "outline_path": f"limitation/explanation/limit-{i}",
            "title": f"Synthetic limit {i}",
            "body": "No scientific claim is made by this synthetic capacity record.",
            "evidence": {"kind": "not_applicable", "detail": "Synthetic boundary input."},
        }
        for i in range(count)
    ]
    if capacity is not None:
        payload["capacity"] = capacity
    return payload


@pytest.mark.parametrize("count,capacity", [(40, None), (68, "expanded"), (96, "expanded")])
def test_explicit_record_boundaries(count, capacity):
    payload = capacity_input(count, capacity)
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(payload, json.loads(SCHEMA.read_text()))
    assert len(document.claims) == count
    assert document.fact_node_limit == (96 if capacity else 40)
    assert document.managed_node_limit == (192 if capacity else 96)


@pytest.mark.parametrize("count,capacity", [(41, None), (97, "expanded")])
def test_over_budget_records_are_rejected(count, capacity):
    with pytest.raises(ValidationError, match="semantic Canvas nodes"):
        AnalysisDocument.model_validate(capacity_input(count, capacity))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(capacity_input(count, capacity), json.loads(SCHEMA.read_text()))


def test_unknown_capacity_and_old_version_are_rejected():
    payload = capacity_input(1, "expanded")
    old = deepcopy(payload)
    old["schema_version"] = 4
    old["profile"]["framework"] = "reference_tree"
    old["profile"]["roles"] = ["abstract", "introduction", "method", "limitation"]
    with pytest.raises(ValidationError, match="capacity"):
        AnalysisDocument.model_validate(old)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(old, json.loads(SCHEMA.read_text()))
    payload["capacity"] = "unlimited"
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, json.loads(SCHEMA.read_text()))


def test_default_serialization_does_not_change_old_input_shape():
    payload = capacity_input(1)
    document = AnalysisDocument.model_validate(payload)
    assert "capacity" not in document.model_dump(mode="json")


def test_capacity_does_not_change_projection_or_bypass_conformance():
    payload = json.loads(FIXTURE.read_text())
    standard = AnalysisDocument.model_validate(payload)
    payload["capacity"] = "expanded"
    expanded = AnalysisDocument.model_validate(payload)
    old_bundle, old_baseline = render_analysis_projection(standard, note_stem="Capacity sample")
    bundle, baseline = render_analysis_projection(expanded, note_stem="Capacity sample")
    assert bundle == old_bundle
    assert baseline.document.capacity == "expanded"
    assert validate_bundle(expanded, bundle, note_stem="Capacity sample").ok
    with pytest.raises(AnalysisUpdateError, match="capacity"):
        plan_analysis_update(
            current=old_bundle, baseline=old_baseline, update=expanded, note_stem="Capacity sample"
        )
    damaged = deepcopy(bundle)
    damaged.canvas["nodes"][0]["height"] = 421
    assert not validate_bundle(expanded, damaged, note_stem="Capacity sample").ok


def test_baseline_expanded_budget_remains_bounded():
    payload = json.loads(FIXTURE.read_text())
    payload["capacity"] = "expanded"
    _, baseline = render_analysis_projection(
        AnalysisDocument.model_validate(payload), note_stem="Capacity sample"
    )
    raw = baseline.model_dump(mode="json")
    ir_schema = json.loads(SCHEMA.read_text())
    registry = Registry().with_resource(ir_schema["$id"], Resource.from_contents(ir_schema))
    baseline_schema = json.loads(SCHEMA.with_name("analysis-baseline.schema.json").read_text())
    while len(raw["generated_node_ids"]) < 192:
        candidate = f"{len(raw['generated_node_ids']):016x}"
        if candidate in raw["generated_node_ids"]:
            candidate = f"{len(raw['generated_node_ids']) + 10000:016x}"
        raw["generated_node_ids"].append(candidate)
    assert len(AnalysisBaseline.model_validate(raw).generated_node_ids) == 192
    jsonschema.Draft202012Validator(baseline_schema, registry=registry).validate(raw)
    raw["generated_node_ids"].append("ffffffffffffffff")
    with pytest.raises(ValidationError, match="192"):
        AnalysisBaseline.model_validate(raw)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(baseline_schema, registry=registry).validate(raw)


def test_focused_update_retains_expanded_capacity():
    payload = json.loads(FIXTURE.read_text())
    payload["capacity"] = "expanded"
    original = AnalysisDocument.model_validate(payload)
    bundle, baseline = render_analysis_projection(original, note_stem="Capacity sample")
    focused = deepcopy(payload)
    focused["profile"]["kind"] = "focused"
    focused["profile"]["roles"] = ["limitation"]
    focused["claims"] = [claim for claim in focused["claims"] if claim["role"] == "limitation"]
    plan = plan_analysis_update(
        current=bundle, baseline=baseline,
        update=AnalysisDocument.model_validate(focused), note_stem="Capacity sample",
    )
    assert plan.status == "ready"
    assert plan.document.capacity == "expanded"
    assert plan.baseline.document.capacity == "expanded"
    assert plan.proposed == bundle


def test_targeted_repair_cannot_switch_capacity():
    payload = json.loads(FIXTURE.read_text())
    original = AnalysisDocument.model_validate(payload)
    payload["capacity"] = "expanded"
    repaired = AnalysisDocument.model_validate(payload)
    with pytest.raises(ValueError, match="capacity"):
        _validate_targeted_repair(original, repaired, ConformanceReport(ok=False, findings=[]))


def test_seventy_independent_records_reach_the_paired_projection():
    """38 approved fixture records plus 8 modules with 4 distinct points each."""
    payload = json.loads(FIXTURE.read_text())
    for index in range(1, 9):
        payload["claims"].append({
            "claim_id": f"expanded-module-{index}",
            "role": "method",
            "outline_path": f"method/modules/expanded-module-{index}",
            "title": f"Synthetic expanded module {index}",
            "container": True,
            "body": "",
            "evidence": {"kind": "not_applicable", "detail": "Structural container only"},
            "points": [
                {
                    "point_id": slot,
                    "text": f"Synthetic module {index} has no source fact for {slot}.",
                    "evidence": {
                        "kind": "not_applicable",
                        "detail": "Synthetic capacity fixture; no scientific claim.",
                    },
                }
                for slot in ("motivation", "method", "why-it-works", "technical-advantage")
            ],
        })
    with pytest.raises(ValidationError, match="40 generated semantic Canvas nodes"):
        AnalysisDocument.model_validate(payload)
    payload["capacity"] = "expanded"
    document = AnalysisDocument.model_validate(payload)
    assert sum(not claim.container for claim in document.claims) + sum(
        len(claim.points) for claim in document.claims
    ) == 70
    bundle, baseline = render_analysis_projection(document, note_stem="Expanded capacity sample")
    assert validate_bundle(document, bundle, note_stem="Expanded capacity sample").ok
    assert 96 < len(bundle.canvas["nodes"]) <= 192
    # Independent dimensions captured before the fix: 3056 x 8250. Only gutters
    # may change; tall-node readability and the complete vertical bands remain.
    nodes = bundle.canvas["nodes"]
    width = max(node["x"] + node["width"] for node in nodes) - min(node["x"] for node in nodes)
    height = max(node["y"] + node["height"] for node in nodes) - min(node["y"] for node in nodes)
    assert height == 8250
    assert 4125 <= width <= 4131
    assert len(baseline.generated_node_ids) == len(bundle.canvas["nodes"])
    for index in range(1, 9):
        for slot in ("motivation", "method", "why-it-works", "technical-advantage"):
            text = f"Synthetic module {index} has no source fact for {slot}."
            assert text in bundle.markdown
            assert sum(text in node["text"] for node in bundle.canvas["nodes"]) == 1
