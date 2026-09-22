import json
import multiprocessing
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError

from scholar_workflow.cli import main
from scholar_workflow.project import experiments as project_experiments
from scholar_workflow.project.experiments import (
    ExperimentError,
    create_attempt,
    create_run,
    finalize_attempt,
    legacy_migration_plan,
    promote_artifact,
    rebuild_index,
    record_manifest_only_artifact,
    register_target,
    start_attempt,
    validate_project,
)
from scholar_workflow.project.models import BackupRecord

ROOT = Path(__file__).resolve().parents[2]
INIT = ROOT / "skills" / "init-project" / "scripts" / "init_project.py"
RUN_ID = "20260922-1200-baseline"


def _record_remote_in_process(
    project_root: str,
    remote_source: str,
    start_event,
    result_queue,
) -> None:
    """Force a wide manifest read/write window in each child process."""

    original_manifest = project_experiments._artifact_manifest

    def delayed_manifest(root, run_id):
        result = original_manifest(root, run_id)
        time.sleep(0.15)
        return result

    project_experiments._artifact_manifest = delayed_manifest
    start_event.wait(timeout=5)
    try:
        artifact = record_manifest_only_artifact(
            project_root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            remote_source=remote_source,
            role="other",
        )
    except (ExperimentError, OSError) as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", artifact.artifact_id, ""))


def _create_attempt_in_process(
    project_root: str,
    start_event,
    result_queue,
) -> None:
    """Widen the Run-read window to expose an unlocked freeze rollback race."""

    original_parse = project_experiments._parse_run

    def delayed_parse(path):
        result = original_parse(path)
        time.sleep(0.15)
        return result

    project_experiments._parse_run = delayed_parse
    start_event.wait(timeout=5)
    try:
        create_attempt(
            project_root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            target_id="local",
        )
    except (ExperimentError, OSError) as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))
    else:
        result_queue.put(("ok", "attempt-01", ""))


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    initialized = subprocess.run(
        [sys.executable, str(INIT), "apply", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert initialized.returncode == 0, initialized.stderr
    (root / "tools" / "run.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "configs" / "recipes" / "resolved.yaml").write_text(
        "learning_rate: 0.001\n", encoding="utf-8"
    )
    (root / "env" / "environment.yaml").write_text(
        "python: '3.11'\n", encoding="utf-8"
    )
    dataset_manifest = root / "dataset" / "demo" / "metadata" / "manifest.yaml"
    dataset_manifest.parent.mkdir(parents=True)
    dataset_manifest.write_text("version: '1'\n", encoding="utf-8")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "baseline")
    return root


def create_baseline_run(root: Path):
    return create_run(
        root,
        run_id=RUN_ID,
        run_script="tools/run.sh",
        resolved_config="configs/recipes/resolved.yaml",
        dataset_manifest="dataset/demo/metadata/manifest.yaml",
        dataset_id="demo",
        dataset_version="1",
        dataset_split="train",
        seed=7,
        environment_definition="env/environment.yaml",
    )


def test_experiment_rejects_noncanonical_project_identity(tmp_path: Path) -> None:
    root = project(tmp_path)
    layout_path = root / "project-layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    layout["project_id"] = f"urn:uuid:{layout['project_id']}"
    layout_path.write_text(json.dumps(layout), encoding="utf-8")

    with pytest.raises(ExperimentError, match="UUIDv4 identity"):
        create_baseline_run(root)


def target_spec(tmp_path: Path, *, secret: bool = False) -> Path:
    payload = {
        "schema_version": 1,
        "target_id": "local",
        "kind": "local",
        "server_alias": None,
        "project_root": "/project",
        "output_root": "/output",
        "executor": {"kind": "shell"},
        "environment_bindings": {"training": "project-env"},
    }
    if secret:
        payload["token"] = "secret"
    path = tmp_path / ("bad-target.yaml" if secret else "target.yaml")
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_run_attempt_target_and_index_lifecycle(tmp_path: Path) -> None:
    root = project(tmp_path)
    run = create_baseline_run(root)
    assert run.record_state == "draft"
    register_target(root, target_spec(tmp_path))

    attempt = create_attempt(
        root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local"
    )
    assert attempt.status == "planned"
    assert (root / "experiments" / RUN_ID / "attempts/attempt-01/target.yaml").is_file()
    frozen = yaml.safe_load(
        (root / "experiments" / RUN_ID / "run.yaml").read_text(encoding="utf-8")
    )
    assert frozen["record_state"] == "frozen"

    counts = validate_project(root)
    assert counts == {"runs": 1, "attempts": 1, "targets": 1, "artifacts": 0}
    first = rebuild_index(root)
    before = (root / "experiments" / "index.yaml").read_bytes()
    second = rebuild_index(root)
    assert second == first
    assert (root / "experiments" / "index.yaml").read_bytes() == before

    current_target_path = root / "experiments/profiles/targets/local.yaml"
    current_target = yaml.safe_load(current_target_path.read_text(encoding="utf-8"))
    current_target["output_root"] = "/new-output"
    current_target_path.write_text(
        yaml.safe_dump(current_target, sort_keys=False), encoding="utf-8"
    )
    assert validate_project(root)["attempts"] == 1
    second_attempt = create_attempt(
        root, run_id=RUN_ID, attempt_id="attempt-02", target_id="local"
    )
    assert second_attempt.target_profile_sha256 != attempt.target_profile_sha256


def test_attempt_requires_explicit_start_before_terminal_state(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    with pytest.raises(ExperimentError, match="running Attempt"):
        finalize_attempt(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            status="succeeded",
            exit_code=0,
            actual={},
        )
    running = start_attempt(root, run_id=RUN_ID, attempt_id="attempt-01")
    assert running.status == "running"
    assert running.started_at is not None
    finished = finalize_attempt(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        status="succeeded",
        exit_code=0,
        actual={},
    )
    assert finished.finished_at is not None
    assert finished.started_at == running.started_at


def test_attempt_bundle_failure_leaves_run_draft_and_no_partial_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))

    def fail_copy(_source, _destination):
        raise OSError("injected copy failure")

    monkeypatch.setattr(project_experiments.shutil, "copyfile", fail_copy)
    with pytest.raises(OSError, match="injected"):
        create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    run = yaml.safe_load(
        (root / "experiments" / RUN_ID / "run.yaml").read_text(encoding="utf-8")
    )
    assert run["record_state"] == "draft"
    attempts = root / "experiments" / RUN_ID / "attempts"
    assert not (attempts / "attempt-01").exists()
    assert not list(attempts.glob(".attempt-01.tmp-*"))


