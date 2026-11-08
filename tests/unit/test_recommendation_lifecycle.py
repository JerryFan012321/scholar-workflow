"""Owned-service lifecycle boundaries, with synthetic runtime records only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import lifecycle


def record():
    return {"generation": "g" * 32, "pid": 999999, "port": 45678, "token": "t" * 43,
            "profile": "test", "version": "0.0.0", "build": "test-build",
            "started_at": "2026-11-08T00:00:00Z", "executable": "/synthetic/python"}


def test_status_never_emits_session_token(tmp_path, monkeypatch):
    runtime = record()
    monkeypatch.setattr(lifecycle, "_read_runtime", lambda path: runtime)
    monkeypatch.setattr(lifecycle, "_health", lambda value: value)
    result = lifecycle.status(tmp_path, "test")
    assert result["status"] == "running"
    assert runtime["token"] not in json.dumps(result)
    assert runtime["generation"] not in json.dumps(result)


def test_unknown_live_process_is_never_stopped(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "_health", lambda value: None)
    monkeypatch.setattr(lifecycle, "_alive", lambda pid: True)
    with pytest.raises(ResearchError) as error:
        lifecycle._stop_record(tmp_path, record())
    assert error.value.exit_code == 7


def test_runtime_must_be_private_and_not_symlinked(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    runtime = state / "runtime.json"
    runtime.write_text(json.dumps(record()))
    runtime.chmod(0o644)
    with pytest.raises(ResearchError):
        lifecycle._read_runtime(state)
    runtime.chmod(0o600)
    assert lifecycle._read_runtime(state)["profile"] == "test"
    other = tmp_path / "other"
    other.mkdir()
    (other / "runtime.json").symlink_to(runtime)
    with pytest.raises(ResearchError):
        lifecycle._read_runtime(other)


def test_runtime_record_is_atomic_and_private(tmp_path):
    lifecycle.ensure_private_dir(tmp_path / "state")
    lifecycle._write_runtime(tmp_path / "state", record())
    assert ((tmp_path / "state/runtime.json").stat().st_mode & 0o777) == 0o600
    assert lifecycle._read_runtime(tmp_path / "state") == record()


def test_profile_mismatch_is_a_safety_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "_read_runtime", lambda path: record())
    with pytest.raises(ResearchError) as error:
        lifecycle.status(tmp_path, "personal")
    assert error.value.exit_code == 7


def test_private_directory_rejects_symlink_ancestor(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ResearchError):
        lifecycle.ensure_private_dir(link / "state")
    assert not (actual / "state").exists()
