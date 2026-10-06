"""Published schema accepts only the explicit safe v5 companion-route contract."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    payload = json.loads((ROOT / "tests/fixtures/analysis_v5_toy.json").read_text())
    schema = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text())
    return payload, schema


def test_safe_vault_relative_companion_route_is_in_published_schema():
    payload, schema = inputs()
    payload["profile"]["canvas_note_path"] = "Examples/Source/Synthetic analysis.md"
    jsonschema.validate(payload, schema)


@pytest.mark.parametrize("path", [
    "/absolute/Note.md", "../Note.md", "a/../Note.md", "a//Note.md", "./Note.md",
    "https://example.org/Note.md", "a\\Note.md", "a/Note.pdf", "a/Note#bad.md",
    "a/Note|bad.md", "a/[Note].md", "a/Note^bad.md", "a/Note\n.md", "a/Note\x00.md",
    "", None, 42, " Note.md", "a/Note.md ", "a/Note\x7f.md", "a/Note.md\n",
])
def test_schema_rejects_unsafe_companion_paths(path):
    payload, schema = inputs()
    payload["profile"]["canvas_note_path"] = path
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_v4_cannot_adopt_the_v5_companion_contract():
    payload, schema = inputs()
    payload["schema_version"] = 4
    payload["profile"].update(framework="reference_tree", canvas_note_path="Analysis.md")
    payload["profile"]["roles"] = ["abstract", "introduction", "method", "limitation"]
    payload["claims"] = [claim for claim in payload["claims"] if claim["role"] != "experiments"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
