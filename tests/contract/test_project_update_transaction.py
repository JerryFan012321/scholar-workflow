"""One synthetic Run exercises update installation and explicit crash recovery."""
import json

import pytest

from scholar_workflow.project.collected import collected_overview
from scholar_workflow.project.reception import ReceptionError
from tests.contract import test_project_update_package as fixture


@pytest.fixture
def sample(tmp_path):
    return fixture.fixtures.sample.__wrapped__(tmp_path)


def apply(parent, child, plan):
    from scholar_workflow.project.transactions import apply_run_update
    return apply_run_update(parent, child, run_id=fixture.RUN, **{
        "expected_" + key: plan[key] for key in (
            "parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256",
        )
    })


def pending(sample, monkeypatch, *, stop_after=1):
    from scholar_workflow.project import transactions
    parent, child, plan = fixture.prepare(sample)
    local = parent / plan["destination"]
    (local / "notes.md").write_text("Human analysis\n")
    before = fixture.snapshot(local)
    original = transactions._install_action
    with monkeypatch.context() as patch:
        installed = 0
        def interrupt(*args, **kwargs):
            nonlocal installed
            original(*args, **kwargs)
            installed += 1
            if installed == stop_after:
                raise OSError("Synthetic interruption after installation")
        patch.setattr(transactions, "_install_action", interrupt)
        with pytest.raises(ReceptionError) as caught:
            apply(parent, child, plan)
        assert caught.value.exit_code == 6
    assert (local / ".collection-update.json").is_file()
    assert collected_overview(parent)["children"][0]["runs"][0]["state"] == "pending_update"
    return parent, child, plan, local, before


def recover(parent, direction):
    from scholar_workflow.project.transactions import plan_run_recovery, recover_run_update
    plan = plan_run_recovery(parent, child_project_id=fixture.fixtures.CHILD, run_id=fixture.RUN)
    return recover_run_update(parent, child_project_id=fixture.fixtures.CHILD,
                              run_id=fixture.RUN, direction=direction,
                              expected_revision=plan["revision_sha256"])


def test_update_applies_selected_changes_and_preserves_human_content(sample):
    parent, child, plan = fixture.prepare(sample)
    local = parent / plan["destination"]
    (local / "notes.md").write_text("Human analysis\n")
    (local / "report.md").write_text("Human comparison\n")
    inode = (local / "notes.md").stat().st_ino
    source = fixture.snapshot(child)
    result = apply(parent, child, plan)
    assert result["status"] == "updated"
    assert not (local / ".collection-update.json").exists()
    assert (local / "notes.md").read_text() == "Human analysis\n"
    assert (local / "notes.md").stat().st_ino == inode
    assert (local / "report.md").read_text() == "Human comparison\n"
    record = collected_overview(parent)["children"][0]["runs"][0]
    assert record["state"] == "verified_archive"
    assert next(row for row in record["attempts"] if row["attempt_id"] == "running")["status"] == "succeeded"
    assert fixture.snapshot(child) == source


@pytest.mark.parametrize("direction", ["commit", "rollback"])
def test_interrupted_update_recovers_without_source(sample, monkeypatch, direction):
    parent, child, _plan, local, before = pending(sample, monkeypatch)
    child.rename(child.with_name("source-offline"))
    result = recover(parent, direction)
    assert result["status"] == ("committed" if direction == "commit" else "rolled_back")
    assert not (local / ".collection-update.json").exists()
    assert (local / "notes.md").read_text() == "Human analysis\n"
    assert collected_overview(parent)["status"] == "complete"
    if direction == "rollback":
        assert fixture.snapshot(local) == before
    else:
        assert (local / "attempts/running/stdout.log").read_text() == "Synthetic result, not executed\n"


def test_unknown_local_edit_refuses_recovery_without_any_writes(sample, monkeypatch):
    parent, _child, _plan, local, _ = pending(sample, monkeypatch)
    # Replace, rather than edit the linked payload, so recovery material remains intact.
    edited = local / "attempts/running/attempt.yaml"
    temporary = edited.with_suffix(".human")
    temporary.write_text("Human correction\n")
    temporary.replace(edited)
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError):
        recover(parent, "rollback")
    assert fixture.snapshot(parent) == before


def test_equal_byte_unowned_new_file_is_not_adopted_or_deleted(sample, monkeypatch):
    parent, _child, _plan, local, _ = pending(sample, monkeypatch)
    (local / "attempts/running/stdout.log").write_text("Synthetic result, not executed\n")
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError):
        recover(parent, "rollback")
    assert fixture.snapshot(parent) == before


def test_stale_recovery_revision_refuses(sample, monkeypatch):
    from scholar_workflow.project.transactions import plan_run_recovery, recover_run_update
    parent, _child, _plan, _local, _ = pending(sample, monkeypatch)
    review = plan_run_recovery(parent, child_project_id=fixture.fixtures.CHILD, run_id=fixture.RUN)
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError) as caught:
        recover_run_update(parent, child_project_id=fixture.fixtures.CHILD, run_id=fixture.RUN,
                           direction="commit", expected_revision="0" * 64)
    assert caught.value.exit_code == 5
    assert fixture.snapshot(parent) == before
    assert review["status"] == "pending_update"


def test_unknown_marker_cannot_choose_arbitrary_journal(sample):
    from scholar_workflow.project.transactions import plan_run_recovery
    parent, _child, plan = fixture.prepare(sample)
    local = parent / plan["destination"]
    (local / ".collection-update.json").write_text(json.dumps({
        "schema_version": 1, "transaction_id": "../../outside", "journal_sha256": "0" * 64,
    }))
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError):
        plan_run_recovery(parent, child_project_id=fixture.fixtures.CHILD, run_id=fixture.RUN)
    assert fixture.snapshot(parent) == before


