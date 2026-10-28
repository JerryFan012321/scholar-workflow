"""Readability contracts use real renderer output and declared synthetic raster assets."""

import hashlib
import json
import os
import struct
import subprocess
import threading
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.contract.explorer_fixture import fixture_server


def _comparison_png():
    width, height = 320, 120
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            color = ((40, 105, 180) if 25 <= x < 135 and 25 <= y < 100 else
                     (45, 145, 100) if 185 <= x < 295 and 50 <= y < 100 else
                     (250, 251, 248))
            row.extend(color)
        rows.append(bytes(row))

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def test_browser_readable_analysis_preview(tmp_path, monkeypatch):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.adapters import knowledge_explorer
    from scholar_workflow.analysis.models import (
        AnalysisReader,
        Evidence,
        EvidenceKind,
        ZoteroPdfSpan,
    )
    from scholar_workflow.analysis.reference_rendering import reference_source_quote_lines
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data

    author_quote = (
        "Under the same synthetic conditions, the variant reduces error relative to the baseline. "
        "The retained context states that this result does not establish general performance."
    )
    author_emphasis = "the variant reduces error relative to the baseline"
    inference_quote = (
        "These synthetic measurements use only one budget and one data split. "
        "They support a limited interpretation rather than a universal advantage."
    )
    inference_emphasis = "only one budget and one data split"
    reader = AnalysisReader(kind="zotflow_library", vault_id="1111111111111111")

    def quote_lines(kind, quote, emphasis, page_index):
        span = ZoteroPdfSpan(
            library_type="personal", library_id="1", attachment_key="PDFD2345",
            content_hash="sha256:" + "a" * 64, page_index=page_index, quote=quote,
            quote_emphasis=[emphasis],
        )
        evidence = Evidence(
            kind=kind, anchor="Synthetic source page" if kind == EvidenceKind.AUTHOR_STATED else None,
            detail="Interpretation remains conditional" if kind == EvidenceKind.ANALYSIS_INFERENCE else None,
            source_spans=[span],
        )
        return "\n".join(reference_source_quote_lines(evidence, "zh", reader=reader, folded=True))

    paragraph_1 = "这是一份用于界面验收的合成分析。正文先说明比较对象和共同条件，再给出能够独立阅读的结果解释，不把技术名称当作解释。"
    paragraph_2 = "本例只改变一个合成模块。图表和数字只服务于展示测试，不代表真实研究结论；下方分别保留作者陈述与分析推断的完整上下文。"
    caption = "图 1 · 合成对比：蓝色表示 baseline，绿色表示 variant；仅用于展示。"
    after_image = "图后说明：该图片仅说明排版和相对资源导航，不证明任何科学优势。"
    text = (
        "---\nsw_schema: 2\nsw_catalog_id: fixture-analysis\nsw_kind: paper-analysis\n---\n\n"
        "# 合成论文分析\n\n" + paragraph_1 + " ^claim-task-core\n\n" + paragraph_2 + "\n"
        + quote_lines(EvidenceKind.AUTHOR_STATED, author_quote, author_emphasis, 3) + "\n"
        + quote_lines(EvidenceKind.ANALYSIS_INFERENCE, inference_quote, inference_emphasis, 4) + "\n\n"
        "- **共同条件**：相同的合成输入和预算。\n- **变化项**：仅替换合成模块。\n\n"
        "## 条件与结果\n\n| 配置 | 共同条件 | 差别 | 合成结果 |\n| --- | --- | --- | --- |\n"
        "| baseline | 同一合成输入、相同预算 | 原模块 | 42 |\n"
        "| variant | 同一合成输入、相同预算 | 新模块 | 36 |\n\n"
        "## 图像证据\n\n图前说明：图中两个色块对应上述两组配置。\n\n"
        "![合成对比图](figures/result.png)\n\n*" + caption + "*\n\n" + after_image + "\n\n"
        "![未知图片](figures/missing.png)\n\n![远程图片](https://example.test/must-not-load.png)\n\n"
        "![SVG图片](figures/unsafe.svg)\n\n"
        "```md\n[代码内伪原文](obsidian://zotflow?vault=1111111111111111&type=open-attachment&libraryID=1&key=PDFD2345)\n"
        "^claim-literal\n<script>window.__previewXss = 99</script>\n```\n\n"
        '<img src="https://example.test/html-image.png" onerror="window.__previewXss = 1">'
        '<script>window.__previewXss = 2</script>\n'
    )
    png = _comparison_png()
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg"><script>window.__previewXss=3</script>'
           b'<image href="https://example.test/svg-image.png"/></svg>')
    code = (
        "---\nkind: literal-code\n---\n# Not a Markdown heading\n**not emphasis**\n^literal-anchor\n"
        "![not an image](figures/result.png)\n"
        "[not a reader](obsidian://zotflow?vault=1111111111111111&type=open-attachment&libraryID=1&key=PDFD2345)\n"
    )
    (tmp_path / "figures").mkdir()
    originals = {"paper.md": text.encode(), "figures/result.png": png,
                 "figures/unsafe.svg": svg, "code.py": code.encode()}
    for relative, content in originals.items():
        (tmp_path / relative).write_bytes(content)
    data = default_data()
    data["works"] = [{
        "id": "paper", "title": "合成可读论文单元", "kind": "paper", "attributes": {},
        "entity_ref": {"source_id": "fixture-source", "object_id": "paper:zotero:1:PARN2345"},
        "assets": [
            {"id": "body", "label": "分析正文", "kind": "markdown", "uri": "paper.md"},
            {"id": "figure", "label": "合成对比图", "kind": "image", "uri": "figures/result.png"},
            {"id": "unsafe-image", "label": "SVG图片", "kind": "image", "uri": "figures/unsafe.svg"},
            {"id": "code", "label": "代码原文", "kind": "code", "uri": "code.py"},
        ],
    }]
    store = ExplorationStore(tmp_path)
    before = store.save(data, expected_revision=None)
    manifest_before = store.path.read_bytes()
    opened = []

    class ReaderGate:
        @staticmethod
        def handles(uri):
            return uri.startswith(("obsidian://zotflow", "zotero://open-pdf"))

        def availability(self, _work, _asset):
            return {"native_available": True}

        def require_current(self, _work, _asset):
            raise AssertionError("The readability test must not open a native reader")

    def native_open(arguments, **_kwargs):
        opened.append(arguments)
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(knowledge_explorer, "subprocess", SimpleNamespace(
        Popen=native_open, DEVNULL=subprocess.DEVNULL,
    ))
    server, token = fixture_server(tmp_path, reader_gate=ReaderGate())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_readable_preview.cjs"))],
            input=json.dumps({
                "url": f"http://127.0.0.1:{server.server_port}/#token={token}", "text": text,
                "document_revision": "sha256:" + hashlib.sha256(originals["paper.md"]).hexdigest(),
                "png_hash": hashlib.sha256(png).hexdigest(), "author_quote": author_quote,
                "author_emphasis": author_emphasis, "inference_quote": inference_quote,
                "inference_emphasis": inference_emphasis, "paragraph_1": paragraph_1,
                "paragraph_2": paragraph_2, "caption": caption, "after_image": after_image,
                "code": code,
            }), text=True, capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert opened == []
        assert store.load() == before and store.path.read_bytes() == manifest_before
        assert all((tmp_path / relative).read_bytes() == content for relative, content in originals.items())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
