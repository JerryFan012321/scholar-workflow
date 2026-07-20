"""Contract: report --handoff output must satisfy handoff.schema.json."""
from __future__ import annotations
import json
from pathlib import Path
import jsonschema
from scholar_workflow.cli import _handoff_snapshot, _format_rows

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "contracts" / "handoff.schema.json").read_text()
)

ROWS = [
    {"job_id": "11111111-1111-1111-1111-111111111111", "plan_id": None,
     "resource_id": "paper:arxiv:2401.01234", "state": "zotero_synced",
     "updated_at": "2026-07-20T00:00:00"},
]


def test_handoff_snapshot_matches_schema():
    jsonschema.validate(_handoff_snapshot(ROWS), SCHEMA)


def test_handoff_snapshot_empty_still_valid():
    jsonschema.validate(_handoff_snapshot([]), SCHEMA)


def test_format_rows_csv_has_header():
    out = _format_rows(ROWS, "csv")
    assert out.splitlines()[0] == "job_id,resource_id,state,updated_at"
    assert "paper:arxiv:2401.01234" in out
