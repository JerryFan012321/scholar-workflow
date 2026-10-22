"""Keep host-judged evidence fixtures valid without pretending to score semantics."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_evidence_review"
INPUTS = json.loads((FIXTURES / "inputs.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


def test_input_and_caller_oracle_have_the_same_unique_case_ids() -> None:
    identifiers = [case["id"] for case in INPUTS["cases"]]
    assert identifiers
    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == set(EXPECTED["cases"])
    assert "expected" not in INPUTS


@pytest.mark.parametrize("case", INPUTS["cases"], ids=lambda case: case["id"])
def test_source_quotes_and_emphasis_are_literal_and_unambiguous(case: dict) -> None:
    sources = {source["id"]: source["text"] for source in case["available_source"]}
    assert len(sources) == len(case["available_source"])
    assert case["statement"]
    assert case["evidence_kind"] in {"author_stated", "analysis_inference"}
    if case["evidence_kind"] == "analysis_inference":
        assert case["evidence_detail"]
    for span in case["presented_spans"]:
        quote = span["quote"]
        assert quote and quote in sources[span["source_id"]]
        ranges = []
        for fragment in span["quote_emphasis"]:
            assert fragment and fragment == fragment.strip()
            assert quote.count(fragment) == 1
            start = quote.index(fragment)
            ranges.append((start, start + len(fragment)))
        ordered = sorted(ranges)
        assert all(left[1] <= right[0] for left, right in pairwise(ordered))


def test_oracle_distinguishes_positive_and_negative_semantic_expectations() -> None:
    statuses = {case["status"] for case in EXPECTED["cases"].values()}
    assert statuses == {"complete", "incomplete"}
    for case in EXPECTED["cases"].values():
        assert case["required"] and all(case["required"])
    # Literal checks intentionally pass for both groups; the host must judge support.
    assert "semantic" in EXPECTED["passing_rule"].lower()
