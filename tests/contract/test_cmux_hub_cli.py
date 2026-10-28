"""Retired front-end entry, with independent cmux and API service contracts."""
from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.cli import main
from scholar_workflow.hub import lifecycle
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


@pytest.mark.parametrize("inside_cmux", [False, True])
@pytest.mark.parametrize("instance", [None, "instance_A234567890abcdef"])
def test_open_hub_is_retired_before_any_runtime_or_browser_side_effect(
    tmp_path: Path, monkeypatch, inside_cmux: bool, instance: str | None,
):
    home = tmp_path / "unused-home"
    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        calls.append("unexpected effect")
        raise AssertionError("retired open-hub must not initialize or launch anything")

    monkeypatch.setattr(lifecycle, "HubServiceManager", forbidden)
    for name in ("_optional_cmux_context", "_ensure_hub_router",
                 "_register_default_destination", "_resolve_cmux_executable"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(webbrowser, "open", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    env = _cmux_env(home)
    if not inside_cmux:
        env.update({"CMUX_WORKSPACE_ID": "", "CMUX_SOCKET_PATH": ""})
    args = ["open-hub"] if instance is None else ["open-hub", "--instance", instance]

    result = CliRunner().invoke(main, args, env=env)

    assert result.exit_code == 3, result.output
    assert "retired" in result.output.lower()
    assert "knowledge explore" in result.output
    assert calls == []
    assert not home.exists()
    assert "must-not-appear-in-the-url" not in result.output


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


def test_serve_hub_foreground_prints_api_and_health_not_frontend(tmp_path, monkeypatch):
    import threading

    from scholar_workflow.hub import server as server_module

    home = _configured_home(tmp_path)
    calls: list[str] = []

    class Server:
        server_address = ("127.0.0.1", 45678)

        def shutdown(self):
            calls.append("shutdown")

    class StopImmediately:
        def wait(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(server_module, "start_hub_server", lambda **_kwargs: Server())
    monkeypatch.setattr(threading, "Event", StopImmediately)
    result = CliRunner().invoke(main, ["serve-hub", "--port", "0"],
                               env={"SCHOLAR_WORKFLOW_HOME": str(home)})

    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:45678/api/v3/directory" in result.output
    assert "http://127.0.0.1:45678/api/v3/health" in result.output
    assert "/hub/" not in result.output
    assert calls == ["shutdown"]


def test_open_hub_rejects_non_opaque_instance_before_probe(tmp_path):
    home = _configured_home(tmp_path)

    result = CliRunner().invoke(
        main,
        ["open-hub", "--instance", "../../secret?token=value"],
        env=_cmux_env(home),
    )

    assert result.exit_code == 2
    assert "URL-safe opaque identifier" in result.output
