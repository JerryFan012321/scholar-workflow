"""Synthetic launchd definitions and ownership checks; never touch a real job."""
import plistlib
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import background


@pytest.fixture
def managed(tmp_path, monkeypatch):
    monkeypatch.setattr(background.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    state = tmp_path / "state/recommendations/personal"
    state.mkdir(parents=True)
    calls = []
    loaded = [False]
    def launch(*args):
        calls.append(args)
        _, path = background.identity(state)
        output = f"path = {path}\nprogram = {background.sys.executable}\n"
        if args[0] == "print":
            return CompletedProcess(args, 0 if loaded[0] else 113, output, "")
        if args[0] == "bootstrap":
            loaded[0] = True
        elif args[0] == "bootout":
            loaded[0] = False
        return CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(background, "_launchctl", launch)
    return state, calls, loaded


def test_install_reuse_remove_and_private_secret_free_definition(managed):
    state, calls, loaded = managed
    background.install(state)
    _, path = background.identity(state)
    config = plistlib.loads(path.read_bytes())
    assert config["KeepAlive"] == {"SuccessfulExit": False}
    assert config["RunAtLoad"] is True
    assert config["ProgramArguments"][-1] == "serve-managed"
    assert config["EnvironmentVariables"] == {"SCHOLAR_WORKFLOW_HOME": str(state.parent.parent)}
    assert "token" not in path.read_text() and "generation" not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    assert background.status(state, "personal")["supervised"]
    background.install(state)
    assert len([c for c in calls if c[0] == "bootstrap"]) == 1
    background.remove(state, "personal")
    assert not loaded[0] and not path.exists()
    background.remove(state, "personal")
    assert len([c for c in calls if c[0] == "bootout"]) == 1


def test_test_pool_never_touches_launchd(managed):
    state, calls, _ = managed
    assert background.status(state, "test") == {"manager": "detached", "login_start": False, "supervised": False}
    background.remove(state, "test")
    assert calls == []


def test_foreign_definition_is_not_overwritten_or_removed(managed):
    state, calls, _ = managed
    _, path = background.identity(state)
    path.parent.mkdir(parents=True)
    path.write_bytes(plistlib.dumps({"Label": "foreign"})); path.chmod(0o600)
    before = path.read_bytes()
    with pytest.raises(ResearchError):
        background.install(state)
    with pytest.raises(ResearchError):
        background.remove(state, "personal")
    assert path.read_bytes() == before and calls == []


def test_foreign_loaded_job_without_owned_plist_is_not_stopped(managed, monkeypatch):
    state, _, _ = managed
    monkeypatch.setattr(background, "_launchctl", lambda *args: CompletedProcess(args, 0, "program = /foreign/python", ""))
    with pytest.raises(ResearchError):
        background.remove(state, "personal")


def test_failed_bootstrap_reports_failure_not_supervised(managed, monkeypatch):
    state, _, _ = managed
    monkeypatch.setattr(background, "_launchctl", lambda *args: CompletedProcess(args, 5, "", ""))
    with pytest.raises(ResearchError, match="could not load"):
        background.install(state)
    assert not background.status(state, "personal")["supervised"]


def test_plist_symlink_is_refused(managed):
    state, calls, _ = managed
    _, path = background.identity(state)
    path.parent.mkdir(parents=True)
    target = state / "elsewhere"
    target.write_bytes(plistlib.dumps(background.definition(state)))
    target.chmod(0o600)
    path.symlink_to(target)
    with pytest.raises(ResearchError):
        background.install(state)
    assert calls == [] and target.exists()
