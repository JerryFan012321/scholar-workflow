"""Recovery checks operate on synthetic local Git only, without checkout or execution."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import jsonschema
import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.collection import plan_run_collection
from tests.contract import test_project_collection_plan as fixtures


def git(root, *args):
    result = subprocess.run(
        [shutil.which("git"), "-C", str(root), "-c", "user.name=Synthetic",
         "-c", "user.email=fixture@example.invalid", *args],
        env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
             "GIT_TERMINAL_PROMPT": "0"}, capture_output=True, check=True,
    )
    return result.stdout.decode().strip()


@pytest.fixture
def sample(tmp_path):
    parent, child, run = fixtures.sample.__wrapped__(tmp_path)
    git(child, "init", "--initial-branch=main")
    code = child / "model.py"
    code.write_text("# Synthetic first version; never executed.\n")
    git(child, "add", "model.py")
    git(child, "commit", "-m", "First synthetic version")
    first = git(child, "rev-parse", "HEAD")
    code.write_text("# Synthetic second version; never executed.\n")
    git(child, "add", "model.py")
    git(child, "commit", "-m", "Second synthetic version")
    second = git(child, "rev-parse", "HEAD")
    path = run / "run.yaml"
    value = yaml.safe_load(path.read_text())
    value["source"]["commit"] = first
    recipe = {"commit": first, "entrypoint_sha256": value["entrypoint"]["sha256"],
              "config_sha256": value["config"]["sha256"],
              "dataset": {"dataset_id": "test", "version": "1", "split": "fixed",
                          "manifest_sha256": value["dataset"]["manifest"]["sha256"]},
              "seed": 3, "environment_sha256": value["environment"]["sha256"]}
    value["recipe_hash"] = hashlib.sha256(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    fixtures.write_yaml(path, value)
    fixtures.receive(parent, child, plan_run_collection(parent, child, run_id=fixtures.RUN))
    bundle = tmp_path / "selected.bundle"
    git(child, "bundle", "create", str(bundle), "main")
    return parent, child, bundle, first, second


def plan(sample, commits=()):
    from scholar_workflow.project.code_recovery import plan_code_recovery
    parent, _child, bundle, _first, _second = sample
    return plan_code_recovery(parent, child_project_id=fixtures.CHILD,
                              bundle_file=bundle, required_commits=commits)


def test_complete_bundle_covers_recorded_and_explicit_commits_without_writes(sample):
    parent, child, bundle, first, second = sample
    before = fixtures.snapshot(parent), fixtures.snapshot(child), bundle.read_bytes()
    result = plan(sample, (second,))
    assert result["status"] == "planned_not_retained"
    assert {row["commit"] for row in result["required_commits"]} == {first, second}
    assert next(row for row in result["required_commits"] if row["commit"] == first)["run_ids"] == [fixtures.RUN]
    assert all(row["object_present"] for row in result["required_commits"])
    assert result["bundle"]["self_contained"] and result["bundle"]["object_check"] == "fsck_strict_passed"
    assert result["backup_state"] == "not-verified"
    assert result["gaps"]["uncommitted"] == "not_checked" and result["gaps"]["untracked"] == "not_checked"
    assert (fixtures.snapshot(parent), fixtures.snapshot(child), bundle.read_bytes()) == before
    assert not (parent / "backups").exists()


def test_parent_git_head_is_never_used_as_child_commit(sample):
    result = plan(sample)
    assert [row["commit"] for row in result["required_commits"]] == [sample[3]]
    assert not (sample[0] / ".git").exists()


def test_saved_material_and_coverage_match_strict_schema(sample):
    schema = json.loads((Path(__file__).parents[2] / "contracts/code-recovery.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    validator.check_schema(schema)
    preview = plan(sample)
    validator.validate(preview)
    result = retain(sample, preview)
    for relative in (result["material_path"] + "/material.json", result["coverage_path"]):
        validator.validate(json.loads((sample[0] / relative).read_text()))
    for changed in ({**preview, "backup_state": "verified"}, {**preview, "source_path": "/private/source"},
                    {**preview, "required_commits": []}):
        assert not validator.is_valid(changed)


def test_missing_git_is_dependency_error_in_cli(sample, monkeypatch):
    from scholar_workflow.project import code_recovery
    monkeypatch.setattr(code_recovery.shutil, "which", lambda name: None)
    result = CliRunner().invoke(cli.main, ["project", "code-recovery-plan", "--project-root", str(sample[0]),
                                         "--child-project-id", fixtures.CHILD, "--bundle-file", str(sample[2])])
    assert result.exit_code == 3, result.output
    assert not (sample[0] / "backups").exists()


def test_missing_commit_refuses(sample):
    with pytest.raises(ValueError, match="missing"):
        plan(sample, ("0" * 40,))


def test_incremental_bundle_requires_an_independent_base_and_is_refused(sample):
    _parent, child, bundle, first, _second = sample
    bundle.unlink()
    git(child, "bundle", "create", str(bundle), f"{first}..main")
    with pytest.raises(ValueError, match="self-contained"):
        plan(sample)


def test_corrupt_bundle_is_not_recoverable(sample):
    bundle = sample[2]
    bundle.write_bytes(bundle.read_bytes()[:-32])
    with pytest.raises(ValueError):
        plan(sample)


def test_lfs_pointer_and_gitlink_are_reported_not_claimed_as_payloads(sample):
    _parent, child, bundle, _first, second = sample
    (child / "weights.bin").write_text("version https://git-lfs.github.com/spec/v1\noid sha256:" + "1" * 64 + "\nsize 42\n")
    git(child, "add", "weights.bin")
    git(child, "update-index", "--add", "--cacheinfo", f"160000,{second},dependency")
    git(child, "commit", "-m", "Synthetic pointer and gitlink")
    latest = git(child, "rev-parse", "HEAD")
    bundle.unlink()
    git(child, "bundle", "create", str(bundle), "main")
    result = plan(sample, (latest,))
    assert {row["path"] for row in result["gaps"]["lfs_pointers"]} == {"weights.bin"}
    assert {row["path"] for row in result["gaps"]["submodules"]} == {"dependency"}
    assert result["backup_state"] == "not-verified"


def test_pending_or_invalid_run_blocks_coverage_claim(sample):
    parent = sample[0]
    local = parent / "experiments/main-method" / fixtures.RUN
    (local / ".collection-update.json").write_text("{}\n")
    with pytest.raises(ValueError, match="archive"):
        plan(sample)


def test_unknown_child_and_malformed_commit_refuse(sample):
    from scholar_workflow.project.code_recovery import plan_code_recovery
    with pytest.raises(ValueError):
        plan_code_recovery(sample[0], child_project_id=fixtures.PARENT, bundle_file=sample[2])
    with pytest.raises(ValueError):
        plan(sample, ("HEAD; touch outside",))


def test_bundle_symlink_is_not_followed(sample):
    bundle = sample[2]
    original = bundle.with_suffix(".original")
    bundle.rename(original)
    bundle.symlink_to(original)
    with pytest.raises(ValueError):
        plan(sample)


def test_cli_reads_only_selected_scope_and_does_not_load_config(sample, monkeypatch):
    parent, _child, bundle, _first, _second = sample
    def forbidden(*args, **kwargs):
        pytest.fail("Code recovery planning must not consult host configuration")
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    before = fixtures.snapshot(parent)
    result = CliRunner().invoke(cli.main, ["project", "code-recovery-plan", "--project-root", str(parent),
                                         "--child-project-id", fixtures.CHILD, "--bundle-file", str(bundle), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "planned_not_retained"
    assert fixtures.snapshot(parent) == before


def retain(sample, preview):
    from scholar_workflow.project.code_recovery import retain_code_recovery
    return retain_code_recovery(sample[0], child_project_id=fixtures.CHILD, bundle_file=sample[2],
                                expected_plan_sha256=preview["plan_sha256"])


def test_retention_saves_one_bundle_and_replays_without_source_changes(sample):
    parent, child, bundle, _first, _second = sample
    preview = plan(sample)
    before = fixtures.snapshot(child)
    result = retain(sample, preview)
    assert result["status"] == "retained" and result["backup_state"] == "not-verified"
    directory = parent / result["material_path"]
    assert (directory / "source.bundle").read_bytes() == bundle.read_bytes()
    assert json.loads((directory / "coverage" / (preview["plan_sha256"] + ".json")).read_text()) == preview
    saved = fixtures.snapshot(parent)
    assert retain(sample, preview)["status"] == "unchanged"
    assert fixtures.snapshot(parent) == saved and fixtures.snapshot(child) == before
    assert not (parent / ".git").exists()


def test_stale_retention_plan_writes_nothing(sample):
    from scholar_workflow.project.code_recovery import retain_code_recovery
    before = fixtures.snapshot(sample[0])
    with pytest.raises(ValueError):
        retain_code_recovery(sample[0], child_project_id=fixtures.CHILD, bundle_file=sample[2],
                             expected_plan_sha256="0" * 64)
    assert fixtures.snapshot(sample[0]) == before
    assert not (sample[0] / "backups").exists()


def test_changed_archive_adds_coverage_without_duplicate_bundle(sample):
    from scholar_workflow.project.code_recovery import retain_code_recovery
    first_plan = plan(sample)
    result = retain(sample, first_plan)
    parent = sample[0]
    directory = parent / result["material_path"]
    inode = (directory / "source.bundle").stat().st_ino
    # Explicitly selecting another commit changes the coverage, not the material.
    newer = plan(sample, (sample[4],))
    applied = retain_code_recovery(parent, child_project_id=fixtures.CHILD, bundle_file=sample[2],
                                   required_commits=(sample[4],), expected_plan_sha256=newer["plan_sha256"])
    assert applied["status"] == "coverage_added"
    assert (directory / "source.bundle").stat().st_ino == inode
    assert len(list((directory / "coverage").iterdir())) == 2
    assert len(list((parent / "backups/code" / fixtures.CHILD).iterdir())) == 1


def test_existing_unknown_material_is_not_overwritten(sample):
    preview = plan(sample)
    path = sample[0] / "backups/code" / fixtures.CHILD / preview["bundle"]["sha256"]
    path.mkdir(parents=True)
    (path / "source.bundle").write_text("Human file\n")
    before = fixtures.snapshot(sample[0])
    with pytest.raises(ValueError):
        retain(sample, preview)
    assert fixtures.snapshot(sample[0]) == before


def test_retention_destination_symlink_is_not_followed(sample, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (sample[0] / "backups").symlink_to(outside)
    preview = plan(sample)
    with pytest.raises(ValueError):
        retain(sample, preview)
    assert list(outside.iterdir()) == []


def test_existing_changed_coverage_is_a_conflict_not_an_overwrite(sample):
    preview = plan(sample)
    result = retain(sample, preview)
    coverage = sample[0] / result["coverage_path"]
    coverage.write_text("Human replacement\n")
    before = fixtures.snapshot(sample[0])
    with pytest.raises(ValueError) as caught:
        retain(sample, preview)
    assert caught.value.exit_code == 5
    assert fixtures.snapshot(sample[0]) == before


def test_post_publication_failure_is_partial_then_identical_retry_resynchronizes(sample, monkeypatch):
    from scholar_workflow.project import code_recovery
    preview = plan(sample)
    original = code_recovery._existing_material
    with monkeypatch.context() as patch:
        def fail(namespace, name, current):
            present = original(namespace, name, current)
            if present and name == preview["bundle"]["sha256"]:
                raise OSError("Synthetic failure after publication")
            return present
        patch.setattr(code_recovery, "_existing_material", fail)
        with pytest.raises(ValueError) as caught:
            retain(sample, preview)
        assert caught.value.exit_code == 6
    before = fixtures.snapshot(sample[0])
    assert retain(sample, preview)["status"] == "unchanged"
    assert fixtures.snapshot(sample[0]) == before


def test_identical_retry_with_unconfirmed_coverage_sync_is_partial(sample, monkeypatch):
    from scholar_workflow.project import code_recovery
    preview = plan(sample)
    result = retain(sample, preview)
    coverage = sample[0] / result["material_path"] / "coverage"
    identity = coverage.stat().st_dev, coverage.stat().st_ino
    before = fixtures.snapshot(sample[0])
    original = os.fsync

    def fail_selected_directory(descriptor):
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) == identity:
            raise OSError("Synthetic coverage directory synchronization failure")
        original(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(code_recovery.os, "fsync", fail_selected_directory)
        with pytest.raises(ValueError) as caught:
            retain(sample, preview)
        assert caught.value.exit_code == 6
    assert fixtures.snapshot(sample[0]) == before
    assert retain(sample, preview)["status"] == "unchanged"


def test_inherited_git_configuration_and_objects_are_not_used(sample, monkeypatch):
    monkeypatch.setenv("GIT_DIR", str(sample[1] / ".git"))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(sample[1] / ".git/objects"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "UNTRUSTED-HOOKS")
    assert plan(sample)["bundle"]["self_contained"]


def test_native_git_is_never_asked_to_checkout_fetch_or_run_code(sample, monkeypatch):
    from scholar_workflow.project import code_recovery
    original = code_recovery._git
    commands = []
    def observe(executable, root, *arguments, **kwargs):
        commands.append(arguments[0])
        return original(executable, root, *arguments, **kwargs)
    monkeypatch.setattr(code_recovery, "_git", observe)
    plan(sample)
    assert set(commands) <= {"init", "bundle", "fsck", "cat-file", "ls-tree"}


def test_git_timeout_reaps_the_created_process_group(tmp_path, monkeypatch):
    from scholar_workflow.project import code_recovery
    killed, waited = [], []
    class Hung:
        pid = 12345678
        def communicate(self, data, timeout):
            raise subprocess.TimeoutExpired("git", timeout)
        def wait(self, timeout):
            waited.append(timeout)
            return 0
    def start(command, **kwargs):
        assert isinstance(command, list) and kwargs["shell"] is False and kwargs["start_new_session"]
        assert "GIT_DIR" not in kwargs["env"] and "SSH_AUTH_SOCK" not in kwargs["env"]
        assert kwargs["env"]["GIT_ALLOW_PROTOCOL"] == ""
        return Hung()
    monkeypatch.setattr(code_recovery.subprocess, "Popen", start)
    monkeypatch.setattr(code_recovery.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(ValueError, match="timed out"):
        code_recovery._git("git", tmp_path, "fsck")
    assert killed == [(12345678, code_recovery.signal.SIGKILL)] and waited == [5]


def test_retain_cli_consumes_preview_and_reports_unverified_backup(sample):
    preview = plan(sample)
    result = CliRunner().invoke(cli.main, ["project", "retain-code", "--project-root", str(sample[0]),
                                         "--child-project-id", fixtures.CHILD,
                                         "--bundle-file", str(sample[2]),
                                         "--expected-plan-sha256", preview["plan_sha256"], "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["backup_state"] == "not-verified"
