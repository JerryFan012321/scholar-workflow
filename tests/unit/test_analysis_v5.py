"""Independent v5 expectations transcribed from the approved synthetic plan.

The source sentences and 38 record mappings below are handwritten expectations,
not snapshots of a renderer. No real library, Vault or external reader is used.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter, deque
from copy import deepcopy
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_v5_toy.json"
NOTE_STEM = "Synthetic Scalar Reader Analysis"
ARTIFACT_ID = "analysis:paper:synthetic-scalar-reader"
ROLES = ("abstract", "introduction", "method", "experiments", "limitation")
SOURCE = {
    0: 'Estimate a scalar from three measurements. Q_TASK: "Three inputs, one scalar."',
    1: 'The first module subtracts the arithmetic mean. Q_METHOD: "Subtract the mean <before> aggregation & preserve signs."',
    2: 'Without centering, the synthetic error is 9; with centering, it is 4. Q_ABLATION: "Error changes from 9 to 4 in this toy comparison."',
    3: 'Only three synthetic measurements are considered. Q_LIMIT: "Evidence is limited to the three-input toy setting."',
}

# ID, claim ID, optional point ID, exact approved readable statement.
RECORDS = (
    ("A-T", "a-t", None, "Estimate a scalar from three measurements."),
    ("A-C", "a-c", None, "No prior-method comparison is defined in this synthetic source."),
    ("A-I-1", "a-i", "motivation", "This synthetic source supplies no abstract-level insight."),
    (
        "A-I-2",
        "a-i",
        "advantage",
        "No abstract-level benefit is specified in this synthetic source.",
    ),
    ("A-K1-1", "a-k1", "summary", "No abstract-level summary for contribution 1 is supplied."),
    ("A-K1-2", "a-k1", "advantage", "No abstract-level benefit for contribution 1 is supplied."),
    ("A-K2-1", "a-k2", "summary", "No abstract-level summary for contribution 2 is supplied."),
    ("A-K2-2", "a-k2", "advantage", "No abstract-level benefit for contribution 2 is supplied."),
    ("A-E", "a-e", None, "This synthetic source supplies no abstract-level experimental account."),
    ("I-T", "i-t", None, "No application scenario is supplied in this synthetic source."),
    ("I-C1-1", "i-c1", "previous-method", "No earlier method is supplied for challenge 1."),
    ("I-C1-2", "i-c1", "limitation", "No failure case is supplied for challenge 1."),
    ("I-C1-3", "i-c1", "technical-reason", "No technical cause is supplied for challenge 1."),
    ("I-C2-1", "i-c2", "previous-method", "No earlier method is supplied for challenge 2."),
    ("I-C2-2", "i-c2", "limitation", "No failure case is supplied for challenge 2."),
    ("I-C2-3", "i-c2", "technical-reason", "No technical cause is supplied for challenge 2."),
    ("I-P", "i-p", None, "No introduction-level innovation statement is supplied."),
    (
        "I-K1-1",
        "i-k1",
        "purpose",
        "No introduction-level problem statement is supplied for contribution 1.",
    ),
    (
        "I-K1-2",
        "i-k1",
        "how",
        "No introduction-level implementation is supplied for contribution 1.",
    ),
    (
        "I-K1-3",
        "i-k1",
        "advantage",
        "No introduction-level advantage is supplied for contribution 1.",
    ),
    (
        "I-K2-1",
        "i-k2",
        "purpose",
        "No introduction-level problem statement is supplied for contribution 2.",
    ),
    (
        "I-K2-2",
        "i-k2",
        "how",
        "No introduction-level implementation is supplied for contribution 2.",
    ),
    (
        "I-K2-3",
        "i-k2",
        "advantage",
        "No introduction-level advantage is supplied for contribution 2.",
    ),
    ("I-D", "i-d", None, "No demo is defined in this synthetic source."),
    (
        "M-O1",
        "m-o",
        "task-io",
        "This fixture tests the task/input/output slot without adding a method summary.",
    ),
    (
        "M-O2",
        "m-o",
        "steps",
        "No complete ordered procedure is supplied; no steps may be invented.",
    ),
    ("M-1-1", "m-1", "motivation", "No motivation statement is supplied for module 1."),
    ("M-1-2", "m-1", "method", "The first module subtracts the arithmetic mean."),
    ("M-1-3", "m-1", "why-it-works", "No causal explanation is supplied for module 1."),
    ("M-1-4", "m-1", "technical-advantage", "No technical advantage is supplied for module 1."),
    ("M-2-1", "m-2", "motivation", "No motivation statement is supplied for module 2."),
    ("M-2-2", "m-2", "method", "No implementation statement is supplied for module 2."),
    ("M-2-3", "m-2", "why-it-works", "No causal explanation is supplied for module 2."),
    ("M-2-4", "m-2", "technical-advantage", "No technical advantage is supplied for module 2."),
    ("E-C", "e-c", None, "No independent baseline comparison is defined in this synthetic source."),
    ("E-A1", "e-a", "components", "The toy error is 9 without centering and 4 with centering."),
    (
        "E-A2",
        "e-a",
        "design-choices",
        "The toy comparison supports a centering effect only within this synthetic setup.",
    ),
    (
        "L-R",
        "l-r",
        None,
        "Only three synthetic measurements are considered, so the described evidence is limited to this toy setting.",
    ),
)
FACT_PAGES = {"A-T": 1, "M-1-2": 2, "E-A1": 3, "E-A2": 3, "L-R": 4}
POINT_LABELS = {
    "a-i": {
        "motivation": "One-sentence insight / motivation",
        "advantage": "Benefit of the insight / motivation",
    },
    "a-k1": {
        "summary": "One-sentence technical contribution",
        "advantage": "Benefit of the technical contribution",
    },
    "a-k2": {
        "summary": "One-sentence technical contribution",
        "advantage": "Benefit of the technical contribution",
    },
    "i-c1": {
        "previous-method": "Previous method",
        "limitation": "Failure cases (Limitation)",
        "technical-reason": "Technical reason",
    },
    "i-c2": {
        "previous-method": "Previous method",
        "limitation": "Failure cases (Limitation)",
        "technical-reason": "Technical reason",
    },
    "i-k1": {
        "purpose": "Problem addressed",
        "how": "How it is done",
        "advantage": "Advantage / insight",
    },
    "i-k2": {
        "purpose": "Problem addressed",
        "how": "How it is done",
        "advantage": "Advantage / insight",
    },
    "m-o": {"task-io": "Task / input / output", "steps": "Method / steps"},
    "m-1": {
        "motivation": "Motivation",
        "method": "Method",
        "why-it-works": "Why it works",
        "technical-advantage": "Technical advantage",
    },
    "m-2": {
        "motivation": "Motivation",
        "method": "Method",
        "why-it-works": "Why it works",
        "technical-advantage": "Technical advantage",
    },
    "e-a": {
        "components": "Effects of core contributions / important components",
        "design-choices": "Effects of design choices in each pipeline module",
    },
}


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _document() -> AnalysisDocument:
    return AnalysisDocument.model_validate(_payload())


def _node_id(path: str) -> str:
    # Standard, externally specified node identity, not a renderer snapshot.
    return sha256(f"{ARTIFACT_ID}\n{path}".encode()).hexdigest()[:16]


def _claim(payload: dict, claim_id: str) -> dict:
    return next(item for item in payload["claims"] if item["claim_id"] == claim_id)


def _point(payload: dict, claim_id: str, point_id: str) -> dict:
    return next(
        item for item in _claim(payload, claim_id)["points"] if item["point_id"] == point_id
    )


def _record_node_id(claim: dict, point_id: str | None) -> str:
    path = f"role/{claim['role']}/{claim['claim_id']}"
    return _node_id(path + (f"/point/{point_id}" if point_id else ""))


def _record_anchor(claim_id: str, point_id: str | None) -> str:
    return f"point-{len(claim_id)}-{claim_id}-{point_id}" if point_id else f"claim-{claim_id}"


def _render() -> tuple[AnalysisDocument, AnalysisBundle]:
    document = _document()
    return document, render_analysis(document, note_stem=NOTE_STEM)


def _changed_canvas(bundle: AnalysisBundle) -> dict:
    return deepcopy(bundle.canvas)


def _reject(document: AnalysisDocument, bundle: AnalysisBundle, canvas: dict) -> None:
    report = validate_bundle(
        document, AnalysisBundle(markdown=bundle.markdown, canvas=canvas), note_stem=NOTE_STEM
    )
    assert not report.ok, "The independently malformed candidate was incorrectly accepted."
    assert report.findings, "Rejected output must include actionable findings."


def _heading(text: str) -> str:
    first = text.splitlines()[0].lstrip("# ").strip()
    return first[2:-2] if first.startswith("**") and first.endswith("**") else first


def _decode_markdown_literal(text: str) -> str:
    return html.unescape(re.sub(r"\\([\\`*_{}\[\]()#+\-.!|>^])", r"\1", text))


def _source_fidelity(payload: dict) -> list[str]:
    """Only the independent synthetic source, not structural conformance, proves this."""
    findings = []
    for claim in payload["claims"]:
        evidence_items = [
            claim["evidence"],
            *(point["evidence"] for point in claim.get("points", [])),
        ]
        for evidence in evidence_items:
            for span in evidence.get("source_spans", []):
                if span.get("quote") not in SOURCE.get(span["page_index"], ""):
                    findings.append(f"{claim['claim_id']}: quote differs from synthetic source")
    return findings


def _hierarchy_depths(canvas: dict) -> dict[str, int]:
    depths = {_node_id("root"): 0}
    children = {}
    for edge in canvas["edges"]:
        children.setdefault(edge["fromNode"], []).append(edge["toNode"])
    pending = deque(depths)
    while pending:
        parent = pending.popleft()
        for child in children.get(parent, []):
            assert child not in depths, (
                "Generated edges must form a tree, not multiple-parent or cyclic graph."
            )
            depths[child] = depths[parent] + 1
            pending.append(child)
    assert set(depths) == {node["id"] for node in canvas["nodes"]}
    return depths


def _square_segments(
    edge: dict, nodes: dict
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Actual Advanced Canvas right-to-left square path, independently calculated.

    The approved plugin's square Z path uses edge-midpoint endpoints and mid-X.
    Shared source trunks may coincide; unrelated branches must not cross them.
    """
    source, target = nodes[edge["fromNode"]], nodes[edge["toNode"]]
    assert edge["fromSide"] == "right"
    assert edge["toSide"] == "left"
    assert edge.get("fromEnd", "none") == edge.get("toEnd", "none") == "none"
    assert edge["styleAttributes"]["pathfindingMethod"] == "square"
    start = (source["x"] + source["width"], source["y"] + source["height"] / 2)
    finish = (target["x"], target["y"] + target["height"] / 2)
    middle_x = (start[0] + finish[0]) / 2
    points = (start, (middle_x, start[1]), (middle_x, finish[1]), finish)
    return [(left, right) for left, right in pairwise(points) if left != right]


