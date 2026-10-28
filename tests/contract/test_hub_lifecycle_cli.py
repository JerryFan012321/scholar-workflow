"""CLI contracts for Hub v3 service discovery and destination routing."""
from __future__ import annotations

import json
import webbrowser
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow import __version__, cli
from scholar_workflow.cli import main
from scholar_workflow.hub import lifecycle
from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.routing import ExecutionTargetRegistry
from scholar_workflow.hub.terminal_worker import TerminalWorkerState


def _record(tmp_path: Path) -> lifecycle.HubDiscoveryRecord:
    return lifecycle.HubDiscoveryRecord(
        schema_version=lifecycle.DISCOVERY_SCHEMA_VERSION,
        service_name=lifecycle.SERVICE_NAME,
        pid=4242,
        port=45678,
        executable="/installed/python",
        package_version=__version__,
        build_hash="sha256:" + "a" * 64,
        protocol_version=3,
        service_generation="service_1234567890abcdef",
        started_at="2026-09-22T00:00:00Z",
        log_path=str((tmp_path / "hub.log").resolve()),
    )


def test_hub_status_reports_discovered_runtime_not_configured_port(tmp_path, monkeypatch):
    record = _record(tmp_path)
    status = lifecycle.HubStatus(True, record, {}, "managed Hub is running")
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type("Manager", (), {"status": lambda self: status})(),
    )

    result = CliRunner().invoke(main, ["hub", "status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["running"] is True
    assert payload["port"] == 45678
    assert payload["executable"] == "/installed/python"
    assert payload["package_version"] == __version__
    assert payload["build_hash"].startswith("sha256:")
    assert payload["started_at"] == "2026-09-22T00:00:00Z"
    assert payload["log_path"].endswith("hub.log")


def test_hub_stop_is_publicly_idempotent(monkeypatch):
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type(
            "Manager",
            (),
            {
                "status": lambda self: lifecycle.HubStatus(False, None, None, "stopped"),
                "stop": lambda self: False,
            },
        )(),
    )

    result = CliRunner().invoke(main, ["hub", "stop"])

    assert result.exit_code == 0, result.output
    assert "already stopped" in result.output


def test_hub_restart_inside_cmux_keeps_window_routing(monkeypatch, tmp_path):
    record = _record(tmp_path)
    workspaces: list[str | None] = []
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type(
            "Manager",
            (),
            {"restart": lambda self: record},
        )(),
    )
    monkeypatch.setattr(
        cli,
        "_ensure_hub_router",
        lambda _record, workspace: workspaces.append(workspace),
    )

    result = CliRunner().invoke(
        main,
        ["hub", "restart"],
        env={
            "CMUX_WORKSPACE_ID": "workspace:7",
            "CMUX_SOCKET_PATH": "/tmp/cmux/socket",
        },
    )

    assert result.exit_code == 0, result.output
    assert workspaces == ["workspace:7"]


