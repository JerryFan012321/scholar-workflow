"""Exact source fragments are emphasized in Markdown, never in Canvas."""
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
from scholar_workflow.analysis.updates import plan_analysis_update, render_analysis_projection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SOURCE = (FIXTURES / "analysis-quote-emphasis/SOURCE.md").read_text().split("\n\n")[1].strip()
DIRECT = "The proposed model achieves 72% success over 50 trials under this setup."


def _evidence(quote=SOURCE, emphasis=None, *, kind="zotero_pdf", inference=False) -> dict:
    span = {
        "kind": "zotero_pdf", "library_type": "personal", "library_id": "99999",
        "attachment_key": "AB12CD34", "content_hash": "md5:" + "a" * 32,
        "page_index": 3,
    } if kind == "zotero_pdf" else {
        "kind": "vault_markdown", "source_id": "00000000-0000-4000-8000-000000000001",
        "artifact_id": "document:synthetic-source", "vault_path": "SOURCE.md",
        "block_id": "fixed-camera",
    }
    span["quote"] = quote
    if emphasis is not None:
        span["quote_emphasis"] = emphasis
    return {
        "kind": "analysis_inference" if inference else "author_stated",
        **({"detail": "Inference restricted to the fixed-camera setup."} if inference
           else {"anchor": "Synthetic physical page 4"}),
        "source_spans": [span],
    }


def _payload(version: int, owner: str, *, emphasis=None) -> dict:
    path = "analysis-quotations/IR.json" if version == 4 else "analysis_v5_toy.json"
    payload = json.loads((FIXTURES / path).read_text())
    claim_id = "fixed-state" if version == 4 else "a-t" if owner == "claim" else "m-1"
    claim = next(claim for claim in payload["claims"] if claim["claim_id"] == claim_id)
    record = claim if owner == "claim" else next(
        point for point in claim["points"] if point["point_id"] == "method"
    )
    record["body" if owner == "claim" else "text"] = (
        "The synthetic model reports 72% success in 50 fixed-camera trials."
    )
    record["evidence"] = _evidence(emphasis=emphasis)
    return payload


def test_emphasis_matches_hand_written_expected_excerpt() -> None:
    evidence = Evidence.model_validate(_evidence(emphasis=[DIRECT]))
    expected = (FIXTURES / "analysis-quote-emphasis/EXPECTED-EXCERPTS.md").read_text().rstrip()
    assert "\n".join(reference_source_quote_lines(evidence, "en")).lstrip("\n") == expected
    assert evidence.source_spans[0].quote == SOURCE
    assert "**" not in evidence.source_spans[0].quote


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("inference", [False, True])
@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_labels_distinguish_direct_evidence_from_inference(language, inference, kind) -> None:
    evidence = Evidence.model_validate(_evidence(emphasis=[DIRECT], kind=kind, inference=inference))
    result = "\n".join(reference_source_quote_lines(evidence, language))
    label = (
        "推断依据" if inference else "直接证据"
    ) if language == "zh" else (
        "basis for inference" if inference else "direct evidence"
    )
    assert label in result
    assert "**The proposed model achieves 72% success over 50 trials under this setup\\.**" in result
    assert "Trials use a fixed camera pose\\. **" in result
    assert "** Performance outside this setup has not been evaluated\\." in result
    if kind == "vault_markdown":
        assert "[[SOURCE#^fixed-camera|" in result


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize("owner", ["claim", "point"])
def test_projection_and_focused_update_keep_all_canvas_data(version, owner) -> None:
    old = AnalysisDocument.model_validate(_payload(version, owner))
    current, baseline = render_analysis_projection(old, note_stem="Synthetic analysis")
    revised_payload = _payload(version, owner, emphasis=[DIRECT])
    revised = AnalysisDocument.model_validate(revised_payload)
    rendered = render_analysis(revised, note_stem="Synthetic analysis")
    assert rendered.canvas == current.canvas
    assert "**The proposed model achieves" in rendered.markdown
    assert validate_bundle(revised, rendered, note_stem="Synthetic analysis").ok
    role = "abstract" if version == 5 and owner == "claim" else "method"
    revised_payload["profile"].update(kind="focused", roles=[role])
    revised_payload["claims"] = [claim for claim in revised_payload["claims"] if claim["role"] == role]
    plan = plan_analysis_update(
        baseline=baseline, current=current,
        update=AnalysisDocument.model_validate(revised_payload), note_stem="Synthetic analysis",
    )
    assert plan.status == "ready", plan.conflicts
    assert plan.proposed.markdown == rendered.markdown
    assert plan.proposed.canvas == current.canvas
    assert [claim.model_dump() for claim in plan.document.claims if claim.role != role] == [
        claim.model_dump() for claim in old.claims if claim.role != role
    ]


@pytest.mark.parametrize("version", [4, 5])
def test_missing_or_empty_emphasis_preserves_old_serialization_and_rendering(version) -> None:
    old = AnalysisDocument.model_validate(_payload(version, "claim"))
    empty = AnalysisDocument.model_validate(_payload(version, "claim", emphasis=[]))
    assert empty.model_dump(mode="json") == old.model_dump(mode="json")
    assert empty.model_dump_json() == old.model_dump_json()
    assert render_analysis(empty, note_stem="Synthetic analysis") == render_analysis(
        old, note_stem="Synthetic analysis"
    )