def _segments_intersect(left: tuple, right: tuple) -> bool:
    a, b = left
    c, d = right
    left_horizontal, right_horizontal = a[1] == b[1], c[1] == d[1]
    if left_horizontal and right_horizontal:
        return a[1] == c[1] and max(min(a[0], b[0]), min(c[0], d[0])) <= min(
            max(a[0], b[0]), max(c[0], d[0])
        )
    if not left_horizontal and not right_horizontal:
        return a[0] == c[0] and max(min(a[1], b[1]), min(c[1], d[1])) <= min(
            max(a[1], b[1]), max(c[1], d[1])
        )
    horizontal, vertical = (left, right) if left_horizontal else (right, left)
    h1, h2 = horizontal
    v1, v2 = vertical
    return min(h1[0], h2[0]) <= v1[0] <= max(h1[0], h2[0]) and min(v1[1], v2[1]) <= h1[1] <= max(
        v1[1], v2[1]
    )


def _segment_passes_node(segment: tuple, node: dict) -> bool:
    start, finish = segment
    left, right = node["x"], node["x"] + node["width"]
    top, bottom = node["y"], node["y"] + node["height"]
    if start[1] == finish[1]:
        return top < start[1] < bottom and max(min(start[0], finish[0]), left) < min(
            max(start[0], finish[0]), right
        )
    return left < start[0] < right and max(min(start[1], finish[1]), top) < min(
        max(start[1], finish[1]), bottom
    )


