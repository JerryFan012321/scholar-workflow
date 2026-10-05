"""Markdown quotations use one synthetic object and do not alter Canvas."""
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
from scholar_workflow.analysis.reference_rendering import reference_source_quote_lines
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "analysis-quotations"


def _payload() -> dict:
    return json.loads((FIXTURE / "IR.json").read_text(encoding="utf-8"))


def _document(**changes) -> AnalysisDocument:
    return AnalysisDocument.model_validate({**_payload(), **changes})


def test_quotes_use_the_hand_written_original_text_and_expected_blocks() -> None:
    document = _document()
    source = (FIXTURE / "SOURCE.md").read_text(encoding="utf-8")
    for evidence in (
        document.claims[0].evidence,
        *(point.evidence for point in document.claims[0].points),
    ):
        assert evidence.source_spans[0].quote in source
    expected = (FIXTURE / "EXPECTED-EXCERPTS.md").read_text(encoding="utf-8")
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    for block in expected.rstrip("\n").split("\n\n---\n\n"):
        assert block in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


def test_enabling_quotes_does_not_change_any_canvas_data() -> None:
    payload = _payload()
    with_quotes = render_analysis(_document(), note_stem="Synthetic analysis")
    payload["profile"].pop("markdown_quotes")
    old = AnalysisDocument.model_validate(payload)
    without_quotes = render_analysis(old, note_stem="Synthetic analysis")
    assert with_quotes.canvas == without_quotes.canvas
    assert "Original excerpt" not in without_quotes.markdown
    assert "markdown_quotes" not in old.model_dump(mode="json")["profile"]
    assert validate_bundle(old, without_quotes, note_stem="Synthetic analysis").ok


@pytest.mark.parametrize("version", [4, 5])
def test_complete_context_quote_renders_and_updates_without_changing_canvas(version) -> None:
    passages = (FIXTURE / "SOURCE-CONTEXT.md").read_text(encoding="utf-8").strip().split("\n\n")
    if version == 4:
        payload = _payload()
        selected_claim = payload["claims"][0]
        selected_evidence = selected_claim["evidence"]
        quote = passages[0]
    else:
        payload = json.loads((FIXTURE.parent / "analysis_v5_toy.json").read_text(encoding="utf-8"))
        selected_claim = next(claim for claim in payload["claims"] if claim["claim_id"] == "m-1")
        selected_evidence = next(point for point in selected_claim["points"] if point["point_id"] == "method")["evidence"]
        quote = passages[1]
    assert 400 < len(quote) <= 1600
    original = AnalysisDocument.model_validate(deepcopy(payload))
    bundle, baseline = render_analysis_projection(original, note_stem="Synthetic analysis")
    selected_evidence["source_spans"][0]["quote"] = quote
    revised = AnalysisDocument.model_validate(payload)
    rendered = render_analysis(revised, note_stem="Synthetic analysis")
    assert rendered.canvas == bundle.canvas
    quote_line = next(line for line in rendered.markdown.splitlines() if line.startswith(
        "> " + quote.split(" ", 3)[0] + " " + quote.split(" ", 3)[1]
    ))
    assert html.unescape(re.sub(r"\\(.)", r"\1", quote_line[2:])) == quote
    assert "\n".join(reference_source_quote_lines(
        revised.claims[0].evidence if version == 4 else next(
            point.evidence for claim in revised.claims if claim.claim_id == "m-1"
            for point in claim.points if point.point_id == "method"
        ), "en", indent="",
    )) in rendered.markdown
    assert validate_bundle(revised, rendered, note_stem="Synthetic analysis").ok

    payload["profile"].update(kind="focused", roles=["method"])
    payload["claims"] = [claim for claim in payload["claims"] if claim["role"] == "method"]
    plan = plan_analysis_update(
        baseline=baseline, current=bundle,
        update=AnalysisDocument.model_validate(payload), note_stem="Synthetic analysis",
    )
    assert plan.status == "ready", plan.conflicts
    assert plan.proposed.canvas == bundle.canvas
    assert plan.proposed.markdown == rendered.markdown


@pytest.mark.parametrize("markdown_quotes", [False, True])
def test_original_sparse_input_keeps_the_canvas_aspect_ratio_guard(markdown_quotes: bool) -> None:
    payload = _payload()
    payload["profile"].update(
        kind="focused", roles=["method"], markdown_quotes=markdown_quotes,
    )
    payload["claims"] = [payload["claims"][0]]
    document = AnalysisDocument.model_validate(payload)
    with pytest.raises(ValueError, match="reference-tree Canvas is too elongated"):
        render_analysis(document, note_stem="Synthetic analysis")


