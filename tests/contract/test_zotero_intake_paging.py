"""Collection pagination must remain Local API-only and preserve legacy calls."""
import httpx
import pytest

from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter


def test_collection_page_passes_bounded_start_and_stable_sort():
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=[], headers={"Zotero-Server-ID": "synthetic", "Zotero-API-Version": "3"})
    with ZoteroLocalAdapter(client=httpx.Client(base_url="http://127.0.0.1:23119/api/", transport=httpx.MockTransport(respond))) as adapter:
        assert adapter.get_collection_items("INBX2345", start=20, limit=10) == []
        adapter.get_collection_items("INBX2345")
    assert seen[0].url.path == "/api/users/0/collections/INBX2345/items/top"
    assert dict(seen[0].url.params) == {"start": "20", "limit": "10", "sort": "dateAdded", "direction": "asc"}
    assert not seen[1].url.params


@pytest.mark.parametrize("start,limit", [(-1, 10), (True, 10), (0, 0), (0, 101)])
def test_invalid_collection_page_never_contacts_provider(start, limit):
    def unexpected(_request):
        pytest.fail("Invalid pagination must fail before transport")
    with ZoteroLocalAdapter(client=httpx.Client(base_url="http://127.0.0.1:23119/api/", transport=httpx.MockTransport(unexpected))) as adapter:
        with pytest.raises(ValueError):
            adapter.get_collection_items("INBX2345", start=start, limit=limit)