def _assert_alignment_and_non_crossing(canvas: dict) -> None:
    nodes = {node["id"]: node for node in canvas["nodes"]}
    depths = _hierarchy_depths(canvas)
    left_edges = {}
    for node_id, depth in depths.items():
        left_edges.setdefault(depth, set()).add(nodes[node_id]["x"])
    assert all(len(positions) == 1 for positions in left_edges.values()), left_edges
    routes = [(edge, _square_segments(edge, nodes)) for edge in canvas["edges"]]
    for index, (edge, segments) in enumerate(routes):
        for node_id, node in nodes.items():
            if node_id not in {edge["fromNode"], edge["toNode"]}:
                assert not any(_segment_passes_node(segment, node) for segment in segments), (
                    edge["id"],
                    node_id,
                )
        for other_edge, other_segments in routes[index + 1 :]:
            if edge["fromNode"] == other_edge["fromNode"]:
                continue  # Shared sibling trunk is explicitly allowed.
            assert not any(_segments_intersect(a, b) for a in segments for b in other_segments), (
                edge["id"],
                other_edge["id"],
            )


def test_input_is_an_exact_38_record_transcription_without_container_facts() -> None:
    payload = _payload()
    assert len(RECORDS) == 38
    assert payload["schema_version"] == 5
    assert payload["profile"]["framework"] == "reference_tree_v5"
    counts = Counter()
    evidence_counts = Counter()
    actual_records = 0
    for claim in payload["claims"]:
        if claim.get("container"):
            assert claim["body"] == ""
            assert claim["evidence"] == {
                "kind": "not_applicable",
                "detail": "Structural container only",
            }
        else:
            actual_records += 1
        actual_records += len(claim.get("points", []))
    assert actual_records == 38
    for record_id, claim_id, point_id, text in RECORDS:
        claim = _claim(payload, claim_id)
        item = _point(payload, claim_id, point_id) if point_id else claim
        assert item["text" if point_id else "body"] == text, record_id
        counts[claim["role"]] += 1
        evidence_counts[item["evidence"]["kind"]] += 1
    assert dict(counts) == {
        "abstract": 9,
        "introduction": 15,
        "method": 10,
        "experiments": 3,
        "limitation": 1,
    }
    assert dict(evidence_counts) == {
        "author_stated": 4,
        "not_applicable": 33,
        "analysis_inference": 1,
    }
    assert _source_fidelity(payload) == []


