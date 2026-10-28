"""Exercise the explorer through real loopback HTTP using disposable data only."""

import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def explorer(tmp_path):
    from tests.contract.explorer_fixture import fixture_server as make_server

    (tmp_path / "paper.md").write_text("# Original\n\nUnchanged evidence.", encoding="utf-8")
    (tmp_path / "tree.canvas").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    server, token = make_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, payload=None, auth=True, origin=None, host=None):
        headers = {}
        if auth:
            headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            if origin is not False:
                headers["Origin"] = base if origin is None else origin
        if origin is not None and origin is not False:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        req = urllib.request.Request(
            base + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
        )
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            if response.headers.get_content_type() == "application/json":
                body = json.loads(body)
            return response.status, body, response.headers

    request.server = server
    yield tmp_path, request
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def sample():
    return {
        "schema_version": 1,
        "dimensions": [
            {"id": "foundation", "label": "基座", "kind": "enum", "multiple": True,
             "scope": "record", "values": [{"id": "b1", "label": "B1"}, {"id": "b2", "label": "B2"}],
             "sortable": False},
            {"id": "task", "label": "任务", "kind": "enum", "multiple": True,
             "scope": "record", "values": [{"id": "t1", "label": "T1"}, {"id": "t2", "label": "T2"}],
             "sortable": False},
        ],
        "works": [{"id": "w1", "title": "Example", "kind": "report", "attributes": {},
                   "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper"},
                   "assets": [{"id": "body", "label": "分析正文", "kind": "markdown", "uri": "paper.md"},
                              {"id": "canvas", "label": "解析树", "kind": "canvas", "uri": "tree.canvas"}]}],
        "records": [
            {"id": "r1", "work_id": "w1", "dimensions": {"foundation": ["b1"], "task": ["t1"]},
             "conditions": {"budget": "equal"}, "result": "First result", "evidence": ["body"],
             "assessment": "Limited", "origin": "author"},
            {"id": "r2", "work_id": "w1", "dimensions": {"foundation": ["b2"], "task": ["t2"]},
             "conditions": {}, "result": "Second result", "evidence": [], "assessment": "Awaiting assessment", "origin": "local"},
        ],
        "edges": [], "views": [],
    }


def confirmed_sample(request, data=None):
    """Prepare the protocol fixture's declared inventory through its existing gate.

    Real provider ownership is covered by the independent unit HTTP contract.
    Negative confirmation cases deliberately do not call this helper.
    """
    data = sample() if data is None else data
    references = [work["entity_ref"] for work in data["works"]]
    return request.server.remember_units(data, references)


def test_http_identity_auth_and_same_origin(explorer):
    _, req = explorer
    assert req("/")[0] == 200
    assert req("/api/state", auth=False)[0] == 401
    assert req("/%61pi/state", auth=False)[0] == 401
    assert req("/api/state", host="attacker.example")[0] == 403
    assert req("/api/state", origin="https://attacker.example")[0] == 403
    assert req("/api/query", {}, origin="null")[0] == 403
    assert req("/api/query", {}, origin=False)[0] == 403
    assert req("/api/state")[1]["revision"] is None
    assert "no-store" in req("/api/state")[2]["Cache-Control"]


def test_http_save_query_conflict_and_external_reload(explorer):
    root, req = explorer
    original = (root / "paper.md").read_bytes()
    status, result, _ = req("/api/save", {"data": confirmed_sample(req), "expected_revision": None})
    assert status == 200
    revision = result["revision"]
    query = {"filters": {"foundation": {"mode": "any", "values": ["b1"]},
                         "task": {"mode": "all", "values": ["t2"]}}}
    assert req("/api/query", query)[1]["works"] == []
    assert req("/api/save", {"data": confirmed_sample(req), "expected_revision": None})[0] == 409
    from scholar_workflow.knowledge.exploration import ExplorationStore

    changed = sample()
    changed["works"][0]["title"] = "Externally edited"
    saved = ExplorationStore(root).save(changed, expected_revision=revision)
    assert req("/api/state")[1]["revision"] == saved["revision"]
    assert req("/api/state")[1]["data"]["works"][0]["title"] == "Externally edited"
    assert req("/api/save", {"data": confirmed_sample(req), "expected_revision": revision})[0] == 409
    assert (root / "paper.md").read_bytes() == original


