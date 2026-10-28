"""Synthetic navigation through real HTTP/Store, with no native application launch."""

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("scenario", [
    "comparison-native", "comparison-native-denied", "removed-poll", "removed-reload",
    "late-assets",
])
def test_browser_navigation_state(tmp_path, monkeypatch, scenario):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.adapters import knowledge_explorer
    from scholar_workflow.adapters.exploration_readers import ReaderUnavailable
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data

    bodies = {letter: f"# Synthetic unit {letter.upper()}\n\nUnchanged source body.\n"
              for letter in ("a", "b")}
    for letter, body in bodies.items():
        (tmp_path / f"{letter}.md").write_text(body, encoding="utf-8")
    data = default_data()
    for index, letter in enumerate(("a", "b")):
        data["works"].append({
            "id": letter, "title": "合成论文 " + letter.upper(), "kind": "paper",
            "year": 2025 + index, "attributes": {},
            "entity_ref": {"source_id": "synthetic-source", "object_id": "unit-" + letter},
            "assets": [
                {"id": letter + "-body", "label": letter.upper() + " 分析正文",
                 "kind": "markdown", "uri": letter + ".md"},
                {"id": letter + "-pdf", "label": letter.upper() + " 原文 PDF",
                 "kind": "pdf", "uri": "zotero://open-pdf/library/items/"
                 + ("PDFD2345" if letter == "a" else "PDFE2345") + "?page=4"},
            ],
        })
        data["records"].append({
            "id": "record-" + letter, "work_id": letter, "dimensions": {},
            "conditions": {"数据与预算": "相同合成条件"}, "result": "合成结果 " + letter,
            "assessment": "仅验证导航，不是科研结论。", "origin": "analysis",
            "evidence": [letter + "-pdf"],
        })
    data["edges"] = [{
        "id": "edge-a-b", "from_id": "a", "to_id": "b", "kind": "extends",
        "label": "合成关系", "explanation": "只检查导航保持。", "evidence": ["a-body"],
    }]
    store = ExplorationStore(tmp_path)
    before = store.save(data, expected_revision=None)
    events, prepared = [], set()

    class ReaderGate:
        @staticmethod
        def handles(uri):
            return uri.startswith("zotero://open-pdf/")

        def availability(self, work, asset):
            expected = next(row for row in data["works"] if row["id"] == work["id"])
            declared = next(row for row in expected["assets"] if row["id"] == asset["id"])
            assert all(asset[key] == value for key, value in declared.items())
            events.append(("prepare", work["id"], asset["id"]))
            if scenario == "comparison-native-denied" and work["id"] == "a":
                return {"native_available": False, "native_reason_code": "unit_unavailable",
                        "native_reason": "Synthetic reader verification refused."}
            prepared.add((work["id"], asset["id"]))
            return {"native_available": True}

        def require_current(self, work, asset):
            events.append(("require", work["id"], asset["id"]))
            if (work["id"], asset["id"]) not in prepared:
                raise ReaderUnavailable("Refresh the current unit assets first.",
                                        code="refresh_required")

    def native_open(arguments, **kwargs):
        assert kwargs["shell"] is False
        assert arguments[-1] == data["works"][0]["assets"][1]["uri"]
        events.append(("open", "a", "a-pdf"))
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(knowledge_explorer, "subprocess", SimpleNamespace(
        Popen=native_open, DEVNULL=subprocess.DEVNULL,
    ))
    monkeypatch.setattr(knowledge_explorer, "shutil", SimpleNamespace(
        which=lambda _name: "/synthetic/native-opener", copyfileobj=shutil.copyfileobj,
    ))
    server, token = knowledge_explorer.make_server(tmp_path, reader_gate=ReaderGate())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_navigation_state.cjs"))],
            input=json.dumps({
                "url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                "scenario": scenario,
            }),
            text=True, capture_output=True, timeout=60, check=False,
        )
        failure = (result.stdout + result.stderr + repr(events)).replace(
            token, "<synthetic-session-token>")
        assert result.returncode == 0, failure
        if scenario == "comparison-native":
            assert events == [("prepare", "a", "a-pdf"), ("require", "a", "a-pdf"),
                              ("open", "a", "a-pdf")]
        elif scenario == "comparison-native-denied":
            assert events == [("prepare", "a", "a-pdf")]
        else:
            assert not any(event[0] == "open" for event in events)
        current = store.load()
        if scenario.startswith("removed-"):
            assert [work["id"] for work in current["data"]["works"]] == ["b"]
            assert [record["id"] for record in current["data"]["records"]] == ["record-b"]
            assert current["data"]["edges"] == []
        else:
            assert current == before
        for letter, body in bodies.items():
            assert (tmp_path / f"{letter}.md").read_text(encoding="utf-8") == body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