def test_attempt_publication_failure_rolls_back_run_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    original_replace = project_experiments.os.replace

    def fail_attempt_publish(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path.is_dir() and destination_path.name == "attempt-01":
            raise OSError("injected attempt publish failure")
        return original_replace(source, destination)

    monkeypatch.setattr(project_experiments.os, "replace", fail_attempt_publish)
    with pytest.raises(OSError, match="injected attempt publish failure"):
        create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    run = yaml.safe_load(
        (root / "experiments" / RUN_ID / "run.yaml").read_text(encoding="utf-8")
    )
    attempts = root / "experiments" / RUN_ID / "attempts"
    assert run["record_state"] == "draft"
    assert not (attempts / "attempt-01").exists()
    assert not list(attempts.glob(".attempt-01.tmp-*"))


def test_cross_process_attempt_collision_cannot_unfreeze_run(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    context = multiprocessing.get_context("fork")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_create_attempt_in_process,
            args=(str(root), start_event, result_queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = [result_queue.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert [result[0] for result in results].count("ok") == 1
    assert [result[0] for result in results].count("error") == 1
    run = yaml.safe_load(
        (root / "experiments" / RUN_ID / "run.yaml").read_text(encoding="utf-8")
    )
    assert run["record_state"] == "frozen"
    assert validate_project(root)["attempts"] == 1


def test_finalize_record_failure_removes_new_output_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    start_attempt(root, run_id=RUN_ID, attempt_id="attempt-01")
    inventory = tmp_path / "outputs.json"
    inventory.write_text('{"files": []}\n', encoding="utf-8")
    original_write = project_experiments._atomic_write_yaml

    def fail_attempt_record(path, payload):
        if Path(path).name == "attempt.yaml" and payload.get("status") == "succeeded":
            raise OSError("injected attempt record failure")
        return original_write(path, payload)

    monkeypatch.setattr(project_experiments, "_atomic_write_yaml", fail_attempt_record)
    with pytest.raises(OSError, match="injected attempt record failure"):
        finalize_attempt(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            status="succeeded",
            exit_code=0,
            actual={},
            output_inventory=inventory,
        )

    attempt_root = root / "experiments" / RUN_ID / "attempts" / "attempt-01"
    assert not (attempt_root / "output-inventory.json").exists()
    attempt = yaml.safe_load((attempt_root / "attempt.yaml").read_text(encoding="utf-8"))
    assert attempt["status"] == "running"


def test_run_bundle_failure_leaves_no_partial_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    original_copy = project_experiments.shutil.copyfile
    copy_count = 0

    def fail_second_copy(source, destination):
        nonlocal copy_count
        copy_count += 1
        if copy_count == 2:
            raise OSError("injected run snapshot failure")
        return original_copy(source, destination)

    monkeypatch.setattr(project_experiments.shutil, "copyfile", fail_second_copy)
    with pytest.raises(OSError, match="injected run snapshot failure"):
        create_baseline_run(root)

    experiments = root / "experiments"
    assert not (experiments / RUN_ID).exists()
    assert not list(experiments.glob(f".{RUN_ID}.tmp-*"))


def test_recipe_hash_excludes_target_but_detects_recipe_mutation(tmp_path: Path) -> None:
    root = project(tmp_path)
    run = create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    run_after = yaml.safe_load(
        (root / "experiments" / RUN_ID / "run.yaml").read_text(encoding="utf-8")
    )
    assert run_after["recipe_hash"] == run.recipe_hash
    snapshot = root / run.config.path
    snapshot.write_text("learning_rate: 1\n", encoding="utf-8")
    with pytest.raises(ExperimentError, match="checksum"):
        create_attempt(root, run_id=RUN_ID, attempt_id="attempt-02", target_id="local")


def test_target_rejects_secret_or_command_fields(tmp_path: Path) -> None:
    root = project(tmp_path)
    with pytest.raises(ExperimentError, match="invalid target profile"):
        register_target(root, target_spec(tmp_path, secret=True))


def test_promotion_remains_unverified_without_a_trusted_backup_medium(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    remote = tmp_path / "remote.ckpt"
    remote.write_bytes(b"checkpoint")

    artifact = promote_artifact(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        source=remote,
        destination="checkpoints/final.ckpt",
        role="checkpoint",
        retention="local-selected",
        remote_source="gpu-a:/results/final.ckpt",
    )
    assert artifact.backup.state == "not-verified"
    manifest = yaml.safe_load(
        (root / "experiments" / RUN_ID / "artifacts.yaml").read_text(encoding="utf-8")
    )
    assert manifest["artifacts"][0]["backup"] == {
        "state": "not-verified",
        "verified_at": None,
        "location": None,
        "sha256": None,
    }


def test_verified_backup_is_unrepresentable_and_cli_validate_rejects_manual_yaml(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="not-verified"):
        BackupRecord(
            state="verified",
            verified_at="2026-09-22T12:00:00Z",
            location="disk-b:/backup",
            sha256="a" * 64,
        )

    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"result")
    promote_artifact(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        source=source,
        destination="result.bin",
        role="other",
        retention="local-selected",
    )
    manifest_path = root / "experiments" / RUN_ID / "artifacts.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["backup"] = {
        "state": "verified",
        "verified_at": "2026-09-22T12:00:00Z",
        "location": "disk-b:/backup",
        "sha256": "a" * 64,
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    with pytest.raises(ExperimentError, match="invalid artifact manifest"):
        validate_project(root)
    result = CliRunner().invoke(
        main,
        ["experiment", "validate", "--project-root", str(root)],
    )
    assert result.exit_code == 2
    assert "invalid artifact manifest" in result.output


def test_promotion_blocks_escape_and_different_content_collision(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"one")
    with pytest.raises(ExperimentError, match="safe relative"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="../escape.bin",
            role="other",
            retention="local-selected",
        )


def test_promotion_exclusive_reservation_preserves_racing_victim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"promoted bytes")
    destination = root / "experiments" / RUN_ID / "artifacts" / "raced.bin"
    original_open = project_experiments.os.open
    injected = False

    def racing_open(path, flags, *args, **kwargs):
        nonlocal injected
        if Path(path) == destination and flags & project_experiments.os.O_EXCL and not injected:
            injected = True
            destination.write_bytes(b"concurrent victim")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(project_experiments.os, "open", racing_open)
    with pytest.raises(ExperimentError, match="already exists"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="raced.bin",
            role="other",
            retention="local-selected",
        )
    assert injected is True
    assert destination.read_bytes() == b"concurrent victim"
    manifest = yaml.safe_load(
        (root / "experiments" / RUN_ID / "artifacts.yaml").read_text(encoding="utf-8")
    )
    assert manifest["artifacts"] == []


@pytest.mark.parametrize("replacement", ("new-inode", "same-inode"))
def test_promotion_failure_cleanup_never_deletes_concurrent_victim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"promoted bytes")
    destination = root / "experiments" / RUN_ID / "artifacts" / "victim.bin"
    original_write = project_experiments._atomic_write_yaml

    def fail_manifest(path, payload):
        if Path(path).name == "artifacts.yaml":
            if replacement == "new-inode":
                destination.unlink()
            destination.write_bytes(b"concurrent victim")
            raise OSError("injected manifest failure")
        return original_write(path, payload)

    monkeypatch.setattr(project_experiments, "_atomic_write_yaml", fail_manifest)
    with pytest.raises(OSError, match="injected manifest failure"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="victim.bin",
            role="other",
            retention="local-selected",
        )
    assert destination.read_bytes() == b"concurrent victim"
    manifest = yaml.safe_load(
        (root / "experiments" / RUN_ID / "artifacts.yaml").read_text(encoding="utf-8")
    )
    assert manifest["artifacts"] == []


def test_promotion_validates_metadata_before_copy_and_rolls_back_manifest_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"result")
    artifacts = root / "experiments" / RUN_ID / "artifacts"

    with pytest.raises(ExperimentError, match="invalid artifact metadata"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="invalid-role.bin",
            role="not-a-role",
            retention="local-selected",
        )
    assert not (artifacts / "invalid-role.bin").exists()

    original_write = project_experiments._atomic_write_yaml

    def fail_manifest(path, payload):
        if Path(path).name == "artifacts.yaml":
            raise OSError("injected manifest failure")
        return original_write(path, payload)

    monkeypatch.setattr(project_experiments, "_atomic_write_yaml", fail_manifest)
    with pytest.raises(OSError, match="injected manifest failure"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="rolled-back.bin",
            role="other",
            retention="local-selected",
        )
    assert not (artifacts / "rolled-back.bin").exists()


def test_validate_rejects_duplicate_artifacts_and_unknown_source_attempt(
    tmp_path: Path,
) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "result.bin"
    source.write_bytes(b"result")
    promote_artifact(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        source=source,
        destination="result.bin",
        role="other",
        retention="local-selected",
    )
    manifest_path = root / "experiments" / RUN_ID / "artifacts.yaml"
    original = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    duplicated = {**original, "artifacts": [*original["artifacts"], original["artifacts"][0]]}
    manifest_path.write_text(yaml.safe_dump(duplicated, sort_keys=False), encoding="utf-8")
    with pytest.raises(ExperimentError, match="unique"):
        validate_project(root)

    unknown = original
    unknown["artifacts"][0]["source_attempt_id"] = "missing-attempt"
    manifest_path.write_text(yaml.safe_dump(unknown, sort_keys=False), encoding="utf-8")
    with pytest.raises(ExperimentError, match="attempt missing-attempt directory is missing"):
        validate_project(root)
    promote_artifact(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        source=source,
        destination="result.bin",
        role="other",
        retention="local-selected",
    )
    source.write_bytes(b"two")
    with pytest.raises(ExperimentError, match="already registered"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="result.bin",
            role="other",
            retention="local-selected",
        )


def test_all_identifier_apis_reject_traversal_and_illegal_ids(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"artifact")

    run_operations = (
        lambda value: create_attempt(
            root,
            run_id=value,
            attempt_id="attempt-02",
            target_id="local",
        ),
        lambda value: start_attempt(root, run_id=value, attempt_id="attempt-01"),
        lambda value: finalize_attempt(
            root,
            run_id=value,
            attempt_id="attempt-01",
            status="failed",
            exit_code=1,
            actual={},
        ),
        lambda value: promote_artifact(
            root,
            run_id=value,
            attempt_id="attempt-01",
            source=source,
            destination="result.bin",
            role="other",
            retention="local-selected",
        ),
        lambda value: record_manifest_only_artifact(
            root,
            run_id=value,
            attempt_id="attempt-01",
            remote_source="gpu-a:/result.bin",
            role="other",
        ),
    )
    for bad_run_id in ("../escape", "/tmp/escape", "invalid-run"):
        with pytest.raises(ExperimentError, match="run_id"):
            create_run(
                root,
                run_id=bad_run_id,
                run_script="tools/run.sh",
                resolved_config="configs/recipes/resolved.yaml",
                dataset_manifest="dataset/demo/metadata/manifest.yaml",
                dataset_id="demo",
                dataset_version="1",
                dataset_split="train",
                seed=7,
                environment_definition="env/environment.yaml",
            )
        for operation in run_operations:
            with pytest.raises(ExperimentError, match="run_id"):
                operation(bad_run_id)

    attempt_operations = (
        lambda value: create_attempt(
            root,
            run_id=RUN_ID,
            attempt_id=value,
            target_id="local",
        ),
        lambda value: start_attempt(root, run_id=RUN_ID, attempt_id=value),
        lambda value: finalize_attempt(
            root,
            run_id=RUN_ID,
            attempt_id=value,
            status="failed",
            exit_code=1,
            actual={},
        ),
        lambda value: promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id=value,
            source=source,
            destination="result.bin",
            role="other",
            retention="local-selected",
        ),
        lambda value: record_manifest_only_artifact(
            root,
            run_id=RUN_ID,
            attempt_id=value,
            remote_source="gpu-a:/result.bin",
            role="other",
        ),
    )
    for bad_attempt_id in ("../escape", "/tmp/escape", "Invalid-Attempt"):
        for operation in attempt_operations:
            with pytest.raises(ExperimentError, match="attempt_id"):
                operation(bad_attempt_id)

    with pytest.raises(ExperimentError, match="target_id"):
        create_attempt(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-02",
            target_id="../target",
        )