@pytest.mark.parametrize("quote,emphasis", [
    (SOURCE, ["A paraphrase of the result."]),
    (SOURCE, [""]), (SOURCE, [" "]), (SOURCE, [" " + DIRECT]),
    (SOURCE, [DIRECT + " "]), (SOURCE, [DIRECT + "\n"]),
    (SOURCE, [DIRECT, "72% success"]),
    (SOURCE, [DIRECT, DIRECT]), ("Same. Same.", ["Same."]), ("aaa", ["aa"]),
    (None, [DIRECT]), (SOURCE, [42]), (SOURCE, DIRECT),
    (SOURCE, [DIRECT] * 9),
])
@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_invalid_fragments_are_rejected_without_changing_source(quote, emphasis, kind) -> None:
    payload = _evidence(quote, emphasis, kind=kind)
    original = deepcopy(payload)
    with pytest.raises(ValidationError):
        Evidence.model_validate(payload)
    assert payload == original


def test_multiple_fragments_use_source_order_not_metadata_order() -> None:
    quote = "Only 50 trials were run. No unseen setup was evaluated."
    evidence = Evidence.model_validate(_evidence(quote, ["No unseen setup", "Only 50 trials"]))
    assert reference_source_quote_lines(evidence, "en")[-1] == (
        "> **Only 50 trials** were run\\. **No unseen setup** was evaluated\\."
    )
    adjacent = Evidence.model_validate(_evidence("AB. Context remains.", ["B.", "A"]))
    assert reference_source_quote_lines(adjacent, "en")[-1] == (
        "> **AB\\.** Context remains\\."
    )


def test_multiline_unicode_and_source_syntax_remain_literal() -> None:
    quote = "背景条件保持不变。\n  不支持 [x](https://example.invalid) *同步* <tag> &\n下一行 ^claim-fake。\n范围未扩展。"
    fragment = "不支持 [x](https://example.invalid) *同步* <tag> &\n下一行 ^claim-fake。"
    evidence = Evidence.model_validate(_evidence(quote, [fragment]))
    lines = reference_source_quote_lines(evidence, "zh")[3:]
    assert lines[0] == "> 背景条件保持不变。"
    assert lines[1].startswith(">   **不支持 \\[x\\]\\(https://example\\.invalid\\) \\*同步\\* &lt;tag&gt; &amp;")
    assert lines[1].endswith("**") and lines[2].endswith("**")
    assert lines[-1] == "> 范围未扩展。"
    decoded = "\n".join(html.unescape(re.sub(r"\\(.)", r"\1", line[2:].replace("**", ""))) for line in lines)
    assert decoded == quote


@pytest.mark.parametrize("kind", ["unverifiable", "not_reported", "not_applicable"])
def test_unavailable_evidence_cannot_present_a_direct_emphasis(kind) -> None:
    payload = _evidence(emphasis=[DIRECT])
    payload.update(kind=kind, detail="Source unavailable.")
    with pytest.raises(ValidationError, match="emphasis"):
        Evidence.model_validate(payload)


def test_quote_free_profile_rejects_non_displaying_emphasis() -> None:
    payload = _payload(4, "claim", emphasis=[DIRECT])
    payload["profile"]["markdown_quotes"] = False
    with pytest.raises(ValidationError, match="emphasis"):
        AnalysisDocument.model_validate(payload)


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize("owner", ["claim", "point"])
@pytest.mark.parametrize("operation", ["remove", "alter", "relocate"])
def test_missing_changed_or_detached_emphasis_fails_conformance(version, owner, operation) -> None:
    document = AnalysisDocument.model_validate(_payload(version, owner, emphasis=[DIRECT]))
    bundle = render_analysis(document, note_stem="Synthetic analysis")
    fragment = "**The proposed model achieves 72% success over 50 trials under this setup\\.**"
    if operation == "alter":
        markdown = bundle.markdown.replace(fragment, fragment.replace("72%", "73%"), 1)
    else:
        markdown = bundle.markdown.replace(fragment, fragment[2:-2], 1)
        if operation == "relocate":
            markdown += "\n\n> " + fragment + "\n"
    report = validate_bundle(
        document, AnalysisBundle(markdown=markdown, canvas=bundle.canvas),
        note_stem="Synthetic analysis",
    )
    assert not report.ok
    code = "markdown-source-quote-mismatch" if version == 4 else "markdown-source-quote-placement"
    assert code in {finding.code for finding in report.findings}


@pytest.mark.parametrize("version", [4, 5])
def test_focused_emphasis_update_preserves_a_concurrent_human_edit_by_conflicting(version) -> None:
    old = AnalysisDocument.model_validate(_payload(version, "point"))
    current, baseline = render_analysis_projection(old, note_stem="Synthetic analysis")
    human = "\n\nHuman reading note: keep this unrelated paragraph.\n"
    mixed = AnalysisBundle(markdown=current.markdown + human, canvas=deepcopy(current.canvas))
    payload = _payload(version, "point", emphasis=[DIRECT])
    payload["profile"].update(kind="focused", roles=["method"])
    payload["claims"] = [claim for claim in payload["claims"] if claim["role"] == "method"]
    plan = plan_analysis_update(
        baseline=baseline, current=mixed,
        update=AnalysisDocument.model_validate(payload), note_stem="Synthetic analysis",
    )
    assert plan.status == "conflict"
    assert "markdown-revision-conflict" in plan.conflicts
    assert plan.current == mixed
    assert human in plan.current.markdown
    assert plan.baseline is None
