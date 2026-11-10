"""External agents share source descriptions/results without a built-in tool runner."""

from __future__ import annotations

import http.client
import json
import socket
import subprocess
import threading
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from scholar_workflow.research.recommendations.server import create_server
from scholar_workflow.research.recommendations.store import RecommendationStore
from scholar_workflow.research.runner import main

TOKEN = "synthetic-source-catalog-browser-token-0123456789"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    allowed_ports = set()
    actual_connect = socket.socket.connect

    def local_only(connection, address):
        if (
            not isinstance(address, tuple)
            or address[0] != "127.0.0.1"
            or address[1] not in allowed_ports
        ):
            raise AssertionError("Source metadata must not contact a remote source")
        return actual_connect(connection, address)

    def no_agent(*args, **kwargs):
        raise AssertionError("Source metadata must not start an agent or native command")

    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setattr(subprocess, "Popen", no_agent)
    return home, allowed_ports


def descriptor():
    return {
        "source_id": "synthetic-lab",
        "name": "Synthetic Lab",
        "purpose": "Explicitly selected research announcements",
        "status": "available",
        "interfaces": [{"kind": "mcp", "url": "https://example.org/research-mcp"}],
        "capabilities": ["research announcements"],
        "documentation": ["https://example.org/docs"],
        "auth": {
            "method": "host_oauth",
            "reference": "host:synthetic-lab",
            "instructions": "Use the external harness native connection.",
        },
    }


def cli(*arguments, payload=None, profile="test"):
    result = CliRunner().invoke(
        main,
        ["recommendations", "--profile", profile, *arguments],
        input=None if payload is None else json.dumps(payload),
    )
    return result


