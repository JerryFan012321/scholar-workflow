"""Versioned Canvas source projection keeps independent Markdown excerpts."""
from __future__ import annotations

import html
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument, AnalysisProfile
from scholar_workflow.analysis.reference_rendering import reference_canvas_inline_evidence
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_v5_toy.json"
QUOTES = (
    "The synthetic predictor reads three measured inputs and returns one scalar.",
    "The synthetic encoder stays frozen while the predictor parameters are updated.",
)


def _payload() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    point = next(
        point for claim in payload["claims"] if claim["claim_id"] == "m-1"
        for point in claim["points"] if point["point_id"] == "method"
    )
    first = point["evidence"]["source_spans"][0]
    point["evidence"]["source_spans"] = [
        {**first, "quote": text} for text in QUOTES
    ]
    return payload


def _point(document: AnalysisDocument):
    return next(
        point for claim in document.claims if claim.claim_id == "m-1"
        for point in claim.points if point.point_id == "method"
    )


def _node(bundle):
    return next(
        node for node in bundle.canvas["nodes"]
        if "point-3-m-1-method" in node.get("text", "")
    )


@pytest.mark.parametrize("reader", [
    {"kind": "zotero_native"},
    {"kind": "zotflow_library", "vault_id": "0123456789abcdef"},
])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_unique_projection_preserves_both_excerpts(reader, language) -> None:
    payload = _payload()
    payload["profile"]["canvas_unique_sources"] = True
    payload.update(reader=reader, language=language)
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    point = _point(document)
    assert len(point.evidence.source_spans) == 2
    label = "PDF p.2" if language == "en" else "PDF·2"
    assert _node(bundle)["text"].count(f"[{label}]") == 1
    visible_quotes = [
        html.unescape(re.sub(r"\\(.)", r"\1", line.strip()[2:]))
        for line in bundle.markdown.splitlines() if line.strip().startswith("> ")
    ]
    for text in QUOTES:
        assert text in visible_quotes
        assert text not in json.dumps(bundle.canvas)
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


def test_default_retains_legacy_projection_and_serialization() -> None:
    document = AnalysisDocument.model_validate(_payload())
    bundle, baseline = render_analysis_projection(document, note_stem="Synthetic analysis")
    assert _node(bundle)["text"].count("[PDF p.2]") == 2
    assert "canvas_unique_sources" not in document.profile.model_dump()
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok
    payload = document.model_dump(mode="json")
    payload["profile"].update(kind="focused", roles=["method"])
    payload["claims"] = [claim for claim in payload["claims"] if claim["role"] == "method"]
    plan = plan_analysis_update(
        current=bundle, baseline=baseline,
        update=AnalysisDocument.model_validate(payload), note_stem="Synthetic analysis",
    )
    assert plan.status == "ready"
    assert plan.proposed == bundle
    assert plan.baseline == baseline


@pytest.mark.parametrize("difference", ["page", "annotation"])
def test_distinct_native_targets_remain_distinct(difference) -> None:
    payload = _payload()
    payload["profile"]["canvas_unique_sources"] = True
    point = next(
        point for claim in payload["claims"] if claim["claim_id"] == "m-1"
        for point in claim["points"] if point["point_id"] == "method"
    )
    if difference == "page":
        point["evidence"]["source_spans"][1]["page_index"] += 1
    else:
        point["evidence"]["source_spans"][0]["annotation_key"] = "ANNOT001"
        point["evidence"]["source_spans"][1]["annotation_key"] = "ANNOT002"
    document = AnalysisDocument.model_validate(payload)
    text = reference_canvas_inline_evidence(
        _point(document).evidence, "en", reader=document.reader, unique_sources=True,
    )
    assert text.count("[PDF p.") == 2


def test_explicit_whole_upgrade_preserves_old_layout_and_focused_option() -> None:
    payload = _payload()
    old = AnalysisDocument.model_validate(deepcopy(payload))
    bundle, baseline = render_analysis_projection(old, note_stem="Synthetic analysis")
    payload["profile"]["canvas_unique_sources"] = True
    plan = plan_analysis_update(
        current=bundle, baseline=baseline,
        update=AnalysisDocument.model_validate(payload), note_stem="Synthetic analysis",
    )
    assert plan.status == "ready"
    assert plan.proposed.markdown == bundle.markdown
    assert plan.proposed.canvas["edges"] == bundle.canvas["edges"]
    assert [
        {key: value for key, value in node.items() if key != "text"}
        for node in plan.proposed.canvas["nodes"]
    ] == [
        {key: value for key, value in node.items() if key != "text"}
        for node in bundle.canvas["nodes"]
    ]
    assert _node(plan.proposed)["text"].count("[PDF p.2]") == 1
    focused = plan.document.model_dump(mode="json")
    focused["profile"].update(kind="focused", roles=["method"])
    focused["claims"] = [claim for claim in focused["claims"] if claim["role"] == "method"]
    next_plan = plan_analysis_update(
        current=plan.proposed, baseline=plan.baseline,
        update=AnalysisDocument.model_validate(focused), note_stem="Synthetic analysis",
    )
    assert next_plan.status == "ready"
    assert next_plan.document.profile.canvas_unique_sources is True
    assert next_plan.proposed == plan.proposed
    focused["profile"].pop("canvas_unique_sources")
    with pytest.raises(AnalysisUpdateError, match="whole analysis update"):
        plan_analysis_update(
            current=plan.proposed, baseline=plan.baseline,
            update=AnalysisDocument.model_validate(focused), note_stem="Synthetic analysis",
        )


@pytest.mark.parametrize("framework", ["legacy", "reference_tree"])
def test_new_projection_requires_v5(framework) -> None:
    with pytest.raises(ValidationError, match="v5"):
        AnalysisProfile(kind="whole", framework=framework, canvas_unique_sources=True)
