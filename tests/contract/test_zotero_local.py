"""Contract test for the read-only Zotero Local API adapter.

Guards the search_by_arxiv contract: Zotero has no native arXiv field, so a text
search may return false positives. The adapter must verify a returned item's
DOI / url / extra actually contains the arXiv id before treating it as a match.
Uses an injected fake HTTP client — no real network.
"""
from __future__ import annotations
from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    """Records the last requested URL and replays a canned payload."""
    def __init__(self, payload):
        self._payload = payload
        self.last_url = None

    def get(self, url):
        self.last_url = url
        return FakeResponse(self._payload)

    def close(self):
        return None


def _adapter(payload):
    return ZoteroLocalAdapter("http://127.0.0.1:23119/api", client=FakeClient(payload))


def test_search_by_arxiv_matches_via_doi():
    # arXiv now mints DOIs of the form 10.48550/arXiv.<id>
    payload = [{"key": "AAAA1111", "data": {"DOI": "10.48550/arXiv.2401.01234",
                                            "title": "Some Paper"}}]
    hits = _adapter(payload).search_by_arxiv("2401.01234")
    assert len(hits) == 1
    assert hits[0]["key"] == "AAAA1111"


def test_search_by_arxiv_matches_via_url():
    payload = [{"key": "BBBB2222", "data": {"url": "https://arxiv.org/abs/2401.01234v2",
                                            "title": "Some Paper"}}]
    hits = _adapter(payload).search_by_arxiv("2401.01234")
    assert len(hits) == 1


def test_search_by_arxiv_matches_via_extra():
    payload = [{"key": "CCCC3333", "data": {"extra": "arXiv:2401.01234",
                                            "title": "Some Paper"}}]
    hits = _adapter(payload).search_by_arxiv("2401.01234")
    assert len(hits) == 1


def test_search_by_arxiv_rejects_text_false_positive():
    # Same digits appear in the title but no identifier field carries the id → no match.
    payload = [{"key": "DDDD4444", "data": {"title": "Results on dataset 2401.01234",
                                            "DOI": "10.1145/9999999"}}]
    hits = _adapter(payload).search_by_arxiv("2401.01234")
    assert hits == []


def test_search_by_arxiv_uses_everything_qmode():
    client = FakeClient([])
    ZoteroLocalAdapter("http://127.0.0.1:23119/api", client=client).search_by_arxiv("2401.01234")
    assert "qmode=everything" in client.last_url
    assert "2401.01234" in client.last_url


def test_get_items_pages_top_level():
    payload = [{"key": "K1", "data": {"title": "P1"}}]
    client = FakeClient(payload)
    out = ZoteroLocalAdapter("http://127.0.0.1:23119/api", client=client).get_items(
        start=100, limit=50)
    assert out == payload
    assert "/users/0/items/top" in client.last_url
    assert "start=100" in client.last_url
    assert "limit=50" in client.last_url
