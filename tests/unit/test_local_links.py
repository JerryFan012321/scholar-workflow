"""Unit tests for the loopback PDF link service (GOALS INV17)."""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import replace
from hashlib import sha256

import pytest

from scholar_workflow.adapters.local_links import start_link_server
from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator, ZoteroLocalError


@pytest.fixture()
def server(tmp_path):
    (tmp_path / "S6LZUS6S").mkdir()
    (tmp_path / "S6LZUS6S" / "paper.pdf").write_bytes(b"%PDF-1.7\nhello")
    (tmp_path / "EMPTYKEY0").mkdir()  # folder exists, no pdf
    srv = start_link_server(port=0, storage_root=tmp_path)
    calls = []

    class LocalZotero:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def resolve_attachment_locator(self, key):
            calls.append(key)
            if key != "S6LZUS6S":
                raise ZoteroLocalError("Synthetic attachment is unavailable")
            pdf = tmp_path / "S6LZUS6S" / "paper.pdf"
            return ZoteroAttachmentLocator(
                attachment_key=key, library_id="1", path=pdf, filename=pdf.name,
                content_hash="sha256:" + sha256(pdf.read_bytes()).hexdigest(),
            )

    srv.runtime = replace(srv.runtime, zotero_adapter_factory=LocalZotero)
    srv.test_locator_calls = calls
    yield srv, srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _get(port, path):
    return urllib.request.urlopen(f"http://127.0.0.1:{port}{path}")


def test_serves_pdf_inline(server):
    srv, port = server
    r = _get(port, "/open/paper/S6LZUS6S")
    body = r.read()
    assert r.status == 200
    assert r.headers.get("Content-Type") == "application/pdf"
    assert int(r.headers.get("Content-Length")) == len(body)
    assert body.startswith(b"%PDF-")
    assert srv.test_locator_calls == ["S6LZUS6S"]


def test_404_when_folder_has_no_pdf(server):
    _srv, port = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(port, "/open/paper/EMPTYKEY0")
    assert e.value.code == 404


def test_404_unknown_key(server):
    _srv, port = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(port, "/open/paper/NOSUCHKEY")
    assert e.value.code == 404


def test_400_malformed_path(server):
    _srv, port = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(port, "/open/paper")  # only two segments
    assert e.value.code == 400


@pytest.mark.parametrize("bad", ["abc123", "AB.CD", "AB%2F..%2Fetc"])
def test_400_invalid_key_blocks_traversal(server, bad):
    """Lowercase, dots, or encoded slashes must be rejected before touching FS."""
    _srv, port = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(port, f"/open/paper/{bad}")
    assert e.value.code == 400
