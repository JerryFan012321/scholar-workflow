"""Exercise the disposable source demo through the real browser and HTTP store."""

import hashlib
import importlib.util
import json
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_synthetic_demo_browser(tmp_path, monkeypatch):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    repository = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "synthetic_explorer_demo", repository / "dev-guide/demos/knowledge_explorer.py",
    )
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)

    from scholar_workflow.adapters import knowledge_explorer
    from scholar_workflow.knowledge.exploration import ExplorationStore

    launches = []

    def forbidden_launch(*args, **kwargs):
        launches.append((args, kwargs))
        raise AssertionError("The synthetic demo must never launch a native application")

    monkeypatch.setattr(knowledge_explorer, "subprocess", SimpleNamespace(
        Popen=forbidden_launch, DEVNULL=subprocess.DEVNULL,
    ))
    root = tmp_path.resolve()
    server, token = demo.demo_server(root)
    server.daemon_threads = False
    before = {
        path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (root / "resources").rglob("*") if path.is_file()
    }
    initial = ExplorationStore(root).load()["data"]
    assert (len(initial["works"]), len(initial["records"]), len(initial["edges"])) == (3, 4, 2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        screenshots = Path(os.environ.get("SCHOLAR_EXPLORER_SCREENSHOT_DIR", root / "screenshots"))
        screenshots.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_demo_browser.cjs"))],
            input=json.dumps({
                "url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                "screenshot_prefix": str(screenshots / "knowledge-explorer-demo"),
            }),
            text=True, capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, (result.stdout + result.stderr).replace(
            token, "<synthetic-session-token>")
        current = ExplorationStore(root).load()["data"]
        assert len(current["works"]) == 4
        assert len(current["records"]) == 4
        assert len(current["edges"]) == 2
        assert len(current["dimensions"]) == 5
        assert current["works"][:3] == initial["works"]
        assert current["records"] == initial["records"]
        assert current["edges"] == initial["edges"]
        assert len(current["works"][-1]["assets"]) == 5
        assert len({(work["entity_ref"]["source_id"], work["entity_ref"]["object_id"])
                    for work in current["works"]}) == 4
        after = {
            path.relative_to(root): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / "resources").rglob("*") if path.is_file()
        }
        assert before == after
        assert launches == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
