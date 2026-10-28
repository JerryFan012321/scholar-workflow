"""Controlled inline citations through real loopback HTTP and synthetic readers."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
from tests.contract.explorer_fixture import fixture_server as make_server

NATIVE = ("obsidian://zotflow?vault=1111111111111111&type=open-attachment"
          "&libraryID=123&key=BCDE3456&navigation=%7B%22pageIndex%22%3A3%7D")
LITERAL = f"[原文·PDF 第 4 页]({NATIVE})"


@pytest.fixture
def previews(tmp_path, monkeypatch):
    text = (f"# 合成正文\n\n中文😀的直接证据。{LITERAL}\n"
            "[官方网页](https://research.example/source)\n"
            "[不允许的动作](obsidian://advanced-uri?commandid=delete)\n"
            f"```text\n{LITERAL}\n```\n![不活化图片]({NATIVE})\n")
    document = tmp_path / "analysis.md"
    document.write_text(text, encoding="utf-8")
    model = default_data()
    model["works"] = [{"id": "paper-a", "kind": "paper", "title": "Synthetic paper",
                       "entity_ref": {"source_id": "synthetic-source", "object_id": "paper:zotero:123:ABCD2345"},
                       "attributes": {}, "assets": [{"id": "analysis-a", "label": "分析正文",
                           "kind": "markdown", "uri": "analysis.md"}]}]
    store = ExplorationStore(tmp_path)
    store.save(model, expected_revision=None)
    calls, opened, prepared = [], [], {}

    class Reader:
        @staticmethod
        def handles(uri):
            return uri.startswith(("obsidian://zotflow", "zotero://open-pdf"))

        def availability(self, work, asset):
            assert work["id"] == "paper-a" and asset["uri"] == NATIVE
            calls.append("prepare")
            prepared[asset["id"]] = asset["uri"]
            return {"native_available": True}

        def require_current(self, work, asset):
            from scholar_workflow.adapters.exploration_readers import ReaderUnavailable

            if prepared.get(asset["id"]) != asset["uri"]:
                raise ReaderUnavailable("Prepare the reader first", code="refresh_required")
            calls.append("require")

    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.shutil.which",
                        lambda _name: "/usr/bin/open")
    monkeypatch.setattr("scholar_workflow.adapters.knowledge_explorer.subprocess.Popen",
                        lambda argv, **kwargs: opened.append((argv, kwargs)))
    server, token = make_server(tmp_path, reader_gate=Reader())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, payload=None, *, auth=True, origin=None):
        headers = {"Authorization": f"Bearer {token}"} if auth else {}
        if payload is not None:
            headers.update({"Content-Type": "application/json", "Origin": origin or base})
        req = urllib.request.Request(base + path, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    yield {"root": tmp_path, "text": text, "document": document, "store": store,
           "server": server, "request": request, "opened": opened, "calls": calls}
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def citation(state):
    status, preview = state["request"]("/api/preview/paper-a/analysis-a")
    assert status == 200
    return preview, next(row for row in preview["links"] if row["label"] == "原文·PDF 第 4 页")


def test_preview_returns_same_read_text_hash_and_utf16_inline_positions(previews):
    preview, link = citation(previews)
    assert preview["text"] == previews["text"]
    assert preview["document_revision"].startswith("sha256:")
    encoded = preview["text"].encode("utf-16-le")
    assert encoded[link["start"] * 2:link["end"] * 2].decode("utf-16-le") == LITERAL
    assert link["kind"] == "native" and link["link_id"]
    assert not any(key in link for key in ("uri", "path", "attachment_key"))
    assert [row["label"] for row in preview["links"]].count("原文·PDF 第 4 页") == 1
    assert next(row for row in preview["links"] if row["label"] == "不允许的动作")["kind"] == "unavailable"
    assert previews["calls"] == [] and previews["opened"] == []


def test_inline_prepare_then_open_preserves_exact_navigation_and_original_files(previews):
    before = previews["document"].read_bytes()
    revision = previews["store"].load()["revision"]
    _, link = citation(previews)
    req = previews["request"]
    assert req("/api/open-link", {"link_id": link["link_id"]})[0] == 403
    assert req("/api/reading-link/" + link["link_id"])[1]["native_available"] is True
    assert req("/api/open-link", {"link_id": link["link_id"]}) == (200, {"submitted": True})
    assert previews["calls"] == ["prepare", "require"]
    argv, options = previews["opened"][0]
    assert argv == ["/usr/bin/open", NATIVE] and options["shell"] is False
    assert previews["document"].read_bytes() == before
    assert previews["store"].load()["revision"] == revision


def test_inline_link_ids_reject_forged_parameters_and_cross_session(previews):
    _, link = citation(previews)
    req = previews["request"]
    assert req("/api/preview/paper-a/analysis-a", auth=False)[0] == 401
    assert req("/api/reading-link/unknown-link")[0] == 403
    assert req("/api/open-link", {"link_id": link["link_id"]}, auth=False)[0] == 401
    assert req("/api/open-link", {"link_id": link["link_id"]}, origin="https://attacker.example")[0] == 403
    for extra in ({"uri": NATIVE}, {"path": "/outside"}, {"key": "BCDE3456"}):
        assert req("/api/open-link", {"link_id": link["link_id"], **extra})[0] == 400
    assert req("/api/open-link", {"link_id": {"path": "/outside"}})[0] == 400
    from scholar_workflow.adapters.exploration_previews import (
        ExplorationPreviewService,
        PreviewUnavailable,
    )

    other = ExplorationPreviewService(previews["root"], previews["store"], previews["server"].reader_gate)
    with pytest.raises(PreviewUnavailable):
        other.require_current(link["link_id"])
    assert previews["opened"] == []


@pytest.mark.parametrize("change", ["bytes", "uri", "symlink"])
def test_inline_link_refuses_changed_document_or_declaration(previews, change):
    _, link = citation(previews)
    req = previews["request"]
    assert req("/api/reading-link/" + link["link_id"])[1]["native_available"] is True
    if change == "bytes":
        previews["document"].write_text("# New version\n" + previews["text"], encoding="utf-8")
    elif change == "symlink":
        target = previews["root"] / "other.md"
        target.write_text(previews["text"], encoding="utf-8")
        previews["document"].unlink()
        previews["document"].symlink_to(target)
    else:
        state = previews["store"].load()
        state["data"]["works"][0]["assets"][0]["uri"] = "other.md"
        (previews["root"] / "other.md").write_text(previews["text"], encoding="utf-8")
        # The generic explorer correctly rejects paper inventory edits; simulate
        # an actual independent file edit to its outer YAML declaration instead.
        import yaml

        (previews["root"] / ".scholar-workflow" / "exploration.yml").write_text(
            yaml.safe_dump(state["data"], allow_unicode=True), encoding="utf-8")
    status, result = req("/api/open-link", {"link_id": link["link_id"]})
    assert status == 403 and result["code"] == "preview_changed"
    assert previews["opened"] == []
