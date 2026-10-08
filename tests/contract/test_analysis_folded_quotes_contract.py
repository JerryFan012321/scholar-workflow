"""Folded excerpts have an explicit opt-in without changing legacy serialization."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.models import AnalysisDocument

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())


def _payload(version=5):
    path = "analysis_v5_toy.json" if version == 5 else "analysis-quotations/IR.json"
    value = json.loads((ROOT / "tests/fixtures" / path).read_text())
    value["profile"]["markdown_folded_quotes"] = True
    return value


@pytest.mark.parametrize("version", [4, 5])
def test_folded_option_round_trips_through_public_schema_and_model(version):
    value = _payload(version)
    jsonschema.validate(value, SCHEMA)
    jsonschema.validate(value, AnalysisDocument.model_json_schema())
    document = AnalysisDocument.model_validate(value)
    jsonschema.validate(document.model_dump(mode="json"), SCHEMA)
    restored = AnalysisDocument.model_validate_json(document.model_dump_json())
    assert restored == document and restored.profile.markdown_folded_quotes


@pytest.mark.parametrize("version", [4, 5])
@pytest.mark.parametrize(
    "invalid", ["no-quotes", "missing-quotes", "legacy", "string", "number", "null"]
)
def test_non_displaying_or_non_boolean_fold_is_rejected(version, invalid):
    value = _payload(version)
    if invalid == "no-quotes":
        value["profile"]["markdown_quotes"] = False
    elif invalid == "missing-quotes":
        value["profile"].pop("markdown_quotes")
    elif invalid == "legacy":
        value["profile"]["framework"] = "legacy"
    else:
        value["profile"]["markdown_folded_quotes"] = {"string": "true", "number": 1, "null": None}[
            invalid
        ]
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, SCHEMA)


@pytest.mark.parametrize("version", [4, 5])
def test_false_and_omitted_fold_have_the_same_legacy_serialized_ir(version):
    value = _payload(version)
    value["profile"]["markdown_folded_quotes"] = False
    jsonschema.validate(value, SCHEMA)
    false = AnalysisDocument.model_validate(value)
    value["profile"].pop("markdown_folded_quotes")
    omitted = AnalysisDocument.model_validate(value)
    assert false.model_dump_json() == omitted.model_dump_json()
    assert "markdown_folded_quotes" not in false.model_dump(mode="json")["profile"]
