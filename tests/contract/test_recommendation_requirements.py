"""Human and external-agent edits share versioned requirements, not source settings."""

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
from scholar_workflow.research.runner import main

TOKEN = "synthetic-requirements-browser-token-0123456789"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))
    allowed_ports = set()
    connect = socket.socket.connect

    def local_only(connection, address):
        if not isinstance(address, tuple) or address[0] != "127.0.0.1" or address[1] not in allowed_ports:
            raise AssertionError("Saving or reading requirements cannot fetch a research source")
        return connect(connection, address)

    def no_agent(*args, **kwargs):
        raise AssertionError("Saving requirements cannot launch a command or agent")

    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setattr(subprocess, "Popen", no_agent)
    return tmp_path / "home", allowed_ports


def invoke(*arguments, payload=None, profile="test"):
    return CliRunner().invoke(main, ["recommendations", "--profile", profile, *arguments],
                              input=None if payload is None else json.dumps(payload, ensure_ascii=False))


def successful(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def requirement(identifier="synthetic-world-models", **changes):
    return {"requirement_id": identifier, "title": "Synthetic research requirements",
            "content": "This is a synthetic task request.\nKeep the original links for reading.",
            "enabled": True, "expected_revision": 0,
            "updated_by": {"kind": "agent", "name": "Synthetic specialist"}} | changes


def save(record):
    return successful(invoke("requirements", "save", "--input", "-", payload=record))


def batch(producer="synthetic-agent-one", submission="one", reference=None):
    result = {"schema_version": 1, "producer": {"producer_id": producer, "name": producer},
              "run_id": "synthetic-run", "items": [{"submission_id": submission,
              "resource": {"kind": "paper", "title": "Shared synthetic paper",
                           "url": "https://example.org/one-paper",
                           "abstract_original": "A complete synthetic abstract, not a real result.",
                           "abstract_zh": "完整的合成摘要，不代表任何真实研究结果。"}, "tags": []}]}
    if reference is not None:
        result["requirement"] = reference
    return result


@contextmanager
def page(isolated):
    home, ports = isolated
    service = create_server(home / "recommendations" / "test", "test", TOKEN)
    ports.add(service.server_port)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    try:
        yield service
    finally:
        service.shutdown()
        service.server_close()
        thread.join(3)
        assert not thread.is_alive()
        ports.remove(service.server_port)


def request(service, method, path, *, body=None, token=TOKEN, origin=True):
    connection = http.client.HTTPConnection("127.0.0.1", service.server_port, timeout=3)
    headers = {"Host": f"127.0.0.1:{service.server_port}"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = f"http://127.0.0.1:{service.server_port}"
    connection.request(method, path, headers=headers,
                       body=None if body is None else json.dumps(body, ensure_ascii=False).encode())
    response = connection.getresponse()
    status, raw = response.status, response.read()
    connection.close()
    return status, json.loads(raw)


def test_human_page_and_agent_cli_share_edits_and_preserve_history(isolated):
    assert successful(invoke("requirements", "list"))["items"] == []
    body = requirement(updated_by=None)
    del body["updated_by"]
    with page(isolated) as service:
        assert request(service, "GET", "/api/requirements", token=None)[0] == 401
        assert request(service, "POST", "/api/requirements", body=body, origin=False)[0] == 403
        assert request(service, "POST", "/api/requirements", body=body | {"updated_by": {"kind": "agent", "name": "spoof"}})[0] == 400
        status, first = request(service, "POST", "/api/requirements", body=body)
        assert status == 200 and first["revision"] == 1
        assert first["updated_by"]["kind"] == "human"
        assert successful(invoke("requirements", "show", body["requirement_id"])) == first
        updated = save(requirement(expected_revision=1, content="Synthetic revised requirements."))
        assert updated["revision"] == 2 and updated["updated_by"]["kind"] == "agent"
        assert request(service, "GET", "/api/requirements/" + body["requirement_id"])[1] == updated
        status, historical = request(service, "GET", "/api/requirements/" + body["requirement_id"] + "?revision=1")
        assert status == 200 and historical == first
        assert request(service, "POST", "/api/requirements", body=body | {"content": "stale"})[0] == 409
        assert request(service, "GET", "/api/requirements/" + body["requirement_id"])[1] == updated


def test_same_candidate_keeps_each_producers_actual_requirement(isolated):
    first = save(requirement())
    second = save(requirement("synthetic-infra", title="Synthetic infrastructure request", content="Read infrastructure project announcements."))
    for producer, record in [("agent-a", first), ("agent-b", second)]:
        reference = {"requirement_id": record["requirement_id"], "revision": record["revision"]}
        receipt = successful(invoke("submit", "--input", "-", payload=batch(producer=producer, reference=reference)))
        assert receipt["receipts"][0]["status"] == "accepted"
    listing = successful(invoke("list", "--format", "json"))
    assert listing["total"] == 1
    candidate = listing["items"][0]
    assert candidate["decision"] == "unread" and not candidate["abstract_reviewed"]
    records = {item["producer"]["producer_id"]: item for item in candidate["recommendations"]}
    assert records["agent-a"]["requirement"] == first
    assert records["agent-b"]["requirement"] == second
    assert candidate["resource"] == batch()["items"][0]["resource"]


def test_update_or_disable_does_not_rebind_history_or_break_exact_retry(isolated):
    first = save(requirement())
    reference = {"requirement_id": first["requirement_id"], "revision": 1}
    original = batch(reference=reference)
    successful(invoke("submit", "--input", "-", payload=original))
    save(requirement(expected_revision=1, content="A different synthetic request."))
    repeated = successful(invoke("submit", "--input", "-", payload=original))
    assert repeated["receipts"][0]["status"] == "duplicate"
    assert invoke("submit", "--input", "-", payload=batch(submission="stale-new", reference=reference)).exit_code != 0
    save(requirement(expected_revision=2, content="A paused synthetic request.", enabled=False))
    assert invoke("submit", "--input", "-", payload=batch(submission="paused-new", reference={**reference, "revision": 3})).exit_code != 0
    repeated = successful(invoke("submit", "--input", "-", payload=original))
    assert repeated["receipts"][0]["status"] == "duplicate"
    candidate = successful(invoke("list", "--format", "json"))["items"][0]
    assert len(candidate["recommendations"]) == 1
    assert candidate["recommendations"][0]["requirement"] == first


def test_unlinked_legacy_submission_and_profiles_remain_independent(isolated):
    save(requirement())
    legacy = batch()
    assert successful(invoke("submit", "--input", "-", payload=legacy))["receipts"][0]["status"] == "accepted"
    assert successful(invoke("submit", "--input", "-", payload=legacy))["receipts"][0]["status"] == "duplicate"
    row = successful(invoke("list", "--format", "json"))["items"][0]
    assert row["recommendations"][0].get("requirement") is None
    assert successful(invoke("requirements", "list", profile="personal"))["items"] == []
    schema = successful(invoke("schema"))
    assert "requirement" in schema["properties"] and "requirement" not in schema["required"]


def test_free_text_does_not_execute_or_import_anything(isolated):
    content = "Synthetic test only: a shell command here is ordinary task text.\n<script>example</script>"
    saved = save(requirement(content=content))
    assert saved["content"] == content
    assert successful(invoke("list", "--format", "json"))["total"] == 0
    assert successful(invoke("ingestion", "history"))["items"] == []
    assert successful(invoke("requirements", "list"))["items"] == [saved]


def test_source_entry_edits_and_agent_filters_do_not_mix_sources(isolated):
    alpha = save(requirement("alpha-criteria", source_id="alphaxiv"))
    hf = save(requirement("hf-criteria", source_id="hf-daily"))
    legacy = save(requirement("legacy-criteria"))
    assert successful(invoke("requirements", "list", "--source-id", "alphaxiv"))["items"] == [alpha]
    assert successful(invoke("requirements", "list", "--source-id", "hf-daily"))["items"] == [hf]
    assert len(successful(invoke("requirements", "list"))["items"]) == 3
    assert "source_id" not in legacy or legacy["source_id"] is None
    with page(isolated) as service:
        assert request(service, "GET", "/api/requirements?source_id=alphaxiv")[1]["items"] == [alpha]
        assert request(service, "GET", "/api/requirements?source_id=hf-daily")[1]["items"] == [hf]
        assert request(service, "GET", "/api/requirements?source_id=alphaxiv&source_id=hf-daily")[0] == 400
        assert request(service, "GET", "/api/requirements?unknown=alphaxiv")[0] == 400
        body = requirement("browser-alpha", source_id="alphaxiv")
        del body["updated_by"]
        status, created = request(service, "POST", "/api/requirements", body=body)
        assert status == 200 and created["source_id"] == "alphaxiv"
        body["requirement_id"] = "unknown-source-record"
        body["source_id"] = "not-a-registered-source"
        assert request(service, "POST", "/api/requirements", body=body)[0] != 200
    assert len(successful(invoke("requirements", "list", "--source-id", "hf-daily"))["items"]) == 1
    assert len(successful(invoke("requirements", "list"))["items"]) == 4


def test_assigning_source_preserves_old_versions_and_omitted_field_retains_binding(isolated):
    first = save(requirement())
    original = batch(reference={"requirement_id": first["requirement_id"], "revision": 1})
    successful(invoke("submit", "--input", "-", payload=original))
    bound = save(requirement(expected_revision=1, source_id="alphaxiv"))
    assert bound["source_id"] == "alphaxiv" and bound["revision"] == 2
    edited = save(requirement(expected_revision=2, content="Edited by a compatible client."))
    assert edited["source_id"] == "alphaxiv" and edited["revision"] == 3
    assert successful(invoke("requirements", "show", first["requirement_id"], "--revision", "1")) == first
    assert successful(invoke("submit", "--input", "-", payload=original))["receipts"][0]["status"] == "duplicate"
    row = successful(invoke("list", "--format", "json"))["items"][0]
    assert row["recommendations"][0]["requirement"] == first
    assert successful(invoke("requirements", "list", "--source-id", "alphaxiv"))["items"] == [edited]
