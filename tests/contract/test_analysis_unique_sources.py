"""Public schema and runtime agree on the v5-only source projection option."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.models import AnalysisDocument

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text(encoding="utf-8"))


def _payload() -> dict:
    return json.loads((ROOT / "tests/fixtures/analysis_v5_toy.json").read_text(encoding="utf-8"))


def test_unique_sources_round_trip_matches_the_public_schema() -> None:
    payload = _payload()
    payload["profile"]["canvas_unique_sources"] = True
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(payload, SCHEMA)
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    assert AnalysisDocument.model_validate_json(document.model_dump_json()) == document


@pytest.mark.parametrize("value", [None, "true", 1])
def test_unique_sources_requires_a_real_boolean(value) -> None:
    payload = _payload()
    payload["profile"]["canvas_unique_sources"] = value
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)


def test_existing_v5_omits_the_new_projection_field() -> None:
    document = AnalysisDocument.model_validate(_payload())
    assert "canvas_unique_sources" not in document.model_dump(mode="json")["profile"]
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)


def test_unique_sources_cannot_be_enabled_on_an_existing_v4_format() -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/analysis-quotations/IR.json").read_text(encoding="utf-8")
    )
    payload["profile"]["canvas_unique_sources"] = True
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)
