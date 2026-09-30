"""Prepared Local API contracts for complete paper child listings."""
import httpx
import pytest

from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter, ZoteroLocalError


def test_related_children_read_every_page_without_annotation_filter() -> None:
    starts = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/items/ABCDEFGH/children"
        assert "itemType" not in request.url.params
        start = int(request.url.params["start"])
        starts.append(start)
        count = min(100, 103 - start)
        return httpx.Response(200, headers={"Total-Results": "103"},
                              json=[{"key": f"CHILD{i}"} for i in range(start, start + count)])

    client = httpx.Client(base_url="http://127.0.0.1:23119/api/",
                         transport=httpx.MockTransport(handler), trust_env=False)
    with ZoteroLocalAdapter(client=client) as adapter:
        rows = adapter.get_children_all("ABCDEFGH")
    assert starts == [0, 100]
    assert len(rows) == 103


def test_related_children_reject_changed_or_invalid_pages() -> None:
    client = httpx.Client(base_url="http://127.0.0.1:23119/api/",
                         transport=httpx.MockTransport(lambda request: httpx.Response(
                             200, headers={"Total-Results": "-1"}, json=[])), trust_env=False)
    with ZoteroLocalAdapter(client=client) as adapter, pytest.raises(ZoteroLocalError):
        adapter.get_children_all("ABCDEFGH")
