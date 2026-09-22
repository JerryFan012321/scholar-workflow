import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
SHA = "a" * 64
RUN_ID = "20260922-1200-baseline"


def schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def test_project_layout_requires_portable_project_identity() -> None:
    payload = {
        "schema_version": 2,
        "project_id": "01234567-89ab-4def-8123-456789abcdef",
        "language": "python",
        "package": "demo_project",
        "source_profile": {"id": "multi-stage-3d", "version": 1},
        "addons": [{"id": "native-kernels", "version": 1}],
    }
    jsonschema.validate(payload, schema("project-layout.schema.json"))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(payload, project_id="/host/project"), schema("project-layout.schema.json"))


def test_run_contract_separates_recipe_from_attempt_runtime() -> None:
    file_snapshot = {"path": "experiments/run/input.yaml", "sha256": SHA}
    payload = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "created_at": "2026-09-22T12:00:00Z",
        "record_state": "frozen",
        "source": {"commit": "b" * 40},
        "entrypoint": {"path": "experiments/run/run.sh", "sha256": SHA},
        "config": file_snapshot,
        "dataset": {
            "dataset_id": "demo",
            "version": "1",
            "split": "train",
            "manifest": file_snapshot,
        },
        "seed": 7,
        "environment": file_snapshot,
        "recipe_hash": SHA,
    }
    jsonschema.validate(payload, schema("experiment-run.schema.json"))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dict(payload, hostname="gpu-a"), schema("experiment-run.schema.json"))


def test_target_contract_rejects_secrets_commands_and_implicit_local() -> None:
    target = {
        "schema_version": 1,
        "target_id": "local",
        "kind": "local",
        "server_alias": None,
        "project_root": "/project",
        "output_root": "/output",
        "executor": {"kind": "shell"},
        "environment_bindings": {"training": "env-name"},
    }
    jsonschema.validate(target, schema("experiment-target.schema.json"))

    for forbidden in ({"token": "secret"}, {"command": "rm -rf x"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(target | forbidden, schema("experiment-target.schema.json"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(target | {"kind": None}, schema("experiment-target.schema.json"))


def test_attempt_contract_keeps_target_snapshot_and_runtime_observations() -> None:
    actual = {
        key: None
        for key in (
            "working_directory", "output_location", "log_location", "hostname", "os",
            "gpu", "driver", "cuda", "python", "commit", "recipe_hash"
        )
    }
    attempt = {
        "schema_version": 1,
        "attempt_id": "attempt-01",
        "run_id": RUN_ID,
        "target_id": "local",
        "target_profile_sha256": SHA,
        "status": "planned",
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "actual": actual,
        "output_inventory": None,
    }
    jsonschema.validate(attempt, schema("experiment-attempt.schema.json"))


def test_artifact_contract_does_not_equate_promotion_with_backup() -> None:
    artifact = {
        "artifact_id": "art_0123456789abcdef",
        "role": "checkpoint",
        "retention": "local-selected",
        "source_attempt_id": "attempt-01",
        "relative_path": "artifacts/model.ckpt",
        "size": 42,
        "sha256": SHA,
        "remote_source": "gpu-a:/results/model.ckpt",
        "promoted_at": "2026-09-22T12:30:00Z",
        "backup": {
            "state": "not-verified",
            "verified_at": None,
            "location": None,
            "sha256": None,
        },
    }
    jsonschema.validate(
        {"schema_version": 1, "run_id": RUN_ID, "artifacts": [artifact]},
        schema("experiment-artifact.schema.json"),
    )

    falsely_verified = {
        **artifact,
        "backup": {
            "state": "verified",
            "verified_at": "2026-09-22T12:45:00Z",
            "location": "disk-b:/backups/model.ckpt",
            "sha256": SHA,
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"schema_version": 1, "run_id": RUN_ID, "artifacts": [falsely_verified]},
            schema("experiment-artifact.schema.json"),
        )

    invalid = artifact | {"retention": "manifest-only", "remote_source": None}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"schema_version": 1, "run_id": RUN_ID, "artifacts": [invalid]},
            schema("experiment-artifact.schema.json"),
        )
