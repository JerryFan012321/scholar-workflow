"""Contract tests for the Zotero 10+ Local API adapter."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scholar_workflow.adapters.zotero_local import (
    MAX_UPLOAD_BYTES,
    ZoteroLocalAdapter,
    ZoteroAuthorizationError,
    ZoteroLocalError,
    ZoteroLocalUnavailable,
)


class MemoryKeyStore:
    def __init__(self, key: str | None = None) -> None:
        self.key = key
        self.saved: tuple[str, str] | None = None
        self.deleted: str | None = None

    def get(self, server_id: str) -> str | None:
        return self.key

    def put(self, server_id: str, key: str) -> None:
        self.key = key
        self.saved = (server_id, key)

    def delete(self, server_id: str) -> None:
        self.key = None
        self.deleted = server_id


def make_adapter(handler, key_store: MemoryKeyStore | None = None) -> ZoteroLocalAdapter:
    client = httpx.Client(
        base_url="http://127.0.0.1:23119/api/",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    return ZoteroLocalAdapter(client=client, key_store=key_store or MemoryKeyStore())


def server_headers() -> dict[str, str]:
    return {
        "Zotero-Server-ID": "server-1",
        "Zotero-API-Version": "3",
        "Zotero-Schema-Version": "42",
    }


def test_rejects_non_loopback_base_url() -> None:
    with pytest.raises(ValueError, match="loopback"):
        ZoteroLocalAdapter(base_url="https://example.com/api")


def test_rejects_path_like_item_keys() -> None:
    with make_adapter(lambda request: httpx.Response(500)) as adapter:
        with pytest.raises(ValueError, match="invalid Zotero object key"):
            adapter.get_item("../../secrets")


def test_probe_reads_server_identity_and_api_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/"
        assert "Zotero-API-Version" not in request.headers
        return httpx.Response(200, headers=server_headers(), json={})

    with make_adapter(handler) as adapter:
        info = adapter.probe()

    assert info.server_id == "server-1"
    assert info.api_version == "3"
    assert info.schema_version == "42"


def test_probe_maps_disabled_local_api_to_unavailable() -> None:
    with make_adapter(lambda request: httpx.Response(403, json={"disabled": True})) as adapter:
        with pytest.raises(ZoteroLocalUnavailable, match="enable"):
            adapter.probe()


def test_search_uses_local_quicksearch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/items/top"
        assert request.url.params["q"] == "world model"
        assert request.url.params["qmode"] == "everything"
        assert request.url.params["limit"] == "25"
        return httpx.Response(200, headers=server_headers(), json=[{"key": "ITEM1"}])

    with make_adapter(handler) as adapter:
        items = adapter.search_items("world model", qmode="everything", limit=25)

    assert items == [{"key": "ITEM1"}]


def test_search_can_omit_limit_for_complete_local_identity_scan() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "A Common Title"
        assert "limit" not in request.url.params
        return httpx.Response(200, headers=server_headers(), json=[])

    with make_adapter(handler) as adapter:
        items = adapter.search_items("A Common Title", limit=None)

    assert items == []


def test_collection_items_use_user_zero_local_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/collections/CDEF4567/items/top"
        assert "limit" not in request.url.params
        return httpx.Response(200, headers=server_headers(), json=[{"key": "ITEM1"}])

    with make_adapter(handler) as adapter:
        items = adapter.get_collection_items("CDEF4567")

    assert items == [{"key": "ITEM1"}]


def test_get_children_uses_item_children_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/users/0/items/ABCD2345/children"
        return httpx.Response(200, headers=server_headers(), json=[{"key": "BCDE3456"}])

    with make_adapter(handler) as adapter:
        children = adapter.get_children("ABCD2345")

    assert children == [{"key": "BCDE3456"}]


def test_item_template_uses_local_schema_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/items/new"
        assert request.url.params["itemType"] == "conferencePaper"
        assert "linkMode" not in request.url.params
        return httpx.Response(
            200,
            headers=server_headers(),
            json={"itemType": "conferencePaper", "title": "", "tags": []},
        )

    with make_adapter(handler) as adapter:
        template = adapter.get_item_template("conferencePaper")

    assert template == {"itemType": "conferencePaper", "title": "", "tags": []}


def test_authorize_persists_only_remembered_key() -> None:
    key_store = MemoryKeyStore()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        assert request.url.path == "/api/local/authorize"
        assert request.headers["Zotero-Server-ID"] == "server-1"
        assert json.loads(request.content)["appName"] == "Scholar Workflow"
        return httpx.Response(
            200,
            headers=server_headers(),
            json={"key": "local-write-key", "remember": True},
        )

    with make_adapter(handler, key_store) as adapter:
        result = adapter.authorize()

    assert result.remember is True
    assert key_store.saved == ("server-1", "local-write-key")


def test_create_item_sends_server_id_key_and_write_token() -> None:
    key_store = MemoryKeyStore("local-write-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        assert request.url.path == "/api/users/0/items"
        assert request.headers["Zotero-Server-ID"] == "server-1"
        assert request.headers["Zotero-API-Key"] == "local-write-key"
        assert request.headers["Zotero-Write-Token"]
        payload = json.loads(request.content)
        assert payload[0]["itemType"] == "journalArticle"
        return httpx.Response(
            200,
            headers=server_headers(),
            json={"success": {"0": "ABCD2345"}, "unchanged": {}, "failed": {}},
        )

    with make_adapter(handler, key_store) as adapter:
        key = adapter.create_item({"itemType": "journalArticle", "title": "Paper"})

    assert key == "ABCD2345"


def test_unauthorized_write_clears_rejected_remembered_key() -> None:
    key_store = MemoryKeyStore("local-write-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        return httpx.Response(401, headers=server_headers())

    with make_adapter(handler, key_store) as adapter:
        with pytest.raises(ZoteroAuthorizationError, match="rejected"):
            adapter.create_item({"itemType": "journalArticle", "title": "Paper"})

    assert key_store.deleted == "server-1"


def test_forbidden_write_is_not_misreported_as_bad_key() -> None:
    key_store = MemoryKeyStore("local-write-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        return httpx.Response(403, headers=server_headers(), text="file editing denied")

    with make_adapter(handler, key_store) as adapter:
        with pytest.raises(ZoteroLocalError, match="HTTP 403"):
            adapter.create_item({"itemType": "journalArticle", "title": "Paper"})

    assert key_store.deleted is None


def test_update_item_uses_object_version_without_write_token() -> None:
    key_store = MemoryKeyStore("local-write-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        assert request.method == "PATCH"
        assert request.url.path == "/api/users/0/items/ABCD2345"
        assert request.headers["If-Unmodified-Since-Version"] == "7"
        assert "Zotero-Write-Token" not in request.headers
        return httpx.Response(204, headers=server_headers())

    with make_adapter(handler, key_store) as adapter:
        adapter.update_item("ABCD2345", {"title": "Fixed"}, version=7)


def test_import_file_uses_three_phase_local_upload(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontent")
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: (_ for _ in ()).throw(AssertionError("uploads must stream from disk")),
    )
    key_store = MemoryKeyStore("local-write-key")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        if request.url.path == "/api/users/0/items":
            payload = json.loads(request.content)
            assert payload[0]["parentItem"] == "ABCD2345"
            assert payload[0]["filename"] == "paper.pdf"
            return httpx.Response(
                200,
                headers=server_headers(),
                json={"success": {"0": "BCDE3456"}, "unchanged": {}, "failed": {}},
            )
        if request.url.path == "/api/users/0/items/BCDE3456/file":
            if b"upload=" in request.content:
                assert request.headers["If-None-Match"] == "*"
                return httpx.Response(204, headers=server_headers())
            assert request.headers["If-None-Match"] == "*"
            return httpx.Response(
                200,
                headers=server_headers(),
                json={
                    "url": "http://127.0.0.1:23119/api/local/uploads/UPLOAD1",
                    "uploadKey": "UPLOAD1",
                    "contentType": "application/pdf",
                    "prefix": "",
                    "suffix": "",
                },
            )
        if request.url.path == "/api/local/uploads/UPLOAD1":
            assert request.content.startswith(b"%PDF-")
            assert "Zotero-API-Key" not in request.headers
            assert "Zotero-Server-ID" not in request.headers
            assert request.headers["Content-Length"] == str(len(request.content))
            assert "Transfer-Encoding" not in request.headers
            return httpx.Response(201)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with make_adapter(handler, key_store) as adapter:
        result = adapter.import_file("ABCD2345", pdf)

    assert result == {"attachment_key": "BCDE3456", "uploaded": True}
    assert calls[-1] == "POST /api/users/0/items/BCDE3456/file"


def test_import_file_accepts_numeric_exists_short_circuit(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontent")
    key_store = MemoryKeyStore("local-write-key")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        if request.url.path == "/api/users/0/items":
            return httpx.Response(
                200,
                headers=server_headers(),
                json={"success": {"0": "BCDE3456"}, "unchanged": {}, "failed": {}},
            )
        if request.url.path == "/api/users/0/items/BCDE3456/file":
            return httpx.Response(200, headers=server_headers(), json={"exists": 1})
        raise AssertionError(f"unexpected upload request: {request.url}")

    with make_adapter(handler, key_store) as adapter:
        result = adapter.import_file("ABCD2345", pdf)

    assert result == {"attachment_key": "BCDE3456", "uploaded": False}
    assert "/api/local/uploads/" not in " ".join(calls)


def test_import_file_rejects_remote_upload_url(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontent")
    key_store = MemoryKeyStore("local-write-key")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        if request.url.path == "/api/users/0/items":
            return httpx.Response(
                200,
                headers=server_headers(),
                json={"success": {"0": "BCDE3456"}, "unchanged": {}, "failed": {}},
            )
        return httpx.Response(
            200,
            headers=server_headers(),
            json={
                "url": "https://example.com/upload",
                "uploadKey": "UPLOAD1",
                "contentType": "application/pdf",
                "prefix": "",
                "suffix": "",
            },
        )

    with make_adapter(handler, key_store) as adapter:
        with pytest.raises(ZoteroLocalError, match="unsafe upload URL"):
            adapter.import_file("ABCD2345", pdf)


def test_import_file_rejects_another_loopback_service(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\ncontent")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            return httpx.Response(200, headers=server_headers(), json={})
        if request.url.path == "/api/items/new":
            return httpx.Response(200, headers=server_headers(), json={})
        if request.url.path == "/api/users/0/items":
            return httpx.Response(
                200,
                headers=server_headers(),
                json={"success": {"0": "BCDE3456"}, "unchanged": {}, "failed": {}},
            )
        return httpx.Response(
            200,
            headers=server_headers(),
            json={
                "url": "http://127.0.0.1:9999/api/local/uploads/UPLOAD1",
                "uploadKey": "UPLOAD1",
            },
        )

    with make_adapter(handler, MemoryKeyStore("local-write-key")) as adapter:
        with pytest.raises(ZoteroLocalError, match="unsafe upload URL"):
            adapter.import_file("ABCD2345", pdf)


def test_import_file_rejects_oversized_attachment_before_network(tmp_path: Path) -> None:
    pdf = tmp_path / "large.pdf"
    with pdf.open("wb") as handle:
        handle.truncate(MAX_UPLOAD_BYTES + 1)

    def must_not_call(request: httpx.Request) -> httpx.Response:
        raise AssertionError("oversized files must fail before Local API access")

    with make_adapter(must_not_call) as adapter:
        with pytest.raises(ZoteroLocalError, match="exceeds"):
            adapter.import_file("ABCD2345", pdf)