def successful(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def operation():
    return {
        "operation_id": "synthetic-external-action",
        "source_id": "synthetic-lab",
        "actor": "external-project-agent",
        "action": "Check selected research releases",
        "status": "unconfirmed",
        "summary": "The external tool response was interrupted; source outcome is unknown.",
        "observed_at": "2026-11-09T00:00:00Z",
        "evidence_urls": ["https://example.org/releases"],
    }


def test_external_agent_source_context_receipt_and_common_submission(isolated):
    home, _ = isolated
    first = successful(cli("sources", "list"))
    assert first["revision"] == 0
    assert {item["source_id"] for item in first["items"]} == {
        "alphaxiv",
        "hf-daily",
        "x-self",
        "zhihu-self",
    }
    alpha = successful(cli("sources", "show", "alphaxiv"))
    assert alpha["execution"] == {"kind": "native_mcp", "host_connection_name": "alphaxiv"}
    assert alpha["connection_status"] == "not_checked"
    registered = successful(
        cli("sources", "register", "--expected-revision", "0", "--input", "-", payload=descriptor())
    )
    assert registered["changed"] and registered["revision"] == 1
    assert successful(cli("sources", "show", "synthetic-lab"))["origin"] == "registered"

    context = successful(
        cli(
            "sources",
            "context",
            "synthetic-lab",
            "--input",
            "-",
            payload={
                "expected_revision": 0,
                "topics": ["world models"],
                "notes": "Track this selected source; verify benchmark conditions.",
            },
        )
    )
    assert context["revision"] == 1
    # A new invocation represents another external agent, with no private chat memory.
    assert successful(cli("sources", "context", "synthetic-lab"))["notes"] == context["notes"]
    assert (
        cli(
            "sources",
            "context",
            "synthetic-lab",
            "--input",
            "-",
            payload={"expected_revision": 0, "topics": [], "notes": "Stale update"},
        ).exit_code
        == 5
    )

    recorded = successful(cli("sources", "record-operation", "--input", "-", payload=operation()))
    assert recorded["status"] == "recorded"
    assert recorded["record"]["verification"] == "agent_reported"
    assert (
        successful(cli("sources", "record-operation", "--input", "-", payload=operation()))[
            "status"
        ]
        == "unchanged"
    )
    changed = {**operation(), "status": "reported_completed"}
    assert cli("sources", "record-operation", "--input", "-", payload=changed).exit_code == 5
    history = successful(cli("sources", "history", "--source-id", "synthetic-lab"))
    assert len(history["items"]) == 1 and history["items"][0]["status"] == "unconfirmed"

    submission = {
        "schema_version": 1,
        "producer": {
            "producer_id": "external-project-agent",
            "name": "Synthetic project agent",
            "host": "external-harness",
        },
        "run_id": "source-contract-run",
        "items": [
            {
                "submission_id": "one-selected-paper",
                "resource": {
                    "kind": "paper",
                    "title": "Synthetic Research Paper",
                    "url": "https://example.org/paper",
                    "abstract_original": "This complete synthetic abstract demonstrates the shared entry.",
                    "abstract_zh": "这是一段完整的合成摘要，用于演示外部 agent 通过统一入口提交推荐。",
                },
                "tags": ["world-models"],
                "channels": [{"name": "Synthetic Lab", "url": "https://example.org/releases"}],
            }
        ],
    }
    accepted = successful(cli("submit", "--input", "-", payload=submission))
    assert accepted["receipts"][0]["status"] == "accepted"
    candidate = successful(cli("list", "--format", "json"))["items"][0]
    assert candidate["decision"] == "unread" and not candidate["abstract_reviewed"]
    recommendation = candidate["recommendations"][0]
    assert recommendation["producer"]["producer_id"] == "external-project-agent"
    assert recommendation["channels"] == submission["items"][0]["channels"]
    store = RecommendationStore(home / "recommendations" / "test")
    assert len(store.recommendation_sources()["items"]) == 1
    assert store.list_candidates()["total"] == 1
    assert len(successful(cli("sources", "list", profile="personal"))["items"]) == 4


def test_registration_cas_and_secret_refusals_preserve_existing_source(isolated):
    successful(
        cli("sources", "register", "--expected-revision", "0", "--input", "-", payload=descriptor())
    )
    assert (
        cli(
            "sources", "register", "--expected-revision", "0", "--input", "-", payload=descriptor()
        ).exit_code
        == 5
    )
    bad = {**descriptor(), "source_id": "another-lab", "command": "run arbitrary program"}
    assert (
        cli(
            "sources", "register", "--expected-revision", "1", "--input", "-", payload=bad
        ).exit_code
        == 2
    )
    bad = {
        **descriptor(),
        "source_id": "another-lab",
        "auth": {"method": "api_key", "instructions": "API_KEY=synthetic-do-not-store"},
    }
    assert (
        cli(
            "sources", "register", "--expected-revision", "1", "--input", "-", payload=bad
        ).exit_code
        == 7
    )
    listed = successful(cli("sources", "list"))
    assert listed["revision"] == 1 and len(listed["items"]) == 5
    assert "synthetic-do-not-store" not in json.dumps(listed)


@contextmanager
def page(home, allowed_ports):
    server = create_server(home / "recommendations" / "test", "test", TOKEN)
    allowed_ports.add(server.server_port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        assert not thread.is_alive()
        allowed_ports.remove(server.server_port)


def request(server, method, path, *, body=None, token=TOKEN):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    headers = {"Host": f"127.0.0.1:{server.server_port}"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers.update(
            {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
        )
    connection.request(
        method, path, headers=headers, body=None if body is None else json.dumps(body)
    )
    response = connection.getresponse()
    status, raw = response.status, response.read()
    connection.close()
    return status, json.loads(raw)


def test_sources_http_is_authenticated_and_has_no_native_tool_proxy(isolated):
    home, allowed_ports = isolated
    successful(
        cli("sources", "register", "--expected-revision", "0", "--input", "-", payload=descriptor())
    )
    with page(home, allowed_ports) as server:
        assert request(server, "GET", "/api/sources", token=None)[0] == 401
        assert request(server, "GET", "/api/sources", token="incorrect-synthetic-token")[0] == 401
        status, catalog = request(server, "GET", "/api/sources")
        assert status == 200 and catalog["revision"] == 1
        assert catalog == successful(cli("sources", "list"))
        for path in [
            "/api/alphaxiv/status",
            "/api/alphaxiv/context",
            "/api/alphaxiv/history",
            "/api/alphaxiv/staged",
        ]:
            assert request(server, "GET", path)[0] == 404
        for path in [
            "/api/alphaxiv/tools",
            "/api/alphaxiv/call",
            "/api/alphaxiv/stage",
            "/api/sources/invoke",
        ]:
            assert (
                request(
                    server,
                    "POST",
                    path,
                    body={"tool_name": "follow_researcher", "arguments": {}, "confirmed": True},
                )[0]
                == 404
            )
    assert successful(cli("sources", "history"))["items"] == []


def test_planned_sources_do_not_claim_access_or_execute_when_selected(isolated):
    for source_id in ["x-self", "zhihu-self"]:
        source = successful(cli("sources", "show", source_id))
        assert source["status"] == "planned" and not source["enabled"]
        assert (
            source["scope"] == "self_account_only"
            and source["connection_status"] == "not_implemented"
        )
    assert cli("sources", "invoke", "alphaxiv").exit_code == 2