@pytest.mark.parametrize("stop_after", [2, 3])
@pytest.mark.parametrize("direction", ["commit", "rollback"])
def test_each_file_boundary_including_receipt_can_recover(sample, monkeypatch, stop_after, direction):
    parent, _child, _plan, local, before = pending(sample, monkeypatch, stop_after=stop_after)
    result = recover(parent, direction)
    assert result["status"] == ("committed" if direction == "commit" else "rolled_back")
    assert collected_overview(parent)["status"] == "complete"
    if direction == "rollback":
        assert fixture.snapshot(local) == before
        # Removed new files remain recoverable in the private package.
        assert any(path.read_text() == "Synthetic result, not executed\n"
                   for path in (parent / ".scholar-workflow/collection-transactions").glob("*/after/*"))


def test_recovery_cli_is_local_only_and_explicit(sample, monkeypatch):
    from click.testing import CliRunner

    from scholar_workflow import cli
    parent, _child, _plan, _local, _before = pending(sample, monkeypatch)
    def forbidden(*args, **kwargs):
        pytest.fail("Recovery must not run a tool, use host config or contact a server")
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    arguments = ["--project-root", str(parent), "--child-project-id", fixture.fixtures.CHILD,
                 "--run-id", fixture.RUN]
    before = fixture.snapshot(parent)
    preview = CliRunner().invoke(cli.main, ["experiment", "recovery-plan", *arguments, "--json"])
    assert preview.exit_code == 0, preview.output
    assert fixture.snapshot(parent) == before
    revision = json.loads(preview.output)["revision_sha256"]
    applied = CliRunner().invoke(cli.main, ["experiment", "recover-update", *arguments,
                                          "--direction", "commit", "--expected-revision", revision, "--json"])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "committed"


def test_update_cli_installs_the_previewed_version(sample):
    from click.testing import CliRunner

    from scholar_workflow import cli
    parent, child, plan = fixture.prepare(sample)
    arguments = ["experiment", "update-run", "--project-root", str(parent),
                 "--child-root", str(child), "--run-id", fixture.RUN, "--json"]
    for key in ("parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256"):
        arguments.extend(["--expected-" + key.replace("_", "-"), plan[key]])
    result = CliRunner().invoke(cli.main, arguments)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "updated"


def test_unchanged_update_has_no_additional_recovery_package(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, plan = fixture.prepare(sample)
    apply(parent, child, plan)
    before = fixture.snapshot(parent)
    assert apply(parent, child, plan_run_update(parent, child, run_id=fixture.RUN))["status"] == "unchanged"
    assert fixture.snapshot(parent) == before


@pytest.mark.parametrize("direction", ["commit", "rollback"])
def test_unknown_temporary_file_blocks_before_recovery_writes(sample, monkeypatch, direction):
    from scholar_workflow.project import transactions
    parent, _child, _plan, local, _before = pending(sample, monkeypatch)
    marker = json.loads((local / ".collection-update.json").read_text())
    journal = json.loads((parent / ".scholar-workflow/collection-transactions" /
                          marker["transaction_id"] / "journal.json").read_text())
    temporary = local / transactions._temp(journal, 2, direction)
    temporary.write_text("Human file, not owned by the update\n")
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError):
        recover(parent, direction)
    assert fixture.snapshot(parent) == before


def test_journal_cannot_claim_local_analysis_even_with_new_marker_digest(sample, monkeypatch):
    parent, _child, _plan, local, _before = pending(sample, monkeypatch)
    marker_path = local / ".collection-update.json"
    marker = json.loads(marker_path.read_text())
    journal_path = parent / ".scholar-workflow/collection-transactions" / marker["transaction_id"] / "journal.json"
    journal = json.loads(journal_path.read_text())
    journal["actions"][0]["destination_path"] = "notes.md"
    journal_path.write_text(json.dumps(journal))
    marker["journal_sha256"] = fixture.sha(journal_path.read_bytes())
    marker_path.write_text(json.dumps(marker))
    before = fixture.snapshot(parent)
    with pytest.raises(ReceptionError):
        recover(parent, "commit")
    assert fixture.snapshot(parent) == before


def test_recovery_is_itself_interruptible_and_retryable(sample, monkeypatch):
    from scholar_workflow.project import transactions
    parent, _child, _plan, _local, _before = pending(sample, monkeypatch)
    original = transactions._install_action
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("Synthetic second interruption")
        patch.setattr(transactions, "_install_action", interrupt)
        with pytest.raises(ReceptionError) as caught:
            recover(parent, "rollback")
        assert caught.value.exit_code == 6
    assert recover(parent, "rollback")["status"] == "rolled_back"


def test_unchanged_retry_does_not_claim_durability_when_sync_fails(sample, monkeypatch):
    from scholar_workflow.project import transactions
    from scholar_workflow.project.updates import plan_run_update
    parent, child, plan = fixture.prepare(sample)
    apply(parent, child, plan)
    same = plan_run_update(parent, child, run_id=fixture.RUN)
    before = fixture.snapshot(parent)
    def fail(*args):
        raise OSError("Synthetic unavailable flush")
    with monkeypatch.context() as patch:
        patch.setattr(transactions, "_sync_dirs", fail)
        with pytest.raises(ReceptionError) as caught:
            apply(parent, child, same)
        assert caught.value.exit_code == 6
    assert fixture.snapshot(parent) == before
    assert apply(parent, child, same)["status"] == "unchanged"
