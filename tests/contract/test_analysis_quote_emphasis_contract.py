"""Public source-span schema accepts emphasis without rewriting quotations."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.models import AnalysisDocument

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
QUOTE = "Trials use a fixed camera pose. Success is 72% under this setup. No other setup was tested."
DIRECT = "Success is 72% under this setup."


def _payload(kind="zotero_pdf", emphasis=None) -> dict:
    payload = json.loads((ROOT / "tests/fixtures/analysis-quotations/IR.json").read_text())
    evidence = payload["claims"][0]["evidence"]
    if kind == "vault_markdown":
        evidence["source_spans"] = [{
            "kind": kind, "source_id": "00000000-0000-4000-8000-000000000001",
            "artifact_id": "document:synthetic-source", "vault_path": "SOURCE.md",
            "block_id": "fixed-camera",
        }]
    evidence["source_spans"][0].update(quote=QUOTE, quote_emphasis=[DIRECT] if emphasis is None else emphasis)
    return payload


@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_optional_emphasis_round_trips_through_model_and_public_schema(kind) -> None:
    payload = _payload(kind)
    jsonschema.validate(payload, SCHEMA)
    jsonschema.validate(payload, AnalysisDocument.model_json_schema())
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    restored = AnalysisDocument.model_validate_json(document.model_dump_json())
    assert restored == document
    assert restored.claims[0].evidence.source_spans[0].quote == QUOTE
    assert restored.claims[0].evidence.source_spans[0].quote_emphasis == [DIRECT]


@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
@pytest.mark.parametrize("emphasis", [[""], [" "], [" " + DIRECT], [DIRECT + " "], [DIRECT + "\n"], [42], ["x" * 1601], DIRECT, [DIRECT] * 9])
def test_structurally_invalid_emphasis_fails_both_contracts(kind, emphasis) -> None:
    payload = _payload(kind, emphasis)
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


@pytest.mark.parametrize("kind", ["zotero_pdf", "vault_markdown"])
def test_nonempty_emphasis_needs_a_quote_in_both_contracts(kind) -> None:
    payload = _payload(kind)
    payload["profile"]["markdown_quotes"] = False
    payload["claims"][0]["evidence"]["source_spans"][0].pop("quote")
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_public_schema_does_not_claim_to_compare_arbitrary_source_strings() -> None:
    payload = _payload(emphasis=["This does not occur in the quote."])
    jsonschema.validate(payload, SCHEMA)
    with pytest.raises(ValidationError, match="emphasis"):
        AnalysisDocument.model_validate(payload)


@pytest.mark.parametrize("owner", ["claim", "point"])
@pytest.mark.parametrize("invalid", ["quote-free-profile", "unavailable-evidence"])
def test_non_displaying_or_unavailable_evidence_is_rejected_by_both_contracts(owner, invalid) -> None:
    payload = _payload()
    claim = payload["claims"][0]
    if owner == "point":
        claim["points"][0]["evidence"] = claim["evidence"]
        claim["evidence"] = {"kind": "unverifiable", "detail": "Claim is unavailable."}
    evidence = claim["evidence"] if owner == "claim" else claim["points"][0]["evidence"]
    if invalid == "quote-free-profile":
        payload["profile"]["markdown_quotes"] = False
    else:
        evidence.update(kind="unverifiable", detail="Unavailable source.")
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)
