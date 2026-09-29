"""Contract tests for the cmux-first ``open-hub`` CLI entry point."""
from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.cli import main
from scholar_workflow.hub import lifecycle
from scholar_workflow.hub.actions import CmuxUnavailable
from scholar_workflow.hub.cmux import CmuxControl


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


def test_cmux_terminal_worker_uses_server_owned_command_and_target_cwd(tmp_path):
    cmux = tmp_path / "cmux"
    cmux.write_text("", encoding="utf-8")
    cmux.chmod(0o755)
    target = tmp_path / "registered-target"
    target.mkdir()
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return _completed()

    control = CmuxControl(configured_path=cmux, runner=runner)
    control.new_terminal_worker(
        workspace_id="workspace:7",
        working_directory=target,
        command="/installed/python -m scholar_workflow.hub.terminal_worker --slot slot_A",
    )

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [
        str(cmux),
        "new-surface",
        "--type",
        "terminal",
        "--working-directory",
        str(target.resolve()),
        "--workspace",
        "workspace:7",
        "--command",
        "/installed/python -m scholar_workflow.hub.terminal_worker --slot slot_A",
        "--focus",
        "true",
    ]
    assert kwargs["shell"] is False
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True


def _managed_record(tmp_path: Path, *, port: int = 45678):
    return lifecycle.HubDiscoveryRecord(
        schema_version=1,
        service_name="scholar-workflow-hub",
        pid=4242,
        port=port,
        executable="/installed/python",
        package_version="0.29.0",
        build_hash="sha256:" + "a" * 64,
        protocol_version=3,
        service_generation="service_1234567890abcdef",
        started_at="2026-09-23T00:00:00Z",
        log_path=str((tmp_path / "hub.log").resolve()),
    )


def _use_managed_record(monkeypatch, record):
    monkeypatch.setattr(cli, "_ensure_hub_router", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type(
            "Manager",
            (),
            {"ensure_running": lambda self: record},
        )(),
    )


def test_open_hub_uses_exact_cmux_argv_and_no_shell(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    record = _managed_record(tmp_path)
    _use_managed_record(monkeypatch, record)
    cmux = tmp_path / "cmux"
    cmux.write_text("", encoding="utf-8")
    cmux.chmod(0o755)
    calls: list[tuple[list[str], dict[str, object]]] = []
    destinations: list[tuple[int, str, str]] = []
    monkeypatch.setattr(
        cli,
        "_register_default_destination",
        lambda port, instance, workspace: destinations.append(
            (port, instance, workspace)
        )
        or True,
    )
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
        "http://127.0.0.1:45678/hub/?instance=instance_A234567890abcdef"
    )
    assert result.exit_code == 0, result.output
    assert destinations == [(45678, "instance_A234567890abcdef", "workspace:7")]
    assert "default opening place" in result.output
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
    record = _managed_record(tmp_path)
    _use_managed_record(monkeypatch, record)
    calls: list[list[str]] = []
    destinations: list[tuple[int, str, str]] = []
    monkeypatch.setattr(
        cli,
        "_register_default_destination",
        lambda port, instance, workspace: destinations.append(
            (port, instance, workspace)
        )
        or True,
    )
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
    assert parsed.port == 45678
    assert parsed.path == "/hub/"
    assert instance.startswith("hub_")
    assert len(instance) >= 24
    assert all(char.isalnum() or char in "_-" for char in instance)
    assert destinations == [(45678, instance, "workspace:7")]


def test_serve_hub_canary_routes_to_ephemeral_mode(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli,
        "_serve_hub_foreground",
        lambda **kwargs: calls.append(kwargs),
    )

    result = CliRunner().invoke(main, ["serve-hub", "--canary", "--port", "0"])

    assert result.exit_code == 0, result.output
    assert calls == [{"port_override": 0, "canary": True}]


def test_open_hub_outside_cmux_remains_readable(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    record = _managed_record(tmp_path)
    _use_managed_record(monkeypatch, record)
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url, new=0: opened.append(url) or True)

    result = CliRunner().invoke(
        main,
        ["open-hub"],
        env={
            "SCHOLAR_WORKFLOW_HOME": str(home),
            "CMUX_WORKSPACE_ID": "",
            "CMUX_SOCKET_PATH": "",
        },
    )

    assert result.exit_code == 0, result.output
    assert len(opened) == 1
    assert opened[0].startswith("http://127.0.0.1:45678/hub/?instance=hub_")
    assert "choose a cmux destination" in result.output


def test_open_hub_starts_managed_service_automatically(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    record = _managed_record(tmp_path)
    starts: list[bool] = []
    routed: list[str] = []
    monkeypatch.setattr(
        lifecycle,
        "HubServiceManager",
        lambda: type(
            "Manager",
            (),
            {
                "ensure_running": lambda self: starts.append(True) or record
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "_ensure_hub_router",
        lambda _record, workspace: routed.append(workspace),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "_register_default_destination", lambda *_args: True)
    monkeypatch.setattr(cli, "_resolve_cmux_executable", lambda: Path("/safe/cmux"))
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda argv, **_kwargs: calls.append(argv) or _completed(),
    )

    result = CliRunner().invoke(main, ["open-hub"], env=_cmux_env(home))

    assert result.exit_code == 0, result.output
    assert starts == [True]
    assert routed == ["workspace:7"]
    assert calls[0][2].startswith("http://127.0.0.1:45678/hub/")


def test_open_hub_maps_missing_cmux_to_dependency_error(tmp_path, monkeypatch):
    home = _configured_home(tmp_path)
    _use_managed_record(monkeypatch, _managed_record(tmp_path))
    monkeypatch.setattr(cli, "_register_default_destination", lambda *_args: True)

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
    _use_managed_record(monkeypatch, _managed_record(tmp_path))
    calls: list[list[str]] = []
    monkeypatch.setattr(cli, "_register_default_destination", lambda *_args: True)
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


def test_open_hub_rejects_non_opaque_instance_before_probe(tmp_path):
    home = _configured_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["open-hub", "--instance", "../../secret?token=value"],
        env=_cmux_env(home),
    )

    assert result.exit_code == 2
    assert "URL-safe opaque identifier" in result.output