def test_chinese_labels_keep_the_english_source_words() -> None:
    payload = _payload()
    payload["language"] = "zh"
    claim = payload["claims"][0]
    claim["title"] = "固定状态表示"
    claim["body"] = "此合成方法保持状态表示不变。"
    claim["evidence"]["anchor"] = "合成第4页"
    claim["points"][0]["text"] = "只更新预测头。"
    claim["points"][0]["evidence"]["anchor"] = "合成第5页"
    claim["points"][1]["text"] = "据此推断，状态表示可被复用。"
    claim["points"][1]["evidence"]["detail"] = "依据表示保持不变作出的推断，不是作者解释。"
    for gap in payload["claims"][1:]:
        gap["title"] = {
            "abstract": "任务来源缺口",
            "introduction": "应用背景来源缺口",
            "limitation": "局限来源缺口",
        }[gap["role"]]
        gap["body"] = (
            "此合成材料只提供两句方法原文，没有可核对的本节内容；"
            "这里明确记录来源缺口，不据此推断真实论文是否报告相关内容。"
        )
        gap["evidence"]["detail"] = "当前输入不包含这一节，不能据此断言论文未报告。"
    bundle = render_analysis(AnalysisDocument.model_validate(payload), note_stem="合成分析")
    assert "> **原文摘录** · [原文·PDF 第 4 页]" in bundle.markdown
    assert "> The method keeps the state representation fixed\\." in bundle.markdown
    assert "Original excerpt" not in bundle.markdown
    assert all("原文摘录" not in node["text"] for node in bundle.canvas["nodes"])


def test_quoted_pdf_uses_the_selected_zotflow_reader() -> None:
    payload = _payload()
    payload["reader"] = {"kind": "zotflow_library", "vault_id": "0123456789abcdef"}
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    assert "> **Original excerpt** · [Source · PDF page 4](obsidian://zotflow?" in bundle.markdown
    assert "navigation=%7B%22pageIndex%22%3A3%7D" in bundle.markdown
    assert "zotero://" not in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


def test_registered_markdown_span_can_quote_and_link_its_block() -> None:
    payload = _payload()
    payload["claims"][0]["evidence"]["source_spans"] = [{
        "kind": "vault_markdown",
        "source_id": "00000000-0000-4000-8000-000000000001",
        "artifact_id": "document:synthetic-source",
        "vault_path": "SOURCE.md",
        "block_id": "fixed-state",
        "quote": "The method keeps the state representation fixed.",
    }]
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    assert "> **Original excerpt** · [[SOURCE#^fixed-state|Source · paragraph]]" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


@pytest.mark.parametrize("owner", ["claim", "author-point", "inference-point"])
@pytest.mark.parametrize("quote", [None, " \t\n"])
def test_supported_statements_require_a_nonblank_excerpt(owner: str, quote: str | None) -> None:
    payload = _payload()
    claim = payload["claims"][0]
    evidence = (
        claim["evidence"] if owner == "claim"
        else claim["points"][0 if owner == "author-point" else 1]["evidence"]
    )
    evidence["source_spans"][0]["quote"] = quote
    with pytest.raises(ValidationError, match="quotations"):
        AnalysisDocument.model_validate(payload)


def test_source_gaps_do_not_invent_quotations() -> None:
    payload = _payload()
    payload["claims"][0]["evidence"] = {"kind": "unverifiable", "detail": "Text is unavailable."}
    payload["claims"][0]["points"] = []
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    assert "Original excerpt" not in bundle.markdown
    assert "Unavailable in the current text channel" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


def test_quotations_escape_source_syntax_and_preserve_line_content() -> None:
    payload = _payload()
    payload["claims"][0]["evidence"]["source_spans"][0]["quote"] = (
        "[x](https://example.invalid) *word* <tag> & ^claim-fake\n# Not a heading"
    )
    document = AnalysisDocument.model_validate(payload)
    quote_lines = reference_source_quote_lines(document.claims[0].evidence, "en")
    text = "\n".join(quote_lines)
    assert r"\[x\]\(https://example\.invalid\) \*word\* &lt;tag&gt; &amp; \^claim\-fake" in text
    assert "> \\# Not a heading" in text
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


