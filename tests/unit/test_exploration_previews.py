"""Controlled source-link previews over synthetic documents and fake reader gates."""

import base64
import hashlib
import struct
import zlib
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from scholar_workflow.adapters import exploration_previews as module
from scholar_workflow.adapters.exploration_readers import ReaderUnavailable

PDF = "ABCD2345"
VAULT = "1111111111111111"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aR1kAAAAASUVORK5CYII=")


@pytest.fixture
def preview(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    document = notes / "Analysis.md"
    target = notes / "Original.md"
    target.write_text("# Original\n\nEvidence paragraph. ^evidence\n", encoding="utf-8")
    uri = f"zotero://open-pdf/library/items/{PDF}?page=4"
    state = SimpleNamespace(root=tmp_path, document=document, target=target, calls=[], allowed=True,
                            uri=uri, data={"works": [{"id": "paper-a", "kind": "paper",
                              "entity_ref": {"source_id": "source-a", "object_id": "paper:a"},
                              "assets": [
                                  {"id": "analysis", "label": "Analysis", "kind": "analysis", "uri": "notes/Analysis.md"},
                                  {"id": "original", "label": "Original", "kind": "note", "uri": "notes/Original.md"},
                                  {"id": "pdf", "label": "PDF", "kind": "zotero-pdf", "uri": uri},
                              ]}]})

    class Store:
        def load(self):
            return {"data": deepcopy(state.data), "revision": "outer-revision"}

    class Gate:
        def availability(self, work, asset):
            state.calls.append(("prepare", work["id"], deepcopy(asset)))
            return {"native_available": state.allowed, **({} if state.allowed else {
                "native_reason": "Reader unavailable", "native_reason_code": "zotflow_unavailable"})}

        def require_current(self, work, asset):
            state.calls.append(("open", work["id"], deepcopy(asset)))
            if not state.allowed:
                raise ReaderUnavailable("Reader unavailable", code="pdf_changed")

    state.store, state.gate = Store(), Gate()
    state.service = module.ExplorationPreviewService(tmp_path, state.store, state.gate)
    document.write_text(f"# 分析😀\n\n证据 [原文·PDF 第4页]({uri})\n", encoding="utf-8")
    return state


def test_preview_retains_exact_source_link_in_place_and_utf16_offsets(preview):
    body = preview.document.read_text(encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert result["text"] == body
    assert result["document_revision"] == "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    assert len(result["links"]) == 1 and preview.calls == []
    link = result["links"][0]
    assert link["kind"] == "native" and link["label"] == "原文·PDF 第4页"
    assert "uri" not in link and preview.uri not in link["link_id"]
    literal = body.encode("utf-16-le")[link["start"] * 2:link["end"] * 2].decode("utf-16-le")
    assert literal == f"[原文·PDF 第4页]({preview.uri})"
    assert link["start"] != body.index("[原文")


@pytest.mark.parametrize("uri", [
    f"zotero://open-pdf/library/items/{PDF}?page=4&annotation=BCDE3456",
    f"obsidian://zotflow?vault={VAULT}&type=open-attachment&libraryID=123&key={PDF}&navigation=%7B%22pageIndex%22%3A3%7D",
    f"obsidian://zotflow?vault={VAULT}&type=open-annotation&libraryID=123&key=BCDE3456",
])
def test_prepare_and_open_use_exact_server_bound_reader_uri(preview, uri):
    preview.document.write_text(f"[Source]({uri})", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    assert preview.service.prepare(link["link_id"]) == {"native_available": True}
    assert preview.service.require_current(link["link_id"]) == uri
    assert [call[0] for call in preview.calls] == ["prepare", "open"]
    assert all(call[2]["uri"] == uri for call in preview.calls)


def test_open_without_prepare_and_unknown_or_cross_session_tokens_refuse(preview):
    token = preview.service.preview("paper-a", "analysis")["links"][0]["link_id"]
    with pytest.raises(module.PreviewUnavailable):
        preview.service.require_current(token)
    another = module.ExplorationPreviewService(preview.root, preview.store, preview.gate)
    for service, link_id in ((preview.service, "unknown"), (another, token)):
        with pytest.raises(module.PreviewUnavailable):
            service.prepare(link_id)
    assert preview.calls == []


@pytest.mark.parametrize("change", ["body", "uri", "entity", "remove"])
def test_changed_document_declaration_or_bytes_reject_old_links(preview, change):
    token = preview.service.preview("paper-a", "analysis")["links"][0]["link_id"]
    preview.service.prepare(token)
    if change == "body":
        preview.document.write_text(preview.document.read_text() + "Updated", encoding="utf-8")
    elif change == "uri":
        preview.data["works"][0]["assets"][0]["uri"] = "notes/Other.md"
    elif change == "entity":
        preview.data["works"][0]["entity_ref"]["object_id"] = "paper:b"
    else:
        preview.data["works"][0]["assets"] = preview.data["works"][0]["assets"][1:]
    with pytest.raises(module.PreviewUnavailable) as error:
        preview.service.require_current(token)
    assert error.value.code == "preview_changed"
    assert all(call[0] != "open" for call in preview.calls)


def test_code_images_and_unknown_syntax_remain_text_without_active_tokens(preview):
    body = (f"`[inline]({preview.uri})`\n```markdown\n[fenced]({preview.uri})\n```\n"
            f"![image]({preview.uri})\n[web](https://research.example/page)\n"
            "[unsafe](javascript:alert)\n[[missing/path#^block|Unknown original]]\n")
    preview.document.write_text(body, encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert result["text"] == body
    assert {link["label"] for link in result["links"]} == {"web", "unsafe", "Unknown original"}
    web = next(link for link in result["links"] if link["kind"] == "web")
    assert web["uri"] == "https://research.example/page" and "link_id" not in web
    unavailable = [link for link in result["links"] if link["kind"] == "unavailable"]
    assert all(link.get("reason_code") and "link_id" not in link and "uri" not in link for link in unavailable)


@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_fence_with_trailing_text_cannot_reactivate_native_links(preview, marker):
    body = (f"{marker}text\n{marker}not-a-close\n[Still code]({preview.uri})\n"
            f"{marker}\n[Real source]({preview.uri})\n")
    preview.document.write_text(body, encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert result["text"] == body
    assert [link["label"] for link in result["links"]] == ["Real source"]
    assert result["links"][0]["kind"] == "native"


@pytest.mark.parametrize("target", ["notes/Original#^evidence", "notes/Original#Original"])
def test_explicit_wikilink_keeps_native_block_or_heading_inside_path_value(preview, target):
    preview.document.write_text(f"[[{target}|原文·段落]]", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    assert link["kind"] == "native"
    preview.service.prepare(link["link_id"])
    uri = preview.service.require_current(link["link_id"])
    parsed = urlsplit(uri)
    params = parse_qs(parsed.query)
    assert parsed.scheme == "obsidian" and parsed.netloc == "open"
    assert set(params) == {"path"}
    assert params["path"][0] == str(preview.target) + "#" + target.split("#", 1)[1]


def test_relative_markdown_document_link_resolves_only_declared_target(preview):
    preview.document.write_text("[Original](Original.md#^evidence)", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    assert link["kind"] == "native"
    preview.service.prepare(link["link_id"])
    assert "evidence" in preview.service.require_current(link["link_id"])


@pytest.mark.parametrize("target", ["Original", "../outside.md", "/private/outside.md"])
def test_bare_name_escape_and_absolute_path_are_not_guessed(preview, target):
    preview.document.write_text(f"[[{target}#^block|Keep label]]", encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert result["links"][0]["kind"] == "unavailable"
    assert result["links"][0]["label"] == "Keep label" and preview.calls == []


@pytest.mark.parametrize("annotation", ["", "&annotation=BCDE3456"])
def test_cross_paper_reader_link_uses_unique_explicit_registered_asset(preview, annotation):
    other = {"id": "paper-b", "kind": "paper", "entity_ref": {
        "source_id": "source-b", "object_id": "paper:b"}, "assets": [
            {"id": "other-pdf", "uri": "zotero://open-pdf/library/items/DEFG5678", "kind": "zotero-pdf"}]}
    preview.data["works"].append(other)
    uri = "zotero://open-pdf/library/items/DEFG5678?page=7" + annotation
    preview.document.write_text(f"[Other original]({uri})", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    preview.service.prepare(link["link_id"])
    assert preview.calls[-1][1] == "paper-b"
    assert preview.service.require_current(link["link_id"]) == uri


def test_ambiguous_registered_target_preserves_label_with_diagnostic(preview):
    preview.data["works"].append({**deepcopy(preview.data["works"][0]), "id": "paper-b"})
    result = preview.service.preview("paper-a", "analysis")
    assert result["links"][0]["kind"] == "unavailable"
    assert result["links"][0]["reason_code"] == "ambiguous_target"


def test_missing_symlink_nonmarkdown_and_oversized_documents_refuse(preview, tmp_path):
    for uri in ("notes/missing.md", "../outside.md", "notes/plain.txt"):
        preview.data["works"][0]["assets"][0]["uri"] = uri
        with pytest.raises(module.PreviewUnavailable):
            preview.service.preview("paper-a", "analysis")
    outside = tmp_path / "outside.md"
    outside.write_text("Outside", encoding="utf-8")
    (preview.root / "notes/link.md").symlink_to(outside)
    preview.data["works"][0]["assets"][0]["uri"] = "notes/link.md"
    with pytest.raises(module.PreviewUnavailable):
        preview.service.preview("paper-a", "analysis")
    preview.data["works"][0]["assets"][0]["uri"] = "notes/Analysis.md"
    preview.document.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(module.PreviewUnavailable):
        preview.service.preview("paper-a", "analysis")


def test_reader_refusal_is_reported_with_safe_stable_code(preview):
    token = preview.service.preview("paper-a", "analysis")["links"][0]["link_id"]
    preview.allowed = False
    result = preview.service.prepare(token)
    assert result["native_available"] is False and result["native_reason_code"] == "zotflow_unavailable"
    with pytest.raises(module.PreviewUnavailable):
        preview.service.require_current(token)


def test_invalid_utf8_and_midread_modification_refuse(preview, monkeypatch):
    preview.document.write_bytes(b"\xff invalid UTF-8")
    with pytest.raises(module.PreviewUnavailable):
        preview.service.preview("paper-a", "analysis")
    preview.document.write_text("Readable document", encoding="utf-8")
    original = module.os.read
    changed = False

    def modifying_read(fd, count):
        nonlocal changed
        result = original(fd, count)
        if not changed:
            changed = True
            preview.document.write_text("Changed while reading", encoding="utf-8")
        return result

    monkeypatch.setattr(module.os, "read", modifying_read)
    with pytest.raises(module.PreviewUnavailable):
        preview.service.preview("paper-a", "analysis")


def test_registered_provider_path_alias_is_not_a_basename_guess(preview):
    ref = preview.data["works"][0]["entity_ref"]
    preview.data["works"][0]["assets"][1]["id"] = module._identity(
        ref["source_id"], ref["object_id"], "original-owner", prefix="paper-asset-")

    class References:
        def current_unit(self, requested):
            assert requested == ref
            return {"files": [{"object_id": "original-owner",
                               "relative_path": "Field/notes/Original.md",
                               "uri": f"obsidian://open?vault={VAULT}&file=Field%2Fnotes%2FOriginal.md"}]}

    preview.gate.references = References()
    preview.document.write_text("[[Field/notes/Original#^evidence|Original source]]", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    assert link["kind"] == "native"
    preview.service.prepare(link["link_id"])
    uri = preview.service.require_current(link["link_id"])
    assert parse_qs(urlsplit(uri).query)["path"] == [str(preview.target) + "#^evidence"]


def test_wrong_vault_cannot_match_a_same_named_declared_local_document(preview):
    preview.document.write_text(
        "[Original](obsidian://open?vault=2222222222222222&file=notes%2FOriginal.md)", encoding="utf-8")
    link = preview.service.preview("paper-a", "analysis")["links"][0]
    assert link["kind"] == "unavailable" and "link_id" not in link


@pytest.mark.parametrize("operation", ["prepare", "open"])
def test_document_changed_during_reader_check_never_returns_an_open_uri(preview, operation):
    token = preview.service.preview("paper-a", "analysis")["links"][0]["link_id"]
    if operation == "prepare":
        original = preview.gate.availability

        def changing(work, asset):
            preview.document.write_text("Changed during check", encoding="utf-8")
            return original(work, asset)

        preview.gate.availability = changing
        call = preview.service.prepare
    else:
        preview.service.prepare(token)
        original = preview.gate.require_current

        def changing(work, asset):
            preview.document.write_text("Changed during check", encoding="utf-8")
            return original(work, asset)

        preview.gate.require_current = changing
        call = preview.service.require_current
    with pytest.raises(module.PreviewUnavailable):
        call(token)


def _image(preview, *, uri="notes/figures/figure.png", identity="figure", content=PNG):
    path = preview.root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    asset = {"id": identity, "label": "Declared figure", "kind": "image", "uri": uri}
    preview.data["works"][0]["assets"].append(asset)
    return path, asset


@pytest.mark.parametrize("literal", [
    "![完整图注](figures/figure.png)",
    "![[notes/figures/figure.png|320]]",
])
def test_declared_raster_images_are_utf16_bound_session_media_not_native_actions(preview, literal):
    path, _ = _image(preview)
    body = "# 中文😀分析\n\n" + literal + "\n"
    preview.document.write_text(body, encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert result["text"] == body and result["links"] == []
    image, = result["images"]
    assert body.encode("utf-16-le")[image["start"] * 2:image["end"] * 2].decode("utf-16-le") == literal
    assert image["label"] == ("完整图注" if literal.startswith("![完整") else "notes/figures/figure.png")
    assert not set(image) & {"uri", "path", "root", "link_id"}
    assert preview.service.media(image["media_id"]) == (PNG, "image/png")
    assert preview.calls == [] and path.read_bytes() == PNG
    assert preview.document.read_text(encoding="utf-8") == body


def test_image_code_and_escaped_syntax_are_not_activated(preview):
    _image(preview)
    literal = "![Visible](figures/figure.png)"
    preview.document.write_text(
        "`" + literal + "`\n```markdown\n" + literal + "\n```\n\\" + literal + "\n" + literal,
        encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    assert len(result["images"]) == 1 and result["images"][0]["label"] == "Visible"
    assert result["links"] == []


@pytest.mark.parametrize("target", [
    "https://example.invalid/tracker.png", f"zotero://open-pdf/library/items/{PDF}",
    "../../../outside.png", "/private/outside.png", "figures/missing.png",
    "figure.png", "figures/unsafe.svg", "figures/fake.png",
])
def test_unsafe_unregistered_or_nonraster_image_remains_with_diagnostic(preview, target):
    _image(preview)
    _image(preview, uri="notes/figures/unsafe.svg", identity="svg", content=b"<svg/>")
    _image(preview, uri="notes/figures/fake.png", identity="fake", content=b"<html>Not PNG</html>")
    preview.document.write_text(f"![Keep caption]({target})", encoding="utf-8")
    result = preview.service.preview("paper-a", "analysis")
    image, = result["images"]
    assert image["label"] == "Keep caption" and image.get("reason_code")
    assert "media_id" not in image and "uri" not in image and result["links"] == []
    assert preview.calls == []


@pytest.mark.parametrize("change", ["body", "image", "declaration", "entity", "remove", "symlink"])
def test_changed_source_or_declared_image_refuses_old_media(preview, change):
    path, asset = _image(preview)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    token = preview.service.preview("paper-a", "analysis")["images"][0]["media_id"]
    if change == "body":
        preview.document.write_text("Changed document", encoding="utf-8")
    elif change == "image":
        path.write_bytes(PNG + b"changed")
    elif change == "declaration":
        asset["uri"] = "notes/other.png"
    elif change == "entity":
        preview.data["works"][0]["entity_ref"]["object_id"] = "paper:b"
    elif change == "remove":
        preview.data["works"][0]["assets"].remove(asset)
    else:
        other = preview.root / "other.png"
        other.write_bytes(PNG)
        path.unlink()
        path.symlink_to(other)
    with pytest.raises(module.PreviewUnavailable):
        preview.service.media(token)
    assert preview.calls == []


def test_media_unknown_cross_session_and_replaced_preview_tokens_refuse(preview):
    _image(preview)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    token = preview.service.preview("paper-a", "analysis")["images"][0]["media_id"]
    other = module.ExplorationPreviewService(preview.root, preview.store, preview.gate)
    for service, unknown in ((preview.service, "unknown"), (other, token)):
        with pytest.raises(module.PreviewUnavailable):
            service.media(unknown)
    preview.service.preview("paper-a", "analysis")
    with pytest.raises(module.PreviewUnavailable):
        preview.service.media(token)


def test_images_do_not_silently_borrow_another_paper_asset(preview):
    _, asset = _image(preview)
    preview.data["works"][0]["assets"].remove(asset)
    preview.data["works"].append({"id": "paper-b", "kind": "paper", "entity_ref": {
        "source_id": "source-a", "object_id": "paper:b"}, "assets": [asset]})
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image["reason_code"] == "cross_paper_image" and "media_id" not in image
    preview.data["works"][0]["assets"].append({**asset, "id": "own-figure"})
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert preview.service.media(image["media_id"]) == (PNG, "image/png")


def test_image_reads_are_bounded_and_reject_symlink_parents(preview):
    path, _ = _image(preview)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    path.write_bytes(b"x" * (16 * 1024 * 1024 + 1))
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image.get("reason_code") and "media_id" not in image
    path.unlink()
    path.parent.rmdir()
    outside = preview.root / "elsewhere"
    outside.mkdir()
    (outside / "figure.png").write_bytes(PNG)
    path.parent.symlink_to(outside, target_is_directory=True)
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image.get("reason_code") and "media_id" not in image


def test_image_fd_changes_during_read_are_refused(preview, monkeypatch):
    path, _ = _image(preview)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    original, changed = module.os.read, False
    image_ino = path.stat().st_ino

    def modifying_read(fd, count):
        nonlocal changed
        result = original(fd, count)
        if module.os.fstat(fd).st_ino == image_ino and not changed:
            changed = True
            path.write_bytes(PNG + b"modified during read")
        return result

    monkeypatch.setattr(module.os, "read", modifying_read)
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert changed and image.get("reason_code") and "media_id" not in image


def test_explicit_provider_image_alias_is_not_a_basename_guess(preview):
    path, asset = _image(preview, uri="notes/figures/figure space.png")
    ref = preview.data["works"][0]["entity_ref"]
    asset["id"] = module._identity(ref["source_id"], ref["object_id"], "figure-owner", prefix="paper-asset-")

    class References:
        def current_unit(self, requested):
            assert requested == ref
            return {"files": [{"object_id": "figure-owner", "relative_path": "Field/images/figure space.png"}]}

    preview.gate.references = References()
    preview.document.write_text("![[Field/images/figure space.png|400]]", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert preview.service.media(image["media_id"]) == (PNG, "image/png")
    preview.document.write_text("![Space](figures/figure%20space.png)", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert preview.service.media(image["media_id"]) == (path.read_bytes(), "image/png")


def test_ambiguous_declared_image_alias_refuses_instead_of_choosing_first(preview):
    _, asset = _image(preview)
    preview.data["works"][0]["assets"].append({**asset, "id": "duplicate"})
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image["reason_code"] == "ambiguous_image" and "media_id" not in image


def test_raster_pixel_limit_checked_before_decoder_allocation(preview, monkeypatch):
    huge = PNG[:16] + struct.pack(">II", 100_000, 100_000) + PNG[24:]
    _image(preview, content=huge)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    import fitz

    def no_decoder(*args, **kwargs):
        pytest.fail("oversized image reached the raster decoder")

    monkeypatch.setattr(fitz, "Pixmap", no_decoder)
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image["reason_code"] == "image_too_large" and "media_id" not in image


def test_high_dpi_cannot_hide_encoded_pixel_dimensions(preview, monkeypatch):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload)))

    # Valid metadata with huge pixels but an extremely small DPI-scaled page rectangle.
    raw = (PNG[:8] + chunk(b"IHDR", struct.pack(">II", 100_000, 100_000) + PNG[24:29])
           + chunk(b"pHYs", struct.pack(">IIB", 118_110_236, 118_110_236, 1)) + PNG[33:])
    _image(preview, content=raw)
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    import fitz

    def no_decoder(*args, **kwargs):
        pytest.fail("high-DPI oversized image reached the decoder")

    monkeypatch.setattr(fitz, "open", no_decoder)
    monkeypatch.setattr(fitz, "Pixmap", no_decoder)
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image["reason_code"] == "image_too_large" and "media_id" not in image


def test_malformed_raster_decoder_errors_are_safe_diagnostics(preview):
    _image(preview, content=PNG[:33] + b"invalid compressed image bytes")
    preview.document.write_text("![Figure](figures/figure.png)", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert image["reason_code"] == "unsupported_image" and "media_id" not in image


@pytest.mark.parametrize("suffix", ["gif", "jpg", "jpeg"])
def test_verified_supported_raster_formats(preview, suffix):
    if suffix == "gif":
        raw = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
        content_type = "image/gif"
    else:
        import fitz

        raw = fitz.Pixmap(fitz.Pixmap(PNG), 0).tobytes("jpeg")
        content_type = "image/jpeg"
    _image(preview, uri=f"notes/figures/image.{suffix}", content=raw)
    preview.document.write_text(f"![Figure](figures/image.{suffix})", encoding="utf-8")
    image, = preview.service.preview("paper-a", "analysis")["images"]
    assert preview.service.media(image["media_id"]) == (raw, content_type)


def test_constructor_does_not_read_store_or_files(tmp_path):
    class Store:
        def load(self):
            pytest.fail("construction must not read the exploration manifest")

    module.ExplorationPreviewService(tmp_path / "nonexistent", Store(), object())
    assert not (tmp_path / "nonexistent").exists()
