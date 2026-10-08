"""Uniform foldable excerpts retain the exact source and complete editable graph."""

from __future__ import annotations

import html
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisDocument, Evidence
from scholar_workflow.analysis.reference_rendering import reference_source_quote_lines
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
QUOTE = (FIXTURES / "analysis-quote-emphasis/SOURCE.md").read_text().split("\n\n")[1].strip()
DIRECT = "The proposed model achieves 72% success over 50 trials under this setup."


def payload(version=5, *, folded=True, language="en", inference=False):
    path = "analysis_v5_toy.json" if version == 5 else "analysis-quotations/IR.json"
    value = json.loads((FIXTURES / path).read_text())
    value["profile"]["markdown_folded_quotes"] = folded
    value["language"] = language
    claim = value["claims"][0]
    claim["evidence"] = {
        "kind": "analysis_inference" if inference else "author_stated",
        "anchor": "Synthetic physical page 4",
        **({"detail": "Limited to the fixed-camera setup."} if inference else {}),
        "source_spans": [
            {
                "kind": "zotero_pdf",
                "library_type": "personal",
                "library_id": "99999",
                "attachment_key": "AB12CD34",
                "content_hash": "md5:" + "a" * 32,
                "page_index": 3,
                "quote": QUOTE,
                "quote_emphasis": [DIRECT],
            }
        ],
    }
    return value


def test_folded_excerpt_matches_independent_hand_written_expected():
    evidence = Evidence.model_validate(payload()["claims"][0]["evidence"])
    expected = (FIXTURES / "analysis-folded-quotes/EXPECTED.md").read_text().rstrip()
    actual = "\n".join(reference_source_quote_lines(evidence, "en", folded=True)).lstrip("\n")
    assert actual == expected
    assert evidence.source_spans[0].quote == QUOTE


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("inference", [False, True])
def test_every_provided_excerpt_folds_but_canvas_and_source_remain(version, language, inference):
    old = AnalysisDocument.model_validate(
        payload(version, folded=False, language=language, inference=inference)
    )
    new = AnalysisDocument.model_validate(payload(version, language=language, inference=inference))
    old_bundle = render_analysis(old, note_stem="Synthetic analysis")
    bundle = render_analysis(new, note_stem="Synthetic analysis")
    quotes = [
        s
        for c in new.claims
        for owner in [c, *c.points]
        for s in owner.evidence.source_spans
        if s.quote
    ]
    assert bundle.markdown.count("[!quote]-") == len(quotes)
    assert bundle.canvas == old_bundle.canvas
    assert validate_bundle(new, bundle, note_stem="Synthetic analysis").ok
    if inference:
        assert ("basis for inference" if language == "en" else "推断依据") in bundle.markdown
    assert new.claims[0].evidence.source_spans[0].quote == QUOTE
    block = bundle.markdown.index("[!quote]-")
    assert "^claim-" in bundle.markdown[:block]
    assert "zotero://open-pdf/library/items/AB12CD34?page=4" in bundle.markdown[:block]


@pytest.mark.parametrize("version", [4, 5])
def test_omitted_and_false_preserve_previous_ir_and_output(version):
    omitted = payload(version, folded=False)
    omitted["profile"].pop("markdown_folded_quotes")
    first = AnalysisDocument.model_validate(omitted)
    second = AnalysisDocument.model_validate(payload(version, folded=False))
    assert first.model_dump_json() == second.model_dump_json()
    assert "markdown_folded_quotes" not in first.model_dump(mode="json")["profile"]
    assert render_analysis(first, note_stem="Synthetic analysis") == render_analysis(
        second, note_stem="Synthetic analysis"
    )


@pytest.mark.parametrize("operation", ["open", "remove", "source", "move"])
@pytest.mark.parametrize("version", [4, 5])
def test_changed_or_detached_folded_block_is_nonconformant(operation, version):
    document = AnalysisDocument.model_validate(payload(version))
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    start = bundle.markdown.index("> [!quote]-")
    end = bundle.markdown.index("\n\n", start)
    excerpt = bundle.markdown[start:end]
    changed = {
        "open": excerpt.replace("[!quote]-", "[!quote]+", 1),
        "remove": excerpt.replace("[!quote]- ", "", 1),
        "source": excerpt.replace("page=4", "page=5", 1),
        "move": "",
    }[operation]
    markdown = bundle.markdown[:start] + changed + bundle.markdown[end:]
    if operation == "move":
        markdown += "\n\n" + excerpt + "\n"
    assert not validate_bundle(
        document,
        AnalysisBundle(markdown=markdown, canvas=bundle.canvas),
        note_stem="Synthetic analysis",
    ).ok


