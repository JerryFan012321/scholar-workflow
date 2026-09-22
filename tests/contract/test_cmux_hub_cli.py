"""Contract tests for the cmux-first ``open-hub`` CLI entry point."""
from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.cli import main
from scholar_workflow.hub.actions import CmuxUnavailable


def _configured_home(tmp_path: Path, *, port: int = 24680) -> Path:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    storage = tmp_path / "storage"
    home.mkdir()
    vault.mkdir()
    storage.mkdir()
    (home / "config.yml").write_text(
        "version: 1\n"
        f"research_vault_root: {vault}\n"
        "link_service:\n"
        f"  port: {port}\n"
        f"  storage_root: {storage}\n",
        encoding="utf-8",
    )
    return home


def _cmux_env(home: Path) -> dict[str, str]:
    return {
        "SCHOLAR_WORKFLOW_HOME": str(home),
        "CMUX_WORKSPACE_ID": "workspace:7",
        "CMUX_SOCKET_PATH": "/tmp/cmux-session/socket",
        "SCHOLAR_WORKFLOW_NOTION_TOKEN": "must-not-appear-in-the-url",
    }


def _completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout="", stderr=stderr)


def test_open_hub_uses_exact_cmux_argv_and_no_shell(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    cmux = tmp_path / "cmux"
    cmux.write_text("", encoding="utf-8")
    cmux.chmod(0o755)
    calls: list[tuple[list[str], dict[str, object]]] = []
    probes: list[int] = []

    monkeypatch.setattr(cli, "_probe_hub_health", lambda port: probes.append(port))
    monkeypatch.setattr(cli, "_resolve_cmux_executable", lambda: cmux)

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed()

    monkeypatch.setattr(cli.subprocess, "run", runner)
    result = CliRunner().invoke(
        main,
        ["open-hub", "--instance", "instance_A234567890abcdef"],
        env=_cmux_env(home),
    )

    expected_url = (
        "http://127.0.0.1:24680/hub/?instance=instance_A234567890abcdef"
    )
    assert result.exit_code == 0, result.output
    assert probes == [24680]
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        str(cmux),
        "open",
        expected_url,
        "--workspace",
        "workspace:7",
        "--focus",
        "true",
    ]
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["env"]["CMUX_SOCKET_PATH"] == "/tmp/cmux-session/socket"
    assert "SCHOLAR_WORKFLOW_NOTION_TOKEN" not in kwargs["env"]
    assert "/tmp/cmux-session/socket" not in expected_url
    assert str(home) not in expected_url
    assert "must-not-appear-in-the-url" not in expected_url


def test_open_hub_generates_a_url_safe_opaque_instance(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "_probe_hub_health", lambda _port: None)
    monkeypatch.setattr(cli, "_resolve_cmux_executable", lambda: Path("/safe/cmux"))

    def runner(argv, **_kwargs):
        calls.append(argv)
        return _completed()

    monkeypatch.setattr(cli.subprocess, "run", runner)
    result = CliRunner().invoke(main, ["open-hub"], env=_cmux_env(home))

    assert result.exit_code == 0, result.output
    parsed = urlsplit(calls[0][2])
    instance = parse_qs(parsed.query)["instance"][0]
    assert parsed.scheme == "http"
    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 24680
    assert parsed.path == "/hub/"
    assert instance.startswith("hub_")
    assert len(instance) >= 24
    assert all(char.isalnum() or char in "_-" for char in instance)


def test_serve_hub_canary_routes_to_ephemeral_read_only_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "_serve_hub_foreground",
        lambda **kwargs: calls.append(kwargs),
    )

    result = CliRunner().invoke(main, ["serve-hub", "--canary", "--port", "0"])

    assert result.exit_code == 0, result.output
    assert calls == [{"port_override": 0, "canary": True}]


