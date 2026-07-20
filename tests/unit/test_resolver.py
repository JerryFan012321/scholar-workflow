"""Unit tests for the offline input resolver."""
from __future__ import annotations
from scholar_workflow.resolver import (
    classify_input, resolve_one, resolve_many, resolve_csv,
)


def test_arxiv_resolves_to_placeholder_title():
    res = resolve_one("2401.01234")
    assert res.title == "arXiv:2401.01234"  # metadata comes from Zotero Local API downstream
    assert res.identifiers.arxiv == "2401.01234"


def test_classify_arxiv_bare_and_versioned():
    assert classify_input("2401.01234") == "arxiv"
    assert classify_input("2401.01234v2") == "arxiv"
    assert classify_input("arxiv:2401.01234") == "arxiv"


def test_classify_arxiv_url():
    assert classify_input("https://arxiv.org/abs/2401.01234") == "arxiv"
    assert classify_input("https://arxiv.org/pdf/2401.01234v3") == "arxiv"


def test_classify_doi_and_url_and_title():
    assert classify_input("10.1145/1234567.8901234") == "doi"
    assert classify_input("https://doi.org/10.1145/1234567.8901234") == "doi"
    assert classify_input("https://example.com/paper") == "url"
    assert classify_input("Attention Is All You Need") == "title"


def test_arxiv_version_dedup():
    # GOALS INV / outcomes: v1/v2/v3 collapse to one identity
    v1 = resolve_one("2401.01234v1")
    v2 = resolve_one("2401.01234v2")
    plain = resolve_one("2401.01234")
    assert v1.resource_id == v2.resource_id == plain.resource_id
    assert v1.identifiers.arxiv == "2401.01234"


def test_doi_dedup_same_identity():
    a = resolve_one("10.1145/1234567.8901234")
    b = resolve_one("https://doi.org/10.1145/1234567.8901234")
    assert a.resource_id == b.resource_id


def test_resolve_many_collapses_duplicates():
    out = resolve_many(["2401.01234", "2401.01234v2", "", "2401.01234"])
    assert len(out) == 1


def test_resolve_csv(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text("2401.01234\n10.1145/1234567.8901234\n2401.01234v9\n", encoding="utf-8")
    out = resolve_csv(p)
    # arxiv rows collapse -> 2 distinct identities
    assert len(out) == 2
