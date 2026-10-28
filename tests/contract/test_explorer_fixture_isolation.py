"""Development fixture isolation is independent of personal/native configuration."""

import http.client
import json
import threading
from contextlib import closing

from tests.contract.explorer_fixture import fixture_server


def _get(server, token):
    with closing(http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)) as connection:
        connection.request("GET", "/api/vaults", headers={"Authorization": "Bearer " + token})
        response = connection.getresponse()
        return response.status, json.loads(response.read())


def test_fixture_never_constructs_ambient_services(tmp_path, monkeypatch):
    from scholar_workflow.adapters import knowledge_explorer
    from scholar_workflow.workflows import exploration_references, vault_connections

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Synthetic HTTP fixtures must supply their dependencies")

    monkeypatch.setattr(exploration_references, "ExplorationReferenceService", forbidden)
    monkeypatch.setattr(vault_connections, "VaultConnectionService", forbidden)
    monkeypatch.setattr(knowledge_explorer, "ExplorationReaderGate", forbidden)
    server, token = fixture_server(tmp_path)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        assert server.environment.state_root == tmp_path / ".fixture-state"
        assert _get(server, token) == (200, {"revision": None, "connections": [], "diagnostics": []})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_fixture_close_waits_for_its_inflight_request(tmp_path):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()
    response = []

    class SlowVault:
        def list_connections(self):
            entered.set()
            assert release.wait(5), "The test must release its request"
            return {"connections": []}

    service = SlowVault()
    server, token = fixture_server(tmp_path, vault_service=service)
    assert server.vaults is service
    listener = threading.Thread(target=server.serve_forever)
    request = threading.Thread(target=lambda: response.append(_get(server, token)))

    def close():
        server.shutdown()
        server.server_close()
        closed.set()

    closer = threading.Thread(target=close)
    listener.start()
    request.start()
    try:
        assert entered.wait(3)
        closer.start()
        listener.join(timeout=3)
        assert not listener.is_alive()
        assert not closed.is_set(), "Closing must wait for the handler, not leak it into another test"
    finally:
        release.set()
        if closer.ident is None:
            closer.start()
        for thread in (listener, request, closer):
            thread.join(timeout=5)
            assert not thread.is_alive()
    assert closed.is_set()
    assert response == [(200, {"connections": []})]