def test_checked_ir_and_baseline_contracts_accept_the_approved_input() -> None:
    from scholar_workflow.analysis.updates import create_baseline

    root = FIXTURE.parents[2]
    ir_schema = json.loads((root / "contracts/analysis-ir.schema.json").read_text())
    baseline_schema = json.loads((root / "contracts/analysis-baseline.schema.json").read_text())
    document, bundle = _render()
    jsonschema.Draft202012Validator(ir_schema).validate(document.model_dump(mode="json"))
    baseline = create_baseline(document, bundle, note_stem=NOTE_STEM)
    registry = Registry().with_resource(ir_schema["$id"], Resource.from_contents(ir_schema))
    jsonschema.Draft202012Validator(baseline_schema, registry=registry).validate(
        baseline.model_dump(mode="json")
    )


def test_five_branches_preserve_full_markdown_and_all_38_editable_records() -> None:
    document, bundle = _render()
    assert [role.value for role in document.profile.roles] == list(ROLES)
    assert re.findall(r"^## (.+)$", bundle.markdown, flags=re.MULTILINE) == [
        "Abstract",
        "Introduction",
        "Method",
        "Experiments",
        "Limitation",
    ]
    payload = _payload()
    nodes = {node["id"]: node for node in bundle.canvas["nodes"]}
    assert len(nodes) == len(bundle.canvas["nodes"])
    for record_id, claim_id, point_id, text in RECORDS:
        claim = _claim(payload, claim_id)
        node = nodes[_record_node_id(claim, point_id)]
        assert node["type"] == "text", record_id
        assert text in bundle.markdown, record_id
        assert text in node["text"], record_id
        anchor = _record_anchor(claim_id, point_id)
        assert f"^{anchor}" in bundle.markdown
        assert f"[[{NOTE_STEM}#^{anchor}|Analysis" in node["text"]
        if point_id:
            assert _heading(node["text"]) == POINT_LABELS[claim_id][point_id]
    assert "Structural container only" not in bundle.markdown
    assert "Structural container only" not in json.dumps(bundle.canvas)
    assert "sw-analysis-claim" not in bundle.markdown
    assert not re.search(r"^#{1,6} Evidence\b", bundle.markdown, re.MULTILINE)
    report = validate_bundle(document, bundle, note_stem=NOTE_STEM)
    assert report.ok, [(finding.code, finding.path, finding.message) for finding in report.findings]


