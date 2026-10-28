"""Exercise isolated Vault onboarding without touching an existing paper package."""

import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture
def vault_server(tmp_path, monkeypatch):
    from scholar_workflow.adapters.knowledge_explorer import make_server
    from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment
    from scholar_workflow.workflows.vault_connections import VaultConnectionService

    root, vault, state = (tmp_path / name for name in ("explorer", "chosen-vault", "private"))
    root.mkdir()
    vault.mkdir()
    original = b"# Existing paper\n\nPreserve this accepted text.\n"
    (vault / "Paper.md").write_bytes(original)
    (vault / "Paper.canvas").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "secret.md").write_text("private settings", encoding="utf-8")
    environment = ExplorerEnvironment("test", state, (tmp_path,))

    class Picker:
        def choose(self):
            return vault

    service = VaultConnectionService(environment, picker=Picker())
    server, token = make_server(root, environment=environment, vault_service=service)
    server.daemon_threads = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(route, payload=None, authenticated=True):
        headers = {"Authorization": f"Bearer {token}"} if authenticated else {}
        if payload is not None:
            headers.update({"Content-Type": "application/json", "Origin": base})
        req = urllib.request.Request(base + route, headers=headers,
            data=None if payload is None else json.dumps(payload).encode())
        try:
            response = opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    request.server = server
    yield root, vault, environment, request, original
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_environment_and_connection_require_session(vault_server):
    root, _vault, _environment, request, _original = vault_server
    assert request("/api/environment", authenticated=False)[0] == 401
    status, context = request("/api/environment")
    assert status == 200 and context["mode"] == "test"
    assert context["root_name"] == root.name and context["version"]
    assert str(root) not in json.dumps(context)
    assert request("/api/vaults", authenticated=False)[0] == 401
    assert request("/api/vaults/choose", {"path": "/arbitrary"})[0] == 400


def test_preview_then_readonly_connect_preserves_paper_files(vault_server):
    _root, vault, _environment, request, original = vault_server
    assert request("/api/vaults")[1]["connections"] == []
    status, preview = request("/api/vaults/choose", {})
    assert status == 200 and preview["candidate_id"]
    assert preview["layers"]["readable"]["status"] == "available"
    assert preview["layers"]["referenceable"]["status"] == "needs-registration"
    assert str(vault) not in json.dumps(preview)
    assert request("/api/vaults/preview", {"candidate_id": preview["candidate_id"]})[0] == 200
    assert not (vault / ".scholar-workflow").exists()
    status, result = request("/api/vaults/connect", {
        "candidate_id": preview["candidate_id"], "expected_revision": preview["revision"]})
    assert status == 200 and result["status"] in {"connected", "unchanged"}
    connections = request("/api/vaults")[1]["connections"]
    assert len(connections) == 1
    identity = connections[0]["connection_id"]
    status, documents = request(f"/api/vaults/{identity}/documents")
    assert status == 200
    assert "secret.md" not in json.dumps(documents)
    status, content = request("/api/vaults/document-preview", {
        "connection_id": identity, "relative_path": "Paper.md"})
    assert status == 200 and "Preserve this accepted text" in content["text"]
    assert request("/api/vaults/document-preview", {
        "connection_id": identity, "relative_path": "../private.md"})[0] in {400, 403}
    assert (vault / "Paper.md").read_bytes() == original
    assert not (vault / ".scholar-workflow").exists()


def test_test_environment_refuses_native_open_without_launch(vault_server, monkeypatch):
    _root, _vault, _environment, request, _original = vault_server
    from scholar_workflow.adapters import knowledge_explorer

    def forbidden(*args, **kwargs):
        pytest.fail("A test session launched an external application")

    monkeypatch.setattr(knowledge_explorer.subprocess, "Popen", forbidden)
    from scholar_workflow.knowledge.exploration import default_data

    data = default_data()
    data["works"] = [{"id": "article", "title": "Synthetic article", "kind": "webpage",
                      "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-article"},
                      "attributes": {}, "assets": [{"id": "web", "kind": "web",
                          "label": "Original", "uri": "https://example.test/original"}]}]
    request.server.remember_units(data, [data["works"][0]["entity_ref"]])
    assert request("/api/save", {"data": data, "expected_revision": None})[0] == 200
    assert request("/api/open", {"work_id": "article", "asset_id": "web"})[0] == 403
    assert request("/api/assets/article")[1][0]["native_available"] is False


def test_foreign_registration_added_after_start_refuses_before_provider_read(vault_server):
    _root, _vault, environment, request, _original = vault_server
    outside = environment.allowed_roots[0].parent / "foreign-registration"
    outside.mkdir(exist_ok=True)
    environment.registry_path.parent.mkdir(parents=True, exist_ok=True)
    environment.registry_path.write_text(json.dumps({
        "schema_version": 1,
        "folders": [{"folder_id": "foreign", "root": str(outside), "capabilities": ["read"]}],
        "sources": [],
    }))
    for route in ("/api/unit-fields", "/api/vaults", "/api/state"):
        assert request(route)[0] == 403


def test_uncertain_connection_publication_is_not_reported_as_conflict(vault_server, monkeypatch):
    _root, _vault, _environment, request, _original = vault_server
    from scholar_workflow.knowledge.exploration import ExplorationError

    def uncertain(*args):
        raise ExplorationError("Connection may have completed; inspect current connections", 6)

    monkeypatch.setattr(request.server.vaults, "connect", uncertain)
    status, body = request("/api/vaults/connect", {
        "candidate_id": "synthetic-candidate", "expected_revision": None})
    assert status == 503 and body["status"] == "uncertain" and body["code"] == 6
