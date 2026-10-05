"""The public IR schema and model agree on Markdown-only quotations."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.models import AnalysisDocument

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text(encoding="utf-8"))
FIXTURE = ROOT / "tests/fixtures/analysis-quotations/IR.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_quote_format_round_trip_matches_the_public_schema() -> None:
    document = AnalysisDocument.model_validate(_payload())
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    assert AnalysisDocument.model_validate_json(document.model_dump_json()) == document


@pytest.mark.parametrize("quote", [None, "", " \n", "x" * 1601])
@pytest.mark.parametrize("owner", ["claim", "point"])
def test_invalid_quoted_evidence_fails_both_contracts(quote: str | None, owner: str) -> None:
    payload = _payload()
    claim = payload["claims"][0]
    evidence = claim["evidence"] if owner == "claim" else claim["points"][0]["evidence"]
    evidence["source_spans"][0]["quote"] = quote
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


@pytest.mark.parametrize("length", [400, 401, 1600])
@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
@pytest.mark.parametrize("owner", ["claim", "point"])
def test_context_quote_capacity_matches_model_and_public_schema(length, kind, owner) -> None:
    payload = _payload()
    claim = payload["claims"][0]
    evidence = claim["evidence"] if owner == "claim" else claim["points"][0]["evidence"]
    if kind == "vault_markdown":
        evidence["source_spans"] = [{
            "kind": kind,
            "source_id": "00000000-0000-4000-8000-000000000001",
            "artifact_id": "document:synthetic-source",
            "vault_path": "SOURCE.md",
            "block_id": "fixed-state",
        }]
    evidence["source_spans"][0]["quote"] = "x" * length
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(payload, SCHEMA)
    jsonschema.validate(payload, AnalysisDocument.model_json_schema())
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    selected = document.claims[0].evidence if owner == "claim" else document.claims[0].points[0].evidence
    assert selected.source_spans[0].quote == "x" * length


@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_context_quote_above_capacity_is_rejected(kind) -> None:
    payload = _payload()
    evidence = payload["claims"][0]["evidence"]
    if kind == "vault_markdown":
        evidence["source_spans"] = [{
            "kind": kind,
            "source_id": "00000000-0000-4000-8000-000000000001",
            "artifact_id": "document:synthetic-source",
            "vault_path": "SOURCE.md",
            "block_id": "fixed-state",
        }]
    evidence["source_spans"][0]["quote"] = "x" * 1601
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


@pytest.mark.parametrize("value", [None, "true", 1])
def test_quotation_profile_requires_a_real_boolean(value) -> None:
    payload = _payload()
    payload["profile"]["markdown_quotes"] = value
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_older_quote_free_payload_keeps_its_serialized_profile() -> None:
    payload = _payload()
    payload["profile"].pop("markdown_quotes")
    claim = payload["claims"][0]
    for evidence in (claim["evidence"], *(point["evidence"] for point in claim["points"])):
        evidence["source_spans"][0].pop("quote")
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    assert "markdown_quotes" not in document.model_dump(mode="json")["profile"]


def test_registered_markdown_quote_is_an_additive_source_span_field() -> None:
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
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    assert document.claims[0].evidence.source_spans[0].quote == "The method keeps the state representation fixed."
