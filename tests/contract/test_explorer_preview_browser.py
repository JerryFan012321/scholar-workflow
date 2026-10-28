"""Real preview/link HTTP with synthetic external reader and native opener boundaries."""

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest


def test_browser_preview_source_links(tmp_path, monkeypatch):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.adapters import knowledge_explorer
    from scholar_workflow.analysis.models import AnalysisReader, ZoteroPdfSpan
    from scholar_workflow.analysis.reference_rendering import reference_source_link
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data

    span = ZoteroPdfSpan(library_type="personal", library_id="1", attachment_key="PDFD2345",
                         content_hash="sha256:" + "a" * 64, page_index=3)
    reader = AnalysisReader(kind="zotflow_library", vault_id="1111111111111111")
    source_link = reference_source_link(span, "zh", reader=reader)
    label, uri = source_link[1:].split("](", 1)
    uri = uri[:-1]
    text = (
        "# 合成分析\n\n中文 🧪 证据位于前文，😀 " + source_link + "，这里继续解释。\n\n"
        "[研究官网](https://example.test/research)\n\n"
        "`[行内代码伪链接](" + uri + ")`\n\n"
        "```md\n[代码块伪链接](" + uri + ")\n```\n\n"
        "![图片伪链接](" + uri + ")\n\n"
        "[不允许的动作](obsidian://advanced-uri?vault=1111111111111111&commandid=delete)\n"
    )
    original = text.encode("utf-8")
    (tmp_path / "paper.md").write_bytes(original)
    data = default_data()
    data["works"] = [{
        "id": "paper", "title": "合成论文单元", "kind": "paper", "attributes": {},
        "entity_ref": {"source_id": "fixture-source", "object_id": "paper:zotero:1:PARN2345"},
        "assets": [{"id": "body", "label": "论文分析正文", "kind": "markdown", "uri": "paper.md"}],
    }]
    store = ExplorationStore(tmp_path)
    before = store.save(data, expected_revision=None)
    events = []

    class ReaderGate:
        @staticmethod
        def handles(value):
            return value.startswith(("obsidian://zotflow", "zotero://open-pdf"))

        def availability(self, work, asset):
            assert work["entity_ref"] == data["works"][0]["entity_ref"]
            assert asset["uri"] == uri
            events.append(("prepare", asset["uri"]))
            return {"native_available": True}

        def require_current(self, work, asset):
            assert work["entity_ref"] == data["works"][0]["entity_ref"]
            assert asset["uri"] == uri
            events.append(("require-current", asset["uri"]))

    def native_open(arguments, **kwargs):
        assert kwargs["shell"] is False
        assert arguments[-1] == uri
        events.append(("open", arguments[-1]))
        return SimpleNamespace(pid=1)

    # Replace only the adapter's external process handle, not subprocess.run used by this test.
    monkeypatch.setattr(knowledge_explorer, "subprocess", SimpleNamespace(
        Popen=native_open, DEVNULL=subprocess.DEVNULL,
    ))
    server, token = knowledge_explorer.make_server(tmp_path, reader_gate=ReaderGate())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_preview_browser.cjs"))],
            input=json.dumps({
                "url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                "text": text, "document_revision": "sha256:" + hashlib.sha256(original).hexdigest(),
                "source_link": source_link, "source_label": label, "expected_uri": uri,
            }),
            text=True, capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert events == [("prepare", uri), ("require-current", uri), ("open", uri)]
        parameters = parse_qs(urlsplit(events[-1][1]).query)
        assert json.loads(parameters["navigation"][0]) == {"pageIndex": 3}
        assert "page" not in parameters
        assert (tmp_path / "paper.md").read_bytes() == original
        assert store.load() == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
