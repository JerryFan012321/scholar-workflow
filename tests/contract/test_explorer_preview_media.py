"""Authenticated, source-bound image previews with synthetic paper assets only."""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from scholar_workflow.adapters.knowledge_explorer import make_server
from scholar_workflow.knowledge.exploration import ExplorationStore, default_data

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aR1kAAAAASUVORK5CYII=")


@pytest.fixture
def media_preview(tmp_path):
    folder = tmp_path / "paper"
    (folder / "attachments").mkdir(parents=True)
    image = folder / "attachments" / "figure.png"
    image.write_bytes(PNG)
    (folder / "attachments" / "unsafe.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>bad()</script></svg>', encoding="utf-8")
    literal = "![完整图注](attachments/figure.png)"
    text = ("# 合成正文\n\n中文😀论点。\n\n" + literal + "\n\n"
            "![未登记图片](attachments/unknown.png)\n"
            "![网页图片](https://example.invalid/track.png)\n"
            "![[paper/attachments/unsafe.svg|300]]\n"
            "`![代码伪图片](attachments/figure.png)`\n")
    document = folder / "analysis.md"
    document.write_text(text, encoding="utf-8")
    data = default_data()
    data["works"] = [{"id": "paper", "kind": "paper", "title": "Synthetic paper unit",
        "entity_ref": {"source_id": "fixture", "object_id": "paper:fixture"}, "attributes": {},
        "assets": [
            {"id": "analysis", "kind": "markdown", "label": "正文", "uri": "paper/analysis.md"},
            {"id": "figure", "kind": "image", "label": "图表", "uri": "paper/attachments/figure.png"},
            {"id": "svg", "kind": "image", "label": "SVG", "uri": "paper/attachments/unsafe.svg"},
        ]}]
    store = ExplorationStore(tmp_path)
    store.save(data, expected_revision=None)
    server, token = make_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def request(path, *, auth=True, origin=None):
        headers = {"Authorization": f"Bearer {token}"} if auth else {}
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(base + path, headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=3)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    yield {"root": tmp_path, "document": document, "image": image, "text": text,
           "literal": literal, "store": store, "server": server, "request": request}
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def _preview(state):
    status, _, raw = state["request"]("/api/preview/paper/analysis")
    assert status == 200
    result = json.loads(raw)
    return result, next(row for row in result["images"] if row["label"] == "完整图注")


def test_declared_image_is_in_place_bounded_and_readonly(media_preview):
    state = media_preview
    original = state["document"].read_bytes()
    revision = state["store"].load()["revision"]
    preview, image = _preview(state)
    assert preview["text"] == state["text"]
    encoded = preview["text"].encode("utf-16-le")
    assert encoded[image["start"] * 2:image["end"] * 2].decode("utf-16-le") == state["literal"]
    assert not any(field in image for field in ("uri", "path", "root", "link_id"))
    status, headers, body = state["request"]("/api/preview-media/" + image["media_id"])
    assert status == 200 and headers["Content-Type"] == "image/png" and body == PNG
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert state["document"].read_bytes() == original
    assert state["image"].read_bytes() == PNG
    assert state["store"].load()["revision"] == revision
    assert len(preview["images"]) == 4
    assert all("reason_code" in row and "media_id" not in row
               for row in preview["images"] if row["label"] != "完整图注")


def test_media_ids_do_not_grant_paths_or_other_sessions(media_preview):
    state = media_preview
    _, image = _preview(state)
    path = "/api/preview-media/" + image["media_id"]
    request = state["request"]
    assert request(path, auth=False)[0] == 401
    assert request(path, origin="https://example.invalid")[0] == 403
    assert request(path + "?path=/private/outside.png")[0] == 400
    assert request("/api/preview-media/unknown")[0] == 403
    from scholar_workflow.adapters.exploration_previews import (
        ExplorationPreviewService,
        PreviewUnavailable,
    )

    other = ExplorationPreviewService(state["root"], state["store"], state["server"].reader_gate)
    with pytest.raises(PreviewUnavailable):
        other.media(image["media_id"])


@pytest.mark.parametrize("change", ["document", "image", "symlink", "declaration"])
def test_changed_source_or_image_refuses_old_media_id(media_preview, change):
    state = media_preview
    _, image = _preview(state)
    if change == "document":
        state["document"].write_text(state["text"] + "\nA changed source.\n", encoding="utf-8")
    elif change == "image":
        state["image"].write_bytes(PNG + b"changed image bytes")
    elif change == "symlink":
        target = state["root"] / "another.png"
        target.write_bytes(PNG)
        state["image"].unlink()
        state["image"].symlink_to(target)
    else:
        import yaml

        data = state["store"].load()["data"]
        data["works"][0]["assets"][1]["uri"] = "paper/attachments/another.png"
        (state["root"] / ".scholar-workflow" / "exploration.yml").write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    status, _, raw = state["request"]("/api/preview-media/" + image["media_id"])
    assert status == 403 and json.loads(raw)["code"]
