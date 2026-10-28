"""Optional browser interaction check against disposable source-development fixtures."""
import json
import os
import subprocess
import threading
from copy import deepcopy
from pathlib import Path

import pytest


def test_browser_file_roundtrip(tmp_path):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome smoke test")
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
    from tests.contract.explorer_fixture import fixture_server as make_server

    original = b"# Accepted analysis\n\nOriginal paper content.\n"
    (tmp_path / "paper.md").write_bytes(original)
    data = default_data()
    for dimension in data["dimensions"]:
        if dimension["id"] in {"foundation", "task"}:
            prefix = "b" if dimension["id"] == "foundation" else "t"
            dimension["values"] = [{"id": prefix + str(i), "label": prefix.upper() + str(i)}
                                   for i in (1, 2)]
    data["works"] = [{"id": "a", "title": "示例工作 A", "kind": "paper", "year": 2025,
                      "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper-a"},
                      "attributes": {}, "assets": [{"id": "body", "label": "原有分析",
                                                      "kind": "markdown", "uri": "paper.md"}]},
                     {"id": "b", "title": "示例工作 B", "kind": "webpage", "year": 2026,
                      "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-document-b"},
                      "attributes": {}, "assets": []},
                     {"id": "c", "title": "示例工作 C", "kind": "paper", "year": 2026,
                      "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper-c"},
                      "attributes": {}, "assets": []}]
    data["records"] = [{"id": "r" + str(i), "work_id": "a",
                        "dimensions": {"foundation": ["b" + str(i)], "task": ["t" + str(i)]},
                        "conditions": {"数据": "相同数据", "预算": "相同预算"},
                        "result": "合成结果，仅验证呈现", "assessment": "待评价",
                        "evidence": ["body"], "origin": "local"} for i in (1, 2)]
    data["edges"] = [{"id": "e", "from_id": "a", "to_id": "b", "kind": "extends",
                      "label": "合成继承关系", "explanation": "测试图形，不是科研结论",
                      "evidence": ["body"]},
                     {"id": "e2", "from_id": "a", "to_id": "c", "kind": "borrows",
                      "label": "合成借用关系", "explanation": "另一条测试分支，不是科研结论",
                      "evidence": ["body"]}]
    unit_ref = {"source_id": "fixture-source", "object_id": "unit-d"}
    unit_work = {
        "id": "unit-d", "title": "完整论文单元 D", "kind": "paper",
        "entity_ref": unit_ref, "year": 2026, "attributes": {},
        "assets": [
            {"id": "unit-d-body", "label": "论文分析", "kind": "markdown",
             "uri": "https://example.test/unit-d-analysis"},
            {"id": "unit-d-canvas", "label": "解析树", "kind": "canvas",
             "uri": "https://example.test/unit-d-canvas"},
        ],
    }
    reference_calls = []

    class References:
        """Supply one complete synthetic unit through the real HTTP boundary."""

        def fields(self):
            return {"fields": [{"source_id": unit_ref["source_id"],
                                 "field_id": "fixture-field", "title": "合成领域",
                                 "source_title": "合成来源"}], "diagnostics": []}

        def units(self, source_id, field_id):
            assert source_id == unit_ref["source_id"] and field_id == "fixture-field"
            return {"units": [{"entity_ref": deepcopy(unit_ref),
                               "title": unit_work["title"], "asset_count": 2,
                               "diagnostics": ["分析正文与Canvas均保留原件。"]}],
                    "diagnostics": []}

        def reference(self, root_arg, candidate, source_id, field_id, unit_refs):
            assert root_arg == tmp_path
            assert source_id == unit_ref["source_id"] and field_id == "fixture-field"
            assert unit_refs == [unit_ref]
            reference_calls.append(deepcopy(unit_refs))
            proposed = deepcopy(candidate)
            if not any(work.get("entity_ref") == unit_ref for work in proposed["works"]):
                proposed["works"].append(deepcopy(unit_work))
            return proposed

    store = ExplorationStore(tmp_path)
    store.save(data, expected_revision=None)
    server, token = make_server(tmp_path, reference_service=References())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_browser.cjs"))],
            input=json.dumps({"url": f"http://127.0.0.1:{server.server_port}/#token={token}"}),
            text=True, capture_output=True, timeout=75, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        saved = store.load()["data"]
        assert len(saved["dimensions"]) == 6
        modality = next(item for item in saved["dimensions"] if item["label"] == "输入模态")
        chosen = saved["records"][0]["dimensions"][modality["id"]]
        assert [item["label"] for item in modality["values"] if item["id"] in chosen] == ["视频"]
        latency = next(item for item in saved["dimensions"] if item["label"] == "响应时间")
        assert saved["records"][0]["dimensions"][latency["id"]] == 0.81
        assert saved["records"][0]["assessment"] == "只在相同数据和预算下支持当前比较。"
        assert reference_calls == [[unit_ref], [unit_ref]]
        referenced = [work for work in saved["works"] if work.get("entity_ref") == unit_ref]
        assert len(referenced) == 1 and referenced[0]["assets"] == unit_work["assets"]
        assert (tmp_path / "paper.md").read_bytes() == original
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
