"""V5 source counts follow the record; legacy bounds and per-span checks remain."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.cli import main

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text(encoding="utf-8"))
NOTE_STEM = "Synthetic multi-source analysis"


def _payload(version: int, count: int, target: str) -> dict:
    statement = " ".join(f"Apply operation {index}." for index in range(1, count + 1))
    evidence = {
        "kind": "author_stated",
        "anchor": "Independent synthetic physical pages",
        "source_spans": [
            {
                "kind": "zotero_pdf",
                "library_type": "personal",
                "library_id": "99999999",
                "attachment_key": "SYNTH001",
                "content_hash": "sha256:" + "0" * 64,
                "page_index": index - 1,
                "quote": f"Apply operation {index}.",
                "quote_emphasis": [f"Apply operation {index}."],
            }
            for index in range(1, count + 1)
        ],
    }
    absent = {"kind": "not_applicable", "detail": "Synthetic grouping only."}
    claim = {
        "claim_id": "multi-source",
        "role": "method",
        "outline_path": "method/modules/synthetic",
        "title": "Synthetic source sequence",
        "body": statement if target == "claim" else "Synthetic source grouping.",
        "evidence": evidence if target == "claim" else absent,
        "points": [],
    }
    if target == "point":
        claim["points"] = [{"point_id": "method", "text": statement, "evidence": evidence}]
    if len(statement) > 180:
        if target == "claim":
            claim["canvas_summary"] = "Apply every operation in the synthetic sequence."
        else:
            claim["points"][0]["canvas_summary"] = "Apply every operation in the synthetic sequence."
    payload = {
        "schema_version": version,
        "artifact_id": "analysis:paper:synthetic-multi-source",
        "paper_title": "Synthetic multi-source record",
        "language": "en",
        "profile": {
            "kind": "focused",
            "framework": "reference_tree_v5" if version == 5 else "reference_tree",
            "roles": ["method"],
            "markdown_quotes": True,
            "markdown_folded_quotes": True,
        },
        "reader": {"kind": "zotero_native"},
        "claims": [claim],
    }
    if version < 4:
        payload.pop("reader")
        payload["profile"].update(
            framework="legacy", roles=["task"], markdown_quotes=False,
            markdown_folded_quotes=False,
        )
        claim["role"] = "task"
        claim.pop("outline_path")
        for span in evidence["source_spans"]:
            span.pop("quote_emphasis")
    return payload


@pytest.mark.parametrize("count", [3, 4, 8, 9, 12, 20])
@pytest.mark.parametrize("target", ["claim", "point"])
def test_v5_model_preserves_every_supplied_span(count: int, target: str) -> None:
    payload = _payload(5, count, target)
    document = AnalysisDocument.model_validate(payload)
    claim = document.claims[0]
    evidence = claim.evidence if target == "claim" else claim.points[0].evidence
    supplied = payload["claims"][0]
    expected = supplied["evidence"] if target == "claim" else supplied["points"][0]["evidence"]
    assert [span.model_dump(mode="json", exclude_none=True) for span in evidence.source_spans] == expected["source_spans"]


@pytest.mark.parametrize("count", [3, 4, 8, 9, 12, 20])
@pytest.mark.parametrize("target", ["claim", "point"])
def test_v5_schema_accepts_all_supplied_sources(count: int, target: str) -> None:
    jsonschema.Draft202012Validator(SCHEMA).validate(_payload(5, count, target))


@pytest.mark.parametrize("count", [3, 4, 8, 9, 12])
@pytest.mark.parametrize("target", ["claim", "point"])
def test_v5_render_keeps_all_sources_and_folded_passages(count: int, target: str) -> None:
    document = AnalysisDocument.model_validate(_payload(5, count, target))
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    assert validate_bundle(document, bundle, note_stem=NOTE_STEM).ok
    text = "\n".join(node.get("text", "") for node in bundle.canvas["nodes"])
    assert bundle.markdown.count("> [!quote]-") == count
    for index in range(1, count + 1):
        uri = f"zotero://open-pdf/library/items/SYNTH001?page={index}"
        assert uri in bundle.markdown and uri in text
        assert rf"**Apply operation {index}\.**" in bundle.markdown
    anchor = "claim-multi-source" if target == "claim" else "point-12-multi-source-method"
    assert f"^{anchor}" in bundle.markdown
    assert f"[[{NOTE_STEM}#^{anchor}|Analysis]]" in text


@pytest.mark.parametrize("count", [4, 8, 9])
@pytest.mark.parametrize("target", ["claim", "point"])
def test_v4_retains_three_sources_and_rejects_more(count: int, target: str) -> None:
    payload = _payload(4, 3, target)
    AnalysisDocument.model_validate(payload)
    jsonschema.Draft202012Validator(SCHEMA).validate(payload)
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(_payload(4, count, target))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(_payload(4, count, target))


@pytest.mark.parametrize("version,target", [(1, "claim"), (2, "claim"), (2, "point"), (3, "claim"), (3, "point")])
def test_legacy_retains_eight_sources_and_rejects_nine(version: int, target: str) -> None:
    payload = _payload(version, 8, target)
    AnalysisDocument.model_validate(payload)
    jsonschema.Draft202012Validator(SCHEMA).validate(payload)
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(_payload(version, 9, target))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(SCHEMA).validate(_payload(version, 9, target))


@pytest.mark.parametrize("field,value", [
    ("attachment_key", "bad-key"),
    ("page_index", -1),
    ("content_hash", "sha256:invalid"),
    ("quote", "x" * 1601),
    ("quote_emphasis", [f"fragment-{index}" for index in range(9)]),
])
@pytest.mark.parametrize("target", ["claim", "point"])
def test_v5_still_rejects_invalid_last_source(field: str, value: object, target: str) -> None:
    payload = _payload(5, 12, target)
    claim = payload["claims"][0]
    evidence = claim["evidence"] if target == "claim" else claim["points"][0]["evidence"]
    evidence["source_spans"][-1][field] = value
    with pytest.raises(ValidationError) as failure:
        AnalysisDocument.model_validate(payload)
    assert any(
        ("source_spans", 11) == error["loc"][-4:-2]
        for error in failure.value.errors()
    )
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(payload))
    assert any(tuple(error.absolute_path)[-2:] == ("source_spans", 11) for error in errors)


@pytest.mark.parametrize("target", ["claim", "point"])
def test_v5_checks_emphasis_against_the_last_quote(target: str) -> None:
    payload = _payload(5, 12, target)
    claim = payload["claims"][0]
    evidence = claim["evidence"] if target == "claim" else claim["points"][0]["evidence"]
    evidence["source_spans"][-1]["quote_emphasis"] = ["Not in the supplied passage."]
    with pytest.raises(ValidationError, match="quote_emphasis"):
        AnalysisDocument.model_validate(payload)


@pytest.mark.parametrize("target", ["claim", "point"])
def test_same_page_passages_stay_complete_with_explicit_link_deduplication(target: str) -> None:
    payload = _payload(5, 12, target)
    payload["profile"]["canvas_unique_sources"] = True
    claim = payload["claims"][0]
    evidence = claim["evidence"] if target == "claim" else claim["points"][0]["evidence"]
    for span in evidence["source_spans"]:
        span["page_index"] = 0
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    assert validate_bundle(document, bundle, note_stem=NOTE_STEM).ok
    assert bundle.markdown.count("> [!quote]-") == 12
    text = "\n".join(node.get("text", "") for node in bundle.canvas["nodes"])
    uri = "zotero://open-pdf/library/items/SYNTH001?page=1"
    assert text.count(uri) == 1
    assert bundle.markdown.count(uri) >= 12
    for index in range(1, 13):
        assert rf"**Apply operation {index}\.**" in bundle.markdown
    saved_claim = document.model_dump(mode="json")["claims"][0]
    saved_evidence = saved_claim["evidence"] if target == "claim" else saved_claim["points"][0]["evidence"]
    assert len(saved_evidence["source_spans"]) == 12


@pytest.mark.parametrize("target", ["claim", "point"])
def test_many_sources_do_not_bypass_real_node_height(target: str) -> None:
    document = AnalysisDocument.model_validate(_payload(5, 200, target))
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    assert any(node["height"] > 420 for node in bundle.canvas["nodes"])
    report = validate_bundle(document, bundle, note_stem=NOTE_STEM)
    assert not report.ok
    assert any(finding.code == "canvas-node-height-limit" for finding in report.findings)
    assert bundle.markdown.count("> [!quote]-") == 200
    text = "\n".join(node.get("text", "") for node in bundle.canvas["nodes"])
    for index in range(1, 201):
        uri = f"zotero://open-pdf/library/items/SYNTH001?page={index}"
        assert uri in bundle.markdown and uri in text


def test_public_batch_retains_late_sources_and_rejects_changed_replay(tmp_path: Path) -> None:
    request = {
        "schema_version": 1,
        "batch_id": "synthetic-source-capacity",
        "items": [{
            "item_id": "synthetic",
            "zotero_item_key": "SYNTH002",
            "note_stem": NOTE_STEM,
            "document": _payload(5, 12, "point"),
        }],
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    stage = tmp_path / "stage"
    args = ["analysis", "batch-run", "--request", str(request_path),
            "--state-db", str(tmp_path / "batch.db"), "--stage-root", str(stage)]
    cli = CliRunner()
    env = {"SCHOLAR_WORKFLOW_HOME": str(tmp_path / "state")}
    first = cli.invoke(main, args, env=env)
    assert first.exit_code == 0, first.output
    assert json.loads(first.output)["items"][0]["state"] == "validated"
    package = stage / request["batch_id"] / "synthetic"
    baseline = AnalysisBaseline.model_validate_json((package / "analysis.baseline.json").read_text())
    assert len(baseline.document.claims[0].points[0].evidence.source_spans) == 12
    before = {path.name: path.read_bytes() for path in package.iterdir()}
    second = cli.invoke(main, args, env=env)
    assert second.exit_code == 0, second.output
    assert {path.name: path.read_bytes() for path in package.iterdir()} == before
    displayed = tmp_path / "displayed"
    displayed.mkdir()
    for name, data in before.items():
        (displayed / (f"{NOTE_STEM}.md" if name == "analysis.md" else name)).write_bytes(data)
    checked = cli.invoke(main, [
        "analysis", "check-bundle", str(displayed), "--markdown", f"{NOTE_STEM}.md",
        "--canvas", "analysis.canvas", "--sidecar", "analysis.baseline.json",
        "--require-ir", "5", "--format", "json",
    ], env=env)
    assert checked.exit_code == 0, checked.output
    assert json.loads(checked.output)["status"] == "conformant"
    spans = request["items"][0]["document"]["claims"][0]["points"][0]["evidence"]["source_spans"]
    spans[-1]["page_index"] += 1
    request_path.write_text(json.dumps(request), encoding="utf-8")
    changed = cli.invoke(main, args, env=env)
    assert changed.exit_code == 5 and "different request" in changed.output
    assert {path.name: path.read_bytes() for path in package.iterdir()} == before
