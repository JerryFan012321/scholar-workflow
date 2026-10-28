"""Independent browser clients exercise real CAS state in synthetic knowledge roots."""

import json
import os
import subprocess
import threading
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", [
    "open-form", "save-pending", "stale-poll-and-dirty", "load-form", "stale-query",
    "reload-draft",
])
def test_browser_edit_conflicts(tmp_path, scenario):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
    from tests.contract.explorer_fixture import fixture_server as make_server

    original = b"# Accepted paper\n\nDo not change the paper unit.\n"
    (tmp_path / "paper.md").write_bytes(original)
    data = default_data()
    data["works"] = [
        {"id": "paper", "title": "合成论文原件", "kind": "paper", "attributes": {},
         "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper"},
         "assets": [{"id": "paper-body", "label": "原有分析", "kind": "markdown",
                     "uri": "paper.md"}]},
        {"id": "editable", "title": "合成网页工作", "kind": "webpage", "year": 2025,
         "summary": "初始说明", "attributes": {}, "assets": []},
    ]
    if scenario == "stale-query":
        data["dimensions"][0]["values"] = [
            {"id": "b1", "label": "条件A"}, {"id": "b2", "label": "条件B"},
        ]
        data["dimensions"].append({
            "id": "latency", "label": "响应时间", "kind": "number", "multiple": False,
            "scope": "record", "values": [], "sortable": True, "unit": "毫秒",
        })
        data["records"] = [
            {"id": "r" + str(index), "work_id": "editable",
             "dimensions": {"foundation": ["b" + str(index)], "latency": index},
             "conditions": {"条件": "不同合成配置"}, "result": "合成结果",
             "evidence": [], "assessment": "仅测试排序口径", "origin": "analysis"}
            for index in (1, 2)
        ]
    store = ExplorationStore(tmp_path)
    published = store.save(data, expected_revision=None)
    paper_before = next(work for work in published["data"]["works"] if work["id"] == "paper")
    server, token = make_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_edit_conflicts.cjs"))],
            input=json.dumps({"url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                              "scenario": scenario}),
            text=True, capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "paper.md").read_bytes() == original
        paper = next(work for work in store.load()["data"]["works"] if work["id"] == "paper")
        assert paper == paper_before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
