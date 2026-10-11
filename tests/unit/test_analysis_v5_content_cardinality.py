"""Content cardinality is not an IR-v5 presentation quota.

All statements, attachment identities and excerpts here are synthetic. The
sample counts cross former limits; they are not replacement limits. Five main
roles, each module's four named slots, evidence and identity checks remain
fixed. Geometry may reject a complete candidate, but cannot delete its content
or diagnose content cardinality as a formatting conflict. No Vault is touched.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from math import ceil
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.batch import _validate_targeted_repair
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument, ConformanceReport
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    create_baseline,
    plan_analysis_update,
    render_analysis_projection,
)

ROOT = Path(__file__).resolve().parents[2]
IR_SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
BASELINE_SCHEMA = json.loads((ROOT / "contracts/analysis-baseline.schema.json").read_text())
REGISTRY = Registry().with_resource(IR_SCHEMA["$id"], Resource.from_contents(IR_SCHEMA))
NOTE = "Synthetic Cardinality Analysis"
ROLES = ["abstract", "introduction", "method", "experiments", "limitation"]
MODULE_SLOTS = ("motivation", "method", "why-it-works", "technical-advantage")
# Role, outline prefix, fixed point slots or an open numbered point family.
FAMILIES = {
    "module": ("method", "method/modules", MODULE_SLOTS),
    "intro-challenge": (
        "introduction", "introduction/previous_methods",
        ("previous-method", "limitation", "technical-reason"),
    ),
    "abstract-contribution": ("abstract", "abstract/contributions", ("summary", "advantage")),
    "intro-contribution": (
        "introduction", "introduction/our_pipeline/contributions", ("purpose", "how", "advantage"),
    ),
    "challenge": ("abstract", "abstract/previous_methods", "challenge"),
    "abstract-finding": ("abstract", "abstract/experiment", "finding"),
    "finding": ("experiments", "experiments/comparison", "finding"),
    "reason": ("limitation", "limitation/explanation", "reason"),
}
LARGE_CASES = [(family, 137 if isinstance(slots, str) else 97)
               for family, (_, _, slots) in FAMILIES.items()]


def _evidence(tag: str) -> dict:
    return {
        "kind": "author_stated", "anchor": "Synthetic physical page 1",
        "source_spans": [{
            "kind": "zotero_pdf", "library_type": "personal", "library_id": "99999999",
            "attachment_key": "SYNTH001", "content_hash": "sha256:" + "0" * 64,
            "page_index": 0, "quote": f"Synthetic excerpt {tag}.",
        }],
    }


def _payload(family: str, count: int, *, capacity: str | None = None) -> dict:
    role, prefix, slots = FAMILIES[family]
    claims = []
    for index in range(1, 2 if isinstance(slots, str) else count + 1):
        claim_id = f"{family}-{index:03d}"
        point_ids = ([f"{slots}-{number}" for number in range(1, count + 1)]
                     if isinstance(slots, str) else slots)
        claims.append({
            "claim_id": claim_id, "role": role, "outline_path": f"{prefix}/{claim_id}",
            "title": f"Synthetic {family} {index}", "container": True, "body": "",
            "evidence": {"kind": "not_applicable", "detail": "Structural container only"},
            "points": [{
                "point_id": slot, "text": f"Record {claim_id}/{slot}.",
                "evidence": _evidence(f"{claim_id}/{slot}"),
            } for slot in point_ids],
        })
    result = {
        "schema_version": 5, "artifact_id": "analysis:paper:synthetic-cardinality",
        "paper_title": "Synthetic Cardinality", "language": "en",
        "profile": {"kind": "whole", "framework": "reference_tree_v5",
                    "roles": ROLES[:], "markdown_quotes": True},
        "claims": claims,
    }
    if capacity is not None:
        result["capacity"] = capacity
    return result


def _records(payload: dict) -> list[tuple]:
    return [
        (claim["claim_id"], point["point_id"], point["text"],
         {key: point["evidence"]["source_spans"][0][key] for key in (
             "kind", "library_type", "library_id", "attachment_key", "content_hash",
             "page_index", "quote",
         )})
        for claim in payload["claims"] for point in claim.get("points", [])
    ]


def _assert_complete_pair(payload: dict, bundle) -> None:
    # The synthetic excerpts contain punctuation escaped for literal Markdown.
    literal_markdown = re.sub(r"\\([-.])", r"\1", bundle.markdown)
    for claim_id, point_id, text, span in _records(payload):
        anchor = f"point-{len(claim_id)}-{claim_id}-{point_id}"
        assert text in bundle.markdown
        assert span["quote"] in literal_markdown
        assert f"^{anchor}" in bundle.markdown
        nodes = [node for node in bundle.canvas["nodes"] if text in node["text"]]
        assert len(nodes) == 1, (claim_id, point_id)
        assert "zotero://open-pdf/library/items/SYNTH001?page=1" in nodes[0]["text"]
        assert f"[[{NOTE}#^{anchor}|" in nodes[0]["text"]
    # The open substantive families do not alter the five top-level roles.
    targets = {edge["toNode"] for edge in bundle.canvas["edges"]}
    roots = {node["id"] for node in bundle.canvas["nodes"]} - targets
    assert len(roots) == 1
    assert sum(edge["fromNode"] in roots for edge in bundle.canvas["edges"]) == 5


@pytest.mark.parametrize("family,count", LARGE_CASES)
def test_v5_model_preserves_repeated_content_without_a_capacity_token(family, count):
    raw = _payload(family, count)
    document = AnalysisDocument.model_validate(raw)
    restored = AnalysisDocument.model_validate_json(document.model_dump_json())
    assert _records(restored.model_dump(mode="json")) == _records(raw)
    assert [claim.claim_id for claim in restored.claims] == [claim["claim_id"] for claim in raw["claims"]]
    assert document.fact_node_limit is None
    assert document.managed_node_limit is None
    assert "capacity" not in document.model_dump(mode="json")


@pytest.mark.parametrize("family,count", LARGE_CASES)
def test_v5_public_schema_accepts_the_same_repeated_content(family, count):
    errors = list(jsonschema.Draft202012Validator(IR_SCHEMA).iter_errors(_payload(family, count)))
    assert not [(list(error.absolute_path), error.validator, error.validator_value) for error in errors]


@pytest.mark.parametrize("family,count", [
    ("module", 49), ("intro-challenge", 65), ("abstract-contribution", 97),
    ("finding", 137), ("reason", 137),
])
def test_large_v5_candidates_keep_every_record_and_report_only_real_format_conflicts(family, count):
    raw = _payload(family, count)
    document = AnalysisDocument.model_validate(raw)
    candidate = render_analysis(document, note_stem=NOTE)
    _assert_complete_pair(raw, candidate)
    report = validate_bundle(document, candidate, note_stem=NOTE)
    assert not {"canvas-node-limit", "canvas-fact-limit", "canvas-semantic-node-limit"} & {
        finding.code for finding in report.findings
    }
    if report.ok:
        baseline = create_baseline(document, candidate, note_stem=NOTE)
        assert set(baseline.generated_node_ids) == {node["id"] for node in candidate.canvas["nodes"]}
    else:
        assert all(finding.path.startswith(("canvas/geometry", "canvas/nodes/", "canvas/edges/"))
                   for finding in report.findings)
        with pytest.raises(AnalysisUpdateError, match="nonconformant"):
            create_baseline(document, candidate, note_stem=NOTE)


def _moderate_payload(capacity: str | None) -> dict:
    raw = json.loads((ROOT / "tests/fixtures/analysis_v5_toy.json").read_text())
    # Existing 38 synthetic records plus seven complete modules and two reasons.
    extra = _payload("module", 7)["claims"]
    for claim in extra:
        for point in claim["points"]:
            point["evidence"] = {"kind": "not_applicable", "detail": "Synthetic input only."}
    raw["claims"].extend(extra)
    for index in range(2):
        raw["claims"].append({
            "claim_id": f"extra-limit-{index}", "role": "limitation",
            "outline_path": f"limitation/explanation/extra-{index}",
            "title": f"Synthetic limit {index}", "body": f"Synthetic boundary {index}.",
            "evidence": {"kind": "not_applicable", "detail": "Synthetic input only."},
        })
    if capacity is not None:
        raw["capacity"] = capacity
    return raw


@pytest.mark.parametrize("capacity", [None, "expanded"])
def test_default_and_compatibility_capacity_render_the_complete_68_fact_pair(capacity):
    raw = _moderate_payload(capacity)
    document = AnalysisDocument.model_validate(raw)
    assert sum(not claim.container for claim in document.claims) + sum(
        len(claim.points) for claim in document.claims
    ) == 68
    bundle, baseline = render_analysis_projection(document, note_stem=NOTE)
    assert validate_bundle(document, bundle, note_stem=NOTE).ok
    for claim in raw["claims"]:
        for point in claim.get("points", []):
            assert point["text"] in bundle.markdown
            assert sum(point["text"] in node["text"] for node in bundle.canvas["nodes"]) == 1
    assert baseline.document.capacity == capacity
    assert AnalysisBaseline.model_validate_json(baseline.model_dump_json()) == baseline
    jsonschema.Draft202012Validator(BASELINE_SCHEMA, registry=REGISTRY).validate(
        baseline.model_dump(mode="json")
    )


def _widen_columns_only(bundle):
    """A manual-layout fixture, not a new default gutter or a geometry waiver."""
    result = deepcopy(bundle)
    nodes = result.canvas["nodes"]
    height = max(node["y"] + node["height"] for node in nodes) - min(node["y"] for node in nodes)
    extent = max(node["x"] for node in nodes)
    factor = max(1, ceil(height / extent))
    for node in nodes:
        node["x"] *= factor
    width = max(node["x"] + node["width"] for node in nodes) - min(node["x"] for node in nodes)
    assert max(width / height, height / width) <= 2
    return result


def test_v5_baseline_owns_all_more_than_192_actual_nodes_after_valid_manual_layout():
    raw = _payload("module", 49)
    document = AnalysisDocument.model_validate(raw)
    candidate = render_analysis(document, note_stem=NOTE)
    assert len(candidate.canvas["nodes"]) > 192
    laid_out = _widen_columns_only(candidate)
    _assert_complete_pair(raw, laid_out)
    # No text, box dimensions, topology or links change to make this admissible.
    for before, after in zip(candidate.canvas["nodes"], laid_out.canvas["nodes"], strict=True):
        assert {key: value for key, value in before.items() if key != "x"} == {
            key: value for key, value in after.items() if key != "x"
        }
    assert candidate.canvas["edges"] == laid_out.canvas["edges"]
    report = validate_bundle(document, laid_out, note_stem=NOTE)
    assert report.ok, report.model_dump()
    baseline = create_baseline(document, laid_out, note_stem=NOTE)
    assert set(baseline.generated_node_ids) == {node["id"] for node in candidate.canvas["nodes"]}
    assert set(baseline.claims) == {claim["claim_id"] for claim in raw["claims"]}
    assert AnalysisBaseline.model_validate_json(baseline.model_dump_json()) == baseline
    jsonschema.Draft202012Validator(BASELINE_SCHEMA, registry=REGISTRY).validate(
        baseline.model_dump(mode="json")
    )
    for damage in ("duplicate-node", "wrong-artifact", "missing-claim", "unowned-claim-node"):
        broken = baseline.model_dump(mode="json")
        if damage == "duplicate-node":
            broken["generated_node_ids"].append(broken["generated_node_ids"][0])
        elif damage == "wrong-artifact":
            broken["artifact_id"] = "analysis:paper:other"
        elif damage == "missing-claim":
            broken["claims"].pop(next(iter(broken["claims"])))
        else:
            broken["claims"][next(iter(broken["claims"]))]["canvas_node_id"] = "f" * 16
        with pytest.raises(ValidationError):
            AnalysisBaseline.model_validate(broken)


@pytest.mark.parametrize("damage", ["sixth-role", "module-extra-slot", "wrong-role",
                                    "duplicate-claim", "duplicate-point", "unquoted-fact"])
def test_unlimited_content_does_not_relax_framework_or_identity(damage):
    raw = _payload("module", 1)
    claim = raw["claims"][0]
    if damage == "sixth-role":
        raw["profile"]["roles"].append("workflow")
    elif damage == "module-extra-slot":
        claim["points"][0]["point_id"] = "additional-module-slot"
    elif damage == "wrong-role":
        claim["role"] = "abstract"
    elif damage == "duplicate-claim":
        raw["claims"].append(deepcopy(claim))
    elif damage == "duplicate-point":
        claim["points"].append(deepcopy(claim["points"][0]))
    else:
        claim["points"][0]["evidence"]["source_spans"][0].pop("quote")
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(raw)
    if damage not in {"duplicate-claim", "duplicate-point"}:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(IR_SCHEMA).validate(raw)


@pytest.mark.parametrize("version", [1, 2, 3, 4])
def test_legacy_versions_keep_their_existing_semantic_boundaries(version):
    if version == 4:
        raw = _payload("reason", 1)
        raw["schema_version"] = 4
        raw["profile"] = {"kind": "whole", "framework": "reference_tree",
                          "roles": ["abstract", "introduction", "method", "limitation"]}
        raw["claims"] = [{
            "claim_id": f"limit-{index}", "role": "limitation",
            "outline_path": f"limitation/explanation/limit-{index}",
            "title": "Synthetic boundary", "body": "Synthetic body.",
            "evidence": {"kind": "not_applicable", "detail": "Synthetic input only."},
        } for index in range(40)]
    else:
        roles = ["task", "input", "workflow", "output", "boundary"]
        raw = {
            "schema_version": version, "artifact_id": "analysis:paper:synthetic-legacy",
            "paper_title": "Synthetic Legacy", "profile": {"kind": "whole", "roles": roles[:]},
            "claims": [{
                "claim_id": f"claim-{index}", "role": roles[index] if index < 5 else "task",
                "title": "Synthetic record", "body": "Synthetic body.",
                "evidence": {"kind": "not_applicable", "detail": "Synthetic input only."},
                **({"order": 1} if index == 2 else {}),
            } for index in range(34)],
        }
    document = AnalysisDocument.model_validate(raw)
    assert document.fact_node_limit == 40
    assert document.managed_node_limit == (96 if version == 4 else 40)
    jsonschema.Draft202012Validator(IR_SCHEMA).validate(raw)
    extra = deepcopy(raw["claims"][-1])
    extra["claim_id"] = "one-too-many"
    if version == 4:
        extra["outline_path"] = "limitation/explanation/one-too-many"
    raw["claims"].append(extra)
    with pytest.raises(ValidationError, match="40 generated semantic Canvas nodes"):
        AnalysisDocument.model_validate(raw)


@pytest.mark.parametrize("version", [2, 3])
def test_legacy_point_array_limit_is_not_removed_with_v5_cardinality(version):
    raw = {
        "schema_version": version, "artifact_id": "analysis:paper:synthetic-legacy-points",
        "paper_title": "Synthetic Legacy Points",
        "profile": {"kind": "focused", "roles": ["task"]},
        "claims": [{
            "claim_id": "task", "role": "task", "title": "Synthetic task", "body": "Synthetic body.",
            "evidence": {"kind": "not_applicable", "detail": "Synthetic input only."},
            "points": [{"point_id": f"point-{index}", "text": "Synthetic point.",
                        "evidence": {"kind": "not_applicable", "detail": "Synthetic input only."}}
                       for index in range(64)],
        }],
    }
    AnalysisDocument.model_validate(raw)
    jsonschema.Draft202012Validator(IR_SCHEMA).validate(raw)
    extra = deepcopy(raw["claims"][0]["points"][-1])
    extra["point_id"] = "one-too-many"
    raw["claims"][0]["points"].append(extra)
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(raw)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(IR_SCHEMA).validate(raw)


MARKER_DIRECTIONS = [(None, "expanded"), ("expanded", None)]


def _marker_update_inputs(saved_marker, submitted_marker, scope, *, changed=False):
    raw = json.loads((ROOT / "tests/fixtures/analysis_v5_toy.json").read_text())
    if saved_marker is not None:
        raw["capacity"] = saved_marker
    original = AnalysisDocument.model_validate(raw)
    current, baseline = render_analysis_projection(original, note_stem=NOTE)
    update = deepcopy(raw)
    update.pop("capacity", None)
    if submitted_marker is not None:
        update["capacity"] = submitted_marker
    if scope == "focused":
        update["profile"]["kind"] = "focused"
        update["profile"]["roles"] = ["limitation"]
        update["claims"] = [claim for claim in update["claims"] if claim["role"] == "limitation"]
    if changed:
        next(claim for claim in update["claims"] if claim["claim_id"] == "l-r")["body"] = (
            "Revised synthetic boundary; no claim about a real paper is made."
        )
    return current, baseline, AnalysisDocument.model_validate(update)


@pytest.mark.parametrize("saved_marker,submitted_marker", MARKER_DIRECTIONS)
@pytest.mark.parametrize("scope", ["whole", "focused"])
@pytest.mark.parametrize("changed", [False, True])
def test_capacity_marker_update_compatibility_preserves_the_saved_marker(
    saved_marker, submitted_marker, scope, changed,
):
    current, baseline, update = _marker_update_inputs(
        saved_marker, submitted_marker, scope, changed=changed,
    )
    before_baseline = baseline.model_dump_json()
    before_update = update.model_dump_json()
    plan = plan_analysis_update(current=current, baseline=baseline, update=update, note_stem=NOTE)
    assert plan.status == "ready"
    assert not plan.conflicts
    assert plan.document.capacity == saved_marker
    assert plan.baseline is not None
    assert plan.baseline.document.capacity == saved_marker
    assert baseline.model_dump_json() == before_baseline
    assert update.model_dump_json() == before_update
    assert plan.document.profile == baseline.document.profile
    assert [claim.claim_id for claim in plan.document.claims] == [
        claim.claim_id for claim in baseline.document.claims
    ]
    old_claims = {claim.claim_id: claim for claim in baseline.document.claims}
    for claim in plan.document.claims:
        if changed and claim.claim_id == "l-r":
            assert claim.body == "Revised synthetic boundary; no claim about a real paper is made."
            assert claim.evidence == old_claims[claim.claim_id].evidence
        else:
            assert claim == old_claims[claim.claim_id]
    assert validate_bundle(plan.document, plan.proposed, note_stem=NOTE).ok
    if not changed:
        assert plan.proposed == current
        assert plan.baseline.markdown_sha256 == baseline.markdown_sha256
        assert plan.baseline.canvas_sha256 == baseline.canvas_sha256
        assert plan.baseline.claims == baseline.claims


@pytest.mark.parametrize("saved_marker,submitted_marker", MARKER_DIRECTIONS)
@pytest.mark.parametrize("damage", ["markdown", "canvas", "baseline"])
def test_capacity_marker_compatibility_keeps_revision_and_baseline_gates(
    saved_marker, submitted_marker, damage,
):
    current, baseline, update = _marker_update_inputs(saved_marker, submitted_marker, "focused")
    before = deepcopy(current)
    if damage == "markdown":
        current = AnalysisBundle(
            markdown=current.markdown + "\nUnreviewed synthetic edit.\n",
            canvas=deepcopy(current.canvas),
        )
    elif damage == "canvas":
        current.canvas["nodes"][0]["text"] += "\nUnreviewed synthetic edit."
    else:
        baseline = baseline.model_copy(update={"markdown_sha256": "f" * 64})
        with pytest.raises(AnalysisUpdateError, match="baseline is corrupt"):
            plan_analysis_update(current=current, baseline=baseline, update=update, note_stem=NOTE)
        assert current == before
        return
    edited = deepcopy(current)
    plan = plan_analysis_update(current=current, baseline=baseline, update=update, note_stem=NOTE)
    assert plan.status == "conflict"
    assert plan.baseline is None
    assert f"{damage}-revision-conflict" in plan.conflicts
    assert plan.current is current
    assert current == edited


@pytest.mark.parametrize("saved_marker,submitted_marker", MARKER_DIRECTIONS)
def test_targeted_repair_accepts_only_capacity_marker_difference(saved_marker, submitted_marker):
    original = AnalysisDocument.model_validate(_payload("module", 1, capacity=saved_marker))
    repaired = AnalysisDocument.model_validate(_payload("module", 1, capacity=submitted_marker))
    _validate_targeted_repair(original, repaired, ConformanceReport(ok=False, findings=[]))
    assert _records(original.model_dump(mode="json")) == _records(repaired.model_dump(mode="json"))


@pytest.mark.parametrize("saved_marker,submitted_marker", MARKER_DIRECTIONS)
@pytest.mark.parametrize("damage", ["artifact", "profile", "point-order", "unreported-evidence"])
def test_capacity_marker_does_not_authorize_targeted_repair_changes(
    saved_marker, submitted_marker, damage,
):
    original = AnalysisDocument.model_validate(_payload("module", 1, capacity=saved_marker))
    raw = _payload("module", 1, capacity=submitted_marker)
    if damage == "artifact":
        raw["artifact_id"] = "analysis:paper:other"
    elif damage == "profile":
        raw["profile"].update({"kind": "focused", "roles": ["method"]})
    elif damage == "point-order":
        raw["claims"][0]["points"].reverse()
    else:
        raw["claims"][0]["points"][0]["evidence"]["source_spans"][0]["quote"] = (
            "An unreported synthetic evidence replacement."
        )
    repaired = AnalysisDocument.model_validate(raw)
    expected = ("point identities or order" if damage == "point-order" else
                "outside reported findings" if damage == "unreported-evidence" else "identity, profile")
    with pytest.raises(ValueError, match=expected):
        _validate_targeted_repair(original, repaired, ConformanceReport(ok=False, findings=[]))
