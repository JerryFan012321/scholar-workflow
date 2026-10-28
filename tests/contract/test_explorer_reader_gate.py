"""Real HTTP and reader gate; only external registrations/API are synthetic."""

import hashlib
import json
import threading
import urllib.error
import urllib.request
from copy import deepcopy

from scholar_workflow.adapters import exploration_readers
from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator
from scholar_workflow.knowledge.exploration import default_data
from tests.contract.explorer_fixture import fixture_server as make_server


def test_http_reader_gate_preserves_page_and_rejects_replaced_bytes(tmp_path, monkeypatch):
    parent_key, attachment_key = "ABCD2345", "BCDE3456"
    source = tmp_path / "source"
    source.mkdir()
    pdf = source / "original.pdf"
    original = b"%PDF-1.7\nsynthetic original bytes\n"
    pdf.write_bytes(original)
    expected_hash = "md5:" + hashlib.md5(original).hexdigest()
    ref = {"source_id": "synthetic-source", "object_id": f"paper:zotero:123:{parent_key}"}
    uri = f"zotero://open-pdf/library/items/{attachment_key}?page=4"
    work = {"id": "paper-a", "kind": "paper", "title": "Synthetic paper", "entity_ref": ref,
            "attributes": {}, "assets": [{"id": "pdf-a", "kind": "zotero-pdf",
                                           "label": "Original PDF", "uri": uri}]}
    library = {"type": "user", "id": 123}
    items = {
        parent_key: {"key": parent_key, "library": library, "data": {"itemType": "journalArticle"}},
        attachment_key: {"key": attachment_key, "library": library, "data": {
            "itemType": "attachment", "parentItem": parent_key, "contentType": "application/pdf"}},
    }

    class Registry:
        def __init__(self, path):
            assert path == tmp_path / "registry.json"

        def revision(self):
            return "synthetic-registry-revision"

        def resolve(self, source_id, *, capability):
            assert source_id == ref["source_id"] and capability == "read"
            return source

    class References:
        def reference(self, root, data, source_id, field_id, unit_refs):
            assert unit_refs == [ref] and source_id == ref["source_id"] and field_id == "field-a"
            result = deepcopy(data)
            result["works"].append(deepcopy(work))
            return result

        def current_unit(self, reference):
            assert reference == ref
            return {"source_id": ref["source_id"], "resource_id": ref["object_id"],
                    "ownership": {"status": "resolved"}, "catalog_resource": {
                        "resource_id": ref["object_id"], "zotero": {"item_key": parent_key}}}

    class Local:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_item(self, key):
            return deepcopy(items[key])

        def resolve_attachment_locator(self, key):
            assert key == attachment_key
            return ZoteroAttachmentLocator(key, "123", expected_hash, pdf, pdf.name)

    monkeypatch.setattr(exploration_readers, "KnowledgeSourceRegistry", Registry)
    references = References()
    gate = exploration_readers.ExplorationReaderGate(
        tmp_path / "registry.json", reference_service=references, adapter_factory=Local,
    )
    opened = []
    monkeypatch.setenv("ZOTERO_API_KEY", "synthetic-never-forward")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which",
                        lambda _name: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen",
                        lambda argv, **kwargs: opened.append((argv, kwargs)))
    server, token = make_server(tmp_path, reference_service=references, reader_gate=gate)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, payload=None):
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
        req = urllib.request.Request(base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    try:
        status, proposal = request("/api/unit-reference", {"data": default_data(),
            "source_id": ref["source_id"], "field_id": "field-a", "unit_refs": [ref]})
        assert status == 200
        status, saved = request("/api/save", {"data": proposal["data"], "expected_revision": None})
        assert status == 200
        selected = {"work_id": "paper-a", "asset_id": "pdf-a"}
        assert request("/api/open", selected) == (403, {
            "error": "Refresh the asset list before opening this reader.", "code": "refresh_required"})
        assert opened == []
        assert request("/api/assets/paper-a")[1][0]["native_available"] is True
        assert request("/api/open", selected) == (200, {"submitted": True})
        assert opened[0][0] == ["/usr/bin/open", uri] and opened[0][1]["shell"] is False
        assert "ZOTERO_API_KEY" not in opened[0][1]["env"]
        pdf.write_bytes(b"%PDF-1.7\nreplaced bytes\n")
        status, refusal = request("/api/open", selected)
        assert status == 403 and refusal["code"] == "pdf_changed"
        assert len(opened) == 1
        listing = request("/api/assets/paper-a")[1][0]
        assert listing["available"] is True and listing["native_available"] is False
        assert listing["native_reason_code"] == "pdf_changed"
        assert str(source) not in json.dumps(refusal)
        assert request("/api/state")[1]["revision"] == saved["revision"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