@pytest.mark.parametrize("version", [4, 5])
def test_whole_adoption_and_focused_preservation_obey_existing_boundaries(version):
    old = AnalysisDocument.model_validate(payload(version, folded=False))
    current, baseline = render_analysis_projection(old, note_stem="Synthetic analysis")
    new = AnalysisDocument.model_validate(payload(version))
    adopted = plan_analysis_update(
        baseline=baseline, current=current, update=new, note_stem="Synthetic analysis"
    )
    assert adopted.status == "ready", adopted.conflicts
    assert adopted.proposed.canvas == current.canvas
    assert adopted.baseline is not None
    role = new.claims[0].role.value
    focused = payload(version)
    focused["profile"].update(kind="focused", roles=[role])
    focused["claims"] = [c for c in focused["claims"] if c["role"] == role]
    with pytest.raises(AnalysisUpdateError, match="whole"):
        plan_analysis_update(
            baseline=baseline,
            current=current,
            update=AnalysisDocument.model_validate(focused),
            note_stem="Synthetic analysis",
        )
    preserved = plan_analysis_update(
        baseline=adopted.baseline,
        current=adopted.proposed,
        update=AnalysisDocument.model_validate(focused),
        note_stem="Synthetic analysis",
    )
    assert preserved.status == "ready", preserved.conflicts
    assert preserved.document.profile.markdown_folded_quotes
    assert preserved.proposed.canvas == current.canvas
    with pytest.raises(AnalysisUpdateError, match="remove"):
        plan_analysis_update(
            baseline=adopted.baseline,
            current=adopted.proposed,
            update=old,
            note_stem="Synthetic analysis",
        )
    human = AnalysisBundle(
        markdown=adopted.proposed.markdown + "\nHuman reading note.\n",
        canvas=deepcopy(adopted.proposed.canvas),
    )
    conflict = plan_analysis_update(
        baseline=adopted.baseline, current=human, update=new, note_stem="Synthetic analysis"
    )
    assert conflict.status == "conflict" and conflict.current == human


@pytest.mark.parametrize("invalid", ["false-quotes", "legacy", "wrong-type"])
def test_fold_requires_displayed_reference_quotes(invalid):
    value = payload(4)
    if invalid == "false-quotes":
        value["profile"]["markdown_quotes"] = False
    elif invalid == "legacy":
        value["profile"]["framework"] = "legacy"
    else:
        value["profile"]["markdown_folded_quotes"] = "true"
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(value)


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_point_quote_preserves_anchor_context_and_own_source(version, kind):
    value = payload(version)
    claim = next(
        c for c in value["claims"] if any(p["point_id"] == "method" for p in c.get("points", []))
    )
    point = next(p for p in claim["points"] if p["point_id"] == "method")
    point["evidence"] = deepcopy(value["claims"][0]["evidence"])
    if kind == "vault_markdown":
        point["evidence"]["source_spans"] = [
            {
                "kind": "vault_markdown",
                "source_id": "00000000-0000-4000-8000-000000000001",
                "artifact_id": "document:synthetic-source",
                "vault_path": "SOURCE.md",
                "block_id": "fixed-camera",
                "quote": QUOTE,
                "quote_emphasis": [DIRECT],
            }
        ]
    document = AnalysisDocument.model_validate(value)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    prefix = "  " if version == 4 else ""
    anchor = f"^point-{len(claim['claim_id'])}-{claim['claim_id']}-{point['point_id']}"
    statement = next(line for line in bundle.markdown.splitlines() if line.endswith(anchor))
    expected_link = (
        "[[SOURCE#^fixed-camera|Source · paragraph]]"
        if kind == "vault_markdown"
        else "[Source · PDF page 4](zotero://open-pdf/library/items/AB12CD34?page=4)"
    )
    assert expected_link in statement and not statement.lstrip().startswith(">")
    expected = (
        statement
        + "\n\n"
        + prefix
        + "> [!quote]- Original excerpt (bold: direct evidence) · "
        + expected_link
        + "\n"
        + prefix
        + ">\n"
        + prefix
        + "> Trials use a fixed camera pose\\. **The proposed model achieves 72% success "
        + "over 50 trials under this setup\\.** Performance outside this setup has not been evaluated\\."
    )
    assert expected in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok


def test_different_source_passages_are_separate_folds_with_their_own_links():
    value = payload()
    evidence = value["claims"][0]["evidence"]
    second = deepcopy(evidence["source_spans"][0])
    second.update(page_index=4, quote="The next trial uses a different camera.", quote_emphasis=[])
    evidence["source_spans"].append(second)
    result = "\n".join(
        reference_source_quote_lines(Evidence.model_validate(evidence), "en", folded=True)
    )
    assert result.count("> [!quote]-") == 2
    first, other = result.split("\n> [!quote]-")[1:]
    assert "page=4" in first and "page=5" not in first
    assert "page=5" in other and "page=4" not in other
    assert other.endswith("> The next trial uses a different camera\\.")


def test_multiline_source_cannot_inject_callouts_links_or_claim_anchors():
    value = payload()["claims"][0]["evidence"]
    quote = "Context remains.\n[!quote]- <tag> **literal** & [x](https://example.invalid)\n\nResult remains qualified. ^claim-fake"
    value["source_spans"][0].update(quote=quote, quote_emphasis=["Result remains qualified."])
    evidence = Evidence.model_validate(value)
    lines = reference_source_quote_lines(evidence, "en", folded=True)
    rendered = "\n".join(lines)
    assert rendered.count("[!quote]-") == 1
    assert "\\[\\!quote\\]\\- &lt;tag&gt; \\*\\*literal\\*\\*" in rendered
    assert "Result remains qualified\\.** \\^claim\\-fake" in rendered
    decoded = "\n".join(
        html.unescape(re.sub(r"\\(.)", r"\1", line[2:].replace("**", ""))) for line in lines[3:]
    )
    assert decoded == quote and evidence.source_spans[0].quote == quote


@pytest.mark.parametrize("version", [4, 5])
def test_fold_retains_verified_zotflow_reader_route_without_touching_canvas(version):
    value = payload(version)
    value["reader"] = {"kind": "zotflow_library", "vault_id": "1234567890abcdef"}
    document = AnalysisDocument.model_validate(value)
    folded = render_analysis(document, note_stem="Synthetic analysis")
    value["profile"]["markdown_folded_quotes"] = False
    plain = render_analysis(AnalysisDocument.model_validate(value), note_stem="Synthetic analysis")
    header = next(line for line in folded.markdown.splitlines() if "[!quote]-" in line)
    assert "obsidian://zotflow?" in header and "navigation=%7B%22pageIndex%22%3A3%7D" in header
    assert "zotero://open-pdf" not in header
    assert folded.canvas == plain.canvas
    assert validate_bundle(document, folded, note_stem="Synthetic analysis").ok


def test_selected_markdown_image_stays_visible_outside_the_folded_quote():
    value = payload()
    value["profile"]["markdown_source_images"] = True
    claim = next(c for c in value["claims"] if c["claim_id"] == "m-1")
    point = next(p for p in claim["points"] if p["point_id"] == "method")
    source = deepcopy(point["evidence"]["source_spans"][0])
    source.pop("quote")
    point["canvas_image"] = {
        "kind": "process_diagram",
        "asset_id": "asset:synthetic-flow",
        "caption": "Figure 1: centering flow",
        "image_path": "attachments/flow.png",
        "sha256": "a" * 64,
        "pixel_width": 1200,
        "pixel_height": 360,
        "source": source,
    }
    document = AnalysisDocument.model_validate(value)
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    value["profile"]["markdown_folded_quotes"] = False
    plain = render_analysis(AnalysisDocument.model_validate(value), note_stem="Synthetic analysis")
    assert bundle.canvas == plain.canvas
    anchor = "^point-3-m-1-method"
    point_block = bundle.markdown[bundle.markdown.index(anchor) :]
    assert point_block.index("[!quote]-") < point_block.index("![")
    image_line = next(line for line in point_block.splitlines() if "attachments/flow.png" in line)
    assert not image_line.lstrip().startswith(">")
    assert "\n\n" + image_line in point_block
    assert "Figure 1: centering flow" in point_block
    assert validate_bundle(document, bundle, note_stem="Synthetic analysis").ok
