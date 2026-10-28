"""Run the current explorer with synthetic units, never personal registrations.

This development-only module is excluded from the installed runtime. The selected
directory must already exist and be empty. Only its disposable synthetic content
is created; the explorer then edits its usual outer manifest. Native launches are
denied even when requested directly through HTTP.
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from copy import deepcopy
from pathlib import Path

from scholar_workflow.adapters.exploration_readers import ReaderUnavailable
from scholar_workflow.adapters.knowledge_explorer import ExplorerHandler, make_server
from scholar_workflow.knowledge.exploration import ExplorationError, ExplorationStore, default_data
from scholar_workflow.knowledge.exploration_import import import_paper_units

SOURCE = "synthetic-demo-source"
FIELD = "synthetic-demo-field"
NOTICE = "合成开发演示：不含真实研究结论；未登记正式知识库；原生应用与真实文库操作禁用。"


class NoNativeReader:
    """Refuse every native action without probing any external tool."""

    @staticmethod
    def handles(_uri):
        return True

    @staticmethod
    def availability(_work, _asset):
        return {"native_available": False, "native_reason": NOTICE,
                "native_reason_code": "reader_unverified"}

    @staticmethod
    def require_current(_work, _asset):
        raise ReaderUnavailable(NOTICE)


class DemoHandler(ExplorerHandler):
    """Label only this developer presentation; retain all production guards."""

    def _bytes(self, status, body, kind="application/json; charset=utf-8"):
        if status == 200 and kind.startswith("text/html"):
            body = body.replace(b"<span>Scholar</span>",
                                "<span>Scholar · 合成演示</span>".encode(), 1)
            body = body.replace("<title>Scholar · 知识探索</title>".encode(),
                                "<title>合成开发演示 · Scholar</title>".encode(), 1)
        return super()._bytes(status, body, kind)


class SyntheticReferences:
    """Explicit fixture provider; not a host registry or a Zotero adapter."""

    def __init__(self, root, units):
        self.root = Path(root)
        self.inventory = deepcopy(units)

    @staticmethod
    def _selection(source_id, field_id):
        if (source_id, field_id) != (SOURCE, FIELD):
            raise ExplorationError("Unknown synthetic Field")

    def fields(self):
        return {"fields": [{"source_id": SOURCE, "field_id": FIELD,
                            "title": "合成领域 · 不是正式登记", "source_title": "开发演示"}],
                "diagnostics": [NOTICE]}

    def units(self, source_id, field_id):
        self._selection(source_id, field_id)
        return {"units": [{"entity_ref": {"source_id": SOURCE, "object_id": unit["resource_id"]},
                           "title": unit["title"], "asset_count": len(unit["files"]),
                           "diagnostics": [NOTICE]} for unit in self.inventory],
                "diagnostics": [NOTICE]}

    def current_unit(self, ref):
        if not isinstance(ref, dict) or set(ref) != {"source_id", "object_id"}:
            raise ExplorationError("Qualified synthetic unit required")
        for unit in self.inventory:
            if ref == {"source_id": SOURCE, "object_id": unit["resource_id"]}:
                return deepcopy(unit)
        raise ExplorationError("Unknown synthetic unit")

    def reference(self, root, data, source_id, field_id, unit_refs):
        self._selection(source_id, field_id)
        if Path(root).resolve() != self.root or not isinstance(unit_refs, list) or not unit_refs:
            raise ExplorationError("Select whole synthetic units in the demo root")
        selected = [self.current_unit(ref) for ref in unit_refs]
        payload = {"schema_version": 1, "source_id": SOURCE, "field_id": FIELD,
                   "paper_units": selected, "unresolved_references": []}
        return import_paper_units(root, data, payload, source_roots={SOURCE: self.root})


def _figure():
    """Encode a small fixture raster, not an extracted scientific result."""
    width, height = 640, 220
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            color = ((51, 98, 151) if 70 <= x < 270 and 45 <= y < 180 else
                     (59, 139, 116) if 370 <= x < 570 and 75 <= y < 180 else (248, 250, 247))
            row.extend(color)
        rows.append(bytes(row))

    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def _body(title):
    return (
        f"# {title} · 阅读片段\n\n{NOTICE}\n\n"
        "## 这项工作解决什么问题\n\n"
        "本片段演示如何在同一论文单元里阅读解释、条件、结果、证据和图片。"
        "这里不是一份真实论文分析，下面的名称、数据和原文都由测试构造；"
        "它们不能用于判断任何真实模型的优劣。完整论文仍执行已有正文与五分支 Canvas 规范。\n\n"
        "## 方法与比较条件\n\n"
        "合成 baseline 先将输入压缩为表示，再由预测模块产生输出；variant 只替换预测模块。"
        "两者使用相同合成输入、相同划分和相同预算。误差以同一合成输出为参照计算，"
        "数值越低仅表示本例误差较小；不能由此推出其他任务、预算或数据上的优势。 ^demo-method\n\n"
        "> [!quote]- 合成原文上下文 · 仅演示折叠与直接证据\n"
        "> Under the same synthetic input and budget, **the variant reduces the example error** "
        "from 42 to 36. This fixture does not establish performance on real data or other tasks.\n\n"
        "| 比较项 | 共同条件 | 唯一差别 | 合成结果与解释 |\n"
        "| --- | --- | --- | --- |\n"
        "| baseline | 同一合成输入、划分、预算 | 原预测模块 | 误差 42，仅为展示数值 |\n"
        "| variant | 同一合成输入、划分、预算 | 新预测模块 | 误差 36，仅支持本例比较 |\n\n"
        "## 图像与边界\n\n![合成条件对比图](figure.png)\n\n"
        "*图 1 · 蓝色为 baseline、绿色为 variant；示意图与数值均不是真实实验。*\n\n"
        "不能把本单元另一条不同基座、不同任务的记录拼接进这次比较。"
        "正文、图片和配置是当前单元的资产，不是三个新的论文节点。\n"
    )


def prepare_demo(root):
    """Populate an explicit empty, nonsymlink directory; never adopt old data."""
    root = Path(root).absolute()
    if (root.is_symlink() or not root.is_dir()
            or any(parent.is_symlink() for parent in root.parents) or any(root.iterdir())):
        raise ValueError("Demo root must be an existing empty directory without symlink components")
    root = root.resolve(strict=True)
    units = []
    for key, name in (("a", "合成论文 A · 基础路线"), ("b", "合成论文 B · 模块改进"),
                      ("c", "合成论文 C · 分支路线"), ("d", "合成论文 D · 待引用单元")):
        directory = root / "resources" / key
        directory.mkdir(parents=True)
        (directory / "Paper.md").write_text(
            f"# {name}\n\n{NOTICE}\n\n这是一个完整合成单元的资料入口，不是独立于分析的第二篇论文。\n",
            encoding="utf-8")
        (directory / "Analysis.md").write_text(_body(name), encoding="utf-8")
        (directory / "figure.png").write_bytes(_figure())
        (directory / "config.yml").write_text(
            "fixture_only: true\nshared_input: synthetic-input\nbudget: synthetic-budget\n"
            "baseline: original-predictor\nvariant: replacement-predictor\n", encoding="utf-8")
        # This is a declared unavailable asset, not a fabricated editable analysis.
        files = [{"object_id": f"demo:{key}:{role}", "kind": kind, "title": label,
                  "relative_path": f"resources/{key}/{filename}", "file_state": state,
                  "open_state": "ready" if state == "available" else "missing"}
                 for role, filename, kind, label, state in (
                     ("note", "Paper.md", "markdown", "资料笔记（合成）", "available"),
                     ("analysis", "Analysis.md", "markdown", "分析阅读片段（合成）", "available"),
                     ("figure", "figure.png", "image", "条件对比示意图（合成）", "available"),
                     ("config", "config.yml", "config", "比较配置（合成）", "available"),
                     ("canvas", "Analysis.canvas", "canvas", "解析树（本演示未生成）", "missing"))]
        units.append({"source_id": SOURCE, "resource_id": f"synthetic-paper:{key}", "title": name,
                      "ownership": {"status": "resolved"}, "files": files,
                      "resource_links": [], "resource_notes": [NOTICE]})
    references = SyntheticReferences(root, units)
    selected = [{"source_id": SOURCE, "object_id": unit["resource_id"]} for unit in units[:3]]
    data = references.reference(root, default_data(), SOURCE, FIELD, selected)
    labels = {
        "foundation": [("base-a", "合成基座 A"), ("base-b", "合成基座 B")],
        "paradigm": [("latent", "表示预测"), ("diffusion", "像素生成")],
        "problem": [("long-horizon", "长时预测"), ("control", "控制条件")],
        "task": [("prediction", "预测任务"), ("control", "控制任务")],
    }
    for dimension in data["dimensions"]:
        dimension["values"] = [{"id": key, "label": label} for key, label in labels[dimension["id"]]]
    by_key = {}
    for work, key in zip(data["works"], "abc", strict=True):
        work["year"] = {"a": 2023, "b": 2024, "c": 2025}[key]
        work["summary"] = NOTICE + " 同一单元保留全部已声明资产，多条记录不增加论文节点。"
        by_key[key] = work

    def record(key, suffix, base, task, value, origin):
        work = by_key[key]
        analysis = next(asset["id"] for asset in work["assets"] if "Analysis.md" in asset["uri"])
        return {"id": f"demo-record-{key}-{suffix}", "work_id": work["id"],
                "dimensions": {"foundation": [base], "paradigm": ["latent"],
                               "problem": ["long-horizon" if task == "prediction" else "control"],
                               "task": [task]},
                "conditions": {"共同输入": "同一合成输入与划分", "共同预算": "相同合成预算",
                               "变化项": "原预测模块" if key == "a" else "替换预测模块",
                               "真实性": "合成示例，不是实验结果"},
                "result": f"合成误差 {value}；只在本条条件下解释。", "evidence": [analysis],
                "assessment": "仅演示条件与结果并列；未证明真实科研结论。", "origin": origin}

    data["records"] = [record("a", "prediction", "base-a", "prediction", 42, "author"),
                       record("a", "control", "base-b", "control", 30, "local"),
                       record("b", "prediction", "base-a", "prediction", 36, "author"),
                       record("c", "prediction", "base-a", "prediction", 39, "analysis")]
    for key in "bc":
        data["edges"].append({"id": f"demo-edge-a-{key}", "from_id": by_key["a"]["id"],
                              "to_id": by_key[key]["id"], "kind": "extends",
                              "label": "合成改进关系" if key == "b" else "合成分支关系",
                              "evidence": [data["records"][2 if key == "b" else 3]["evidence"][0]],
                              "explanation": "仅演示有证据入口的分支，不代表真实文献继承。"})
    data["views"] = [{"id": "demo-prediction", "title": "相同基座与预测任务（合成）",
                      "query": {"filters": {"foundation": {"mode": "any", "values": ["base-a"]},
                                            "task": {"mode": "any", "values": ["prediction"]}},
                                "sort_by": "year", "descending": False, "include_context": True}}]
    ExplorationStore(root).save(data, expected_revision=None)
    return references


class SyntheticVaults:
    """This inert fixture never discovers or connects personal folders."""

    @staticmethod
    def list_connections():
        return {"connections": [], "diagnostics": ["合成演示不连接真实知识库。"]}

    @staticmethod
    def _denied(*args):
        raise ExplorationError("Synthetic demo cannot connect or read external folders", 7)

    choose = preview_adjustments = connect = documents = preview_document = _denied


def demo_server(root):
    references = prepare_demo(root)
    server, token = make_server(root, reference_service=references, reader_gate=NoNativeReader(),
                               vault_service=SyntheticVaults())
    server.RequestHandlerClass = DemoHandler
    return server, token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Existing empty disposable directory")
    args = parser.parse_args()
    server, token = demo_server(args.root)
    # This URL is a local session credential. Never store it in a published artifact.
    print(json.dumps({"mode": "synthetic-source-demo", "url": f"http://127.0.0.1:{server.server_port}/",
                      "session_fragment": f"token={token}"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
