"""Contract: literature-tree.schema.json pins the novelty-tree structure.

The tree is a 3-level classification (topic → task → pipeline) whose leaves are
paper resource_id refs; a flat paper_list is the single metadata ledger. This test
locks the topology, the paper-list-alongside requirement, the classified flag, and
the deferred challenge_insight_tree seam.
"""
from __future__ import annotations
import json
from pathlib import Path
import jsonschema
import pytest

SCHEMA = json.loads(
    (Path(__file__).parents[2] / "contracts" / "literature-tree.schema.json").read_text()
)


def _paper(rid, title, classified):
    return {"resource_id": rid, "title": title, "classified": classified}


FULL = {
    "generated_at": "2026-08-01T00:00:00Z",
    "schema_version": "1",
    "topic": "novel view synthesis",
    "paper_list": [
        _paper("arxiv:2003.08934", "NeRF", True),
        _paper("arxiv:2308.04079", "3D Gaussian Splatting", True),
        _paper("arxiv:2401.00001", "some uncollected follow-up", False),
    ],
    "tree": {
        "name": "novel view synthesis", "kind": "topic",
        "children": [
            {
                "name": "photorealistic scene reconstruction", "kind": "task",
                "novelty_anchor": "arxiv:2003.08934",
                "anchor_note": "first framed as continuous volumetric field",
                "children": [
                    {"name": "implicit neural field", "kind": "pipeline",
                     "novelty_anchor": "arxiv:2003.08934",
                     "papers": ["arxiv:2003.08934"]},
                    {"name": "explicit gaussian primitives", "kind": "pipeline",
                     "novelty_anchor": "arxiv:2308.04079",
                     "papers": ["arxiv:2308.04079"]},
                ],
            }
        ],
    },
}


def test_full_doc_validates():
    jsonschema.validate(FULL, SCHEMA)


def test_minimal_doc_paperlist_only_empty_topic_tree():
    """Collected-but-unclassified state: papers listed, tree is just an empty topic."""
    doc = {
        "generated_at": "2026-08-01T00:00:00Z",
        "paper_list": [_paper("arxiv:2003.08934", "NeRF", False)],
        "tree": {"name": "novel view synthesis", "kind": "topic"},
    }
    jsonschema.validate(doc, SCHEMA)


def test_challenge_insight_seam_is_open():
    doc = dict(FULL, challenge_insight_tree={"challenges": ["aliasing"], "insights": ["mip"]})
    jsonschema.validate(doc, SCHEMA)


@pytest.mark.parametrize("missing", ["paper_list", "tree", "generated_at"])
def test_missing_required_fails(missing):
    doc = {k: v for k, v in FULL.items() if k != missing}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)


def test_unknown_top_level_key_fails():
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(FULL, edges=[]), SCHEMA)


def test_bad_concept_kind_fails():
    doc = json.loads(json.dumps(FULL))
    doc["tree"]["children"][0]["kind"] = "milestone"  # not in enum
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, SCHEMA)
