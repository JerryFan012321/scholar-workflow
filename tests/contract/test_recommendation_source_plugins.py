"""Portable source packages are inert across CLI, HTTP and independent pools."""

from __future__ import annotations

import copy
import http.client
import json
import shlex
import socket
import subprocess
import threading
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from scholar_workflow.research.recommendations.server import create_server
from scholar_workflow.research.recommendations.source_catalog import builtin_sources
from scholar_workflow.research.recommendations.store import RecommendationStore
from scholar_workflow.research.runner import main

TOKEN = "synthetic-source-package-browser-token-0123456789"


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
            raise AssertionError("Source package operations must not contact a provider")
        return actual_connect(connection, address)

    def no_process(*args, **kwargs):
        raise AssertionError("A source package must never start a native tool or agent")

    monkeypatch.setattr(socket.socket, "connect", local_only)
    monkeypatch.setattr(subprocess, "Popen", no_process)
    return home, allowed_ports


def plugin():
    return {
        "schema_version": 1,
        "source": {
            "source_id": "synthetic-lab",
            "name": "Synthetic Lab",
            "purpose": "Selected research announcements from a user-chosen source.",
            "status": "available",
            "enabled": True,
            "scope": "selected_channel",
            "plugin_version": "1.0.0",
            "interfaces": [{"kind": "mcp", "url": "https://example.org/research-mcp"}],
            "capabilities": ["research announcements", "selected researcher suggestions"],
            "documentation": ["https://example.org/docs"],
            "agent": {
                "connection_name": "synthetic-lab",
                "instructions": "Use the host native tool list and current argument schema.",
                "operations": [
                    {
                        "operation_id": "recent-releases",
                        "description": "Read the selected source's current announcements.",
                        "tool_name": "list_releases",
                        "effect": "read",
                        "inputs": "Requested topic and a bounded result count.",
                        "outputs": "Source identifiers and original links; not prepared abstracts.",
                    },
                    {
                        "operation_id": "follow-researcher",
                        "description": "Follow an explicitly selected researcher after authorization.",
                        "tool_name": "follow_researcher",
                        "effect": "write",
                        "inputs": "The verified researcher identifier.",
                        "outputs": "The native tool's observed outcome or an uncertain receipt.",
                    },
                ],
            },
        },
    }


def cli(*arguments, payload=None, profile="test"):
    return CliRunner().invoke(
        main,
        ["recommendations", "--profile", profile, *arguments],
        input=None if payload is None else json.dumps(payload),
    )


