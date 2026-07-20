"""Unit tests for cache sync from Zotero (offline, fake reader + real store)."""
from __future__ import annotations
import pytest
from scholar_workflow.state import StateStore
from scholar_workflow.workflows.sync import sync_cache, _resource_from_item
from scholar_workflow.dedup import DependencyError


@pytest.fixture
def store(tmp_path):
    s = StateStore(tmp_path / "state.db")
    yield s
    s.close()


class FakeZotero:
    def __init__(self, pages, raises=False):
        self._pages = pages  # list of item-lists, one per page
        self._raises = raises

    def get_items(self, *, start, limit):
        if self._raises:
            raise ConnectionError("down")
        idx = start // limit
        return self._pages[idx] if idx < len(self._pages) else []


def _item(key, **data):
    return {"key": key, "data": data}


def test_resource_from_item_extracts_arxiv_from_doi():
    row = _resource_from_item(_item("K", DOI="10.48550/arXiv.2401.01234",
                                    title="A Paper", abstractNote="abs"))
    assert row["arxiv"] == "2401.01234"
    assert row["title"] == "A Paper"
    assert row["abstract"] == "abs"
    assert row["zotero_item_key"] == "K"


def test_resource_from_item_skips_identityless():
    assert _resource_from_item(_item("K")) is None


def test_sync_populates_cache_and_catalog(store):
    z = FakeZotero([[
        _item("K1", DOI="10.1145/1", title="First", abstractNote="a1",
              creators=[{"creatorType": "author", "lastName": "Ng"}], date="2020"),
        _item("K2", url="https://arxiv.org/abs/2401.01234", title="Second"),
    ]])
    summary = sync_cache(z, store, page_size=100)
    assert summary == {"synced": 2, "skipped": 0}
    cat = store.catalog()
    assert {c["zotero_item_key"] for c in cat} == {"K1", "K2"}
    assert any(c["abstract"] == "a1" for c in cat)


def test_sync_paginates(store):
    page = [_item(f"K{i}", DOI=f"10.1/{i}", title=f"T{i}") for i in range(2)]
    z = FakeZotero([page, page[:1]])  # full page then partial -> stop
    summary = sync_cache(z, store, page_size=2)
    assert summary["synced"] == 3


def test_sync_fails_closed(store):
    with pytest.raises(DependencyError):
        sync_cache(FakeZotero([], raises=True), store)
