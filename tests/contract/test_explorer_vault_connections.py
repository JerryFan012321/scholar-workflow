"""Vault onboarding uses the real isolated service and keeps accepted files intact."""

import json
import os
import subprocess
import threading
from pathlib import Path

import pytest


def test_browser_vault_connections_preserve_paper_and_draft(tmp_path):
    executable = os.environ.get("SCHOLAR_BROWSER_NODE")
    if not executable or not os.environ.get("NODE_PATH"):
        pytest.skip("Set SCHOLAR_BROWSER_NODE and NODE_PATH for the optional Chrome contract")
    from scholar_workflow.adapters.knowledge_explorer import make_server
    from scholar_workflow.knowledge.exploration import ExplorationStore, default_data
    from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment
    from scholar_workflow.workflows.vault_connections import VaultConnectionService

    root = tmp_path / "explorer"
    root.mkdir()
    accepted = {
        "analysis.md": b"# Accepted synthetic analysis\n\nKeep its original paragraphs.\n",
        "analysis.canvas": b'{"nodes":[],"edges":[]}\n',
    }
    for relative, content in accepted.items():
        (root / relative).write_bytes(content)
    selected_vault = tmp_path / "Selected test Vault"
    selected_vault.mkdir()
    original_note = b"# Synthetic note\n\nVault content remains unchanged."
    (selected_vault / "note.md").write_bytes(original_note)
    model = default_data()
    model["works"] = [{
        "id": "accepted-paper", "title": "Accepted synthetic paper", "kind": "paper",
        "entity_ref": {"source_id": "synthetic-source", "object_id": "accepted-paper"},
        "attributes": {}, "assets": [
            {"id": "body", "label": "Accepted analysis", "kind": "markdown", "uri": "analysis.md"},
            {"id": "canvas", "label": "Accepted Canvas", "kind": "canvas", "uri": "analysis.canvas"},
        ],
    }]
    store = ExplorationStore(root)
    before = store.save(model, expected_revision=None)
    environment = ExplorerEnvironment("test", tmp_path / "state", (tmp_path,))

    class Picker:
        def choose(self):
            return selected_vault

    service = VaultConnectionService(environment, Picker())
    server, token = make_server(root, environment=environment, vault_service=service)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    screenshot_dir = Path(os.environ.get("SCHOLAR_EXPLORER_SCREENSHOT_DIR", tmp_path / "screenshots"))
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [executable, str(Path(__file__).with_name("explorer_vault_connections.cjs"))],
            input=json.dumps({
                "url": f"http://127.0.0.1:{server.server_port}/#token={token}",
                "title": selected_vault.name, "documentPath": "note.md",
                "expectedText": "Vault content remains unchanged.",
                "screenshotPath": str(screenshot_dir / "vault-documents.png"),
                "inspectionScreenshotPath": str(screenshot_dir / "vault-inspection.png"),
            }),
            text=True, capture_output=True, timeout=90, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert store.load() == before
        assert (selected_vault / "note.md").read_bytes() == original_note
        assert not (selected_vault / ".scholar-workflow").exists()
        for relative, content in accepted.items():
            assert (root / relative).read_bytes() == content
        assert environment.registry_path.is_file()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
