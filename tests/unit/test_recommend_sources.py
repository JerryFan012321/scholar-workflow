"""Unit tests for recommendation-source adapters (feature-ai-reading skim tier).

Uses httpx.MockTransport so no network and no extra deps (matches test_notion.py).
Pins the normalized candidate shape and the merge/dedup contract.
"""
from __future__ import annotations
import httpx
from scholar_workflow.adapters.recommend_sources import (
    fetch_hf_daily, fetch_s2_recommendations, fetch_s2_author_papers,
    normalize_scholar_inbox, merge_candidates,
)

HF_SAMPLE = [
    {"paper": {"id": "2607.23193", "title": "A Paper",
               "authors": [{"name": "Jane Doe"}, {"name": "John Roe"}],
               "upvotes": 42, "summary": "  We propose   a thing.  "}},
    {"paper": {"id": "2607.00001", "title": "B Paper",
               "authors": [], "upvotes": 3, "summary": None}},
    {"other": "no paper key — skipped"},
]


def _client_returning(payload) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url="https://huggingface.co")


def test_hf_daily_normalizes_and_skips_rows_without_paper():
    cands = fetch_hf_daily(client=_client_returning(HF_SAMPLE))
    assert len(cands) == 2  # third row (no paper) dropped
    first = cands[0]
    assert first == {
        "arxiv_id": "2607.23193", "title": "A Paper",
        "authors": ["Jane Doe", "John Roe"], "source": "hf_daily",
        "score": 42, "abstract_snippet": "We propose a thing.",
        "url": "https://arxiv.org/abs/2607.23193",
    }
    assert cands[1]["abstract_snippet"] is None  # missing summary → None


def test_merge_dedups_by_arxiv_id_and_records_sources():
    a = [{"arxiv_id": "X", "title": "t", "authors": [], "source": "hf_daily",
          "score": 1, "abstract_snippet": None, "url": "u"}]
    b = [{"arxiv_id": "X", "title": "t", "authors": [], "source": "s2_author",
          "score": None, "abstract_snippet": None, "url": "u"},
         {"arxiv_id": "Y", "title": "t2", "authors": [], "source": "s2_author",
          "score": None, "abstract_snippet": None, "url": "u2"}]
    merged = merge_candidates(a, b)
    by_id = {c["arxiv_id"]: c for c in merged}
    assert len(merged) == 2
    assert by_id["X"]["sources"] == ["hf_daily", "s2_author"]  # both recorded
    assert by_id["Y"]["sources"] == ["s2_author"]


S2_SAMPLE = {"recommendedPapers": [
    {"title": "Rec One", "year": 2607,
     "authors": [{"name": "A One"}, {"name": "B Two"}],
     "abstract": "  Some   abstract. ", "externalIds": {"ArXiv": "2607.11111", "DOI": "x"}},
    {"title": "No arXiv", "authors": [], "abstract": "z", "externalIds": {"DOI": "y"}},
]}


def test_s2_recommendations_normalizes_and_drops_non_arxiv():
    cands = fetch_s2_recommendations(["2501.00001"], client=_client_returning(S2_SAMPLE))
    assert len(cands) == 1  # non-arXiv row dropped
    assert cands[0] == {
        "arxiv_id": "2607.11111", "title": "Rec One",
        "authors": ["A One", "B Two"], "source": "s2_recommendations",
        "score": None, "abstract_snippet": "Some abstract.",
        "url": "https://arxiv.org/abs/2607.11111",
    }


def test_s2_recommendations_no_seeds_skips_call():
    # empty seeds → no network call, empty result (client would raise if hit)
    assert fetch_s2_recommendations([]) == []


def test_s2_author_papers_normalizes():
    payload = {"data": [
        {"title": "Auth Paper", "authors": [{"name": "Jane"}],
         "abstract": "a", "externalIds": {"ArXiv": "2607.22222"}}]}
    cands = fetch_s2_author_papers("1741101", client=_client_returning(payload))
    assert len(cands) == 1
    assert cands[0]["arxiv_id"] == "2607.22222"
    assert cands[0]["source"] == "s2_author"


def test_scholar_inbox_normalizes_splits_authors_and_filters_score():
    digest = {"digest_df": [
        {"paper_id": 1, "title": "SI One", "arxiv_id": "2607.33333",
         "shortened_authors": "X Yang, Z Wang", "ranking_score": 0.87,
         "abstract": "  hello   world "},
        {"paper_id": 2, "title": "Low", "arxiv_id": "2607.44444",
         "shortened_authors": "", "ranking_score": 0.10, "abstract": "b"},
        {"paper_id": 3, "title": "No arXiv", "arxiv_id": None,
         "shortened_authors": "Q", "ranking_score": 0.99, "abstract": "c"},
    ]}
    cands = normalize_scholar_inbox(digest, min_score=0.5)
    assert len(cands) == 1  # low-score + no-arXiv dropped
    assert cands[0] == {
        "arxiv_id": "2607.33333", "title": "SI One",
        "authors": ["X Yang", "Z Wang"], "source": "scholar_inbox",
        "score": 0.87, "abstract_snippet": "hello world",
        "url": "https://arxiv.org/abs/2607.33333",
    }