def test_open_hub_requires_a_cmux_runtime_context(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    monkeypatch.setattr(
        cli,
        "_probe_hub_health",
        lambda _port: (_ for _ in ()).throw(AssertionError("must not probe")),
    )

    result = CliRunner().invoke(
        main,
        ["open-hub"],
        env={
            "SCHOLAR_WORKFLOW_HOME": str(home),
            "CMUX_WORKSPACE_ID": "",
            "CMUX_SOCKET_PATH": "",
        },
    )

    assert result.exit_code == 3
    assert "inside a cmux workspace" in result.output


def test_open_hub_reports_stopped_hub_without_starting_it(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    calls: list[list[str]] = []
    health_calls: list[tuple[str, int, float]] = []

    class UnavailableConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            health_calls.append((host, port, timeout))

        def request(self, method: str, path: str) -> None:
            assert (method, path) == ("GET", "/api/v1/health")
            raise ConnectionRefusedError

        def close(self) -> None:
            pass

    monkeypatch.setattr(cli.http.client, "HTTPConnection", UnavailableConnection)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda argv, **_kwargs: calls.append(argv) or _completed(),
    )

    result = CliRunner().invoke(main, ["open-hub"], env=_cmux_env(home))

    assert result.exit_code == 3
    assert "serve-hub" in result.output
    assert health_calls == [("127.0.0.1", 24680, 1.5)]
    assert calls == []


def test_health_probe_rejects_an_old_hub_without_cmux_capability(monkeypatch):
    class OldResponse:
        status = 200

        @staticmethod
        def read(_limit):
            return b'{"status":"ok","schema_version":1}'

    class OldHubConnection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert (host, port, timeout) == ("127.0.0.1", 23128, 1.5)

        @staticmethod
        def request(method: str, path: str) -> None:
            assert (method, path) == ("GET", "/api/v1/health")

        @staticmethod
        def getresponse():
            return OldResponse()

        @staticmethod
        def close() -> None:
            pass

    monkeypatch.setattr(cli.http.client, "HTTPConnection", OldHubConnection)

    with pytest.raises(cli.DependencyError, match="Restart it"):
        cli._probe_hub_health(23128)


def test_open_hub_maps_missing_cmux_to_dependency_error(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    monkeypatch.setattr(cli, "_probe_hub_health", lambda _port: None)

    def missing():
        raise CmuxUnavailable("cmux CLI was not found")

    monkeypatch.setattr(cli, "_resolve_cmux_executable", missing)
    result = CliRunner().invoke(main, ["open-hub"], env=_cmux_env(home))

    assert result.exit_code == 3
    assert "cmux CLI was not found" in result.output


def test_open_hub_maps_cmux_failure_to_external_service_without_fallback(
    tmp_path, monkeypatch
):
    home = _configured_home(tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "_probe_hub_health", lambda _port: None)
    monkeypatch.setattr(cli, "_resolve_cmux_executable", lambda: Path("/safe/cmux"))

    def runner(argv, **_kwargs):
        calls.append(argv)
        return _completed(1, "No live cmux socket found")

    monkeypatch.setattr(cli.subprocess, "run", runner)
    result = CliRunner().invoke(main, ["open-hub"], env=_cmux_env(home))

    assert result.exit_code == 8
    assert "No live cmux socket found" in result.output
    assert len(calls) == 1
    assert calls[0][0] == "/safe/cmux"
    assert "/usr/bin/open" not in calls[0]


def test_open_hub_rejects_non_opaque_instance_before_probe(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    monkeypatch.setattr(
        cli,
        "_probe_hub_health",
        lambda _port: (_ for _ in ()).throw(AssertionError("must not probe")),
    )

    result = CliRunner().invoke(
        main,
        ["open-hub", "--instance", "../../secret?token=value"],
        env=_cmux_env(home),
    )

    assert result.exit_code == 2
    assert "URL-safe opaque identifier" in result.output


def test_codex_working_directory_is_enabled_only_for_cmux_terminal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("CMUX_SOCKET_PATH", raising=False)

    assert cli._cmux_codex_working_directory() is None

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux-session/socket")
    assert cli._cmux_codex_working_directory() == tmp_path.resolve()


def test_hub_owner_mode_requires_a_complete_clean_cmux_environment(monkeypatch):
    monkeypatch.delenv("CMUX_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("CMUX_SOCKET_PATH", raising=False)
    assert cli._hub_owner_mode() == "headless"

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7")
    assert cli._hub_owner_mode() == "headless"

    monkeypatch.setenv("CMUX_SOCKET_PATH", "/tmp/cmux-session/socket")
    assert cli._hub_owner_mode() == "cmux-visible"

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace:7\nforged")
    assert cli._hub_owner_mode() == "headless"