@pytest.mark.parametrize("owner", ["claim", "point"])
@pytest.mark.parametrize("operation", ["remove", "alter", "append", "relocate"])
def test_removed_altered_or_detached_excerpts_fail_conformance(owner: str, operation: str) -> None:
    document = _document()
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    evidence = (
        document.claims[0].evidence if owner == "claim"
        else document.claims[0].points[0].evidence
    )
    excerpt = "\n".join(reference_source_quote_lines(
        evidence, "en", indent="" if owner == "claim" else "  "
    ))
    if operation == "alter":
        original = "representation fixed" if owner == "claim" else "head is updated"
        changed = "representation changed" if owner == "claim" else "head is frozen"
        markdown = bundle.markdown.replace(excerpt, excerpt.replace(original, changed), 1)
    elif operation == "append":
        markdown = bundle.markdown.replace(excerpt, excerpt + " CHANGED", 1)
    else:
        markdown = bundle.markdown.replace(excerpt, "", 1)
        if operation == "relocate":
            markdown += "\n" + excerpt + "\n"
    report = validate_bundle(
        document, AnalysisBundle(markdown=markdown, canvas=bundle.canvas),
        note_stem="Synthetic analysis",
    )
    assert not report.ok
    assert "markdown-source-quote-mismatch" in {finding.code for finding in report.findings}


def test_focused_update_preserves_the_quotation_setting_and_quote_hash() -> None:
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Synthetic analysis")
    payload = _payload()
    payload["claims"][0]["body"] = "Revised explanation of the same unchanged state."
    payload["profile"].update(kind="focused", roles=["method"])
    payload["claims"] = [payload["claims"][0]]
    update = AnalysisDocument.model_validate(payload)
    plan = plan_analysis_update(
        baseline=baseline, current=bundle, update=update, note_stem="Synthetic analysis"
    )
    assert plan.status == "ready", plan.conflicts
    assert plan.document.profile.markdown_quotes
    assert "Original excerpt" in plan.proposed.markdown
    assert plan.proposed.canvas["edges"] == bundle.canvas["edges"]
    payload = deepcopy(_payload())
    payload["claims"][0]["evidence"]["source_spans"][0]["quote"] += " More source words."
    different = AnalysisDocument.model_validate(payload)
    _, other_baseline = render_analysis_projection(different, note_stem="Synthetic analysis")
    assert (
        baseline.claims["fixed-state"].markdown_sha256
        != other_baseline.claims["fixed-state"].markdown_sha256
    )
    assert baseline.canvas_sha256 == other_baseline.canvas_sha256


def test_quotation_setting_is_not_silently_removed_on_update() -> None:
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Synthetic analysis")
    payload = _payload()
    payload["profile"].pop("markdown_quotes")
    with pytest.raises(AnalysisUpdateError, match="cannot remove"):
        plan_analysis_update(
            baseline=baseline, current=bundle,
            update=AnalysisDocument.model_validate(payload), note_stem="Synthetic analysis",
        )


def test_legacy_profile_does_not_accept_the_new_format() -> None:
    with pytest.raises(ValidationError, match="reference_tree"):
        AnalysisProfile(kind="whole", markdown_quotes=True)


@pytest.mark.parametrize("whole", [False, True])
def test_older_pair_adopts_quotations_only_in_an_explicit_whole_update(whole: bool) -> None:
    old_payload = _payload()
    old_payload["profile"].pop("markdown_quotes")
    old_payload["profile"].update(kind="whole", roles=[])
    old_document = AnalysisDocument.model_validate(old_payload)
    bundle, baseline = render_analysis_projection(old_document, note_stem="Synthetic analysis")
    new_payload = _payload()
    if not whole:
        new_payload["profile"].update(kind="focused", roles=["method"])
        new_payload["claims"] = [new_payload["claims"][0]]
    update = AnalysisDocument.model_validate(new_payload)
    if not whole:
        with pytest.raises(AnalysisUpdateError, match="whole analysis update"):
            plan_analysis_update(
                current=bundle, baseline=baseline, update=update, note_stem="Synthetic analysis"
            )
    else:
        plan = plan_analysis_update(
            current=bundle, baseline=baseline, update=update, note_stem="Synthetic analysis"
        )
        assert plan.status == "ready", plan.conflicts
        assert plan.proposed.canvas == bundle.canvas
        assert "Original excerpt" in plan.proposed.markdown
