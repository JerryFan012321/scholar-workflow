"""Independent expectations for update staging; never execute the synthetic Run."""
import json
from pathlib import Path

import jsonschema
import pytest

from scholar_workflow.project.collection import plan_run_collection
from scholar_workflow.project.reception import ReceptionError
from scholar_workflow.project.updates import plan_run_update
from tests.contract import test_project_collection_plan as fixtures

RUN = fixtures.RUN
finish_running, receive, sha, snapshot = (
    fixtures.finish_running, fixtures.receive, fixtures.sha, fixtures.snapshot,
)


@pytest.fixture
def sample(tmp_path):
    return fixtures.sample.__wrapped__(tmp_path)


def prepare(sample):
    parent, child, run = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    finish_running(run)
    (run / "attempts/running/stdout.log").write_text("Synthetic result, not executed\n")
    return parent, child, plan_run_update(parent, child, run_id=RUN)


def stage(parent, child, plan):
    from scholar_workflow.project.update_package import stage_run_update
    return stage_run_update(parent, child, run_id=RUN, **{
        "expected_" + key: plan[key] for key in (
            "parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256",
        )
    })


def test_package_keeps_exact_before_after_and_does_not_apply(sample):
    parent, child, plan = prepare(sample)
    local = parent / plan["destination"]
    (local / "notes.md").write_text("Human reasoning stays local\n")
    before, source = snapshot(local), snapshot(child)
    result = stage(parent, child, plan)
    assert result["status"] == "staged_not_applied"
    assert result["backup_state"] == "not-verified"
    package = parent / result["package_path"]
    raw = (package / "journal.json").read_bytes()
    assert sha(raw) == result["journal_sha256"]
    journal = json.loads(raw)
    schema = json.loads((Path(__file__).parents[2] / "contracts/experiment-update-package.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(journal)
    assert {row["destination_path"] for row in journal["actions"]} == {
        "attempts/running/attempt.yaml", "attempts/running/stdout.log", ".collection.json",
    }
    for row in journal["actions"]:
        destination = row["destination_path"]
        old = row["before"]
        new = row["after"]
        if old:
            assert (package / old["path"]).read_bytes() == before[destination]
            assert old["original_inode"] == (local / destination).stat().st_ino
        assert sha((package / new["path"]).read_bytes()) == new["sha256"]
        if destination != ".collection.json":
            assert (package / new["path"]).read_bytes() == (child / "experiments" / RUN / destination).read_bytes()
    assert journal["actions"][-1]["destination_path"] == ".collection.json"
    assert not (local / ".collection-update.json").exists()
    assert snapshot(local) == before and snapshot(child) == source
    assert (package.stat().st_mode & 0o777) == 0o700
    assert (package / "journal.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("key", ["parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256"])
def test_stale_baselines_create_nothing(sample, key):
    parent, child, plan = prepare(sample)
    plan[key] = "0" * 64
    before = snapshot(parent)
    with pytest.raises(ReceptionError) as caught:
        stage(parent, child, plan)
    assert caught.value.exit_code == 5
    assert snapshot(parent) == before
    assert not (parent / ".scholar-workflow").exists()


def test_staging_failure_preserves_original_and_reports_package(sample, monkeypatch):
    from scholar_workflow.project import update_package
    parent, child, plan = prepare(sample)
    local = parent / plan["destination"]
    before = snapshot(local)
    original = update_package._write_file
    def fail(root, path, data, mode):
        if path == "journal.json":
            raise OSError("synthetic storage failure")
        return original(root, path, data, mode)
    monkeypatch.setattr(update_package, "_write_file", fail)
    with pytest.raises(ReceptionError) as caught:
        stage(parent, child, plan)
    assert caught.value.exit_code == 6
    assert "collection-transactions/tx-" in str(caught.value)
    assert snapshot(local) == before
    assert not (local / ".collection-update.json").exists()


def test_symlink_storage_is_not_followed(sample, tmp_path):
    parent, child, plan = prepare(sample)
    outside = tmp_path / "outside"
    outside.mkdir()
    (parent / ".scholar-workflow").symlink_to(outside)
    with pytest.raises(ReceptionError):
        stage(parent, child, plan)
    assert list(outside.iterdir()) == []


def test_source_change_while_staging_does_not_activate(sample, monkeypatch):
    from scholar_workflow.project import update_package
    parent, child, plan = prepare(sample)
    local = parent / plan["destination"]
    before = snapshot(local)
    original = update_package._write_file
    changed = False
    def change(root, path, data, mode):
        nonlocal changed
        original(root, path, data, mode)
        if not changed:
            changed = True
            (child / "experiments" / RUN / "late.log").write_text("Changed source\n")
    monkeypatch.setattr(update_package, "_write_file", change)
    with pytest.raises(ReceptionError) as caught:
        stage(parent, child, plan)
    assert caught.value.exit_code == 6
    assert snapshot(local) == before
    assert not (local / ".collection-update.json").exists()


def test_unchanged_update_creates_no_package(sample):
    parent, child, _ = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    plan = plan_run_update(parent, child, run_id=RUN)
    before = snapshot(parent)
    assert stage(parent, child, plan)["status"] == "unchanged"
    assert snapshot(parent) == before
    assert not (parent / ".scholar-workflow").exists()


def test_equal_bytes_replaced_inode_is_not_original_ownership(sample, monkeypatch):
    from scholar_workflow.project import update_package
    parent, child, plan = prepare(sample)
    local = parent / plan["destination"]
    before = snapshot(local)
    original = update_package._write_file
    replaced = False
    def replace(root, path, data, mode):
        nonlocal replaced
        original(root, path, data, mode)
        if not replaced:
            replaced = True
            target = local / "attempts/running/attempt.yaml"
            temporary = target.with_suffix(".replacement")
            temporary.write_bytes(target.read_bytes())
            temporary.chmod(target.stat().st_mode & 0o777)
            temporary.replace(target)
    monkeypatch.setattr(update_package, "_write_file", replace)
    with pytest.raises(ReceptionError) as caught:
        stage(parent, child, plan)
    assert caught.value.exit_code == 6
    assert snapshot(local) == before


def test_recovery_payload_tamper_prevents_prepared_success(sample, monkeypatch):
    from scholar_workflow.project import update_package
    parent, child, plan = prepare(sample)
    local = parent / plan["destination"]
    before = snapshot(local)
    original = update_package._write_file
    def tamper(root, path, data, mode):
        original(root, path, data, mode)
        if path == "journal.json":
            package = next((parent / ".scholar-workflow/collection-transactions").iterdir())
            (package / "after/0").write_text("Changed recovery payload\n")
    monkeypatch.setattr(update_package, "_write_file", tamper)
    with pytest.raises(ReceptionError) as caught:
        stage(parent, child, plan)
    assert caught.value.exit_code == 6
    assert snapshot(local) == before