def test_http_assets_only_by_identity_and_no_canvas_json_preview(explorer, tmp_path):
    root, req = explorer
    assert req("/api/save", {"data": confirmed_sample(req), "expected_revision": None})[0] == 200
    listing = req("/api/assets/w1")[1]
    assert len(listing) == 2
    assert str(root) not in json.dumps(listing)
    status, body, headers = req("/api/asset/w1/body")
    assert status == 200 and b"Unchanged evidence" in body
    assert headers.get_content_type() == "text/plain"
    assert req("/api/asset/w1/canvas")[0] == 415
    assert req("/api/asset/w1/missing")[0] == 404
    assert req("/api/asset/w1/..%2F..%2Fsecret")[0] in {400, 404}
    outside = root.parent / "outside-explorer-secret.md"
    outside.write_text("private", encoding="utf-8")
    (root / "paper.md").unlink()
    (root / "paper.md").symlink_to(outside)
    assert req("/api/asset/w1/body")[0] in {403, 404}
    assert req("/api/assets/w1")[1][0]["available"] is False


def test_draft_query_never_saves_or_modifies_source(explorer):
    root, req = explorer
    data = sample()
    data["dimensions"].append({"id": "modality", "label": "模态", "kind": "enum", "multiple": True,
                               "scope": "work", "values": [{"id": "video", "label": "视频"}],
                               "sortable": False})
    data["works"][0]["attributes"] = {"modality": ["video"]}
    confirmed_sample(req, data)
    status, result, _ = req("/api/query", {"_draft": data, "filters": {"modality": {"mode": "all", "values": ["video"]}}})
    assert status == 200
    assert result["works"][0]["id"] == "w1"
    assert req("/api/state")[1]["revision"] is None
    assert not (root / ".scholar-workflow" / "exploration.yml").exists()


def test_draft_query_cannot_display_unconfirmed_paper_fragments(explorer):
    root, req = explorer
    original = (root / "paper.md").read_bytes()
    data = sample()
    data["works"][0]["kind"] = "paper"
    status, result, _ = req("/api/query", {"_draft": data})
    assert status == 400
    assert "server-confirmed unit reference" in result["error"]
    assert req("/api/state")[1]["revision"] is None
    assert (root / "paper.md").read_bytes() == original


def test_asset_content_types_and_native_open_are_identity_scoped(explorer, monkeypatch):
    root, req = explorer
    (root / "sample.pdf").write_bytes(b"%PDF-1.7\nfixture")
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    data = sample()
    data["works"][0]["assets"].extend([
        {"id": "pdf", "kind": "pdf", "label": "Original PDF", "uri": "sample.pdf"},
        {"id": "image", "kind": "image", "label": "Figure", "uri": "image.png"},
    ])
    confirmed_sample(req, data)
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 200
    assert req("/api/asset/w1/pdf")[2].get_content_type() == "application/pdf"
    assert req("/api/asset/w1/image")[2].get_content_type() == "image/png"
    opened = []
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which", lambda value: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen", lambda *args, **kwargs: opened.append((args, kwargs)))
    assert req("/api/open", {"work_id": "w1", "asset_id": "canvas"})[1] == {"submitted": True}
    assert opened[0][0][0][1].startswith("obsidian://open?path=")
    assert opened[0][1]["shell"] is False
    assert req("/api/open", {"work_id": "w1", "asset_id": "canvas", "path": "/outside"})[0] == 400
    assert len(opened) == 1


def test_invalid_draft_and_external_paths_are_rejected(explorer):
    _, req = explorer
    data = sample()
    data["works"][0]["assets"][0]["uri"] = "../outside.md"
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 400
    data["works"][0]["assets"][0]["uri"] = "javascript:alert(1)"
    assert req("/api/query", {"_draft": data})[0] == 400
    assert req("/api/state")[1]["revision"] is None


def test_native_open_blocks_executables_and_keeps_safe_text_preview(explorer, monkeypatch):
    root, req = explorer
    opened = []
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which", lambda value: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen", lambda *args, **kwargs: opened.append(args))
    data = sample()
    for suffix in ["command", "desktop", "py", "exe"]:
        (root / f"unsafe.{suffix}").write_text("do not execute", encoding="utf-8")
        data["works"][0]["assets"].append({"id": suffix, "label": suffix, "kind": "code", "uri": f"unsafe.{suffix}"})
    confirmed_sample(req, data)
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 200
    listing = {asset["id"]: asset for asset in req("/api/assets/w1")[1]}
    for suffix in ["command", "desktop", "py", "exe"]:
        assert listing[suffix]["available"] is True
        assert listing[suffix]["native_available"] is False
        assert listing[suffix]["native_reason"]
        assert req("/api/open", {"work_id": "w1", "asset_id": suffix})[0] == 403
    assert req("/api/asset/w1/command")[2].get_content_type() == "text/plain"
    assert req("/api/asset/w1/desktop")[2].get_content_type() == "text/plain"
    assert req("/api/asset/w1/py")[2].get_content_type() == "text/plain"
    assert req("/api/asset/w1/exe")[0] == 415
    assert opened == []


