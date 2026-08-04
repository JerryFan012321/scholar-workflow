"""Contract: literature-tree.schema.json pins the novelty-tree structure.

The tree is a variable-depth concept classification whose leaves are paper resource_id
refs; a flat paper_list is the single metadata ledger. Two isomorphic tree types share
one structure, keyed off node kind: a technical tree (topic → task → pipeline → module)
and a challenge tree (topic → challenge → insight). This test locks the topology, the
kind enum, the paper-list-alongside requirement, and the classified flag.
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


def test_summary_and_asset_note_optional_fields():
    """Concept-level summary (内容简介) and paper-level asset_note are optional additions."""
    doc = json.loads(json.dumps(FULL))
    doc["tree"]["children"][0]["summary"] = "This task frames scene reconstruction as a continuous field."
    doc["tree"]["children"][0]["children"][0]["summary"] = "Implicit MLP-based radiance fields."
    doc["paper_list"][0]["asset_note"] = "paper_assets/2020-Mildenhall-NeRF.md"
    doc["paper_list"][0]["doi"] = "10.1145/xyz"
    jsonschema.validate(doc, SCHEMA)


def test_module_level_validates():
    """A technical tree may descend a 4th level: pipeline → module (类3/类4)."""
    doc = json.loads(json.dumps(FULL))
    doc["tree"]["children"][0]["children"][0]["children"] = [
        {"name": "anti-aliasing", "kind": "module",
         "novelty_anchor": "arxiv:2003.08934",
         "papers": ["arxiv:2003.08934"]},
    ]
    jsonschema.validate(doc, SCHEMA)


def test_challenge_tree_reuses_concept_structure():
    """The challenge tree is not a separate seam — it reuses tree+concept, keyed off the
    challenge/insight kinds (topic → challenge → insight → paper)."""
    doc = {
        "generated_at": "2026-08-01T00:00:00Z",
        "paper_list": [_paper("arxiv:2003.08934", "NeRF", True)],
        "tree": {
            "name": "world models", "kind": "topic",
            "children": [{
                "name": "long-horizon 3D consistency", "kind": "challenge",
                "children": [{
                    "name": "persistent scene memory", "kind": "insight",
                    "novelty_anchor": "arxiv:2003.08934",
                    "papers": ["arxiv:2003.08934"]},
                ]},
            ],
        },
    }
    jsonschema.validate(doc, SCHEMA)


def test_retired_seam_key_now_rejected():
    """The old challenge_insight_tree seam is gone; it's now just an unknown top-level key."""
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(FULL, challenge_insight_tree={"x": 1}), SCHEMA)


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
