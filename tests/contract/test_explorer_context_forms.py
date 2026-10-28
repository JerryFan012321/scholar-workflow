"""Context-sensitive forms and notices use real synthetic Store/HTTP state."""

import json
import os
import subprocess
import threading
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", [
    "filter-defaults", "view-defaults", "ambiguous-defaults", "explicit-context",
    "query-notices",
])
def test_browser_context_forms(tmp_path, scenario):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
    from tests.contract.explorer_fixture import fixture_server as make_server

    original = b"# Accepted synthetic paper\n\nKeep this source unchanged.\n"
    (tmp_path / "paper.md").write_bytes(original)
    data = default_data()
    data["dimensions"][0]["values"] = [
        {"id": "b1", "label": "条件一"}, {"id": "b2", "label": "条件二"},
    ]
    data["dimensions"].append({
        "id": "latency", "label": "响应时间", "kind": "number", "multiple": False,
        "scope": "record", "values": [], "sortable": True, "unit": "毫秒",
    })
    data["works"] = [
        {"id": letter, "title": "工作 " + letter.upper(), "kind": "paper",
         "entity_ref": {"source_id": "synthetic-source", "object_id": "unit-" + letter},
         "year": 2020 + index, "summary": "初始说明 " + letter.upper(), "attributes": {},
         "assets": [{"id": "body", "label": "原有分析", "kind": "markdown",
                     "uri": "paper.md"}] if letter == "a" else []}
        for index, letter in enumerate(("a", "b", "c"))
    ]
    data["records"] = [
        {"id": "r" + str(index), "work_id": "b",
         "dimensions": {"foundation": ["b" + str(index)], "latency": index},
         "conditions": {"条件": "不同合成配置"}, "result": "合成结果",
         "evidence": [], "assessment": "仅测试上下文", "origin": "analysis"}
        for index in (1, 2)
    ]
    data["views"] = [{
        "id": "only-b", "title": "仅工作 B",
        "query": {"filters": {}, "text": "工作 B", "sort_by": "title",
                  "descending": False, "include_context": True},
    }]
    store = ExplorationStore(tmp_path)
    published = store.save(data, expected_revision=None)
    identities = [(work["id"], work["entity_ref"], work["assets"])
                  for work in published["data"]["works"]]
    server, token = make_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_context_forms.cjs"))],
            input=json.dumps({"url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                              "scenario": scenario}),
            text=True, capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "paper.md").read_bytes() == original
        final = store.load()["data"]
        assert [(work["id"], work["entity_ref"], work["assets"])
                for work in final["works"]] == identities
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
