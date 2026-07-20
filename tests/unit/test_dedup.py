"""Unit tests for existence check: Zotero Local API is authoritative (offline).

A fake Zotero reader stands in for the Local API so these stay network-free.
"""
from __future__ import annotations
import pytest
from scholar_workflow.dedup import (
    check_existence, decide_operation, ExistenceResult, Match, DependencyError,
)
from scholar_workflow.resolver import resolve_one


class FakeZotero:
    """Maps arxiv id / doi -> list of {'key': ...} items."""
    def __init__(self, by_arxiv=None, by_doi=None, raises=False):
        self._by_arxiv = by_arxiv or {}
        self._by_doi = by_doi or {}
        self._raises = raises

    def search_by_arxiv(self, arxiv_id):
        if self._raises:
            raise ConnectionError("boom")
        return self._by_arxiv.get(arxiv_id, [])

    def search_by_doi(self, doi):
        if self._raises:
            raise ConnectionError("boom")
        return self._by_doi.get(doi, [])


def test_none_when_zotero_has_nothing():
    out = check_existence(resolve_one("2401.09999"), FakeZotero())
    assert out.match is Match.NONE


def test_exact_by_arxiv_returns_item_key():
    z = FakeZotero(by_arxiv={"2401.01234": [{"key": "ABCD1234"}]})
    out = check_existence(resolve_one("2401.01234v3"), z)  # version stripped upstream
    assert out.match is Match.EXACT
    assert out.zotero_item_key == "ABCD1234"


def test_exact_by_doi():
    z = FakeZotero(by_doi={"10.1145/1234567.8901234": [{"key": "DOIKEY"}]})
    out = check_existence(resolve_one("https://doi.org/10.1145/1234567.8901234"), z)
    assert out.match is Match.EXACT
    assert out.zotero_item_key == "DOIKEY"


def test_unreachable_zotero_fails_closed_not_none():
    # INV: "can't reach Zotero" must never be read as "new paper".
    with pytest.raises(DependencyError):
        check_existence(resolve_one("2401.01234"), FakeZotero(raises=True))


def test_arxiv_versions_all_hit_same_item():
    z = FakeZotero(by_arxiv={"2401.01234": [{"key": "ONE"}]})
    keys = {check_existence(resolve_one(v), z).zotero_item_key
            for v in ("2401.01234", "2401.01234v1", "arxiv:2401.01234v7")}
    assert keys == {"ONE"}


def test_decide_none_creates():
    assert decide_operation(ExistenceResult(Match.NONE)) == ("create", [])


def test_decide_exact_skips():
    r = ExistenceResult(Match.EXACT, resource_id="paper:arxiv:2401.01234",
                        zotero_item_key="ONE")
    assert decide_operation(r) == ("skip", [])


def test_decide_conflict_is_not_merge():
    # NG3: identifiers pointing at different items -> human adjudication, never auto-merge.
    r = ExistenceResult(Match.CONFLICT, conflicts=["ITEM_A", "ITEM_B"])
    op, conflicts = decide_operation(r)
    assert op == "conflict"
    assert conflicts == ["ITEM_A", "ITEM_B"]