def test_every_named_point_has_its_own_parent_and_no_cross_instance_edge() -> None:
    _, bundle = _render()
    for claim in _payload()["claims"]:
        parent = _node_id(f"role/{claim['role']}/{claim['claim_id']}")
        for point in claim.get("points", []):
            child = _record_node_id(claim, point["point_id"])
            incoming = [edge for edge in bundle.canvas["edges"] if edge["toNode"] == child]
            assert len(incoming) == 1
            assert incoming[0]["fromNode"] == parent
    for point_id in ("motivation", "method", "why-it-works", "technical-advantage"):
        assert _record_node_id(_claim(_payload(), "m-1"), point_id) != _record_node_id(
            _claim(_payload(), "m-2"), point_id
        )


def test_source_projection_is_per_record_and_quotes_are_markdown_only() -> None:
    _, bundle = _render()
    payload = _payload()
    nodes = {node["id"]: node for node in bundle.canvas["nodes"]}
    quote_lines = [
        _decode_markdown_literal(line.strip()[2:])
        for line in bundle.markdown.splitlines()
        if line.strip().startswith("> ")
    ]
    assert sum(line.startswith("Q_") for line in quote_lines) == 5
    for record_id, claim_id, point_id, _ in RECORDS:
        claim = _claim(payload, claim_id)
        node_text = nodes[_record_node_id(claim, point_id)]["text"]
        if record_id in FACT_PAGES:
            page = FACT_PAGES[record_id]
            assert f"zotero://open-pdf/library/items/SYNTH001?page={page}" in node_text
            item = _point(payload, claim_id, point_id) if point_id else claim
            excerpt = item["evidence"]["source_spans"][0]["quote"]
            assert excerpt in quote_lines
            assert ("〔Inference〕" if record_id == "E-A2" else "〔Author〕") in node_text
        else:
            assert "〔N/A〕" in node_text
            assert "zotero://" not in node_text
    canvas_text = json.dumps(bundle.canvas, ensure_ascii=False)
    for marker in ("Q_TASK", "Q_METHOD", "Q_ABLATION", "Q_LIMIT"):
        assert marker not in canvas_text
    assert "&lt;before&gt;" in bundle.markdown
    assert "&amp;" in bundle.markdown
    assert "原文" not in canvas_text
    assert "正文" not in canvas_text
    assert "对应挑战" not in canvas_text
    assert "corresponding challenge" not in canvas_text.lower()


def test_geometry_keeps_all_generated_nodes_and_reports_the_real_budget() -> None:
    _, bundle = _render()
    nodes = bundle.canvas["nodes"]
    assert len(nodes) <= 96, f"Actual expanded graph has {len(nodes)} nodes; do not hide records."
    assert all(0 < node["height"] <= 420 for node in nodes)
    assert all(node["width"] > 0 for node in nodes)
    width = max(node["x"] + node["width"] for node in nodes) - min(node["x"] for node in nodes)
    height = max(node["y"] + node["height"] for node in nodes) - min(node["y"] for node in nodes)
    assert max(width / height, height / width) <= 2
    for index, left in enumerate(nodes):
        for right in nodes[index + 1 :]:
            intersects = (
                left["x"] < right["x"] + right["width"]
                and right["x"] < left["x"] + left["width"]
                and left["y"] < right["y"] + right["height"]
                and right["y"] < left["y"] + left["height"]
            )
            assert not intersects, (left["id"], right["id"])


def test_same_depth_left_edges_align_and_square_routes_do_not_cross_or_pass_nodes() -> None:
    _, bundle = _render()
    _assert_alignment_and_non_crossing(bundle.canvas)


def test_alignment_negative_moves_only_one_same_depth_point() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    point_id = _record_node_id(_claim(_payload(), "m-1"), "method")
    node = next(item for item in canvas["nodes"] if item["id"] == point_id)
    node["x"] += 14
    with pytest.raises(AssertionError):
        _assert_alignment_and_non_crossing(canvas)
    _reject(document, bundle, canvas)


def test_cross_branch_rewire_is_not_hidden_by_present_nodes_and_text() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    child_id = _record_node_id(_claim(_payload(), "m-1"), "method")
    edge = next(item for item in canvas["edges"] if item["toNode"] == child_id)
    edge["fromNode"] = _node_id("role/abstract/a-k1")
    with pytest.raises(AssertionError):
        _assert_alignment_and_non_crossing(canvas)
    _reject(document, bundle, canvas)


