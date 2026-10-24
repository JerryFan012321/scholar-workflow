"""Prepared synthetic network-runner checks; no real socket or user configuration."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


def source(identifier="blog", **changes):
    return {"channel_id": identifier, "name": "Sample " + identifier, "publisher": "Sample Lab",
            "publisher_kind": "lab", "kind": "rss", "url": f"https://example.org/{identifier}.xml",
            "enabled": True, "topics": [], **changes}


def observed(revision="first"):
    return {"status": "ok", "items": [{"item_id": "article", "title": "A model release",
            "url": "https://example.org/article", "content_digest": "sha256:" +
            hashlib.sha256(revision.encode()).hexdigest()}]}


def test_runner_baseline_repeat_and_real_update(tmp_path, monkeypatch):
    from scholar_workflow.research import read_updates, register_source, runner

    register_source(tmp_path, source())
    responses = iter([observed(), observed(), observed("second")])
    monkeypatch.setattr(runner, "fetch_channel", lambda *_a, **_k: next(responses))
    initial = runner.run_check(tmp_path, checked_at="2026-10-24T12:00:00+00:00")
    assert initial["events"] == [] and initial["check_results"][0]["status"] == "baseline"
    repeated = runner.run_check(tmp_path, checked_at="2026-10-24T13:00:00+00:00")
    assert repeated["events"] == []
    changed = runner.run_check(tmp_path, checked_at="2026-10-24T14:00:00+00:00")
    assert [event["kind"] for event in changed["events"]] == ["updated"]
    assert len(read_updates(tmp_path)["events"]) == 1


def test_runner_failed_and_disabled_channels_do_not_hide_success(tmp_path, monkeypatch):
    from scholar_workflow.research import register_source, runner

    for identifier in ("good", "bad"):
        register_source(tmp_path, source(identifier))
    register_source(tmp_path, source("disabled", enabled=False))
    calls = []

    def fetch(channel, **_kwargs):
        calls.append(channel["channel_id"])
        if channel["channel_id"] == "bad":
            return {"status": "failed", "diagnostic": {"code": "network_error", "message": "Unavailable"}}
        return observed()

    monkeypatch.setattr(runner, "fetch_channel", fetch)
    result = runner.run_check(tmp_path, initial_mode="report", checked_at="2026-10-24T12:00:00+00:00")
    assert result["status"] == "partial"
    assert set(calls) == {"good", "bad"}
    assert [event["channel_id"] for event in result["events"]] == ["good"]
    assert len(result["check_results"]) == 3


def test_runner_unknown_selection_does_not_make_state(tmp_path):
    from scholar_workflow.research import ResearchError
    from scholar_workflow.research.runner import run_check

    absent = tmp_path / "absent"
    with pytest.raises(ResearchError):
        run_check(absent, channel_ids=["unknown"])
    assert not absent.exists()


def test_runner_entrypoint_is_packaged_and_wrapper_is_thin():
    import tomllib

    repository = Path(__file__).resolve().parents[2]
    project = tomllib.loads((repository / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["scholar-research"] == "scholar_workflow.research.runner:main"
    wrapper = (repository / "bin/track-research.py").read_text()
    assert "scholar_workflow.research.runner import main" in wrapper
    assert "httpx" not in wrapper and "sys.path" not in wrapper


@pytest.mark.parametrize("arguments", [["--version"], ["--help"], ["check", "--help"]])
def test_runner_identity_and_help_are_read_only(tmp_path, monkeypatch, arguments):
    from click.testing import CliRunner

    from scholar_workflow import __version__
    from scholar_workflow.research import runner

    absent = tmp_path / "absent"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(absent))
    monkeypatch.setattr(runner, "fetch_channel", lambda *_a, **_k: pytest.fail("Network must not start"))
    result = CliRunner().invoke(runner.main, arguments)
    assert result.exit_code == 0, result.output
    if arguments == ["--version"]:
        assert result.output.strip() == f"scholar-research, version {__version__}"
    else:
        assert "Usage:" in result.output
    assert not absent.exists()


def test_corrupt_tracking_refuses_before_network(tmp_path, monkeypatch):
    from scholar_workflow.research import ResearchError, register_source, runner

    register_source(tmp_path, source())
    state = tmp_path / "research"
    state.mkdir(mode=0o700)
    (state / "tracking.json").write_text("not json")
    monkeypatch.setattr(runner, "fetch_channel", lambda *_a, **_k: pytest.fail("Network must not start"))
    with pytest.raises(ResearchError) as failure:
        runner.run_check(tmp_path)
    assert failure.value.exit_code == 7


def test_overlapping_checks_refuse_before_network(tmp_path, monkeypatch):
    from scholar_workflow.research import ResearchError, check_lock, register_source, runner

    register_source(tmp_path, source())
    monkeypatch.setattr(runner, "fetch_channel", lambda *_a, **_k: pytest.fail("Network must not start"))
    with check_lock(tmp_path), pytest.raises(ResearchError) as failure:
        runner.run_check(tmp_path)
    assert failure.value.exit_code == 5
