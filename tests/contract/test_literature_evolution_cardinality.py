"""Independent synthetic cardinality and identity contracts for evolution previews."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from scholar_workflow.knowledge.literature_evolution import (
    LiteratureEvolution,
    validate_evolution,
)


def _paper(index: int) -> dict:
    return {
        "paper_id": f"paper-{index}",
        "source_id": "11111111-1111-4111-8111-111111111111",
        "object_id": f"synthetic-paper:{index}",
        "title": f"Synthetic paper {index}",
        "note_path": f"Field/resources/paper-{index}/Paper.md",
    }


def _statement(text: str, *, supported: bool = False) -> dict:
    return {
        "text": text,
        "basis": "author_statement" if supported else "unverified",
        "evidence": [{
            "paper_id": "paper-0",
            "library_type": "personal",
            "library_id": "1",
            "attachment_key": "BCDE3456",
            "content_hash": "sha256:" + "a" * 64,
            "page_index": 0,
            "section": "Synthetic source location",
        }] if supported else [],
    }


def _contribution(index: int) -> dict:
    return {
        "contribution_id": f"contribution-{index}",
        "paper_id": "paper-0",
        "title": f"Synthetic contribution {index}",
        "novelty_types": [1] if index == 0 else [3],
        "placement": "main" if index == 0 else "local",
        "parent_id": None if index == 0 else "contribution-0",
        "classification": _statement(f"Classification {index}", supported=True),
    }


def _relation(index: int) -> dict:
    return {
        "relation_id": f"relation-{index}",
        "from_id": "contribution-0",
        "to_id": "contribution-1",
        "kind": "comparison",
        "change": _statement(f"Change {index}", supported=True),
        "reason": _statement(f"Reason {index}"),
        "benefit": _statement(f"Benefit {index}"),
        "cost": _statement(f"Unverified cost {index}"),
        "conditions": _statement(f"Unverified conditions {index}"),
    }


def _document(collection: str) -> dict:
    document = {
        "schema_version": 1,
        "topic": "Synthetic repeatable collections",
        "corpus_scope": "Explicit synthetic cardinality test, not scientific evidence",
        "language": "en",
        "synthetic": True,
        "papers": [_paper(0)],
        "contributions": [_contribution(0), _contribution(1)],
        "relations": [],
    }
    if collection == "papers":
        document["papers"] = [_paper(index) for index in range(513)]
    elif collection == "contributions":
        document["contributions"] = [_contribution(index) for index in range(2049)]
    elif collection == "relations":
        document["relations"] = [_relation(index) for index in range(4097)]
    else:
        raise AssertionError(f"Unknown independent collection: {collection}")
    return document


@pytest.mark.parametrize("collection,count", [
    ("papers", 513), ("contributions", 2049), ("relations", 4097),
])
def test_repeatable_collections_preserve_every_identity_beyond_old_threshold(collection, count):
    document = _document(collection)
    before = copy.deepcopy(document)
    normalized = validate_evolution(document)
    assert document == before
    assert normalized == before
    assert len(normalized[collection]) == count
    identifier = {"papers": "paper_id", "contributions": "contribution_id",
                  "relations": "relation_id"}[collection]
    assert [row[identifier] for row in normalized[collection]] == [
        row[identifier] for row in before[collection]
    ]
    assert "maxItems" not in LiteratureEvolution.model_json_schema()["properties"][collection]


@pytest.mark.parametrize("collection", ["papers", "contributions", "relations"])
def test_public_schema_has_no_repeatable_collection_quota(collection):
    path = Path(__file__).parents[2] / "contracts/literature-evolution.schema.json"
    schema = json.loads(path.read_bytes())
    errors = [(list(error.absolute_path), error.validator)
              for error in jsonschema.Draft202012Validator(schema).iter_errors(_document(collection))]
    assert errors == []
    assert "maxItems" not in schema["properties"][collection]


@pytest.mark.parametrize("collection,case,message", [
    ("papers", "duplicate-paper-id", "paper and contribution identifiers must be unique"),
    ("papers", "duplicate-qualified-paper", "same qualified paper identity"),
    ("contributions", "duplicate-contribution-id", "identifiers must be unique"),
    ("relations", "duplicate-relation-id", "relation identifiers must be unique"),
    ("contributions", "missing-paper", "unknown contribution paper reference"),
    ("contributions", "missing-parent", "structural parent must exist"),
    ("relations", "missing-endpoint", "unknown scientific relation endpoint"),
    ("relations", "missing-evidence-paper", "unknown evidence paper reference"),
])
def test_large_collections_still_reject_identity_and_reference_errors(collection, case, message):
    document = _document(collection)
    if case == "duplicate-paper-id":
        document["papers"][-1]["paper_id"] = "paper-0"
    elif case == "duplicate-qualified-paper":
        document["papers"][-1]["object_id"] = "synthetic-paper:0"
    elif case == "duplicate-contribution-id":
        document["contributions"][-1]["contribution_id"] = "contribution-0"
    elif case == "duplicate-relation-id":
        document["relations"][-1]["relation_id"] = "relation-0"
    elif case == "missing-paper":
        document["contributions"][-1]["paper_id"] = "paper-absent"
    elif case == "missing-parent":
        document["contributions"][-1]["parent_id"] = "contribution-absent"
    elif case == "missing-endpoint":
        document["relations"][-1]["to_id"] = "contribution-absent"
    elif case == "missing-evidence-paper":
        document["relations"][-1]["change"]["evidence"][0]["paper_id"] = "paper-absent"
    else:
        raise AssertionError(f"Unknown independent mutation: {case}")
    before = copy.deepcopy(document)
    with pytest.raises(ValueError, match=message):
        validate_evolution(document)
    assert document == before