def test_n01_whole_requires_an_independent_experiments_branch() -> None:
    payload = _payload()
    payload["profile"]["roles"].remove("experiments")
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    branch_id = _node_id("role/experiments")
    canvas["nodes"] = [node for node in canvas["nodes"] if node["id"] != branch_id]
    canvas["edges"] = [
        edge for edge in canvas["edges"] if branch_id not in {edge["fromNode"], edge["toNode"]}
    ]
    assert _node_id("role/abstract") in {node["id"] for node in canvas["nodes"]}
    assert _record_node_id(_claim(_payload(), "a-e"), None) in {
        node["id"] for node in canvas["nodes"]
    }
    _reject(document, bundle, canvas)


def test_n02_unknown_method_point_is_not_a_valid_template_slot() -> None:
    payload = _payload()
    _point(payload, "m-1", "why-it-works")["point_id"] = "limitation"
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)


def test_n03_equal_text_in_a_details_card_does_not_replace_four_point_nodes() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    claim = _claim(_payload(), "m-1")
    point_ids = {_record_node_id(claim, point["point_id"]) for point in claim["points"]}
    removed = [node for node in canvas["nodes"] if node["id"] in point_ids]
    canvas["nodes"] = [node for node in canvas["nodes"] if node["id"] not in point_ids]
    canvas["edges"] = [
        edge
        for edge in canvas["edges"]
        if edge["fromNode"] not in point_ids and edge["toNode"] not in point_ids
    ]
    detail = deepcopy(removed[0])
    detail["id"] = _node_id("role/method/m-1/details")
    detail["text"] = "\n\n".join(node["text"] for node in removed)
    canvas["nodes"].append(detail)
    _reject(document, bundle, canvas)


def test_n04_same_named_slot_in_another_module_is_the_wrong_endpoint() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    target = _record_node_id(_claim(_payload(), "m-2"), "method")
    edge = next(item for item in canvas["edges"] if item["toNode"] == target)
    edge["toNode"] = _record_node_id(_claim(_payload(), "m-1"), "method")
    _reject(document, bundle, canvas)


def test_n05_shared_source_page_does_not_allow_a_shared_wrong_analysis_block() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    target = _record_node_id(_claim(_payload(), "e-a"), "design-choices")
    node = next(item for item in canvas["nodes"] if item["id"] == target)
    node["text"] = node["text"].replace(
        _record_anchor("e-a", "design-choices"), _record_anchor("e-a", "components")
    )
    _reject(document, bundle, canvas)


def test_n06_valid_but_wrong_page_is_rejected_against_the_input_span() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    target = _record_node_id(_claim(_payload(), "m-1"), "method")
    node = next(item for item in canvas["nodes"] if item["id"] == target)
    node["text"] = node["text"].replace("SYNTH001?page=2", "SYNTH001?page=3")
    _reject(document, bundle, canvas)


def test_n07_original_excerpt_in_canvas_violates_markdown_only_boundary() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    target = _record_node_id(_claim(_payload(), "m-1"), "method")
    node = next(item for item in canvas["nodes"] if item["id"] == target)
    node["text"] += '\nQ_METHOD: "Subtract the mean <before> aggregation & preserve signs."'
    _reject(document, bundle, canvas)


def test_n08_an_inference_cannot_be_relabelled_as_an_author_fact() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    target = _record_node_id(_claim(_payload(), "e-a"), "design-choices")
    node = next(item for item in canvas["nodes"] if item["id"] == target)
    assert "〔Inference〕" in node["text"]
    node["text"] = node["text"].replace("〔Inference〕", "〔Author〕", 1)
    _reject(document, bundle, canvas)


def test_n09_translated_experiments_label_violates_explicit_english_output() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    node = next(item for item in canvas["nodes"] if item["id"] == _node_id("role/experiments"))
    node["text"] = "实验"
    _reject(document, bundle, canvas)


def test_n10_generated_node_overlap_is_rejected() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    left, right = canvas["nodes"][:2]
    right.update(x=left["x"], y=left["y"])
    _reject(document, bundle, canvas)