@pytest.mark.parametrize(
    "component",
    (
        "experiments",
        "experiments/profiles",
        f"experiments/{RUN_ID}",
        f"experiments/{RUN_ID}/attempts",
        f"experiments/{RUN_ID}/attempts/attempt-01",
        f"experiments/{RUN_ID}/artifacts",
    ),
)
@pytest.mark.parametrize("replacement", ("symlink", "file"))
def test_validate_and_index_reject_unsafe_managed_paths(
    tmp_path: Path,
    component: str,
    replacement: str,
) -> None:
    root = project(tmp_path)
    if component not in {"experiments", "experiments/profiles"}:
        create_baseline_run(root)
    if component.endswith("attempt-01"):
        register_target(root, target_spec(tmp_path))
        create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    managed_path = root / component
    displaced = tmp_path / f"displaced-{component.replace('/', '-')}-{replacement}"
    managed_path.rename(displaced)
    if replacement == "symlink":
        managed_path.symlink_to(displaced, target_is_directory=True)
    else:
        managed_path.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(ExperimentError):
        validate_project(root)
    with pytest.raises(ExperimentError):
        rebuild_index(root)


@pytest.mark.parametrize(
    ("component", "operation"),
    (
        ("experiments", "create-run"),
        ("experiments/profiles", "register-target"),
        (f"experiments/{RUN_ID}", "create-attempt"),
        (f"experiments/{RUN_ID}/attempts", "create-attempt"),
        (f"experiments/{RUN_ID}/attempts/attempt-01", "start-attempt"),
        (f"experiments/{RUN_ID}/artifacts", "record-artifact"),
    ),
)
def test_mutations_reject_symlinked_managed_paths(
    tmp_path: Path,
    component: str,
    operation: str,
) -> None:
    root = project(tmp_path)
    if operation not in {"create-run", "register-target"}:
        create_baseline_run(root)
        register_target(root, target_spec(tmp_path))
    if operation in {"start-attempt", "record-artifact"}:
        create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")

    managed_path = root / component
    displaced = tmp_path / f"mutation-{component.replace('/', '-')}"
    managed_path.rename(displaced)
    managed_path.symlink_to(displaced, target_is_directory=True)

    with pytest.raises(ExperimentError, match="symlink"):
        if operation == "create-run":
            create_baseline_run(root)
        elif operation == "register-target":
            register_target(root, target_spec(tmp_path))
        elif operation == "create-attempt":
            create_attempt(
                root,
                run_id=RUN_ID,
                attempt_id="attempt-02",
                target_id="local",
            )
        elif operation == "start-attempt":
            start_attempt(root, run_id=RUN_ID, attempt_id="attempt-01")
        else:
            record_manifest_only_artifact(
                root,
                run_id=RUN_ID,
                attempt_id="attempt-01",
                remote_source="gpu-a:/result.bin",
                role="other",
            )


