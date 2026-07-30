"""Contract test for the Notion adapter (data-source model, post 2025-09-03).

Pins the request shapes we verified live: query hits /data_sources/{id}/query, a new
row's parent is {"type": "data_source_id", ...}, and upsert is idempotent by Resource ID.
Uses httpx.MockTransport so no network and no extra deps.
"""
from __future__ import annotations
import json
import httpx
from scholar_workflow.adapters.notion import NotionAdapter, DEFAULT_API_VERSION

DS = "60812183-87bc-4769-89d4-a6ad30d6d77b"


def _adapter_with(handler) -> NotionAdapter:
    a = NotionAdapter(token="test-token")
    a._client = httpx.Client(
        base_url="https://api.notion.com/v1",
        headers={
            "Authorization": "Bearer test-token",
            "Notion-Version": DEFAULT_API_VERSION,
            "Content-Type": "application/json",
        },
        transport=httpx.MockTransport(handler),
    )
    return a


def test_create_uses_data_source_parent_and_query_endpoint():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/query"):
            # query miss → no existing row
            return httpx.Response(200, json={"results": []})
        # create page
        return httpx.Response(200, json={"id": "new-page-id"})

    a = _adapter_with(handler)
    page_id = a.upsert_page(DS, "arxiv:2402.10259",
                            {"Name": {"title": [{"text": {"content": "X"}}]}})
    assert page_id == "new-page-id"

    # query went to the data-source endpoint, not /databases/
    query_req = seen[0]
    assert query_req.url.path == f"/v1/data_sources/{DS}/query"
    qbody = json.loads(query_req.content)
    assert qbody["filter"]["property"] == "Resource ID"
    assert qbody["filter"]["rich_text"]["equals"] == "arxiv:2402.10259"

    # create parent uses data_source_id, and Resource ID was injected
    create_req = seen[1]
    assert create_req.url.path == "/v1/pages"
    cbody = json.loads(create_req.content)
    assert cbody["parent"] == {"type": "data_source_id", "data_source_id": DS}
    assert cbody["properties"]["Resource ID"]["rich_text"][0]["text"]["content"] == "arxiv:2402.10259"


def test_upsert_updates_existing_row_instead_of_creating():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"results": [{"id": "existing-page-id"}]})
        # PATCH update
        return httpx.Response(200, json={"id": "existing-page-id"})

    a = _adapter_with(handler)
    page_id = a.upsert_page(DS, "arxiv:2402.10259", {"Status": {"select": {"name": "reading"}}})
    assert page_id == "existing-page-id"

    # second call is a PATCH to /pages/{id}, no new page created
    update_req = seen[1]
    assert update_req.method == "PATCH"
    assert update_req.url.path == "/v1/pages/existing-page-id"


def test_default_api_version_is_data_source_era():
    assert DEFAULT_API_VERSION == "2026-03-11"


RELATED_DS = "a1b2c3d4-0000-4000-8000-000000000000"


def test_related_doc_upserts_by_doc_id_and_links_paper_relation():
    """Two-DB model: a related-materials doc keys on 'Doc ID' (vault path) and
    carries a 'Paper' relation to the already-upserted paper page."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"id": "related-page-id"})

    a = _adapter_with(handler)
    doc_key = "paper/科研项目/上汽标注/Text2CAD论文相关资料.md"
    page_id = a.upsert_page(
        RELATED_DS, doc_key,
        {"Name": {"title": [{"text": {"content": "Text2CAD 相关资料"}}]},
         "Paper": {"relation": [{"id": "paper-page-id"}]}},
        key_property="Doc ID",
    )
    assert page_id == "related-page-id"

    # query filtered on Doc ID, on the Related-Docs data source
    query_req = seen[0]
    assert query_req.url.path == f"/v1/data_sources/{RELATED_DS}/query"
    qbody = json.loads(query_req.content)
    assert qbody["filter"]["property"] == "Doc ID"
    assert qbody["filter"]["rich_text"]["equals"] == doc_key

    # create injected Doc ID (not Resource ID) and kept the Paper relation
    create_req = seen[1]
    cbody = json.loads(create_req.content)
    assert cbody["properties"]["Doc ID"]["rich_text"][0]["text"]["content"] == doc_key
    assert "Resource ID" not in cbody["properties"]
    assert cbody["properties"]["Paper"]["relation"] == [{"id": "paper-page-id"}]


def test_papers_db_still_defaults_to_resource_id_key():
    """Default key_property is unchanged, so Papers-DB upsert is untouched."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/query"):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={"id": "new-page-id"})

    a = _adapter_with(handler)
    a.upsert_page(DS, "arxiv:2409.17106",
                  {"Name": {"title": [{"text": {"content": "X"}}]}})
    qbody = json.loads(seen[0].content)
    assert qbody["filter"]["property"] == "Resource ID"
