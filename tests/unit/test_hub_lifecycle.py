"""Unit coverage for the dynamic, installed-package Hub lifecycle."""
from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow import __version__
from scholar_workflow.hub import lifecycle, service_process


def _record(tmp_path: Path, **changes: object) -> lifecycle.HubDiscoveryRecord:
    values: dict[str, object] = {
        "schema_version": lifecycle.DISCOVERY_SCHEMA_VERSION,
        "service_name": lifecycle.SERVICE_NAME,
        "pid": 4242,
        "port": 43123,
        "executable": "/safe/python",
        "package_version": __version__,
        "build_hash": lifecycle.installed_build_hash(),
        "protocol_version": lifecycle.HUB_PROTOCOL_VERSION,
        "service_generation": "service_1234567890abcdef",
        "started_at": "2026-09-22T00:00:00Z",
        "log_path": str((tmp_path / "hub.log").resolve()),
    }
    values.update(changes)
    return lifecycle.HubDiscoveryRecord(**values)


def _health(record: lifecycle.HubDiscoveryRecord) -> dict[str, object]:
    return {
        "status": "ok",
        "service": {"name": lifecycle.SERVICE_NAME, "version": __version__},
        "process": {"pid": record.pid, "executable": record.executable},
        "service_generation": record.service_generation,
        "protocol": {"version": lifecycle.HUB_PROTOCOL_VERSION},
    }


@pytest.mark.parametrize("field", ["service_version", "executable", "protocol"])
def test_identity_proof_rejects_mismatched_runtime_facts(tmp_path, field):
    record = _record(tmp_path)
    health = _health(record)
    if field == "service_version":
        health["service"] = {"name": lifecycle.SERVICE_NAME, "version": "0.0.0"}
    elif field == "executable":
        health["process"] = {"pid": record.pid, "executable": "/unknown/python"}
    else:
        health["protocol"] = {"version": 999}
    assert not lifecycle.health_matches_record(record, health)


def test_discovery_record_is_atomic_private_and_round_trips(tmp_path):
    destination = tmp_path / "runtime" / "hub.json"
    record = _record(tmp_path)

    lifecycle.write_discovery(record, destination)

    assert lifecycle.load_discovery(destination) == record
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert list(destination.parent.glob("*.tmp")) == []


def test_discovery_rejects_symlink_instead_of_following_it(tmp_path):
    real = tmp_path / "real.json"
    lifecycle.write_discovery(_record(tmp_path), real)
    link = tmp_path / "hub.json"
    link.symlink_to(real)

    with pytest.raises(lifecycle.UnsafeManagedProcess, match="regular file"):
        lifecycle.load_discovery(link)


def test_status_requires_pid_generation_and_service_health_proof(tmp_path, monkeypatch):
    destination = tmp_path / "hub.json"
    record = _record(tmp_path)
    lifecycle.write_discovery(record, destination)
    monkeypatch.setattr(lifecycle, "process_exists", lambda _pid: True)
    monkeypatch.setattr(
        lifecycle,
        "probe_health",
        lambda _port: {**_health(record), "service_generation": "service_other123456789"},
    )

    status = lifecycle.HubServiceManager(record_path=destination).status()

    assert status.running is False
    assert "cannot be proven" in status.detail


def test_lifecycle_probe_does_not_fall_back_to_slow_health_after_identity_timeout(
    monkeypatch,
):
    requested: list[str] = []

    def request(_port, path):
        requested.append(path)
        return 0, None

    monkeypatch.setattr(lifecycle, "_request_json", request)

    assert lifecycle.probe_health(43123) is None
    assert requested == ["/api/v3/identity"]


def test_lifecycle_probe_falls_back_for_managed_build_without_identity_endpoint(
    tmp_path, monkeypatch
):
    record = _record(tmp_path)
    requested: list[str] = []

    def request(_port, path):
        requested.append(path)
        if path == "/api/v3/identity":
            return 404, None
        if path == "/api/v3/health":
            return 200, _health(record)
        raise AssertionError("unexpected health endpoint")

    monkeypatch.setattr(lifecycle, "_request_json", request)

    assert lifecycle.probe_health(record.port) == _health(record)
    assert requested == ["/api/v3/identity", "/api/v3/health"]


def test_detailed_diagnostics_must_match_fast_identity(tmp_path, monkeypatch):
    record = _record(tmp_path)
    identity = _health(record)
    monkeypatch.setattr(lifecycle, "probe_health", lambda _port: identity)
    detailed = {**identity, "hub_directory": {"schema_version": 3}}
    monkeypatch.setattr(
        lifecycle,
        "_request_json",
        lambda _port, _path, **_kwargs: (200, detailed),
    )
    assert lifecycle.probe_diagnostics(record.port) == detailed

    mismatched = {
        **detailed,
        "service_generation": "service_different12345678",
    }
    monkeypatch.setattr(
        lifecycle,
        "_request_json",
        lambda _port, _path, **_kwargs: (200, mismatched),
    )
    assert lifecycle.probe_diagnostics(record.port) is None


def test_detailed_diagnostics_timeout_does_not_change_identity_proof(
    tmp_path, monkeypatch
):
    record = _record(tmp_path)
    identity = _health(record)
    monkeypatch.setattr(lifecycle, "probe_health", lambda _port: identity)
    monkeypatch.setattr(
        lifecycle,
        "_request_json",
        lambda _port, _path, **_kwargs: (0, None),
    )
    assert lifecycle.probe_diagnostics(record.port) is None
    assert lifecycle.health_matches_record(record, identity)


