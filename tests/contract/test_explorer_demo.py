"""Independent synthetic demo boundaries through the real store and HTTP adapter."""

from __future__ import annotations

import importlib.util
import json
import struct
import threading
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def demo_module(monkeypatch):
    from scholar_workflow.adapters import exploration_readers, knowledge_explorer
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry
    from scholar_workflow.workflows import exploration_references

    external_calls = []

    def forbidden(*_args, **_kwargs):
        external_calls.append(True)
        raise AssertionError("The synthetic demo must not access personal or native services")

    monkeypatch.setattr(KnowledgeSourceRegistry, "__init__", forbidden)
    monkeypatch.setattr(ZoteroLocalAdapter, "__init__", forbidden)
    monkeypatch.setattr(exploration_references.ExplorationReferenceService, "__init__", forbidden)
    monkeypatch.setattr(exploration_references, "field_paper_units", forbidden)
    monkeypatch.setattr(exploration_references, "include_resource_links", forbidden)
    monkeypatch.setattr(exploration_readers.ExplorationReaderGate, "__init__", forbidden)
    monkeypatch.setattr(knowledge_explorer, "subprocess", SimpleNamespace(
        Popen=forbidden, DEVNULL=-3,
    ))
    path = Path(__file__).resolve().parents[2] / "dev-guide/demos/knowledge_explorer.py"
    spec = importlib.util.spec_from_file_location("synthetic_explorer_demo", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    assert external_calls == [], "An external service was attempted, even if its error was caught"


@pytest.fixture
def demo(demo_module, tmp_path, monkeypatch):
    root = tmp_path.resolve() / "demo"
    root.mkdir()
    server, token = demo_module.demo_server(root)
    base = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    urlopen = urllib.request.urlopen

    def local_only(request, *_args, **_kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        assert url.startswith(base + "/"), "The demo attempted a non-fixture HTTP request"
        return urlopen(request, *_args, **_kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", local_only)

    def raw_request(path, payload=None):
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
        req = urllib.request.Request(
            base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers.get_content_type(), response.read()

    def request(path, payload=None):
        status, kind, body = raw_request(path, payload)
        assert kind == "application/json", (status, kind)
        return status, json.loads(body)

    try:
        yield SimpleNamespace(root=root, server=server, request=request,
                              raw_request=raw_request, module=demo_module)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def _resources(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in (root / "resources").rglob("*") if path.is_file()}


def _choice(demo):
    return {"source_id": demo.module.SOURCE, "field_id": demo.module.FIELD}


def _state(demo):
    status, state = demo.request("/api/state")
    assert status == 200
    return state


def _ref(demo, letter):
    return {"source_id": demo.module.SOURCE, "object_id": "synthetic-paper:" + letter}


@pytest.mark.parametrize("shape", ["nonempty", "symlink", "symlink-parent", "missing"])
def test_demo_refuses_adopting_old_or_symlink_directories(demo_module, tmp_path, shape):
    directory = tmp_path.resolve() / "owned"
    directory.mkdir()
    old = directory / "existing.md"
    if shape == "nonempty":
        old.write_text("User content must survive.", encoding="utf-8")
        selected = directory
    elif shape == "symlink":
        selected = tmp_path.resolve() / "alias"
        selected.symlink_to(directory, target_is_directory=True)
    elif shape == "symlink-parent":
        (directory / "child").mkdir()
        alias = tmp_path.resolve() / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        selected = alias / "child"
    else:
        selected = tmp_path.resolve() / "not-created"
    before = {path.relative_to(directory): path.read_bytes()
              for path in directory.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="existing empty directory"):
        demo_module.prepare_demo(selected)
    after = {path.relative_to(directory): path.read_bytes()
             for path in directory.rglob("*") if path.is_file()}
    assert after == before
    assert not (directory / ".scholar-workflow").exists()
    assert not (directory / "resources").exists()


def test_demo_contains_whole_units_and_shares_actual_static_interface(demo):
    before = _resources(demo.root)
    state = _state(demo)
    data = state["data"]
    assert len(data["works"]) == 3
    assert len(data["records"]) == 4
    assert len(data["edges"]) == 2
    assert {work["entity_ref"]["object_id"] for work in data["works"]} == {
        "synthetic-paper:a", "synthetic-paper:b", "synthetic-paper:c",
    }
    assert len({work["id"] for work in data["works"]}) == 3
    for work in data["works"]:
        assert work["kind"] == "paper"
        assert len(work["assets"]) == 5
        assert {Path(asset["uri"]).name for asset in work["assets"]} == {
            "Paper.md", "Analysis.md", "figure.png", "config.yml", "Analysis.canvas",
        }
        assert demo.module.NOTICE in work["summary"]
    status, fields = demo.request("/api/unit-fields")
    assert status == 200 and len(fields["fields"]) == 1
    assert demo.module.NOTICE in fields["diagnostics"]
    status, options = demo.request("/api/unit-options", _choice(demo))
    assert status == 200 and len(options["units"]) == 4
    assert all(unit["asset_count"] == 5 for unit in options["units"])
    for path, expected_kind in (("/", "text/html"), ("/explore.js", "text/javascript"),
                                ("/explore.css", "text/css")):
        status, kind, body = demo.raw_request(path)
        assert status == 200 and kind == expected_kind and len(body) > 100
    assert _state(demo) == state
    assert _resources(demo.root) == before


def test_demo_filters_one_record_instead_of_combining_a_records(demo):
    state = _state(demo)
    before = _resources(demo.root)
    status, rejected_combination = demo.request("/api/query", {"filters": {
        "foundation": {"mode": "any", "values": ["base-a"]},
        "task": {"mode": "any", "values": ["control"]},
    }})
    assert status == 200
    assert rejected_combination["works"] == []
    assert rejected_combination["records"] == []
    status, valid = demo.request("/api/query", {"filters": {
        "foundation": {"mode": "any", "values": ["base-b"]},
        "task": {"mode": "any", "values": ["control"]},
    }})
    assert status == 200 and len(valid["works"]) == len(valid["records"]) == 1
    assert valid["works"][0]["entity_ref"] == _ref(demo, "a")
    assert valid["records"][0]["id"] == "demo-record-a-control"
    assert _state(demo) == state
    assert _resources(demo.root) == before


def test_fourth_unit_proposal_is_complete_and_save_only_changes_outer_manifest(demo):
    state = _state(demo)
    before = _resources(demo.root)
    status, proposal = demo.request("/api/unit-reference", {
        **_choice(demo), "data": state["data"], "unit_refs": [_ref(demo, "d")],
    })
    assert status == 200, proposal
    assert _state(demo) == state, "Preparing a reference must not save it"
    assert len(proposal["data"]["works"]) == 4
    fourth = next(work for work in proposal["data"]["works"]
                  if work["entity_ref"] == _ref(demo, "d"))
    assert len(fourth["assets"]) == 5
    assert {Path(asset["uri"]).name for asset in fourth["assets"]} == {
        "Paper.md", "Analysis.md", "figure.png", "config.yml", "Analysis.canvas",
    }
    status, saved = demo.request("/api/save", {
        "data": proposal["data"], "expected_revision": state["revision"],
    })
    assert status == 200 and saved["revision"] != state["revision"]
    assert _state(demo) == saved
    assert saved["data"]["records"] == state["data"]["records"]
    assert saved["data"]["edges"] == state["data"]["edges"]
    status, repeated = demo.request("/api/unit-reference", {
        **_choice(demo), "data": saved["data"], "unit_refs": [_ref(demo, "d")],
    })
    assert status == 200 and repeated["data"] == saved["data"]
    assert _resources(demo.root) == before
    assert {path.name for path in (demo.root / ".scholar-workflow").iterdir()} == {
        "exploration.yml",
    }


def test_fragment_and_invented_paper_cannot_be_saved_or_queried_as_units(demo):
    state = _state(demo)
    before = _resources(demo.root)
    status, proposal = demo.request("/api/unit-reference", {
        **_choice(demo), "data": state["data"], "unit_refs": [_ref(demo, "d")],
    })
    assert status == 200
    fragmented = deepcopy(proposal["data"])
    fragmented["works"][-1]["assets"] = fragmented["works"][-1]["assets"][:1]
    invented = deepcopy(state["data"])
    fake = deepcopy(invented["works"][0])
    fake.update(id="invented-card", title="An invented title is not a whole unit",
                entity_ref=_ref(demo, "unknown"), assets=[])
    invented["works"].append(fake)
    for draft in (fragmented, invented):
        status, result = demo.request("/api/save", {
            "data": draft, "expected_revision": state["revision"],
        })
        assert status == 400 and "complete server-confirmed unit reference" in result["error"]
        status, result = demo.request("/api/query", {"_draft": draft})
        assert status == 400 and "complete server-confirmed unit reference" in result["error"]
    assert _state(demo) == state
    assert _resources(demo.root) == before


@pytest.mark.parametrize("problem", ["unknown-field", "unknown-source", "unknown-unit",
                                    "fragment-selector", "duplicate-selector", "duplicate-identity"])
def test_bad_unit_selections_and_duplicate_identities_never_write(demo, problem):
    state = _state(demo)
    before = _resources(demo.root)
    choice = _choice(demo)
    refs = [_ref(demo, "d")]
    if problem == "unknown-field":
        choice["field_id"] = "not-a-field"
    elif problem == "unknown-source":
        choice["source_id"] = "not-a-source"
    elif problem == "unknown-unit":
        refs = [_ref(demo, "not-declared")]
    elif problem == "fragment-selector":
        refs[0]["asset_id"] = "one-caption-not-a-paper"
    elif problem == "duplicate-selector":
        refs *= 2
    else:
        duplicate = deepcopy(state["data"])
        work = deepcopy(duplicate["works"][0])
        work.update(id="duplicate-unit", assets=[])
        duplicate["works"].append(work)
        status, result = demo.request("/api/save", {
            "data": duplicate, "expected_revision": state["revision"],
        })
        assert status == 400 and "error" in result
        assert _state(demo) == state
        assert _resources(demo.root) == before
        return
    status, result = demo.request("/api/unit-reference", {
        **choice, "data": state["data"], "unit_refs": refs,
    })
    assert status == 400 and "error" in result
    if problem in {"unknown-field", "unknown-source"}:
        status, result = demo.request("/api/unit-options", choice)
        assert status == 400 and "Unknown synthetic Field" in result["error"]
    assert _state(demo) == state
    assert _resources(demo.root) == before


def test_all_native_asset_actions_fail_closed_without_external_probes(demo):
    state = _state(demo)
    before = _resources(demo.root)
    for work in state["data"]["works"]:
        status, listing = demo.request("/api/assets/" + work["id"])
        assert status == 200 and len(listing) == len(work["assets"])
        assert all(asset["native_available"] is False for asset in listing)
        assert len([asset for asset in listing if asset["available"]]) == 4
        for asset in work["assets"]:
            status, result = demo.request("/api/open", {
                "work_id": work["id"], "asset_id": asset["id"],
            })
            assert status == 403 and "error" in result
    assert _state(demo) == state
    assert _resources(demo.root) == before


def test_declared_body_and_image_preview_serve_actual_unchanged_fixture_bytes(demo):
    state = _state(demo)
    before = _resources(demo.root)
    for work in state["data"]["works"]:
        asset = next(row for row in work["assets"] if row["uri"].endswith("/Analysis.md"))
        status, preview = demo.request(f"/api/preview/{work['id']}/{asset['id']}")
        assert status == 200, preview
        assert preview["text"].encode("utf-8") == before[asset["uri"]]
        assert "> [!quote]-" in preview["text"]
        assert "**the variant reduces the example error**" in preview["text"]
        assert demo.module.NOTICE in preview["text"]
        assert len(preview["images"]) == 1
        image = preview["images"][0]
        assert "media_id" in image and "reason_code" not in image
        status, kind, body = demo.raw_request("/api/preview-media/" + image["media_id"])
        assert status == 200 and kind == "image/png"
        declared_image = next(row for row in work["assets"] if row["uri"].endswith("/figure.png"))
        assert body == before[declared_image["uri"]]
        assert struct.unpack(">II", body[16:24]) == (640, 220)
        for link in preview["links"]:
            if link["kind"] == "native":
                status, availability = demo.request("/api/reading-link/" + link["link_id"])
                assert status == 200 and availability["native_available"] is False
                status, denied = demo.request("/api/open-link", {"link_id": link["link_id"]})
                assert status == 403 and "error" in denied
    status, unknown = demo.request("/api/open-link", {"link_id": "not-a-session-link"})
    assert status == 403 and unknown["code"] == "link_expired"
    assert _state(demo) == state
    assert _resources(demo.root) == before


def test_demo_denies_registered_inline_reading_links_even_when_requested_directly(demo):
    state = _state(demo)
    work = state["data"]["works"][0]
    asset = next(row for row in work["assets"] if row["uri"].endswith("/Analysis.md"))
    body = demo.root / asset["uri"]
    # Only this disposable fixture changes. The real paper packages are never read.
    body.write_text(body.read_text(encoding="utf-8")
                    + "\n[合成资料入口](Paper.md)\n", encoding="utf-8")
    before = _resources(demo.root)
    status, preview = demo.request(f"/api/preview/{work['id']}/{asset['id']}")
    assert status == 200
    native = [link for link in preview["links"] if link["kind"] == "native"]
    assert len(native) == 1 and native[0]["label"] == "合成资料入口"
    link = native[0]
    assert "uri" not in link, "The browser receives a controlled action, not a native URI"
    status, unprepared = demo.request("/api/open-link", {"link_id": link["link_id"]})
    assert status == 403 and unprepared["code"] == "refresh_required"
    status, availability = demo.request("/api/reading-link/" + link["link_id"])
    assert status == 200 and availability["native_available"] is False
    status, denied = demo.request("/api/open-link", {"link_id": link["link_id"]})
    assert status == 403 and denied["code"] == "refresh_required"
    assert _state(demo) == state
    assert _resources(demo.root) == before
