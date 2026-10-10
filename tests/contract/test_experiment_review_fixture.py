"""Check handwritten review inputs, not the host model's report behavior."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scholar_workflow.project.models import (
    ArtifactManifest,
    AttemptRecord,
    RunRecord,
    TargetProfile,
)

ROOT = Path(__file__).parents[1] / "fixtures" / "experiment-review" / "project"
RUNS = ("20261009-1000-baseline", "20261009-1100-variant")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_bytes())


def _digest(path: Path) -> str:
    assert not path.is_symlink()
    assert path.resolve().is_relative_to(ROOT.resolve())
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("run_id", RUNS)
def test_run_recipe_inputs_and_captured_targets(run_id):
    folder = ROOT / "experiments" / run_id
    run = RunRecord.model_validate(_yaml(folder / "run.yaml"))
    assert run.run_id == run_id
    for snapshot in (run.entrypoint, run.config, run.dataset.manifest, run.environment):
        assert _digest(ROOT / snapshot.path) == snapshot.sha256
    for path in sorted((folder / "attempts").glob("*/attempt.yaml")):
        attempt = AttemptRecord.model_validate(_yaml(path))
        assert attempt.run_id == run_id
        assert attempt.attempt_id == path.parent.name
        target_path = path.parent / "target.yaml"
        target = TargetProfile.model_validate(_yaml(target_path))
        assert target.target_id == attempt.target_id
        assert _digest(target_path) == attempt.target_profile_sha256
        assert attempt.actual.log_location is not None
        assert (ROOT / attempt.actual.log_location).is_file()


@pytest.mark.parametrize("run_id,score", [(RUNS[0], 0.80), (RUNS[1], 0.85)])
def test_selected_metrics_have_local_byte_and_attempt_identity(run_id, score):
    folder = ROOT / "experiments" / run_id
    manifest = ArtifactManifest.model_validate(_yaml(folder / "artifacts.yaml"))
    assert manifest.run_id == run_id
    assert len(manifest.artifacts) == 1
    artifact = manifest.artifacts[0]
    assert artifact.role == "metrics"
    assert artifact.source_attempt_id == "primary"
    path = folder / artifact.relative_path
    payload = path.read_bytes()
    assert len(payload) == artifact.size
    assert _digest(path) == artifact.sha256
    assert payload == (folder / "attempts" / "primary" / "metrics.json").read_bytes()
    metrics = json.loads(payload)
    assert metrics["metrics"]["accuracy"]["value"] == score
    assert artifact.backup.state == "not-verified"


def test_history_keeps_failure_and_same_run_replay():
    attempts = ROOT / "experiments" / RUNS[0] / "attempts"
    assert {path.name for path in attempts.iterdir()} == {"wrong-cwd", "primary", "replay"}
    failed = AttemptRecord.model_validate(_yaml(attempts / "wrong-cwd" / "attempt.yaml"))
    assert failed.status == "failed" and failed.exit_code == 2
    assert not (attempts / "wrong-cwd" / "metrics.json").exists()
    replay = AttemptRecord.model_validate(_yaml(attempts / "replay" / "attempt.yaml"))
    assert replay.run_id == RUNS[0] and replay.status == "succeeded"
    assert (attempts / "primary" / "metrics.json").read_bytes() == (
        attempts / "replay" / "metrics.json"
    ).read_bytes()