def successful(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def assert_profile_handoff(guide, profile):
    assert guide["profile"] == profile
    prefix = ["scholar-research", "recommendations", "--profile", profile]
    assert shlex.split(guide["submission"]["schema"]) == [*prefix, "schema"]
    assert shlex.split(guide["submission"]["entry"]) == [*prefix, "submit"]


def import_plugin(package=None, revision=0):
    return cli(
        "sources", "import", "--expected-revision", str(revision), "--input", "-",
        payload=plugin() if package is None else package,
    )


def test_source_package_roundtrip_across_pools_and_agent_handoff(isolated, monkeypatch):
    home, _ = isolated
    package = plugin()
    receipt = successful(import_plugin(package))
    assert receipt["changed"] and receipt["revision"] == 1
    assert receipt["source"]["source_id"] == "synthetic-lab"
    exported = successful(cli("sources", "export", "synthetic-lab"))
    assert exported == package
    # Read-only discovery/export must not create a recommendation or execute a hint.
    assert successful(cli("list", "--format", "json"))["total"] == 0
    assert successful(import_plugin(package, revision=1))["changed"] is False

    requirement = {
        "requirement_id": "synthetic-recommendation-purpose",
        "source_id": "synthetic-lab",
        "title": "Selected test purpose",
        "content": "Only announce the selected research direction; preserve source links.",
        "enabled": True,
        "expected_revision": 0,
        "updated_by": {"kind": "human", "name": "Synthetic reviewer"},
    }
    saved = successful(cli("requirements", "save", "--input", "-", payload=requirement))
    context = successful(cli(
        "sources", "context", "synthetic-lab", "--input", "-",
        payload={"expected_revision": 0, "topics": ["selected topic"], "notes": "Pending researcher suggestion."},
    ))
    operation = {
        "operation_id": "synthetic-observation",
        "source_id": "synthetic-lab",
        "actor": "another-external-agent",
        "action": "Inspect current release metadata",
        "status": "unconfirmed",
        "summary": "No live request was made in this package test.",
        "observed_at": "2026-11-10T00:00:00Z",
        "evidence_urls": ["https://example.org/releases"],
    }
    successful(cli("sources", "record-operation", "--input", "-", payload=operation))
    guide = successful(cli("sources", "guide", "synthetic-lab"))
    assert guide["source"]["agent"] == package["source"]["agent"]
    assert guide["source"]["connection_status"] == "not_checked"
    assert guide["catalog_revision"] == 1
    assert guide["context"] == context
    assert guide["requirements"]["items"] == [saved]
    assert guide["recent_operations"]["items"][0]["operation_id"] == operation["operation_id"]
    assert guide["discovery"]["method"] == "host_native"
    assert guide["discovery"]["require_current_tool_schema"] is True
    assert_profile_handoff(guide, "test")

    # The portable package contains the definition, not local human preferences/history.
    assert successful(cli("sources", "export", "synthetic-lab")) == exported
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home.parent / "another-home"))
    assert successful(import_plugin(exported))["changed"]
    second = successful(cli("sources", "guide", "synthetic-lab"))
    assert_profile_handoff(second, "test")
    assert second["source"]["agent"] == guide["source"]["agent"]
    assert second["requirements"]["items"] == []
    assert second["context"]["revision"] == 0
    assert second["recent_operations"]["items"] == []
    assert successful(cli("list", "--format", "json"))["total"] == 0
    assert len(successful(cli("sources", "list", profile="personal"))["items"]) == len(builtin_sources())


def test_file_import_edit_and_stale_revision_do_not_create_duplicates(isolated, tmp_path):
    path = tmp_path / "source-package.json"
    path.write_text(json.dumps(plugin()), encoding="utf-8")
    successful(cli("sources", "import", "--input", str(path), "--expected-revision", "0"))
    changed = plugin()
    changed["source"]["plugin_version"] = "1.1.0"
    changed["source"]["agent"]["instructions"] = "Inspect the current host tools before using updated operations."
    assert import_plugin(changed, revision=0).exit_code == 5
    assert successful(cli("sources", "export", "synthetic-lab")) == plugin()
    assert successful(import_plugin(changed, revision=1))["revision"] == 2
    catalog = successful(cli("sources", "list"))
    assert sum(item["source_id"] == "synthetic-lab" for item in catalog["items"]) == 1
    assert successful(cli("sources", "export", "synthetic-lab")) == changed


def test_disable_retains_source_requirements_context_and_history(isolated):
    successful(import_plugin())
    store = RecommendationStore(isolated[0] / "recommendations" / "test")
    requirement = store.save_requirement(
        "selected-purpose", "Purpose", "Only selected material.", True, 0,
        {"kind": "human", "name": "Synthetic reviewer"}, source_id="synthetic-lab",
    )
    context = store.update_source_context(
        "synthetic-lab", expected_revision=0, topics=["world models"], notes="Keep this pending suggestion.",
    )
    operation = store.record_source_operation({
        "operation_id": "before-disable", "source_id": "synthetic-lab",
        "actor": "synthetic-agent", "action": "Record a proposed check", "status": "proposed",
        "summary": "Keep this proposal when the source is disabled.",
        "observed_at": "2026-11-10T00:00:00Z", "evidence_urls": ["https://example.org/releases"],
    })
    result = successful(cli("sources", "disable", "synthetic-lab", "--expected-revision", "1"))
    assert result["changed"] and result["revision"] == 2
    assert result["source"]["enabled"] is False
    assert cli("sources", "enable", "synthetic-lab", "--expected-revision", "1").exit_code == 5
    guide = successful(cli("sources", "guide", "synthetic-lab"))
    assert guide["source"]["enabled"] is False
    assert guide["requirements"]["items"] == [requirement]
    assert guide["context"] == context
    assert guide["recent_operations"]["items"] == [operation["record"]]
    assert store.list_candidates()["total"] == 0
    unchanged = successful(cli("sources", "disable", "synthetic-lab", "--expected-revision", "2"))
    assert unchanged["changed"] is False and unchanged["revision"] == 2
    assert successful(cli("sources", "enable", "synthetic-lab", "--expected-revision", "2"))["source"]["enabled"] is True