def test_n11_single_axis_three_to_one_stretch_is_rejected() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    nodes = canvas["nodes"]
    width = max(node["x"] + node["width"] for node in nodes) - min(node["x"] for node in nodes)
    minimum_y = min(node["y"] for node in nodes)
    maximum_y = max(node["y"] for node in nodes)
    scale = 3 * width / (maximum_y - minimum_y)
    for node in nodes:
        node["y"] = round(minimum_y + (node["y"] - minimum_y) * scale)
    # Only placement changes: node heights, text and all identities stay fixed.
    report = validate_bundle(
        document, AnalysisBundle(markdown=bundle.markdown, canvas=canvas), note_stem=NOTE_STEM
    )
    assert "canvas-aspect-limit" in {finding.code for finding in report.findings}


def test_n12_node_height_above_420_is_rejected() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    canvas["nodes"][0]["height"] = 421
    _reject(document, bundle, canvas)


def test_n13_a_corresponding_challenge_axis_cannot_be_a_generated_module_slot() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    parent_id = _node_id("role/method/m-1")
    parent = next(node for node in canvas["nodes"] if node["id"] == parent_id)
    child_id = _node_id("role/method/m-1/corresponding-challenge")
    canvas["nodes"].append(
        {
            "id": child_id,
            "type": "text",
            "text": "Corresponding challenge",
            "x": max(node["x"] + node["width"] for node in canvas["nodes"]) + 100,
            "y": parent["y"],
            "width": 180,
            "height": 80,
        }
    )
    canvas["edges"].append(
        {
            "id": "abcdef1234567890",
            "fromNode": parent_id,
            "toNode": child_id,
            "fromSide": "right",
            "toSide": "left",
            "fromEnd": "none",
            "toEnd": "none",
            "styleAttributes": {"pathfindingMethod": "square"},
        }
    )
    _reject(document, bundle, canvas)


def test_n14_five_dashboard_cards_do_not_satisfy_the_expanded_tree() -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    keep_ids = {_node_id("root"), *(_node_id(f"role/{role}") for role in ROLES)}
    all_text = "\n\n".join(node["text"] for node in canvas["nodes"])
    canvas["nodes"] = [node for node in canvas["nodes"] if node["id"] in keep_ids]
    for node in canvas["nodes"]:
        if node["id"] != _node_id("root"):
            node["text"] += "\n" + all_text
    canvas["edges"] = [
        edge
        for edge in canvas["edges"]
        if edge["fromNode"] in keep_ids and edge["toNode"] in keep_ids
    ]
    _reject(document, bundle, canvas)


@pytest.mark.parametrize("operation", ["visible-marker", "private-identity"])
def test_n15_machine_marks_do_not_belong_in_human_text_or_canvas_identity(operation: str) -> None:
    document, bundle = _render()
    canvas = _changed_canvas(bundle)
    if operation == "private-identity":
        canvas["sw_catalog_id"] = ARTIFACT_ID
    else:
        canvas["nodes"][0]["text"] += '\n<!-- sw-analysis-claim id="a-t" role="abstract" -->'
    _reject(document, bundle, canvas)


def test_n16_absent_availability_leaves_an_empty_slot_without_an_invented_fact() -> None:
    payload = _payload()
    claim = _claim(payload, "a-i")
    removed = next(point for point in claim["points"] if point["point_id"] == "advantage")
    claim["points"] = [point for point in claim["points"] if point["point_id"] != "advantage"]
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    assert removed["text"] not in bundle.markdown
    assert removed["text"] not in json.dumps(bundle.canvas)
    remaining = [row for row in RECORDS if row[0] != "A-I-2"]
    for _, _, _, text in remaining:
        assert text in bundle.markdown
    assert "Benefit of the insight / motivation" in json.dumps(bundle.canvas)
    assert validate_bundle(document, bundle, note_stem=NOTE_STEM).ok


def test_n17_a_paraphrase_does_not_pass_independent_source_quote_fidelity() -> None:
    payload = _payload()
    _point(payload, "m-1", "method")["evidence"]["source_spans"][0]["quote"] = (
        'Q_METHOD: "Remove the average prior to combination and keep signs."'
    )
    assert _source_fidelity(payload) == ["m-1: quote differs from synthetic source"]
    # Schema/render checks alone cannot prove a string matches an unseen source.
    # Deliberately do not expect the structural validator to read this SOURCE map.
