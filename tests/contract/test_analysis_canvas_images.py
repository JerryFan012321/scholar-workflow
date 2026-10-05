"""Independent selected-image expectations; no real Vault or reader is used."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import create_baseline, plan_analysis_update

ROOT = Path(__file__).resolve().parents[2]
NOTE = "Synthetic Scalar Reader Analysis"


def _payload(*, with_images: bool = True) -> dict:
    data = json.loads((ROOT / "tests/fixtures/analysis_v5_toy.json").read_text())
    if not with_images:
        return data
    for claim_id, point_id, kind, caption, path in (
        ("m-1", "method", "process_diagram", "Figure 1: centering flow", "attachments/flow.png"),
        ("e-a", "components", "experimental_table", "Table 1: synthetic errors", "attachments/table.png"),
    ):
        claim = next(c for c in data["claims"] if c["claim_id"] == claim_id)
        point = next(p for p in claim["points"] if p["point_id"] == point_id)
        source = deepcopy(point["evidence"]["source_spans"][0])
        source.pop("quote", None)
        point["canvas_image"] = {
            "kind": kind,
            "asset_id": "asset:synthetic-" + ("flow" if kind == "process_diagram" else "table"),
            "caption": caption,
            "image_path": path,
            "sha256": "a" * 64,
            "pixel_width": 1200,
            "pixel_height": 360,
            "source": source,
        }
    return data


def _image_point(data: dict) -> dict:
    return next(c for c in data["claims"] if c["claim_id"] == "e-a")["points"][0]


def test_selected_images_keep_five_branches_records_and_markdown() -> None:
    document = AnalysisDocument.model_validate(_payload())
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    jsonschema.validate(document.model_dump(mode="json"), schema)
    plain = render_analysis(AnalysisDocument.model_validate(_payload(with_images=False)), note_stem=NOTE)
    bundle = render_analysis(document, note_stem=NOTE)
    assert bundle.markdown == plain.markdown
    old_ids = {node["id"] for node in plain.canvas["nodes"]}
    images = [n for n in bundle.canvas["nodes"] if n["id"] not in old_ids]
    assert len(images) == 2
    assert len(bundle.canvas["edges"]) == len(plain.canvas["edges"]) + 2
    assert all(node["type"] == "text" for node in images)
    flow = next(n for n in images if "./attachments/flow.png" in n["text"])
    table = next(n for n in images if "./attachments/table.png" in n["text"])
    assert "Figure 1: centering flow" in flow["text"]
    assert "#^point-3-m-1-method|" in flow["text"]
    assert "page=2" in flow["text"]
    assert "Table 1: synthetic errors" in table["text"]
    assert "#^point-3-e-a-components|" in table["text"]
    assert "page=3" in table["text"]
    assert all("Q_METHOD" not in node["text"] and "Q_ABLATION" not in node["text"] for node in images)
    expected_text = {n["id"]: n["text"] for n in plain.canvas["nodes"]}
    assert {n["id"]: n["text"] for n in bundle.canvas["nodes"] if n["id"] in old_ids} == expected_text
    report = validate_bundle(document, bundle, note_stem=NOTE)
    assert report.ok, report.findings
    create_baseline(document, bundle, note_stem=NOTE)


@pytest.mark.parametrize("kind", ["paragraph", "quote", "screenshot", "other"])
def test_only_tables_and_process_diagrams_are_accepted(kind: str) -> None:
    data = _payload()
    _image_point(data)["canvas_image"]["kind"] = kind
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


@pytest.mark.parametrize("path", ["/tmp/table.png", "../table.png", "attachments/../table.png", "https://example.test/table.png", "attachments/table.svg", "attachments/a[bad].png"])
def test_images_cannot_inject_urls_or_escape_the_paper(path: str) -> None:
    data = _payload()
    _image_point(data)["canvas_image"]["image_path"] = path
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


@pytest.mark.parametrize("mutation", ["wrong-kind", "wrong-page", "wrong-pdf", "unverified", "quote-in-image"])
def test_image_matches_its_supported_record(mutation: str) -> None:
    data = _payload()
    point = _image_point(data)
    image = point["canvas_image"]
    if mutation == "wrong-kind":
        image["kind"] = "process_diagram"
    elif mutation == "wrong-page":
        image["source"]["page_index"] += 1
    elif mutation == "wrong-pdf":
        image["source"]["attachment_key"] = "ZZZZ9999"
    elif mutation == "unverified":
        point["evidence"] = {"kind": "not_reported"}
    else:
        image["source"]["quote"] = "Paragraph excerpts do not belong in Canvas."
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)


@pytest.mark.parametrize("caption", ["Table <img src='https://example.test/quote.png'>", "Figure <svg></svg>"])
def test_plain_caption_cannot_add_untyped_html_images(caption: str) -> None:
    data = _payload()
    _image_point(data)["canvas_image"]["caption"] = caption
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


@pytest.mark.parametrize("mutation", ["image-link", "source-link", "backlink", "too-short", "overlap"])
def test_actual_image_card_cannot_lose_content_or_readability(mutation: str) -> None:
    document = AnalysisDocument.model_validate(_payload())
    bundle = render_analysis(document, note_stem=NOTE)
    node = next(n for n in bundle.canvas["nodes"] if "./attachments/table.png" in n.get("text", ""))
    if mutation == "too-short":
        node["height"] = 60
    elif mutation == "overlap":
        other = next(n for n in bundle.canvas["nodes"] if n["id"] != node["id"])
        node["x"], node["y"] = other["x"], other["y"]
    else:
        replacement = {"image-link": "table.png", "source-link": "page=3", "backlink": "point-3-e-a-components"}[mutation]
        node["text"] = node["text"].replace(replacement, "invalid")
    assert not validate_bundle(document, bundle, note_stem=NOTE).ok


def test_focused_update_retains_unselected_images() -> None:
    document = AnalysisDocument.model_validate(_payload())
    current = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, current, note_stem=NOTE)
    update = document.model_dump(mode="json")
    update["profile"]["kind"] = "focused"
    update["profile"]["roles"] = ["limitation"]
    update["claims"] = [c for c in update["claims"] if c["role"] == "limitation"]
    planned = plan_analysis_update(current=current, baseline=baseline, update=AnalysisDocument.model_validate(update), note_stem=NOTE)
    assert planned.status == "ready"
    assert planned.proposed.canvas == current.canvas
    assert planned.proposed.markdown == current.markdown


def test_images_are_not_backported_to_v4() -> None:
    data = _payload()
    data["schema_version"] = 4
    data["profile"]["framework"] = "reference_tree"
    data["profile"]["roles"] = ["abstract", "introduction", "method", "limitation"]
    data["claims"] = [c for c in data["claims"] if c["role"] != "experiments"]
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)


def test_no_image_fields_are_added_to_legacy_serialization() -> None:
    document = AnalysisDocument.model_validate(_payload(with_images=False))
    payload = document.model_dump(mode="json")
    assert all("canvas_image" not in c for c in payload["claims"])
    assert all("canvas_image" not in p for c in payload["claims"] for p in c.get("points", []))


@pytest.mark.parametrize("field", ["canvas_summary", "title"])
def test_untyped_canvas_embed_cannot_bypass_image_scope(field: str) -> None:
    data = _payload(with_images=False)
    data["claims"][0][field] = "![paragraph](attachments/untyped.png)"
    with pytest.raises(ValidationError, match="typed canvas_image"):
        AnalysisDocument.model_validate(data)


def test_markdown_paragraph_crop_keeps_plain_canvas_summary() -> None:
    data = _payload(with_images=False)
    claim = data["claims"][0]
    claim["body"] += "\n\n![Paragraph](attachments/paragraph.png)"
    claim["canvas_summary"] = "Estimate a scalar from three measurements."
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert "attachments/paragraph.png" in bundle.markdown
    assert not any("attachments/paragraph.png" in node["text"] for node in bundle.canvas["nodes"])


def test_root_title_cannot_create_untyped_source_images() -> None:
    data = _payload(with_images=False)
    data["paper_title"] = "![Untyped](https://example.test/image.png)"
    with pytest.raises(ValidationError, match="typed canvas_image"):
        AnalysisDocument.model_validate(data)


def test_added_images_follow_retained_owner_without_reflowing_old_nodes() -> None:
    old_document = AnalysisDocument.model_validate(_payload(with_images=False))
    current = render_analysis(old_document, note_stem=NOTE)
    baseline = create_baseline(old_document, current, note_stem=NOTE)
    plan = plan_analysis_update(current=current, baseline=baseline, update=AnalysisDocument.model_validate(_payload()), note_stem=NOTE)
    before = {n["id"]: n for n in current.canvas["nodes"]}
    after = {n["id"]: n for n in plan.proposed.canvas["nodes"]}
    for node_id in before:
        assert {key: after[node_id][key] for key in ("x", "y", "width", "height")} == {key: before[node_id][key] for key in ("x", "y", "width", "height")}
    images = set(after) - set(before)
    assert len(images) == 2
    for image_id in images:
        edge = next(e for e in plan.proposed.canvas["edges"] if e["toNode"] == image_id)
        image, parent = after[image_id], after[edge["fromNode"]]
        assert 2 * image["y"] + image["height"] == 2 * parent["y"] + parent["height"]
    # A non-fitting old layout stays a conflict proposal, never a canonical write.
    if not validate_bundle(plan.document, plan.proposed, note_stem=NOTE).ok:
        assert plan.status == "conflict" and plan.baseline is None
        assert "canvas-integrity-conflict" in plan.conflicts
    assert plan.current.canvas == current.canvas