def test_builtin_enable_state_is_local_and_does_not_copy_packaged_definition(isolated):
    before = copy.deepcopy(builtin_sources())
    result = successful(cli("sources", "disable", "alphaxiv", "--expected-revision", "0"))
    assert result["revision"] == 1 and result["source"]["enabled"] is False
    assert builtin_sources() == before
    store = RecommendationStore(isolated[0] / "recommendations" / "test")
    assert store.recommendation_sources()["items"] == []
    assert successful(cli("sources", "show", "alphaxiv", profile="personal"))["enabled"] is True
    assert successful(cli("sources", "guide", "alphaxiv"))["source"]["enabled"] is False
    assert cli("sources", "enable", "alphaxiv", "--expected-revision", "0").exit_code == 5
    assert successful(cli("sources", "enable", "alphaxiv", "--expected-revision", "1"))["source"]["enabled"] is True
    for source_id in ["x-self", "zhihu-self"]:
        assert cli("sources", "enable", source_id, "--expected-revision", "2").exit_code != 0
        assert successful(cli("sources", "show", source_id))["enabled"] is False
    assert builtin_sources() == before


def test_guide_handoff_keeps_the_selected_pool_context_and_destination(isolated):
    for profile in ["test", "personal"]:
        successful(cli(
            "sources", "context", "alphaxiv", "--input", "-", profile=profile,
            payload={"expected_revision": 0, "topics": [profile + " topic"], "notes": profile + " only"},
        ))
    successful(cli("sources", "disable", "alphaxiv", "--expected-revision", "0"))
    test_guide = successful(cli("sources", "guide", "alphaxiv"))
    personal_guide = successful(cli("sources", "guide", "alphaxiv", profile="personal"))
    assert_profile_handoff(test_guide, "test")
    assert_profile_handoff(personal_guide, "personal")
    assert test_guide["context"]["notes"] == "test only"
    assert personal_guide["context"]["notes"] == "personal only"
    assert test_guide["source"]["enabled"] is False
    assert personal_guide["source"]["enabled"] is True
    assert test_guide["catalog_revision"] == 1
    assert personal_guide["catalog_revision"] == 0
    assert successful(cli("list", "--format", "json"))["total"] == 0
    assert successful(cli("list", "--format", "json", profile="personal"))["total"] == 0


@pytest.mark.parametrize("missing", ["plugin_version", "agent"])
def test_plugin_import_requires_versioned_agent_contract(isolated, missing):
    package = plugin()
    del package["source"][missing]
    assert import_plugin(package).exit_code != 0
    assert successful(cli("sources", "list"))["revision"] == 0


@pytest.mark.parametrize("mutation", ["unknown-wrapper", "projection", "builtin", "bad-version", "bad-effect", "private-path", "secret"])
def test_untrusted_package_refusals_preserve_catalog(isolated, mutation):
    package = plugin()
    if mutation == "unknown-wrapper":
        package["source_id"] = "different-source"
    elif mutation == "projection":
        package["source"]["origin"] = "builtin"
    elif mutation == "builtin":
        package["source"]["source_id"] = "alphaxiv"
    elif mutation == "bad-version":
        package["source"]["plugin_version"] = "run latest arbitrary code"
    elif mutation == "bad-effect":
        package["source"]["agent"]["operations"][0]["effect"] = "shell"
    elif mutation == "private-path":
        package["source"]["agent"]["instructions"] = "Read /Users/alice/private/credential"
    else:
        package["source"]["agent"]["instructions"] = "API_KEY=synthetic-do-not-store"
    assert import_plugin(package).exit_code != 0
    assert successful(cli("sources", "list"))["revision"] == 0
    assert successful(cli("list", "--format", "json"))["total"] == 0


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


