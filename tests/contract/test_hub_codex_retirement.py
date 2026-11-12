"""Retired entry points must not reactivate the old Codex execution broker."""
from __future__ import annotations

import importlib.util
import json

import pytest
from types import SimpleNamespace

from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.hub import terminal_worker


def _unexpected(*_args, **_kwargs):
    raise AssertionError("Retired Codex control must not inspect or launch an executable")


def test_retired_cli_configure_does_not_probe_or_write_state(tmp_path, monkeypatch):
    executable = tmp_path / "codex"
    executable.write_text("not an executable", encoding="utf-8")
    state = tmp_path / "state"
    monkeypatch.setattr("scholar_workflow.hub.tasks.CodexCapabilityProbe.probe", _unexpected)

    result = CliRunner().invoke(main, ["hub", "codex", "configure", "--executable",
        str(executable), "--model", "legacy-model"], env={"SCHOLAR_WORKFLOW_HOME": str(state)})

    assert result.exit_code == 7
    assert "retired" in result.output.lower()
    assert "external" in result.output.lower()
    assert not state.exists()


def test_retired_worker_entry_does_not_read_queue_or_construct_worker(tmp_path, monkeypatch, capsys):
    state = tmp_path / "legacy-worker"
    monkeypatch.setattr(terminal_worker.TerminalSlotWorker, "from_state", _unexpected)
    monkeypatch.setattr(terminal_worker, "TerminalWorkerState", _unexpected)

    result = terminal_worker.main(["--state-root", str(state), "--slot", "old-slot",
                                  "--generation", "old-generation"])

    assert result == 7
    message = json.loads(capsys.readouterr().err)
    assert message["type"] == "scholar_workflow.worker.retired"
    assert "external" in message["detail"].lower()
    assert not state.exists()


def test_retired_status_preserves_unconfigured_state_without_probing(tmp_path, monkeypatch):
    state = tmp_path / "state"
    monkeypatch.setattr("scholar_workflow.hub.tasks.CodexCapabilityProbe.probe", _unexpected)

    result = CliRunner().invoke(main, ["hub", "codex", "status"],
                               env={"SCHOLAR_WORKFLOW_HOME": str(state)})

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["retired"] is True
    assert payload["available"] is False
    assert payload["configured"] is False
    assert not state.exists()


def test_retired_status_can_read_retained_metadata_without_activation(tmp_path, monkeypatch):
    state = tmp_path / "state"
    worker = terminal_worker.TerminalWorkerState(state / "hub" / "task-worker")
    worker.root.mkdir(parents=True)
    worker.runtime_path.write_text("retained fixture", encoding="utf-8")
    before = worker.runtime_path.read_bytes()
    monkeypatch.setattr("scholar_workflow.hub.tasks.CodexCapabilityProbe.probe", _unexpected)
    monkeypatch.setattr(terminal_worker.TerminalWorkerState, "current_runtime",
        lambda _self: SimpleNamespace(recipe_registry_path=state / "legacy-recipes.json"))
    monkeypatch.setattr("scholar_workflow.hub.tasks.TaskRecipeRegistry.load",
        lambda _self: SimpleNamespace(recipes=[SimpleNamespace(recipe_id="old-recipe")]))

    result = CliRunner().invoke(main, ["hub", "codex", "status"],
                               env={"SCHOLAR_WORKFLOW_HOME": str(state)})

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["configured"] is True
    assert payload["recipes"] == ["old-recipe"]
    assert payload["retired"] is True
    assert payload["available"] is False
    assert worker.runtime_path.read_bytes() == before


@pytest.mark.parametrize("module", [
    "scholar_workflow.hub.codex_setup",
    "scholar_workflow.hub.task_control",
    "scholar_workflow.hub.target_setup",
    "scholar_workflow.workflows.service",
    "scholar_workflow.workflows.document",
])
def test_removed_private_execution_and_archival_modules_are_not_importable(module):
    assert importlib.util.find_spec(module) is None


@pytest.mark.parametrize("command", ["serve-links", "install-service"])
def test_retired_service_entry_never_installs_or_starts_a_process(tmp_path, monkeypatch, command):
    import subprocess
    state = tmp_path / "state"
    monkeypatch.setattr(subprocess, "Popen", _unexpected)
    result = CliRunner().invoke(main, [command], env={"SCHOLAR_WORKFLOW_HOME": str(state)})
    assert result.exit_code == 3, result.output
    assert "retired" in result.output.lower()
    assert not state.exists()