def test_mutation_rejects_symlinked_artifact_parent(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    external = tmp_path / "external-artifacts"
    external.mkdir()
    artifact_parent = root / "experiments" / RUN_ID / "artifacts" / "escaped"
    artifact_parent.symlink_to(external, target_is_directory=True)
    source = tmp_path / "artifact.bin"
    source.write_bytes(b"artifact")

    with pytest.raises(ExperimentError, match="symlink"):
        promote_artifact(
            root,
            run_id=RUN_ID,
            attempt_id="attempt-01",
            source=source,
            destination="escaped/result.bin",
            role="other",
            retention="local-selected",
        )
    assert not (external / "result.bin").exists()


def test_validate_and_index_reject_illegal_discovered_ids(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    run_directory = root / "experiments" / RUN_ID
    invalid_run = root / "experiments" / "invalid-run"
    run_directory.rename(invalid_run)

    with pytest.raises(ExperimentError, match="run_id"):
        validate_project(root)
    with pytest.raises(ExperimentError, match="run_id"):
        rebuild_index(root)

    invalid_run.rename(run_directory)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    attempt_directory = run_directory / "attempts" / "attempt-01"
    attempt_directory.rename(run_directory / "attempts" / "Invalid-Attempt")

    with pytest.raises(ExperimentError, match="attempt_id"):
        validate_project(root)
    with pytest.raises(ExperimentError, match="attempt_id"):
        rebuild_index(root)


def test_manifest_only_artifact_and_legacy_plan_are_non_destructive(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    artifact = record_manifest_only_artifact(
        root,
        run_id=RUN_ID,
        attempt_id="attempt-01",
        remote_source="gpu-a:/large/intermediate.bin",
        role="intermediate",
    )
    assert artifact.retention == "manifest-only"
    assert artifact.relative_path is None

    legacy = root / "experiments" / "legacy-run"
    legacy.mkdir()
    marker = legacy / "notes.txt"
    marker.write_text("keep me\n", encoding="utf-8")
    plan = legacy_migration_plan(root)
    assert plan["write_performed"] is False
    assert plan["experiments"][0]["state"] == "unresolved"
    assert marker.read_text(encoding="utf-8") == "keep me\n"


def test_cross_process_manifest_mutations_do_not_lose_updates(tmp_path: Path) -> None:
    root = project(tmp_path)
    create_baseline_run(root)
    register_target(root, target_spec(tmp_path))
    create_attempt(root, run_id=RUN_ID, attempt_id="attempt-01", target_id="local")
    context = multiprocessing.get_context("fork")
    start_event = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_record_remote_in_process,
            args=(str(root), f"gpu-a:/result-{index}.bin", start_event, result_queue),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    start_event.set()
    results = [result_queue.get(timeout=10) for _ in processes]
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0

    assert all(result[0] == "ok" for result in results), results
    manifest = yaml.safe_load(
        (root / "experiments" / RUN_ID / "artifacts.yaml").read_text(encoding="utf-8")
    )
    assert len(manifest["artifacts"]) == 2
    assert {item["remote_source"] for item in manifest["artifacts"]} == {
        "gpu-a:/result-0.bin",
        "gpu-a:/result-1.bin",
    }


def test_experiment_lockfile_symlink_fails_closed(tmp_path: Path) -> None:
    root = project(tmp_path)
    lock_directory = root / ".scholar-workflow" / "locks"
    lock_directory.mkdir(parents=True)
    victim = tmp_path / "victim.lock"
    victim.write_text("do not touch\n", encoding="utf-8")
    (lock_directory / "experiments.lock").symlink_to(victim)

    with pytest.raises(ExperimentError, match="lockfile is unsafe"):
        create_baseline_run(root)
    assert victim.read_text(encoding="utf-8") == "do not touch\n"


def test_project_identity_is_preserved_when_directory_is_copied(tmp_path: Path) -> None:
    root = project(tmp_path)
    project_id = json.loads(
        (root / "project-layout.json").read_text(encoding="utf-8")
    )["project_id"]
    copied = tmp_path / "copied"
    shutil.copytree(root, copied, symlinks=True)
    copied_id = json.loads(
        (copied / "project-layout.json").read_text(encoding="utf-8")
    )["project_id"]
    assert copied_id == project_id