def test_hub_doctor_proves_runtime_identity_build_and_private_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))
    log = home / "runtime" / "hub.log"
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")
    log.chmod(0o600)
    record = _record(tmp_path)
    record = lifecycle.HubDiscoveryRecord(
        **{
            **record.as_payload(),
            "executable": "/installed/python",
            "build_hash": lifecycle.installed_build_hash(),
            "log_path": str(log.resolve()),
        }
    )
    lifecycle.write_discovery(record, lifecycle.discovery_path())
    health = {
        "status": "ok",
        "service": {
            "name": lifecycle.SERVICE_NAME,
            "version": record.package_version,
        },
        "process": {"pid": record.pid, "executable": record.executable},
        "service_generation": record.service_generation,
        "protocol": {"version": 3},
        "build": {"version": record.package_version},
    }
    status = lifecycle.HubStatus(True, record, health, "managed Hub is running")
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type("Manager", (), {"status": lambda self: status})(),
    )

    result = CliRunner().invoke(main, ["hub", "doctor", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert {row["name"] for row in payload["checks"]} >= {
        "discovery-mode",
        "managed-process",
        "installed-build",
        "health-identity",
        "protocol",
        "health-build",
        "private-log",
    }


@pytest.mark.parametrize("inside_cmux", [False, True])
def test_open_hub_retirement_never_constructs_a_service_manager(tmp_path, monkeypatch, inside_cmux):
    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        calls.append("constructed or launched")
        raise AssertionError("retired front end must not affect API service lifecycle")

    monkeypatch.setattr(lifecycle, "HubServiceManager", forbidden)
    monkeypatch.setattr(cli, "_ensure_hub_router", forbidden)
    monkeypatch.setattr(cli, "_register_default_destination", forbidden)
    monkeypatch.setattr(webbrowser, "open", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    home = tmp_path / "uninitialized-home"
    result = CliRunner().invoke(
        main, ["open-hub", "--instance", "instance_A234567890abcdef"],
        env={"SCHOLAR_WORKFLOW_HOME": str(home),
             "CMUX_WORKSPACE_ID": "workspace:7" if inside_cmux else "",
             "CMUX_SOCKET_PATH": "/tmp/cmux/socket" if inside_cmux else ""},
    )

    assert result.exit_code == 3, result.output
    assert "retired" in result.output.lower()
    assert "knowledge explore" in result.output
    assert calls == []
    assert not home.exists()


def test_destination_registration_uses_csrf_and_never_puts_workspace_in_url(
    monkeypatch,
):
    requests: list[tuple[str, str, bytes | None, dict[str, str]]] = []
    responses = iter(
        [
            (200, b'{"csrf_token":"private-session-token"}'),
            (200, b'{"ok":true,"destination_id":"destination_1"}'),
        ]
    )

    class Response:
        def __init__(self, status: int, body: bytes) -> None:
            self.status = status
            self._body = body

        def read(self, _limit: int) -> bytes:
            return self._body

    class Connection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 45678, 2.0)

        def request(self, method, path, body=None, headers=None):
            requests.append((method, path, body, headers or {}))

        @staticmethod
        def getresponse():
            status, body = next(responses)
            return Response(status, body)

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(cli.http.client, "HTTPConnection", Connection)
    monkeypatch.setattr(
        lifecycle,
        "probe_health",
        lambda _port: {"capabilities": ["cmux-destinations-v1"]},
    )

    assert cli._register_default_destination(
        45678,
        "instance_A234567890abcdef",
        "workspace:7",
    )

    assert requests[0][:2] == ("GET", "/api/v1/session")
    method, path, body, headers = requests[1]
    assert (method, path) == ("POST", "/api/v3/destinations/default")
    assert json.loads(body) == {"workspace_id": "workspace:7"}
    assert headers["X-Scholar-Hub-Token"] == "private-session-token"
    assert headers["X-Scholar-Hub-Instance"] == "instance_A234567890abcdef"
    assert headers["Origin"] == "http://127.0.0.1:45678"
    assert "workspace:7" not in path


def test_hub_target_add_source_registers_folder_authority_without_cli_path(tmp_path):
    home = tmp_path / "home"
    vault = tmp_path / "world-models"
    vault.mkdir()
    source_id = "22222222-2222-4222-8222-222222222222"
    sources = KnowledgeSourceRegistry(home / "hub" / "sources.json")
    sources.save(
        KnowledgeSourceRegistryDocument(
            folders=[
                FolderRegistration(
                    folder_id="folder-world-models",
                    root=vault,
                    capabilities=["read", "write"],
                )
            ],
            sources=[
                KnowledgeSourceRegistration(
                    source_id=source_id,
                    folder_id="folder-world-models",
                    capabilities=["read", "write"],
                )
            ],
        )
    )

    result = CliRunner().invoke(
        main,
        [
            "hub",
            "target",
            "add-source",
            source_id,
            "--target-id",
            "world-models",
        ],
        env={"SCHOLAR_WORKFLOW_HOME": str(home)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {
        "capabilities": ["codex"],
        "kind": "vault",
        "target_id": "world-models",
    }
    target_registry = ExecutionTargetRegistry(
        home / "hub" / "execution-targets.json",
        project_registry=ProjectRegistry(home / "hub" / "projects.json"),
        source_registry=sources,
    )
    resolved = target_registry.resolve("world-models", capability="codex")
    assert resolved.cwd == vault.resolve()
    assert resolved.target.registered_root_id == "folder-world-models"
    assert str(vault) not in result.output

    listed = CliRunner().invoke(
        main,
        ["hub", "target", "list"],
        env={"SCHOLAR_WORKFLOW_HOME": str(home)},
    )
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output) == {"targets": [payload]}


def test_hub_codex_configure_retires_without_changing_existing_registrations(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    vault = tmp_path / "world-models"
    vault.mkdir()
    source_id = "22222222-2222-4222-8222-222222222222"
    sources = KnowledgeSourceRegistry(home / "hub" / "sources.json")
    sources.save(
        KnowledgeSourceRegistryDocument(
            folders=[
                FolderRegistration(
                    folder_id="folder-world-models",
                    root=vault,
                    capabilities=["read", "write"],
                )
            ],
            sources=[
                KnowledgeSourceRegistration(
                    source_id=source_id,
                    folder_id="folder-world-models",
                    capabilities=["read", "write"],
                )
            ],
        )
    )
    target = CliRunner().invoke(
        main,
        [
            "hub",
            "target",
            "add-source",
            source_id,
            "--target-id",
            "world-models",
        ],
        env={"SCHOLAR_WORKFLOW_HOME": str(home)},
    )
    assert target.exit_code == 0, target.output

    executable = tmp_path / "codex-private-path"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    def refuse_probe(_self):
        raise AssertionError("Retired configuration must not start a Codex capability probe")

    monkeypatch.setattr("scholar_workflow.hub.tasks.CodexCapabilityProbe.probe", refuse_probe)

    result = CliRunner().invoke(
        main,
        [
            "hub",
            "codex",
            "configure",
            "--executable",
            str(executable),
            "--model",
            "private-model",
            "--sandbox",
            "workspace-write",
        ],
        env={"SCHOLAR_WORKFLOW_HOME": str(home)},
    )

    assert result.exit_code == 7, result.output
    assert "retired" in result.output.lower()
    assert str(executable) not in result.output
    assert "private-model" not in result.output

    assert not (home / "hub" / "task-recipes.json").exists()
    state = TerminalWorkerState(home / "hub" / "task-worker")
    assert not state.runtime_path.exists()
    assert not (home / "hub" / "tools.json").exists()
    assert sources.resolve(source_id, capability="read") == vault.resolve()
