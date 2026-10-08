"""Independent selected-image expectations; no real Vault or reader is used."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
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


def test_new_image_layer_extends_the_retained_wide_last_column() -> None:
    data = _payload(with_images=False)
    comparison = next(claim for claim in data["claims"] if claim["claim_id"] == "e-c")
    second = deepcopy(comparison)
    second.update(claim_id="e-c2", outline_path="experiments/comparison/second")
    data["claims"].append(second)
    comparison.update(container=True, body="", evidence={
        "kind": "not_applicable", "detail": "Structural container only"
    })
    finding = deepcopy(_image_point(_payload()))
    image = finding.pop("canvas_image")
    finding["point_id"] = "finding-1"
    comparison["points"] = [finding]
    document = AnalysisDocument.model_validate(data)
    current = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, current, note_stem=NOTE)
    last_x = max(node["x"] for node in current.canvas["nodes"])
    for node in current.canvas["nodes"]:
        if node["x"] == last_x:
            node["width"] = 1000
    before = {node["id"]: deepcopy(node) for node in current.canvas["nodes"]}
    update = document.model_dump(mode="json")
    next(claim for claim in update["claims"] if claim["claim_id"] == "e-c")["points"][0]["canvas_image"] = image
    plan = plan_analysis_update(
        current=current,
        baseline=baseline,
        update=AnalysisDocument.model_validate(update),
        note_stem=NOTE,
    )
    after = {node["id"]: node for node in plan.proposed.canvas["nodes"]}
    images = set(after) - set(before)
    assert len(images) == 1
    for image_id in images:
        edge = next(edge for edge in plan.proposed.canvas["edges"] if edge["toNode"] == image_id)
        image, parent = after[image_id], after[edge["fromNode"]]
        assert image["x"] >= parent["x"] + parent["width"] + 64
        assert parent["x"] == last_x
        assert image["x"] >= last_x + 1000 + 64
    for node_id, node in before.items():
        assert {key: after[node_id][key] for key in ("x", "y", "width", "height")} == {
            key: node[key] for key in ("x", "y", "width", "height")
        }


def _markdown_image_payload() -> dict:
    data = _payload()
    data["profile"]["markdown_source_images"] = True
    return data


@pytest.mark.parametrize("language", ["en", "zh"])
def test_selected_images_render_beside_markdown_records_without_canvas_change(language: str) -> None:
    data = _markdown_image_payload()
    data["language"] = language
    flow_caption = "Figure 1: centering flow" if language == "en" else "图1：居中流程"
    table_caption = "Table 1: synthetic errors" if language == "en" else "表1：合成误差"
    for claim in data["claims"]:
        for point in claim.get("points", []):
            if image := point.get("canvas_image"):
                image["caption"] = flow_caption if image["kind"] == "process_diagram" else table_caption
    plain_data = deepcopy(data)
    plain_data["profile"].pop("markdown_source_images")
    plain = render_analysis(AnalysisDocument.model_validate(plain_data), note_stem=NOTE)
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert bundle.canvas == plain.canvas
    assert f"![{flow_caption}](attachments/flow.png)" in bundle.markdown
    assert f"![{table_caption}](attachments/table.png)" in bundle.markdown
    flow_block = bundle.markdown.split("^point-3-m-1-method", 1)[1].split("\n#", 1)[0]
    table_block = bundle.markdown.split("^point-3-e-a-components", 1)[1].split("\n#", 1)[0]
    assert r"Q\_METHOD" in flow_block and "attachments/flow.png" in flow_block
    assert r"Q\_ABLATION" in table_block and "attachments/table.png" in table_block
    assert "page=2" in flow_block and "page=3" in table_block
    assert flow_caption in flow_block and table_caption in table_block
    assert all(line in bundle.markdown for line in plain.markdown.splitlines() if line.strip())
    assert validate_bundle(document, bundle, note_stem=NOTE).ok
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    jsonschema.validate(document.model_dump(mode="json"), schema)


def test_selected_claim_image_is_rendered_after_its_quote() -> None:
    data = _markdown_image_payload()
    claim = next(c for c in data["claims"] if c["claim_id"] == "e-c")
    point = _image_point(data)
    claim["evidence"] = deepcopy(point["evidence"])
    claim["canvas_image"] = deepcopy(point["canvas_image"])
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    block = bundle.markdown.split("^claim-e-c", 1)[1].split("\n#", 1)[0]
    assert block.index(r"Q\_ABLATION") < block.index("attachments/table.png")
    assert "page=3" in block
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


@pytest.mark.parametrize("mutation", ["remove", "wrong-file", "detached", "wrong-record", "caption", "source-link"])
def test_markdown_image_omission_or_misplacement_fails_conformance(mutation: str) -> None:
    document = AnalysisDocument.model_validate(_markdown_image_payload())
    bundle = render_analysis(document, note_stem=NOTE)
    image = "![Table 1: synthetic errors](attachments/table.png)"
    assert image in bundle.markdown
    markdown = bundle.markdown
    if mutation == "wrong-file":
        markdown = markdown.replace("attachments/table.png", "attachments/other.png")
    elif mutation in {"caption", "source-link"}:
        caption = "Table 1: synthetic errors · [Source · PDF page 3](zotero://open-pdf/library/items/SYNTH001?page=3)"
        assert caption in markdown
        markdown = markdown.replace(caption, "Wrong caption" if mutation == "caption" else caption.replace("page=3", "page=4"))
    else:
        markdown = markdown.replace(image, "")
        if mutation == "detached":
            markdown += "\n" + image + "\n"
        elif mutation == "wrong-record":
            markdown = markdown.replace("\n## Method", "\n" + image + "\n\n## Method")
    changed = AnalysisBundle(markdown=markdown, canvas=bundle.canvas)
    assert not validate_bundle(document, changed, note_stem=NOTE).ok


@pytest.mark.parametrize("location", ["point", "claim"])
@pytest.mark.parametrize("embed", [
    "![Already selected](attachments/table.png)",
    "![Already selected](./attachments/table.png)",
    "![[attachments/table.png|Already selected]]",
])
def test_existing_associated_embed_is_not_duplicated(location: str, embed: str) -> None:
    data = _markdown_image_payload()
    point = _image_point(data)
    if location == "point":
        point["canvas_summary"] = point["text"]
        point["text"] += " " + embed
    else:
        claim = next(c for c in data["claims"] if c["claim_id"] == "e-a")
        claim.pop("container", None)
        claim["body"] = "Complete labeled result. " + embed
        claim["canvas_summary"] = "Complete labeled result."
        claim["evidence"] = deepcopy(point["evidence"])
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert bundle.markdown.count("attachments/table.png") == 1
    assert "Table 1: synthetic errors · [Source · PDF page 3]" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


@pytest.mark.parametrize("mention", [
    "File: attachments/table.png",
    "[Not an image](attachments/table.png)",
    "`![Code sample](attachments/table.png)`",
    r"\![Escaped sample](attachments/table.png)",
    "<!-- ![Hidden sample](attachments/table.png) -->",
])
def test_mentions_or_code_cannot_satisfy_markdown_image_requirement(mention: str) -> None:
    data = _markdown_image_payload()
    point = _image_point(data)
    point["canvas_summary"] = point["text"]
    point["text"] += " " + mention
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert "![Table 1: synthetic errors](attachments/table.png)" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


def test_markdown_image_encoded_relative_path_deduplicates() -> None:
    data = _markdown_image_payload()
    point = _image_point(data)
    point["canvas_image"]["image_path"] = "attachments/result table.png"
    point["canvas_summary"] = point["text"]
    point["text"] += " ![Table](attachments/result%20table.png)"
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert bundle.markdown.count("result%20table.png") == 1
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


def test_image_in_another_point_does_not_satisfy_the_selected_record() -> None:
    data = _markdown_image_payload()
    other = next(c for c in data["claims"] if c["claim_id"] == "e-a")["points"][1]
    other["canvas_summary"] = other["text"]
    other["text"] += " ![Other point](attachments/table.png)"
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    block = bundle.markdown.split("^point-3-e-a-components", 1)[1].split("\n#", 1)[0]
    assert "![Table 1: synthetic errors](attachments/table.png)" in block
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("longer_close", [False, True])
def test_fenced_image_sample_does_not_count_as_a_displayed_image(fence: str, longer_close: bool) -> None:
    data = _markdown_image_payload()
    claim = next(c for c in data["claims"] if c["claim_id"] == "e-a")
    claim.pop("container", None)
    closing = fence + (fence[0] * 2 if longer_close else "")
    claim["body"] = f"Code example only.\n\n{fence}markdown\n![Example](attachments/table.png)\n{closing}"
    claim["canvas_summary"] = "Code example only."
    claim["evidence"] = deepcopy(_image_point(data)["evidence"])
    document = AnalysisDocument.model_validate(data)
    bundle = render_analysis(document, note_stem=NOTE)
    assert "![Table 1: synthetic errors](attachments/table.png)" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem=NOTE).ok


def test_disabled_markdown_images_preserve_old_render_and_serialization() -> None:
    data = _payload()
    old = AnalysisDocument.model_validate(data)
    data["profile"]["markdown_source_images"] = False
    disabled = AnalysisDocument.model_validate(data)
    assert disabled.model_dump(mode="json") == old.model_dump(mode="json")
    assert render_analysis(disabled, note_stem=NOTE) == render_analysis(old, note_stem=NOTE)


def test_markdown_image_setting_requires_v5() -> None:
    data = _payload(with_images=False)
    data["schema_version"] = 4
    data["profile"].update(framework="reference_tree", markdown_source_images=True)
    data["profile"]["roles"].remove("experiments")
    data["claims"] = [c for c in data["claims"] if c["role"] != "experiments"]
    with pytest.raises(ValidationError, match="v5"):
        AnalysisDocument.model_validate(data)
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


@pytest.mark.parametrize("value", ["true", 1, None])
def test_markdown_image_setting_is_strict_boolean(value: object) -> None:
    data = _markdown_image_payload()
    data["profile"]["markdown_source_images"] = value
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(data)
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_focused_update_keeps_unselected_markdown_images_and_canvas() -> None:
    document = AnalysisDocument.model_validate(_markdown_image_payload())
    current = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, current, note_stem=NOTE)
    data = document.model_dump(mode="json")
    data["profile"].update(kind="focused", roles=["limitation"])
    data["claims"] = [c for c in data["claims"] if c["role"] == "limitation"]
    plan = plan_analysis_update(current=current, baseline=baseline, update=AnalysisDocument.model_validate(data), note_stem=NOTE)
    assert plan.status == "ready"
    assert plan.document.profile.markdown_source_images
    assert plan.proposed == current


def test_image_profile_baseline_round_trips_through_public_schema() -> None:
    document = AnalysisDocument.model_validate(_markdown_image_payload())
    bundle = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, bundle, note_stem=NOTE)
    ir_schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    baseline_schema = json.loads((ROOT / "contracts/analysis-baseline.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(
        baseline_schema,
        registry=Registry().with_resource(ir_schema["$id"], Resource.from_contents(ir_schema)),
    )
    validator.validate(baseline.model_dump(mode="json"))
    assert type(baseline).model_validate_json(baseline.model_dump_json()) == baseline


def test_whole_image_format_adoption_changes_markdown_only() -> None:
    document = AnalysisDocument.model_validate(_payload())
    current = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, current, note_stem=NOTE)
    plan = plan_analysis_update(current=current, baseline=baseline, update=AnalysisDocument.model_validate(_markdown_image_payload()), note_stem=NOTE)
    assert plan.status == "ready"
    assert plan.proposed.canvas == current.canvas
    assert plan.document.profile.markdown_source_images
    assert "![Table 1: synthetic errors](attachments/table.png)" in plan.proposed.markdown


@pytest.mark.parametrize("baseline_enabled,kind", [(False, "focused"), (True, "focused"), (True, "whole")])
def test_markdown_image_format_cannot_change_in_focus_or_be_removed(baseline_enabled: bool, kind: str) -> None:
    from scholar_workflow.analysis.updates import AnalysisUpdateError

    data = _payload()
    data["profile"]["markdown_source_images"] = baseline_enabled
    document = AnalysisDocument.model_validate(data)
    current = render_analysis(document, note_stem=NOTE)
    baseline = create_baseline(document, current, note_stem=NOTE)
    data["profile"].update(kind=kind, markdown_source_images=not baseline_enabled)
    if kind == "focused":
        data["profile"]["roles"] = ["limitation"]
        data["claims"] = [c for c in data["claims"] if c["role"] == "limitation"]
    with pytest.raises(AnalysisUpdateError, match="Markdown.*image"):
        plan_analysis_update(current=current, baseline=baseline, update=AnalysisDocument.model_validate(data), note_stem=NOTE)
