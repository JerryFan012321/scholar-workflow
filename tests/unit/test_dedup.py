"""Unit tests for existence check: exact writes, fuzzy reads (offline)."""
from __future__ import annotations
import pytest
from scholar_workflow.state import StateStore
from scholar_workflow.dedup import check_existence, Match
from scholar_workflow.resolver import resolve_one
from scholar_workflow.identity import normalize_title


@pytest.fixture
def state(tmp_path):
    s = StateStore(tmp_path / "state.db")
    yield s
    s.close()


def _seed(state, **kw):
    state.upsert_resource(kw.pop("resource_id"), **kw)


def test_none_when_empty(state):
    res = resolve_one("2401.09999")
    assert check_existence(res, state).match is Match.NONE


def test_exact_by_arxiv(state):
    _seed(state, resource_id="paper:arxiv:2401.01234", arxiv="2401.01234",
          zotero_item_key="ABCD1234")
    out = check_existence(resolve_one("2401.01234v3"), state)
    assert out.match is Match.EXACT
    assert out.zotero_item_key == "ABCD1234"


def test_exact_by_doi(state):
    _seed(state, resource_id="paper:doi:10.1145/1234567.8901234",
          doi="10.1145/1234567.8901234")
    out = check_existence(resolve_one("https://doi.org/10.1145/1234567.8901234"), state)
    assert out.match is Match.EXACT


def test_fuzzy_returns_candidates_no_decision(state):
    _seed(state, resource_id="paper:meta:aaaa",
          title_norm=normalize_title("Attention Is All You Need"), year=2017)
    out = check_existence(resolve_one("Attention Is All You Need"), state)
    assert out.match is Match.FUZZY
    assert out.resource_id is None  # fuzzy never decides
    assert len(out.candidates) == 1


def test_inv1_versions_collapse_to_one_exact(state):
    # One paper -> one Zotero item: every arXiv version hits the same record.
    _seed(state, resource_id="paper:arxiv:2401.01234", arxiv="2401.01234",
          zotero_item_key="ONE")
    keys = {check_existence(resolve_one(v), state).zotero_item_key
            for v in ("2401.01234", "2401.01234v1", "arxiv:2401.01234v7")}
    assert keys == {"ONE"}