def request(server, method, path, *, body=None, token=TOKEN, origin="same-origin"):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    headers = {"Host": f"127.0.0.1:{server.server_port}"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = f"http://127.0.0.1:{server.server_port}" if origin == "same-origin" else origin
    connection.request(method, path, headers=headers, body=None if body is None else json.dumps(body))
    response = connection.getresponse()
    status, raw = response.status, response.read()
    connection.close()
    return status, json.loads(raw)


def test_http_source_package_management_matches_cli_and_never_calls_tools(isolated):
    home, allowed_ports = isolated
    with page(home, allowed_ports) as server:
        body = {"expected_revision": 0, "plugin": plugin()}
        assert request(server, "POST", "/api/sources/import", body=body, token=None)[0] == 401
        assert request(server, "POST", "/api/sources/import", body=body, origin=None)[0] == 403
        assert request(server, "POST", "/api/sources/import", body=body, origin="https://example.org")[0] == 403
        assert successful(cli("sources", "list"))["revision"] == 0
        status, receipt = request(server, "POST", "/api/sources/import", body=body)
        assert status == 200 and receipt["revision"] == 1
        status, exported = request(server, "GET", "/api/sources/export?source_id=synthetic-lab")
        assert status == 200 and exported == plugin()
        status, guide = request(server, "GET", "/api/sources/guide?source_id=synthetic-lab")
        assert status == 200 and guide == successful(cli("sources", "guide", "synthetic-lab"))
        assert_profile_handoff(guide, "test")
        assert request(server, "POST", "/api/sources/import", body=body)[0] == 409
        status, receipt = request(server, "POST", "/api/sources/enabled", body={
            "source_id": "synthetic-lab", "enabled": False, "expected_revision": 1,
        })
        assert status == 200 and receipt["source"]["enabled"] is False
        assert successful(cli("sources", "show", "synthetic-lab"))["enabled"] is False
        status, receipt = request(server, "POST", "/api/sources/enabled", body={
            "source_id": "synthetic-lab", "enabled": True, "expected_revision": 2,
        })
        assert status == 200 and receipt["source"]["enabled"] is True
        assert request(server, "POST", "/api/sources/invoke", body={"source_id": "synthetic-lab"})[0] == 404
    assert successful(cli("list", "--format", "json"))["total"] == 0
    assert successful(cli("sources", "history"))["items"] == []


@pytest.mark.parametrize("query", ["", "source_id=", "source_id=a&source_id=b", "source_id=synthetic-lab&url=https://example.org/"])
@pytest.mark.parametrize("route", ["export", "guide"])
def test_http_source_identity_is_explicit_and_query_cannot_supply_execution(isolated, route, query):
    home, allowed_ports = isolated
    with page(home, allowed_ports) as server:
        path = "/api/sources/" + route + ("?" + query if query else "")
        assert request(server, "GET", path)[0] in {400, 403, 503}


@pytest.mark.parametrize("extra", [{"command": "arbitrary native command"}, {"url": "https://example.org/tool"}, {"source_id": "another-source"}])
def test_http_import_does_not_accept_out_of_band_identity_or_execution(isolated, extra):
    home, allowed_ports = isolated
    with page(home, allowed_ports) as server:
        status, _ = request(server, "POST", "/api/sources/import", body={
            "expected_revision": 0, "plugin": plugin(), **extra,
        })
        assert status == 400
    assert successful(cli("sources", "list"))["revision"] == 0
