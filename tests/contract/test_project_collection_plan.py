"""Independent single-Run transfer inputs; no code is executed."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.collection import plan_run_collection

PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
RUN = "20261018-1200-example"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value))


@pytest.fixture
def sample(tmp_path):
    parent, child = tmp_path / "parent", tmp_path / "child"
    for root, identity, management in (
        (parent, PARENT, {"kind": "research-parent", "children": [
            {"project_id": CHILD, "archive_segment": "main-method", "primary": True}]}),
        (child, CHILD, {"kind": "execution-child", "parent_project_id": PARENT, "primary": True}),
    ):
        root.mkdir()
        (root / "project-layout.json").write_text(json.dumps({"schema_version": 2, "project_id": identity}))
        (root / "project-management.json").write_text(json.dumps({
            "schema_version": 1, "project_id": identity, **management,
        }))
    run = child / "experiments" / RUN
    files = {"run.sh": b"DO NOT EXECUTE\n", "inputs/config.json": b'{"rate": 1}\n',
             "inputs/data.json": b'{"version": "test"}\n', "inputs/env.txt": b"synthetic\n"}
    for name, content in files.items():
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    def snap(name):
        return {"path": f"experiments/{RUN}/{name}", "sha256": sha(files[name])}
    recipe = {"commit": "f" * 40, "entrypoint_sha256": sha(files["run.sh"]),
              "config_sha256": sha(files["inputs/config.json"]),
              "dataset": {"dataset_id": "test", "version": "1", "split": "fixed",
                          "manifest_sha256": sha(files["inputs/data.json"])},
              "seed": 3, "environment_sha256": sha(files["inputs/env.txt"])}
    write_yaml(run / "run.yaml", {
        "schema_version": 1, "run_id": RUN, "created_at": "2026-10-18T12:00:00Z",
        "record_state": "frozen", "source": {"commit": "f" * 40},
        "entrypoint": snap("run.sh"), "config": snap("inputs/config.json"),
        "dataset": {"dataset_id": "test", "version": "1", "split": "fixed", "manifest": snap("inputs/data.json")},
        "seed": 3, "environment": snap("inputs/env.txt"),
        "recipe_hash": sha(json.dumps(recipe, sort_keys=True, separators=(",", ":")).encode()),
    })
    target = {"schema_version": 1, "target_id": "test", "kind": "local", "server_alias": None,
              "project_root": ".", "output_root": "outputs", "executor": {"kind": "shell"},
              "environment_bindings": {}}
    for status in ("planned", "running", "succeeded", "failed", "interrupted"):
        attempt = run / "attempts" / status
        write_yaml(attempt / "target.yaml", target)
        terminal = status not in {"planned", "running"}
        write_yaml(attempt / "attempt.yaml", {
            "schema_version": 1, "attempt_id": status, "run_id": RUN, "target_id": "test",
            "target_profile_sha256": sha((attempt / "target.yaml").read_bytes()), "status": status,
            "started_at": None if status == "planned" else "2026-10-18T12:01:00Z",
            "finished_at": "2026-10-18T12:02:00Z" if terminal else None,
            "exit_code": (0 if status == "succeeded" else 1) if terminal else None,
            "actual": {}, "output_inventory": None,
        })
    (run / "artifacts").mkdir()
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": []})
    (run / "report.md").write_text("Remote execution report\n")
    (run / "notes.md").write_text("Remote execution notes\n")
    (parent / "PROJECT.md").write_text("Local management and plan\n")
    return parent, child, run


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_plan_accounts_for_all_states_and_preserves_originals(sample):
    parent, child, run = sample
    before = snapshot(parent), snapshot(child)
    result = plan_run_collection(parent, child, run_id=RUN)
    assert result["source_commit"] == "f" * 40
    assert result["destination"] == f"experiments/main-method/{RUN}"
    assert {row["status"] for row in result["attempts"]} == {
        "planned", "running", "succeeded", "failed", "interrupted",
    }
    files = {row["source_path"]: row for row in result["files"]}
    assert files["report.md"]["destination_path"] == "execution-report.md"
    assert files["notes.md"]["destination_path"] == "execution-notes.md"
    assert len(files) == len(snapshot(run))
    assert {"artifacts", "attempts", "inputs"}.issubset(result["directories"])
    assert files["run.sh"]["mode"] == (run / "run.sh").stat().st_mode & 0o777
    assert result["execution_verification"] == "records_only"
    assert (snapshot(parent), snapshot(child)) == before
    assert not (parent / "experiments").exists()


@pytest.mark.parametrize("change", ["config", "recipe", "escape", "target", "attempt", "artifact"])
def test_invalid_evidence_is_not_a_successful_plan(sample, change):
    parent, child, run = sample
    if change == "config":
        (run / "inputs/config.json").write_text("changed")
    else:
        name = "artifacts.yaml" if change == "artifact" else (
            "attempts/failed/attempt.yaml" if change in {"target", "attempt"} else "run.yaml")
        path = run / name
        payload = yaml.safe_load(path.read_text())
        if change == "recipe":
            payload["recipe_hash"] = "0" * 64
        elif change == "escape":
            payload["config"]["path"] = f"experiments/{RUN}/../../secret"
        elif change == "target":
            payload["target_profile_sha256"] = "0" * 64
        elif change == "attempt":
            payload["run_id"] = "20261018-1201-other"
        else:
            payload["run_id"] = "20261018-1201-other"
        write_yaml(path, payload)
    before = snapshot(parent), snapshot(child)
    with pytest.raises(ValueError):
        plan_run_collection(parent, child, run_id=RUN)
    assert (snapshot(parent), snapshot(child)) == before


def test_scoped_plan_ignores_other_run_but_refuses_selected_symlink(sample, tmp_path):
    parent, child, run = sample
    (child / "experiments/broken-unselected").mkdir()
    plan_run_collection(parent, child, run_id=RUN)
    outside = tmp_path / "external"
    outside.write_text("Do not read\n")
    (run / "unexpected-link").symlink_to(outside)
    with pytest.raises(ValueError):
        plan_run_collection(parent, child, run_id=RUN)
    assert outside.read_text() == "Do not read\n"


def test_cli_is_read_only_and_runs_no_tools(sample, monkeypatch):
    parent, child, _ = sample
    def forbidden(*args, **kwargs):
        pytest.fail("Collection planning must not run tools or consult host config")
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collection-plan", "--project-root", str(parent),
        "--child-root", str(child), "--run-id", RUN, "--json",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["run_id"] == RUN
    assert (snapshot(parent), snapshot(child)) == before


@pytest.mark.parametrize("change", ["lifecycle", "actual_commit", "duplicate_yaml", "collision", "unregistered"])
def test_inconsistent_or_ambiguous_records_refuse(sample, change):
    parent, child, run = sample
    path = run / "attempts/succeeded/attempt.yaml"
    if change in {"lifecycle", "actual_commit"}:
        value = yaml.safe_load(path.read_text())
        if change == "lifecycle":
            value["started_at"] = None
        else:
            value["actual"]["commit"] = "a" * 40
        write_yaml(path, value)
    elif change == "duplicate_yaml":
        path.write_text(path.read_text() + "status: failed\n")
    elif change == "collision":
        (run / "execution-report.md").write_text("A different remote file\n")
    else:
        path = parent / "project-management.json"
        value = json.loads(path.read_text())
        value["children"] = []
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        plan_run_collection(parent, child, run_id=RUN)


def test_input_changes_during_plan_refuse(sample, monkeypatch):
    from scholar_workflow.project import collection

    parent, child, run = sample
    original = collection._tree
    calls = 0
    def changed(root, run_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            (run / "notes.md").write_text("New remote observation\n")
        return original(root, run_id)
    monkeypatch.setattr(collection, "_tree", changed)
    with pytest.raises(ValueError, match="changed"):
        plan_run_collection(parent, child, run_id=RUN)


def receive(parent, child, plan):
    from scholar_workflow.project.reception import receive_run
    return receive_run(parent, child, run_id=RUN,
                       expected_parent_sha256=plan["parent_sha256"],
                       expected_child_sha256=plan["child_sha256"],
                       expected_evidence_sha256=plan["evidence_sha256"])


def test_receive_writes_real_files_and_repeat_preserves_local_analysis(sample):
    import jsonschema
    parent, child, run = sample
    before_child = snapshot(child)
    plan = plan_run_collection(parent, child, run_id=RUN)
    result = receive(parent, child, plan)
    assert result["status"] == "received"
    destination = parent / plan["destination"]
    schema_path = Path(__file__).resolve().parents[2] / "contracts/experiment-collection.schema.json"
    jsonschema.validate(json.loads((destination / ".collection.json").read_text()),
                        json.loads(schema_path.read_text()))
    for row in plan["files"]:
        assert (destination / row["destination_path"]).read_bytes() == (run / row["source_path"]).read_bytes()
    assert (destination / "artifacts").is_dir()
    assert (destination / "inputs").is_dir()
    assert not (destination / "report.md").exists()
    assert not (destination / "notes.md").exists()
    (destination / "report.md").write_text("Human comparison\n")
    (destination / "notes.md").write_text("Human analysis\n")
    (destination / "custom.md").write_text("Additional local work\n")
    before_parent = snapshot(parent)
    assert receive(parent, child, plan)["status"] == "unchanged"
    assert snapshot(parent) == before_parent
    assert snapshot(child) == before_child
    assert yaml.safe_load((destination / "run.yaml").read_text())["source"]["commit"] == "f" * 40


@pytest.mark.parametrize("baseline", ["parent_sha256", "child_sha256", "evidence_sha256"])
def test_stale_receive_writes_nothing(sample, baseline):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    plan[baseline] = "0" * 64
    before = snapshot(parent), snapshot(child)
    with pytest.raises(ValueError, match="stale"):
        receive(parent, child, plan)
    assert (snapshot(parent), snapshot(child)) == before
    assert not (parent / "experiments").exists()


def test_existing_directory_and_local_evidence_changes_are_never_overwritten(sample):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    destination = parent / plan["destination"]
    destination.mkdir(parents=True)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert list(destination.iterdir()) == []
    destination.rmdir()
    receive(parent, child, plan)
    (destination / "inputs/config.json").write_text("Local changed execution evidence\n")
    before = snapshot(parent)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert snapshot(parent) == before


def test_publish_collision_refuses_even_when_foreign_directory_is_empty(sample, monkeypatch):
    from scholar_workflow.project import reception
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    destination = parent / plan["destination"]
    original = reception._publish
    def collide(descriptor, staged, final):
        destination.mkdir()
        original(descriptor, staged, final)
    monkeypatch.setattr(reception, "_publish", collide)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert list(destination.iterdir()) == []
    assert sorted(p.name for p in destination.parent.iterdir()) == [RUN]


def test_failed_stage_is_not_a_partially_received_run(sample, monkeypatch):
    from scholar_workflow.project import reception
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    original = reception._write_file
    calls = 0
    def fail(descriptor, relative, data, mode):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("Synthetic stage failure")
        original(descriptor, relative, data, mode)
    monkeypatch.setattr(reception, "_write_file", fail)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    destination = parent / plan["destination"]
    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_receive_cli_and_stale_error_mapping(sample):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    args = ["experiment", "receive-run", "--project-root", str(parent),
            "--child-root", str(child), "--run-id", RUN, "--json",
            "--expected-parent-sha256", plan["parent_sha256"],
            "--expected-child-sha256", plan["child_sha256"],
            "--expected-evidence-sha256", plan["evidence_sha256"]]
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "received"
    args[-1] = "0" * 64
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 5


def test_unconfirmed_durability_is_partial_then_safe_to_read_and_retry(sample, monkeypatch):
    from scholar_workflow.project import reception
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    original_publish, original_fsync = reception._publish, reception.os.fsync
    published = False
    def publish(*args):
        nonlocal published
        original_publish(*args)
        published = True
    def fsync(descriptor):
        if published:
            raise OSError("Synthetic post-publication fsync failure")
        original_fsync(descriptor)
    monkeypatch.setattr(reception, "_publish", publish)
    monkeypatch.setattr(reception.os, "fsync", fsync)
    with pytest.raises(reception.ReceptionError) as caught:
        receive(parent, child, plan)
    assert caught.value.exit_code == 6
    assert (parent / plan["destination"] / ".collection.json").is_file()
    with pytest.raises(reception.ReceptionError) as retry:
        receive(parent, child, plan)
    assert retry.value.exit_code == 6
    monkeypatch.setattr(reception.os, "fsync", original_fsync)
    assert receive(parent, child, plan)["status"] == "unchanged"


def test_source_change_during_stage_does_not_publish(sample, monkeypatch):
    from scholar_workflow.project import reception
    parent, child, run = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    original = reception._write_file
    def changed(descriptor, relative, data, mode):
        original(descriptor, relative, data, mode)
        (run / "notes.md").write_text("New remote note\n")
    monkeypatch.setattr(reception, "_write_file", changed)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert not (parent / plan["destination"]).exists()


def test_same_run_name_in_two_children_is_separate(sample, tmp_path):
    import shutil
    parent, child, _ = sample
    first = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, first)
    other = tmp_path / "other-child"
    shutil.copytree(child, other)
    other_id = "33333333-3333-4333-8333-333333333333"
    for name in ("project-layout.json", "project-management.json"):
        path = other / name
        value = json.loads(path.read_text())
        value["project_id"] = other_id
        if name == "project-management.json":
            value["primary"] = False
        path.write_text(json.dumps(value))
    path = parent / "project-management.json"
    value = json.loads(path.read_text())
    value["children"].append({"project_id": other_id, "archive_segment": "baseline", "primary": False})
    path.write_text(json.dumps(value))
    (other / "experiments" / RUN / "notes.md").write_text("Other child observations\n")
    second = plan_run_collection(parent, other, run_id=RUN)
    assert receive(parent, other, second)["status"] == "received"
    assert first["destination"] != second["destination"]
    assert (parent / first["destination"] / "execution-notes.md").read_text() == "Remote execution notes\n"
    assert (parent / second["destination"] / "execution-notes.md").read_text() == "Other child observations\n"
    assert receive(parent, child, plan_run_collection(parent, child, run_id=RUN))["status"] == "unchanged"
    from scholar_workflow.project.collected import collected_overview
    overview = collected_overview(parent)
    assert len(overview["children"]) == 2
    assert len({run["child_project_id"] for entry in overview["children"] for run in entry["runs"]}) == 2
    (parent / second["destination"] / "inputs/config.json").write_text("Changed second child\n")
    overview = collected_overview(parent)
    assert overview["status"] == "partial"
    assert overview["children"][0]["runs"][0]["state"] == "verified_archive"
    assert overview["children"][1]["runs"][0]["state"] == "invalid"
    assert collected_overview(parent, child_project_id=CHILD)["status"] == "complete"


@pytest.mark.parametrize("command", ["validate", "index"])
def test_flat_legacy_commands_cannot_report_zero_runs_for_parent_collections(sample, command):
    parent, child, _ = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    before = snapshot(parent)
    result = CliRunner().invoke(cli.main, ["experiment", command, "--project-root", str(parent)])
    assert result.exit_code == 2
    assert "execution child" in result.output
    assert snapshot(parent) == before


@pytest.mark.parametrize("level", ["experiments", "namespace"])
def test_destination_symlinks_refuse_without_writing_outside(sample, tmp_path, level):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    outside = tmp_path / "outside"
    outside.mkdir()
    if level == "experiments":
        (parent / "experiments").symlink_to(outside, target_is_directory=True)
    else:
        (parent / "experiments").mkdir()
        (parent / "experiments/main-method").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert list(outside.iterdir()) == []


def test_parent_can_still_register_credential_free_targets(sample):
    from scholar_workflow.project import register_target
    parent, _, run = sample
    (parent / "experiments/profiles/targets").mkdir(parents=True)
    target = register_target(parent, run / "attempts/succeeded/target.yaml")
    assert target.target_id == "test"
    assert (parent / "experiments/profiles/targets/test.yaml").is_file()


def test_failed_cleanup_reports_partial_and_preserves_stage_for_review(sample, monkeypatch):
    from scholar_workflow.project import reception
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    def fail(*args, **kwargs):
        raise PermissionError("Synthetic write/cleanup failure")
    monkeypatch.setattr(reception, "_write_file", fail)
    monkeypatch.setattr(reception.shutil, "rmtree", fail)
    with pytest.raises(reception.ReceptionError) as caught:
        receive(parent, child, plan)
    assert caught.value.exit_code == 6
    assert "cleanup is incomplete" in str(caught.value)
    destination = parent / plan["destination"]
    assert not destination.exists()
    remaining = list(destination.parent.iterdir())
    assert len(remaining) == 1 and remaining[0].name.startswith(".receive-")


def test_receipt_boolean_does_not_impersonate_integer_schema_version(sample):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, plan)
    path = parent / plan["destination"] / ".collection.json"
    receipt = json.loads(path.read_text())
    receipt["schema_version"] = True
    path.write_text(json.dumps(receipt))
    before = snapshot(parent)
    with pytest.raises(ValueError):
        receive(parent, child, plan)
    assert snapshot(parent) == before


def test_collected_reader_is_source_independent_and_read_only(sample, tmp_path, monkeypatch):
    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, plan)
    child.rename(tmp_path / "source-now-unavailable")
    before = snapshot(parent)
    def forbidden(*args, **kwargs):
        pytest.fail("Collected reading must not execute or load host configuration")
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    result = collected_overview(parent)
    assert result["status"] == "complete"
    record = result["children"][0]["runs"][0]
    assert record["state"] == "verified_archive"
    assert record["source_commit"] == "f" * 40
    assert record["config_path"] == f"experiments/main-method/{RUN}/inputs/config.json"
    assert {row["status"] for row in record["attempts"]} == {
        "planned", "running", "succeeded", "failed", "interrupted",
    }
    assert record["dataset"] == {"dataset_id": "test", "version": "1", "split": "fixed"}
    assert record["seed"] == 3
    markdown = render_collected_overview(result, language="en")
    assert "Conditions / captured config" in markdown and "Recorded outcome / result files" in markdown
    assert "f" * 40 not in markdown and PARENT not in markdown and CHILD not in markdown
    assert "not a scientific comparison" in markdown
    assert snapshot(parent) == before
    cli_result = CliRunner().invoke(cli.main, ["experiment", "collected", "--project-root", str(parent), "--json"])
    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.output) == result
    assert snapshot(parent) == before


@pytest.mark.parametrize("change", ["receipt", "file", "symlink", "path"])
def test_collected_reader_retains_invalid_record_without_false_success(sample, tmp_path, change):
    from scholar_workflow.project.collected import collected_overview
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, plan)
    destination = parent / plan["destination"]
    if change == "file":
        (destination / "inputs/config.json").write_text("changed\n")
    elif change == "symlink":
        outside = tmp_path / "outside"
        outside.write_text("outside\n")
        path = destination / "inputs/config.json"
        path.unlink()
        path.symlink_to(outside)
    else:
        path = destination / ".collection.json"
        value = json.loads(path.read_text())
        if change == "receipt":
            value["child_project_id"] = PARENT
        else:
            value["files"][0]["destination_path"] = "../escape"
        path.write_text(json.dumps(value))
    before = snapshot(parent)
    result = collected_overview(parent)
    assert result["status"] == "partial"
    assert result["children"][0]["runs"][0]["state"] == "invalid"
    assert snapshot(parent) == before


def test_collected_reader_does_not_discover_unregistered_roots(sample):
    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, _, _ = sample
    (parent / "experiments/unregistered").mkdir(parents=True)
    (parent / "experiments/unregistered/private.txt").write_text("not an archive\n")
    before = snapshot(parent)
    result = collected_overview(parent)
    assert result["children"][0]["state"] == "not_received"
    assert result["status"] == "complete"  # Query scope only; no delivery checklist was supplied.
    assert "required_runs" not in result
    assert "private.txt" not in json.dumps(result)
    assert "not received" in render_collected_overview(result, language="en")
    assert snapshot(parent) == before


def test_collected_reader_requires_registered_child_selector(sample):
    from scholar_workflow.project.collected import collected_overview
    parent, _, _ = sample
    with pytest.raises(ValueError):
        collected_overview(parent, child_project_id="33333333-3333-4333-8333-333333333333")


@pytest.mark.parametrize("empty_namespace", [False, True])
def test_required_archives_do_not_accept_report_only_delivery(sample, monkeypatch, empty_namespace):
    parent, child, _ = sample
    report = parent / "docs/report/summary.md"
    report.parent.mkdir(parents=True)
    report.write_text("Results remain on remote-host:/results; not collected.\n")
    if empty_namespace:
        (parent / "experiments/main-method").mkdir(parents=True)
    before = snapshot(parent), snapshot(child)

    def forbidden(*args, **kwargs):
        pytest.fail("Archive delivery checking must not launch tools or load host config")

    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collected", "--project-root", str(parent),
        "--child-project-id", CHILD, "--require-run", RUN, "--json",
    ])
    assert result.exit_code == 6, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "partial"
    assert payload["required_runs"] == {"requested": [RUN], "missing": [RUN]}
    assert payload["children"][0]["runs"] == []
    assert (snapshot(parent), snapshot(child)) == before


@pytest.mark.parametrize("damage", [False, True])
def test_required_archives_check_received_evidence_not_report_claims(sample, damage):
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, plan)
    if damage:
        (parent / plan["destination"] / "inputs/config.json").write_text("changed\n")
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collected", "--project-root", str(parent),
        "--child-project-id", CHILD, "--require-run", RUN, "--json",
    ])
    assert result.exit_code == (6 if damage else 0), result.output
    payload = json.loads(result.stdout)
    assert payload["required_runs"] == {"requested": [RUN], "missing": []}
    record = payload["children"][0]["runs"][0]
    assert record["state"] == ("invalid" if damage else "verified_archive")
    if not damage:
        assert record["source_commit"] == "f" * 40
        assert len(record["attempts"]) == 5
    assert (snapshot(parent), snapshot(child)) == before


def test_required_archives_keep_present_runs_when_another_is_missing(sample):
    parent, child, _ = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    missing = "20261018-1300-uncollected"
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collected", "--project-root", str(parent),
        "--child-project-id", CHILD, "--require-run", RUN,
        "--require-run", missing, "--language", "zh",
    ])
    assert result.exit_code == 6, result.output
    assert missing in result.stdout and RUN in result.stdout
    assert "尚未接收" in result.stdout
    assert "配置" in result.stdout and "中断" in result.stdout
    assert (snapshot(parent), snapshot(child)) == before


@pytest.mark.parametrize("args,message", [
    (["--require-run", RUN], "explicit registered child selector"),
    (["--child-project-id", CHILD, "--require-run", "../escape"], "Invalid required Run ID"),
    (["--child-project-id", CHILD, "--require-run", RUN, "--require-run", RUN], "must be unique"),
])
def test_required_archives_reject_ambiguous_or_invalid_scope(sample, args, message):
    parent, child, _ = sample
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collected", "--project-root", str(parent), *args, "--json",
    ])
    assert result.exit_code == 2, result.output
    assert message in result.output
    assert (snapshot(parent), snapshot(child)) == before


def test_required_archives_do_not_convert_legacy_project_or_read_reports(sample):
    parent, child, _ = sample
    (parent / "project-management.json").unlink()
    (parent / "report.md").write_text("All experiments completed remotely.\n")
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, [
        "experiment", "collected", "--project-root", str(parent),
        "--child-project-id", CHILD, "--require-run", RUN, "--json",
    ])
    assert result.exit_code == 2, result.output
    assert "project-management.json" in result.output
    assert (snapshot(parent), snapshot(child)) == before


def test_legacy_role_adoption_connects_to_registration_and_real_archive_reception(sample):
    parent, child, _ = sample
    for root, identity in ((parent, PARENT), (child, CHILD)):
        (root / "project-management.json").unlink()
        (root / "project-layout.json").write_text(json.dumps({
            "schema_version": 2, "project_id": identity, "language": "python",
            "package": None, "source_profile": None, "addons": [],
        }))
        (root / "AGENTS.md").write_text("Preserve existing human instructions.\n")
        (root / ".gitignore").write_text("dataset/\ndocs/\nexperiments/\n")
    before_parent, before_child = snapshot(parent), snapshot(child)
    runner = CliRunner()

    def command(*args):
        result = runner.invoke(cli.main, [*args, "--json"])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    for root, role, extras in (
        (parent, "research-parent", []),
        (child, "execution-child", ["--parent-project-id", PARENT, "--primary"]),
    ):
        args = ["project", "adopt-role", "--project-root", str(root), "--role", role, *extras]
        plan = command(*args)
        command(*args, "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    args = ["project", "register-child", "--project-root", str(parent),
            "--child-root", str(child), "--archive-segment", "main-method"]
    registration = command(*args)
    command(*args, "--apply", "--expected-parent-sha256", registration["parent_sha256"],
            "--expected-child-sha256", registration["child_sha256"])
    args = ["--project-root", str(parent), "--child-root", str(child), "--run-id", RUN]
    plan = command("experiment", "collection-plan", *args)
    command("experiment", "receive-run", *args,
            "--expected-parent-sha256", plan["parent_sha256"],
            "--expected-child-sha256", plan["child_sha256"],
            "--expected-evidence-sha256", plan["evidence_sha256"])
    collected = command("experiment", "collected", "--project-root", str(parent),
                        "--child-project-id", CHILD, "--require-run", RUN)
    record = collected["children"][0]["runs"][0]
    assert record["state"] == "verified_archive" and record["source_commit"] == "f" * 40
    assert len(record["attempts"]) == 5
    assert collected["execution_verification"] == "records_only"
    assert {key: snapshot(parent)[key] for key in before_parent} == before_parent
    assert {key: snapshot(child)[key] for key in before_child} == before_child


def test_collected_markdown_links_and_chinese_labels_are_usable(sample):
    import re
    from urllib.parse import unquote

    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, child, _ = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    markdown = render_collected_overview(collected_overview(parent), language="zh")
    assert "条件／配置快照" in markdown and "记录结果／结果文件" in markdown
    assert "开始：" in markdown and "退出码" in markdown and "随机种子" in markdown
    assert "f" * 40 not in markdown and PARENT not in markdown
    for value in re.findall(r"\]\(([^)]+)\)", markdown):
        assert (parent / unquote(value)).is_file()


def test_collected_metrics_are_links_not_invented_scientific_scores(sample):
    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, child, run = sample
    metrics = b'{"score": 0.8}\n'
    (run / "artifacts/metrics.json").write_bytes(metrics)
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": [
        {"artifact_id": "art_1111111111111111", "role": "metrics", "retention": "local-required",
         "source_attempt_id": "succeeded", "relative_path": "artifacts/metrics.json",
         "size": len(metrics), "sha256": sha(metrics), "remote_source": None,
         "promoted_at": "2026-10-18T12:05:00Z"},
        {"artifact_id": "art_2222222222222222", "role": "metrics", "retention": "manifest-only",
         "source_attempt_id": "failed", "remote_source": "remote-only-metrics", "promoted_at": None},
    ]})
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    result = collected_overview(parent)
    assert result["status"] == "complete"
    record = result["children"][0]["runs"][0]
    assert {item["state"] for item in record["metrics"]} == {"local_unreviewed", "remote_only"}
    markdown = render_collected_overview(result, language="en")
    assert "Metrics (unreviewed)" in markdown and "Metrics remote only" in markdown
    assert "0.8" not in markdown and "best" not in markdown


def finish_running(run):
    path = run / "attempts/running/attempt.yaml"
    value = yaml.safe_load(path.read_text())
    value.update(status="succeeded", finished_at="2026-10-18T12:03:00Z", exit_code=0)
    write_yaml(path, value)


def test_update_preview_is_precise_and_preserves_local_analysis(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, run = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    local = parent / "experiments/main-method" / RUN
    (local / "notes.md").write_text("Concurrent human analysis\n")
    (local / "report.md").write_text("Human comparison\n")
    finish_running(run)
    (run / "attempts/running/stdout.log").write_text("Synthetic completion, not actual execution\n")
    before = snapshot(parent), snapshot(child)
    result = plan_run_update(parent, child, run_id=RUN)
    assert result["status"] == "planned_update"
    assert {(row["destination_path"], row["kind"]) for row in result["changes"]} == {
        ("attempts/running/attempt.yaml", "replace"), ("attempts/running/stdout.log", "add"),
    }
    assert {"attempt_id": "running", "from": "running", "to": "succeeded"} in result["transitions"]
    assert result["local_receipt_sha256"] == sha((local / ".collection.json").read_bytes())
    assert result["old_evidence_sha256"] != result["new_evidence_sha256"]
    assert (snapshot(parent), snapshot(child)) == before


def test_identical_update_preview_has_no_writes_or_changes(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, _ = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    before = snapshot(parent), snapshot(child)
    result = plan_run_update(parent, child, run_id=RUN)
    assert result["status"] == "unchanged" and result["changes"] == []
    assert (snapshot(parent), snapshot(child)) == before


@pytest.mark.parametrize("change", ["backward", "terminal", "target", "recipe", "delete", "collision", "dirty_local"])
def test_unsafe_update_is_not_a_valid_preview(sample, change):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, run = sample
    if change == "delete":
        (run / "history.log").write_text("Keep this old evidence\n")
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    if change == "backward":
        path = run / "attempts/running/attempt.yaml"
        value = yaml.safe_load(path.read_text())
        value.update(status="planned", started_at=None)
        write_yaml(path, value)
    elif change == "terminal":
        path = run / "attempts/succeeded/attempt.yaml"
        value = yaml.safe_load(path.read_text())
        value["actual"] = {"hostname": "corrected-after-completion"}
        write_yaml(path, value)
    elif change == "target":
        target = run / "attempts/running/target.yaml"
        value = yaml.safe_load(target.read_text())
        value["project_root"] = "another-working-root"
        write_yaml(target, value)
        path = run / "attempts/running/attempt.yaml"
        value = yaml.safe_load(path.read_text())
        value["target_profile_sha256"] = sha(target.read_bytes())
        write_yaml(path, value)
    elif change == "recipe":
        from scholar_workflow.project.experiments import _canonical_hash, _recipe_payload
        from scholar_workflow.project.models import RunRecord
        path = run / "run.yaml"
        value = yaml.safe_load(path.read_text())
        value["source"]["commit"] = "a" * 40
        value["recipe_hash"] = _canonical_hash(_recipe_payload(RunRecord.model_validate(value)))
        write_yaml(path, value)
    elif change == "delete":
        (run / "history.log").unlink()
    elif change == "collision":
        (parent / "experiments/main-method" / RUN / "custom.md").write_text("Human file\n")
        (run / "custom.md").write_text("New remote file\n")
    else:
        (parent / "experiments/main-method" / RUN / "run.sh").write_text("Locally edited evidence\n")
    before = snapshot(parent), snapshot(child)
    with pytest.raises(ValueError):
        plan_run_update(parent, child, run_id=RUN)
    assert (snapshot(parent), snapshot(child)) == before


def test_pending_update_is_not_a_verified_or_idempotently_received_archive(sample):
    from scholar_workflow.project.collected import collected_overview
    from scholar_workflow.project.reception import ReceptionError
    parent, child, _ = sample
    plan = plan_run_collection(parent, child, run_id=RUN)
    receive(parent, child, plan)
    path = parent / plan["destination"] / ".collection-update.json"
    path.write_text("{}\n")
    before = snapshot(parent)
    result = collected_overview(parent)
    assert result["status"] == "partial"
    assert result["children"][0]["runs"][0]["state"] == "pending_update"
    with pytest.raises(ReceptionError) as caught:
        receive(parent, child, plan)
    assert caught.value.exit_code == 6
    assert snapshot(parent) == before


def test_update_preview_records_new_attempt_and_empty_directories(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, run = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    value = yaml.safe_load((run / "attempts/planned/attempt.yaml").read_text())
    value["attempt_id"] = "new-attempt"
    write_yaml(run / "attempts/new-attempt/attempt.yaml", value)
    target = yaml.safe_load((run / "attempts/planned/target.yaml").read_text())
    write_yaml(run / "attempts/new-attempt/target.yaml", target)
    (run / "artifacts/new-empty-group").mkdir()
    result = plan_run_update(parent, child, run_id=RUN)
    assert result["status"] == "planned_update"
    assert {"attempt_id": "new-attempt", "from": None, "to": "planned"} in result["transitions"]
    assert "artifacts/new-empty-group" in result["new_directories"]
    assert {row["destination_path"] for row in result["changes"]} == {
        "attempts/new-attempt/attempt.yaml", "attempts/new-attempt/target.yaml",
    }


def test_empty_directory_only_change_is_not_unchanged(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, run = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    (run / "artifacts/new-empty-group").mkdir()
    result = plan_run_update(parent, child, run_id=RUN)
    assert result["status"] == "planned_update" and result["changes"] == []
    assert result["new_directories"] == ["artifacts/new-empty-group"]


def test_manifest_only_promotion_can_be_previewed_without_faking_backup(sample):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, run = sample
    entry = {"artifact_id": "art_1111111111111111", "role": "metrics", "retention": "manifest-only",
             "source_attempt_id": "succeeded", "remote_source": "remote-metrics", "promoted_at": None}
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": [entry]})
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    data = b'{"score": 0.8}\n'
    (run / "artifacts/metrics.json").write_bytes(data)
    entry.update(retention="local-required", relative_path="artifacts/metrics.json", size=len(data),
                 sha256=sha(data), promoted_at="2026-10-18T12:04:00Z")
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": [entry]})
    result = plan_run_update(parent, child, run_id=RUN)
    assert {row["destination_path"] for row in result["changes"]} == {"artifacts.yaml", "artifacts/metrics.json"}
    assert result["status"] == "planned_update"
    assert result["artifact_transitions"] == [{
        "artifact_id": "art_1111111111111111", "role": "metrics", "source_attempt_id": "succeeded",
        "from": "manifest-only", "to": "local-required", "backup_state": "not-verified",
    }]


def test_update_plan_cli_is_read_only(sample):
    parent, child, run = sample
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN))
    finish_running(run)
    before = snapshot(parent), snapshot(child)
    result = CliRunner().invoke(cli.main, ["experiment", "update-plan", "--project-root", str(parent),
                                         "--child-root", str(child), "--run-id", RUN, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "planned_update"
    assert (snapshot(parent), snapshot(child)) == before


@pytest.mark.parametrize("name", [".collection.json", ".collection-update.json"])
@pytest.mark.parametrize("kind", ["file", "directory"])
def test_source_cannot_import_local_collection_transaction_metadata(sample, name, kind):
    parent, child, run = sample
    if kind == "file":
        (run / name).write_text("{}\n")
    else:
        (run / name).mkdir()
    before = snapshot(parent), snapshot(child)
    with pytest.raises(ValueError, match="reserved"):
        plan_run_collection(parent, child, run_id=RUN)
    assert (snapshot(parent), snapshot(child)) == before