def test_stop_refuses_unknown_live_pid_without_sending_signal(tmp_path, monkeypatch):
    destination = tmp_path / "hub.json"
    record = _record(tmp_path)
    lifecycle.write_discovery(record, destination)
    monkeypatch.setattr(lifecycle, "process_exists", lambda _pid: True)
    monkeypatch.setattr(lifecycle, "probe_health", lambda _port: None)
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(lifecycle.os, "kill", lambda pid, sig: signals.append((pid, sig)))

    with pytest.raises(lifecycle.UnsafeManagedProcess, match="Refusing to stop"):
        lifecycle.HubServiceManager(record_path=destination).stop()

    assert signals == []
    assert destination.exists()


def test_stop_is_idempotent_and_clears_a_stale_record(tmp_path, monkeypatch):
    destination = tmp_path / "hub.json"
    lifecycle.write_discovery(_record(tmp_path), destination)
    monkeypatch.setattr(lifecycle, "process_exists", lambda _pid: False)
    manager = lifecycle.HubServiceManager(record_path=destination)

    assert manager.stop() is False
    assert manager.stop() is False
    assert not destination.exists()


def test_healthy_installed_build_is_reused_without_spawning(tmp_path, monkeypatch):
    destination = tmp_path / "hub.json"
    record = _record(tmp_path)
    lifecycle.write_discovery(record, destination)
    monkeypatch.setattr(lifecycle, "process_exists", lambda _pid: True)
    monkeypatch.setattr(lifecycle, "probe_health", lambda _port: _health(record))
    monkeypatch.setattr(
        lifecycle.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not spawn")),
    )
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "home"))

    actual = lifecycle.HubServiceManager(record_path=destination).ensure_running()

    assert actual == record


def test_detached_service_does_not_inherit_a_transient_cmux_socket(monkeypatch):
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux/socket")

    environment = lifecycle._service_environment()

    assert "CMUX_WORKSPACE_ID" not in environment
    assert "CMUX_SOCKET_PATH" not in environment


def test_managed_http_service_is_detached_even_when_cli_is_inside_cmux(tmp_path, monkeypatch):
    destination = tmp_path / "a folder" / "runtime" / "hub.json"
    published: dict[str, lifecycle.HubDiscoveryRecord] = {}
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux/socket")
    monkeypatch.setattr(lifecycle, "load_discovery", lambda _path: published.get("record"))
    monkeypatch.setattr(lifecycle, "_installed_cli_executable", lambda: Path("/installed/scholar-workflow"))

    class DetachedChild:
        pid = 4242

        def __init__(self, argv: list[str], **kwargs: object) -> None:
            calls.append(kwargs)
            generation = argv[argv.index("--generation") + 1]
            published["record"] = _record(
                tmp_path,
                service_generation=generation,
                log_path=str(destination.parent / "hub.log"),
            )

        @staticmethod
        def poll() -> None:
            return None

    monkeypatch.setattr(lifecycle.subprocess, "Popen", DetachedChild)
    monkeypatch.setattr(
        lifecycle,
        "probe_health",
        lambda _port: _health(published["record"]),
    )

    result = lifecycle.HubServiceManager(record_path=destination).ensure_running()

    assert result == published["record"]
    assert len(calls) == 1
    assert calls[0]["start_new_session"] is True
    assert "CMUX_SOCKET_PATH" not in calls[0]["env"]
    assert "CMUX_WORKSPACE_ID" not in calls[0]["env"]


def test_detached_process_uses_ephemeral_port_and_disables_workspace_gate(
    tmp_path,
    monkeypatch,
):
    calls: list[dict[str, object]] = []
    written: list[lifecycle.HubDiscoveryRecord] = []
    removed: list[lifecycle.HubDiscoveryRecord] = []

    class Server:
        server_address = ("127.0.0.1", 45678)

        def shutdown(self):
            calls.append({"shutdown": True})

        def server_close(self):
            calls.append({"closed": True})

    class ImmediateEvent:
        @staticmethod
        def wait():
            return True

        @staticmethod
        def set():
            pass

    monkeypatch.setattr(
        service_process,
        "load_config",
        lambda: SimpleNamespace(
            link_service=SimpleNamespace(storage_root=tmp_path / "storage"),
            research_vault_root=None,
        ),
    )
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(
        service_process,
        "start_hub_server",
        lambda **kwargs: calls.append(kwargs) or Server(),
    )
    monkeypatch.setattr(service_process, "load_discovery", lambda _path: None)
    monkeypatch.setattr(
        service_process,
        "write_discovery",
        lambda record, _path: written.append(record),
    )
    monkeypatch.setattr(
        service_process,
        "remove_discovery_if_owned",
        lambda record, _path: removed.append(record),
    )
    monkeypatch.setattr(service_process.threading, "Event", ImmediateEvent)
    monkeypatch.setattr(service_process.signal, "signal", lambda *_args: None)

    result = service_process.run(
        [
            "--generation",
            "service_1234567890abcdef",
            "--discovery",
            str(tmp_path / "runtime" / "hub.json"),
            "--log",
            str(tmp_path / "runtime" / "hub.log"),
        ]
    )

    assert result == 0
    assert calls[0]["port"] == 0
    assert calls[0]["require_workspace_binding"] is False
    assert calls[0]["owner_mode"] == "headless"
    assert calls[0]["vault_root"] == (
        tmp_path / "state" / "hub" / "empty-compatibility-vault"
    )
    assert calls[0]["vault_root"].is_dir()
    assert written[0].port == 45678
    assert written[0].protocol_version == 3
    assert removed == written