def test_native_protocols_only_allow_known_reading_actions(explorer, monkeypatch):
    _, req = explorer
    permitted = [
        "https://example.org/paper",
        "http://example.org/release",
        "obsidian://open?vault=test&file=Paper",
        "obsidian://zotflow?vault=test&type=open-attachment&libraryID=1&key=ABCDEFGH&page=4",
        "obsidian://zotflow?vault=test&type=open-annotation&libraryID=1&key=ABCDEFGH",
        "zotero://open-pdf/library/items/ABCDEFGH?page=4",
        "zotero://select/library/items/ABCDEFGH",
    ]
    blocked = [
        "obsidian://advanced-uri?vault=test&commandid=delete-file",
        "obsidian://new?vault=test&file=Unwanted",
        "obsidian://open?vault=test&file=Paper&append=Unwanted",
        "obsidian://zotflow?vault=test&type=sync",
        "obsidian://zotflow?type=open-attachment&type=delete",
        "obsidian://zotflow?type=open-note&key=ABCDEFGH",
        "zotero://debug-bridge/execute?code=Unwanted",
    ]
    # Protocol allowlisting is separate from the live local-reader gate.
    class ConfirmedReader:
        @staticmethod
        def handles(uri):
            return uri.startswith(("obsidian://zotflow", "zotero://open-pdf"))

        def require_current(self, work, asset):
            return None

    req.server.reader_gate = ConfirmedReader()
    data = sample()
    for index, uri in enumerate(permitted + blocked):
        data["works"][0]["assets"].append({"id": f"link-{index}", "label": f"Link {index}", "kind": "link", "uri": uri})
    confirmed_sample(req, data)
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 200
    opened = []
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which", lambda value: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen", lambda *args, **kwargs: opened.append(args))
    for index in range(len(permitted)):
        assert req("/api/open", {"work_id": "w1", "asset_id": f"link-{index}"})[0] == 200
    for index in range(len(permitted), len(permitted + blocked)):
        assert req("/api/open", {"work_id": "w1", "asset_id": f"link-{index}"})[0] == 403
    assert len(opened) == len(permitted)


def test_reader_availability_is_not_inferred_from_uri_or_asset_kind(explorer):
    _, req = explorer
    calls = []

    class UnavailableReader:
        @staticmethod
        def handles(uri):
            return uri.startswith("obsidian://zotflow")

        def availability(self, work, asset):
            calls.append((work["id"], asset["id"]))
            return {"native_available": False, "native_reason": "Local PDF mode is unverified",
                    "native_reason_code": "zotflow_unavailable"}

    req.server.reader_gate = UnavailableReader()
    data = sample()
    data["works"][0]["assets"].append({
        "id": "reader", "label": "Registered reader", "kind": "unrelated-label",
        "uri": "obsidian://zotflow?vault=1111111111111111&type=open-attachment&libraryID=1&key=PDFD2345",
    })
    confirmed_sample(req, data)
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 200
    listing = {row["id"]: row for row in req("/api/assets/w1")[1]}
    assert listing["reader"]["available"] is True
    assert listing["reader"]["native_available"] is False
    assert listing["reader"]["native_reason_code"] == "zotflow_unavailable"
    assert calls == [("w1", "reader")]


def test_reader_gate_refusal_never_launches_or_modifies_files(explorer, monkeypatch):
    root, req = explorer
    opened = []
    calls = []

    class UnconfirmedReader:
        @staticmethod
        def handles(uri):
            return uri.startswith("zotero://open-pdf")

        def require_current(self, work, asset):
            from scholar_workflow.adapters.exploration_readers import ReaderUnavailable

            calls.append((work["id"], asset["id"]))
            raise ReaderUnavailable("Refresh assets before opening", code="refresh_required")

    req.server.reader_gate = UnconfirmedReader()
    data = sample()
    data["works"][0]["assets"].append({"id": "reader", "label": "Original PDF",
        "kind": "link", "uri": "zotero://open-pdf/library/items/PDFD2345?page=4"})
    confirmed_sample(req, data)
    assert req("/api/save", {"data": data, "expected_revision": None})[0] == 200
    original = (root / "paper.md").read_bytes()
    revision = req("/api/state")[1]["revision"]
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which", lambda value: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen", lambda *args, **kwargs: opened.append(args))
    status, result, _ = req("/api/open", {"work_id": "w1", "asset_id": "reader"})
    assert status == 403 and result["code"] == "refresh_required"
    assert calls == [("w1", "reader")] and opened == []
    assert req("/api/state")[1]["revision"] == revision
    assert (root / "paper.md").read_bytes() == original


def test_whole_unit_http_selector_never_creates_files_or_accepts_paths(explorer):
    root, req = explorer
    calls = []

    class References:
        def fields(self):
            calls.append("fields")
            return {"fields": [{"source_id": "source-a", "field_id": "field-a", "title": "Field"}],
                    "diagnostics": []}

        def units(self, source_id, field_id):
            calls.append((source_id, field_id))
            return {"units": [{"entity_ref": {"source_id": source_id, "object_id": "paper-a"},
                               "title": "Existing paper", "asset_count": 4, "diagnostics": []}],
                    "diagnostics": []}

        def reference(self, root_arg, data, source_id, field_id, unit_refs):
            assert root_arg == root
            assert source_id == "source-a" and field_id == "field-a"
            assert unit_refs == [{"source_id": "source-a", "object_id": "paper-a"}]
            calls.append("reference")
            result = sample()
            result["works"][0].update(kind="paper", entity_ref=unit_refs[0])
            return result

    req.server.references = References()
    assert req("/api/unit-fields", auth=False)[0] == 401
    assert req("/api/unit-fields")[1]["fields"][0]["title"] == "Field"
    choice = {"source_id": "source-a", "field_id": "field-a"}
    assert req("/api/unit-options", choice)[1]["units"][0]["asset_count"] == 4
    assert req("/api/unit-options", {**choice, "path": "/arbitrary"})[0] == 400
    assert req("/api/unit-options", {**choice, "source_id": ["source-a"]})[0] == 400
    from scholar_workflow.knowledge.exploration import default_data

    selection = {**choice, "data": default_data(),
                 "unit_refs": [{"source_id": "source-a", "object_id": "paper-a"}]}
    status, result, _ = req("/api/unit-reference", selection)
    assert status == 200 and result["data"]["works"][0]["title"] == "Example"
    assert req("/api/unit-reference", {**selection, "cwd": "/arbitrary"})[0] == 400
    assert req("/api/state")[1]["revision"] is None
    assert not (root / ".scholar-workflow").exists()
    assert calls == ["fields", ("source-a", "field-a"), "reference"]


def test_whole_unit_http_conflicts_remain_explicit(explorer):
    from scholar_workflow.knowledge.exploration import ExplorationError, default_data

    _, req = explorer

    class References:
        def reference(self, *_args):
            raise ExplorationError("Selected unit ownership changed", 5)

    req.server.references = References()
    status, result, _ = req("/api/unit-reference", {
        "source_id": "source-a", "field_id": "field-a", "data": default_data(),
        "unit_refs": [{"source_id": "source-a", "object_id": "paper-a"}]})
    assert status == 409 and "ownership changed" in result["error"]
    assert req("/api/state")[1]["revision"] is None


def test_raw_save_or_reference_cannot_inject_a_new_fragment_paper(explorer):
    root, req = explorer
    fake = sample()
    fake["works"][0]["kind"] = "paper"
    assert req("/api/save", {"data": fake, "expected_revision": None})[0] == 400
    assert req("/api/unit-reference", {"data": fake, "source_id": "source-a", "field_id": "field-a",
                                       "unit_refs": [{"source_id": "source-a", "object_id": "paper-a"}]})[0] == 400
    assert not (root / ".scholar-workflow").exists()


def test_server_confirmed_whole_unit_cannot_be_saved_as_a_fragment(explorer):
    from copy import deepcopy

    from scholar_workflow.knowledge.exploration import default_data

    root, req = explorer
    original = (root / "paper.md").read_bytes()
    unit_ref = {"source_id": "source-a", "object_id": "paper-a"}

    class References:
        def reference(self, *_args):
            result = sample()
            result["works"][0].update(kind="paper", entity_ref=unit_ref)
            return result

    req.server.references = References()
    response = req("/api/unit-reference", {"data": default_data(), "source_id": "source-a",
                                          "field_id": "field-a", "unit_refs": [unit_ref]})
    assert response[0] == 200
    data = response[1]["data"]
    assert req("/api/query", {"_draft": data})[0] == 200
    fragment = deepcopy(data)
    fragment["works"][0]["assets"].pop()
    assert req("/api/query", {"_draft": fragment})[0] == 400
    assert req("/api/save", {"data": fragment, "expected_revision": None})[0] == 400
    assert req("/api/state")[1]["revision"] is None
    saved = req("/api/save", {"data": data, "expected_revision": None})
    assert saved[0] == 200
    data["works"][0]["summary"] = "A human outer assessment, not a package rewrite"
    assert req("/api/save", {"data": data, "expected_revision": saved[1]["revision"]})[0] == 200
    current = req("/api/state")[1]
    data["works"][0]["assets"].append({"id": "unregistered", "label": "Unrelated note",
                                         "kind": "markdown", "uri": "unrelated.md"})
    assert req("/api/save", {"data": data, "expected_revision": current["revision"]})[0] == 400
    assert req("/api/state")[1]["revision"] == current["revision"]
    assert (root / "paper.md").read_bytes() == original
