"""Independent expected deliveries from one synthetic Run, never an experiment."""

import base64
import builtins
import io
import json
import os
from pathlib import Path

import pytest
import yaml

from scholar_workflow.project.collection import plan_run_collection
from scholar_workflow.project.reception import receive_run
from tests.contract.test_project_collection_plan import (
    CHILD,
    PARENT,
    RUN,
    sample,  # noqa: F401
    sha,
    snapshot,
    write_yaml,
)


@pytest.fixture
def delivery(sample):  # noqa: F811
    parent, child, run = sample
    metrics = b'{"accuracy": 0.8}\n'
    model = b"SYNTHETIC MODEL PAYLOAD; MUST NOT BE READ\n"
    (run / "artifacts/metrics.json").write_bytes(metrics)
    (run / "artifacts/model.safetensors").write_bytes(model)
    rows = []
    for number, (name, role, content) in enumerate((
        ("metrics.json", "metrics", metrics), ("model.safetensors", "checkpoint", model),
    ), 1):
        rows.append({"artifact_id": "art_" + str(number) * 16, "role": role,
                     "retention": "local-required", "source_attempt_id": "succeeded",
                     "relative_path": "artifacts/" + name, "size": len(content),
                     "sha256": sha(content), "remote_source": None,
                     "promoted_at": "2026-10-18T12:05:00Z"})
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": rows})
    selection = {"schema_version": 1, "include": [
        {"path": "artifacts/metrics.json", "kind": "metrics", "purpose": "Compare recorded accuracy"},
    ], "defer": []}
    return parent, child, run, selection


def receive(parent, child, plan, selection):
    return receive_run(parent, child, run_id=RUN, selection=selection, **{
        "expected_" + key: plan[key] for key in ("parent_sha256", "child_sha256", "evidence_sha256")
    })


def deny_model_open(monkeypatch):
    original = os.open
    io_open, builtin_open = io.open, builtins.open

    def check(path):
        if not isinstance(path, int):
            assert os.fspath(path).split("/")[-1] != "model.safetensors", "Model bytes must stay unread"

    def guarded(path, *args, **kwargs):
        check(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded)
    def checked_open(operation):
        def opened(path, *args, **kwargs):
            check(path)
            return operation(path, *args, **kwargs)
        return opened
    monkeypatch.setattr(io, "open", checked_open(io_open))
    monkeypatch.setattr(builtins, "open", checked_open(builtin_open))


def test_default_collection_refuses_model_payload_before_reading(delivery, monkeypatch):
    parent, child, _run, _selection = delivery
    deny_model_open(monkeypatch)
    with pytest.raises(ValueError, match="selection|model|payload"):
        plan_run_collection(parent, child, run_id=RUN)
    assert not (parent / "experiments").exists()


def test_selected_results_receive_original_records_and_omit_model(delivery, monkeypatch):
    parent, child, run, selection = delivery
    original = snapshot(child)
    with monkeypatch.context() as guard:
        deny_model_open(guard)
        plan = plan_run_collection(parent, child, run_id=RUN, selection=selection)
        assert plan["schema_version"] == 2
        assert "artifacts/model.safetensors" not in {row["source_path"] for row in plan["files"]}
        omitted = plan["result_delivery"]["omitted"]
        assert len(omitted) == 1
        assert omitted[0]["source_path"] == "artifacts/model.safetensors"
        assert omitted[0]["reason"] == "model"
        assert omitted[0]["declared_sha256"] == sha(original[f"experiments/{RUN}/artifacts/model.safetensors"])
        assert plan["result_delivery"]["omitted_byte_verification"] == "not-performed"
        result = receive(parent, child, plan, selection)
        assert result["status"] == "received"
        local = parent / result["destination"]
        for name in ("run.yaml", "artifacts.yaml", "inputs/config.json", "artifacts/metrics.json"):
            assert (local / name).read_bytes() == (run / name).read_bytes()
        assert not (local / "artifacts/model.safetensors").exists()
        assert len(list((local / "attempts").iterdir())) == 5
        receipt = json.loads((local / ".collection.json").read_text())
        assert receipt["schema_version"] == 2 and receipt["result_delivery"] == plan["result_delivery"]
        assert receive(parent, child, plan, selection)["status"] == "unchanged"
    assert snapshot(child) == original


def test_model_cannot_be_included_under_an_invented_result_label(delivery, monkeypatch):
    parent, child, _run, selection = delivery
    selection["include"].append({"path": "artifacts/model.safetensors", "kind": "metrics",
                                 "purpose": "This label must not bypass the payload boundary"})
    deny_model_open(monkeypatch)
    with pytest.raises(ValueError, match="model|payload"):
        plan_run_collection(parent, child, run_id=RUN, selection=selection)


def test_checkpoint_role_cannot_be_disguised_as_readable_text(delivery, monkeypatch):
    parent, child, run, selection = delivery
    (run / "artifacts/model.safetensors").rename(run / "artifacts/weights.txt")
    record = yaml.safe_load((run / "artifacts.yaml").read_text())
    record["artifacts"][1]["relative_path"] = "artifacts/weights.txt"
    write_yaml(run / "artifacts.yaml", record)
    selection["include"].append({"path": "artifacts/weights.txt", "kind": "metrics",
                                 "purpose": "A readable suffix must not override the checkpoint role"})
    original = os.open
    def guarded(path, *args, **kwargs):
        assert os.fspath(path).split("/")[-1] != "weights.txt", "Checkpoint bytes were opened"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded)
    with pytest.raises(ValueError, match="model|payload"):
        plan_run_collection(parent, child, run_id=RUN, selection=selection)


def test_required_metrics_need_selection_or_an_explicit_deferral(delivery):
    parent, child, _run, selection = delivery
    selection["include"] = []
    with pytest.raises(ValueError, match="(?i)required|metrics"):
        plan_run_collection(parent, child, run_id=RUN, selection=selection)


def test_selective_archive_is_readable_and_keeps_omissions_honest(delivery, monkeypatch):
    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, child, _run, selection = delivery
    deny_model_open(monkeypatch)
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    result = collected_overview(parent, child_project_id=CHILD, required_run_ids=(RUN,))
    assert result["status"] == "complete"
    row = result["children"][0]["runs"][0]
    assert row["state"] == "verified_archive"
    assert row["metrics"][0]["state"] == "local_unreviewed"
    assert row["result_delivery"]["omitted"][0]["reason"] == "model"
    markdown = render_collected_overview(result, language="zh")
    assert "留在源端" in markdown and "字节未读取核验" in markdown
    assert "safetensors](" not in markdown and "[指标（未解读）]" in markdown


def test_explicit_required_result_deferral_is_partial_not_received_evidence(delivery):
    from scholar_workflow.project.collected import collected_overview, render_collected_overview
    parent, child, _run, selection = delivery
    selection["include"] = []
    selection["defer"] = [{"path": "artifacts/metrics.json", "reason": "Operator deferred this transfer"}]
    plan = plan_run_collection(parent, child, run_id=RUN, selection=selection)
    receive(parent, child, plan, selection)
    result = collected_overview(parent)
    assert result["status"] == "partial"
    row = result["children"][0]["runs"][0]
    assert row["state"] == "verified_archive" and row["metrics"][0]["path"] is None
    assert row["result_gaps"] == ["artifacts/metrics.json"]
    assert "必需成果已明确延后" in render_collected_overview(result, language="zh")


def test_omitted_large_model_does_not_consume_readable_result_budget(delivery, monkeypatch):
    parent, child, run, selection = delivery
    with (run / "artifacts/model.safetensors").open("wb") as stream:
        stream.truncate(256 * 1024 * 1024)
    deny_model_open(monkeypatch)
    plan = plan_run_collection(parent, child, run_id=RUN, selection=selection)
    assert sum(row["size"] for row in plan["files"]) < 32 * 1024
    assert receive(parent, child, plan, selection)["status"] == "received"


def test_selected_figure_is_received_in_its_original_report_location(delivery):
    parent, child, run, selection = delivery
    image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    (run / "artifacts/figure.png").write_bytes(image)
    selection["include"].append({"path": "artifacts/figure.png", "kind": "image",
                                 "purpose": "Synthetic figure transfer fixture"})
    (run / "report.md").write_text("# Synthetic report\n\n![Figure](artifacts/figure.png)\n")
    result = receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    local = parent / result["destination"]
    assert (local / "artifacts/figure.png").read_bytes() == image
    assert (local / "execution-report.md").read_bytes() == (run / "report.md").read_bytes()


def test_changed_selection_is_stale_before_any_archive_creation(delivery):
    from scholar_workflow.project.reception import ReceptionError
    parent, child, _run, selection = delivery
    plan = plan_run_collection(parent, child, run_id=RUN, selection=selection)
    selection["include"][0]["purpose"] = "Different reviewed scope"
    with pytest.raises(ReceptionError) as caught:
        receive(parent, child, plan, selection)
    assert caught.value.exit_code == 5
    assert not (parent / "experiments").exists()


@pytest.mark.parametrize("direction", ["commit", "rollback"])
def test_selective_update_recovers_offline_and_preserves_local_analysis(delivery, monkeypatch, direction):
    from scholar_workflow.project import transactions
    from scholar_workflow.project.collected import collected_overview
    from scholar_workflow.project.reception import ReceptionError
    from scholar_workflow.project.updates import plan_run_update
    from tests.contract.test_project_collection_plan import finish_running
    parent, child, run, selection = delivery
    deny_model_open(monkeypatch)
    received = receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    local = parent / received["destination"]
    (local / "notes.md").write_text("Human local analysis survives\n")
    before = snapshot(local)
    finish_running(run)
    (run / "attempts/running/stdout.log").write_text("Synthetic progress\n")
    selection["include"].append({"path": "attempts/running/stdout.log", "kind": "log",
                                 "purpose": "Explain the observed completion"})
    plan = plan_run_update(parent, child, run_id=RUN, selection=selection)
    original = transactions._install_action
    with monkeypatch.context() as patch:
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError("Synthetic interruption after the first action")
        patch.setattr(transactions, "_install_action", interrupted)
        with pytest.raises(ReceptionError) as caught:
            transactions.apply_run_update(parent, child, run_id=RUN, selection=selection, **{
                "expected_" + key: plan[key] for key in (
                    "parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256")})
        assert caught.value.exit_code == 6
    child.rename(child.with_name("child-offline"))
    recovery = transactions.plan_run_recovery(parent, child_project_id=CHILD, run_id=RUN)
    result = transactions.recover_run_update(parent, child_project_id=CHILD, run_id=RUN,
        direction=direction, expected_revision=recovery["revision_sha256"])
    assert result["status"] == ("committed" if direction == "commit" else "rolled_back")
    assert (local / "notes.md").read_text() == "Human local analysis survives\n"
    assert not (local / "artifacts/model.safetensors").exists()
    assert collected_overview(parent)["status"] == "complete"
    if direction == "rollback":
        assert snapshot(local) == before
    else:
        assert (local / "attempts/running/stdout.log").read_text() == "Synthetic progress\n"


def test_cli_selection_config_and_public_schema(delivery, tmp_path):
    import jsonschema
    from click.testing import CliRunner

    from scholar_workflow.cli import main
    parent, child, _run, selection = delivery
    config = tmp_path / "result-selection.yaml"
    write_yaml(config, selection)
    args = ["--project-root", str(parent), "--child-root", str(child), "--run-id", RUN,
            "--selection-file", str(config), "--json"]
    preview = CliRunner().invoke(main, ["experiment", "collection-plan", *args])
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.output)
    received = CliRunner().invoke(main, ["experiment", "receive-run", *args, *[
        argument for key in ("parent_sha256", "child_sha256", "evidence_sha256")
        for argument in ("--expected-" + key.replace("_", "-"), plan[key])]])
    assert received.exit_code == 0, received.output
    local = parent / json.loads(received.output)["destination"]
    receipt = json.loads((local / ".collection.json").read_text())
    root = Path(__file__).parents[2] / "contracts"
    jsonschema.Draft202012Validator(json.loads((root / "experiment-result-selection.schema.json").read_text())).validate(selection)
    jsonschema.Draft202012Validator(json.loads((root / "experiment-collection.schema.json").read_text())).validate(receipt)


def test_unknown_payload_is_refused_before_opening_even_without_artifact_registration(delivery, monkeypatch):
    parent, child, run, _selection = delivery
    # The model suffix is already covered; exercise an otherwise unknown file.
    (run / "artifacts/model.safetensors").unlink()
    write_yaml(run / "artifacts.yaml", {"schema_version": 1, "run_id": RUN, "artifacts": []})
    (run / "artifacts/weights.payload").write_bytes(b"Synthetic opaque payload")
    original = os.open
    def guarded(path, *args, **kwargs):
        assert os.fspath(path).split("/")[-1] != "weights.payload", "Unknown payload was opened"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", guarded)
    with pytest.raises(ValueError, match="payload|selection"):
        plan_run_collection(parent, child, run_id=RUN)


def test_omitted_symlink_is_not_followed(delivery, tmp_path):
    parent, child, run, selection = delivery
    outside = tmp_path / "outside-data"
    outside.write_bytes(b"Keep outside data unchanged")
    model = run / "artifacts/model.safetensors"
    model.unlink()
    model.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink|unsafe"):
        plan_run_collection(parent, child, run_id=RUN, selection=selection)
    assert outside.read_bytes() == b"Keep outside data unchanged"
    assert not (parent / "experiments").exists()


def test_old_complete_receipt_remains_readable_without_automatic_rewrite(delivery):
    from scholar_workflow.project.collected import collected_overview
    from scholar_workflow.project.collection import _tree
    parent, child, _run, _selection = delivery
    # Prepare a historical schema-1 archive directly, not through the new writer.
    files, directories, modes = _tree(child, RUN)
    local = parent / "experiments/main-method" / RUN
    local.mkdir(parents=True)
    for directory in directories:
        (local / directory).mkdir(parents=True, exist_ok=True)
    rows = []
    for name, data in sorted(files.items()):
        destination = {"report.md": "execution-report.md", "notes.md": "execution-notes.md"}.get(name, name)
        (local / destination).write_bytes(data)
        (local / destination).chmod(modes[name])
        rows.append({"source_path": name, "destination_path": destination, "size": len(data),
                     "sha256": sha(data), "mode": modes[name]})
    recipe = yaml.safe_load(files["run.yaml"])
    receipt = {"schema_version": 1, "parent_project_id": PARENT, "child_project_id": CHILD,
               "run_id": RUN, "source_commit": recipe["source"]["commit"], "recipe_hash": recipe["recipe_hash"],
               "evidence_sha256": sha(json.dumps({"files": rows, "directories": sorted(directories)},
                                                sort_keys=True, separators=(",", ":")).encode()),
               "files": rows, "directories": sorted(directories), "execution_verification": "records_only"}
    (local / ".collection.json").write_text(json.dumps(receipt))
    before = snapshot(parent)
    assert collected_overview(parent)["status"] == "complete"
    assert snapshot(parent) == before


@pytest.mark.parametrize("change", ["declared-hash", "verified-claim"])
def test_forged_omission_is_not_a_valid_archive(delivery, change):
    from scholar_workflow.project.collected import collected_overview
    parent, child, _run, selection = delivery
    result = receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    path = parent / result["destination"] / ".collection.json"
    receipt = json.loads(path.read_text())
    if change == "declared-hash":
        receipt["result_delivery"]["omitted"][0]["declared_sha256"] = "0" * 64
    else:
        receipt["result_delivery"]["omitted_byte_verification"] = "verified"
    receipt["evidence_sha256"] = sha(json.dumps({key: receipt[key] for key in (
        "files", "directories", "result_delivery")}, sort_keys=True, separators=(",", ":")).encode())
    path.write_text(json.dumps(receipt))
    assert collected_overview(parent)["children"][0]["runs"][0]["state"] == "invalid"


@pytest.mark.parametrize("change", ["version-bool", "traversal", "absolute", "duplicate", "unknown"])
def test_bad_selection_does_not_create_archive(delivery, change):
    parent, child, _run, selection = delivery
    if change == "version-bool":
        selection["schema_version"] = True
    elif change == "duplicate":
        selection["include"].append(dict(selection["include"][0]))
    else:
        selection["include"][0]["path"] = {"traversal": "../outside.json", "absolute": "/tmp/result.json",
                                            "unknown": "artifacts/missing.json"}[change]
    with pytest.raises(ValueError):
        plan_run_collection(parent, child, run_id=RUN, selection=selection)
    assert not (parent / "experiments").exists()


def test_readable_only_staging_keeps_original_declared_model_as_unreceived(delivery, monkeypatch):
    from scholar_workflow.project.collected import collected_overview
    parent, child, run, selection = delivery
    original = (run / "artifacts.yaml").read_bytes()
    (run / "artifacts/model.safetensors").unlink()
    deny_model_open(monkeypatch)
    plan = plan_run_collection(parent, child, run_id=RUN, selection=selection)
    assert plan["result_delivery"]["omitted"][0]["reason"] == "model"
    result = receive(parent, child, plan, selection)
    assert (parent / result["destination"] / "artifacts.yaml").read_bytes() == original
    assert collected_overview(parent)["status"] == "complete"


def test_cli_update_uses_the_same_selection_and_keeps_model_unopened(delivery, tmp_path, monkeypatch):
    from click.testing import CliRunner

    from scholar_workflow.cli import main
    from tests.contract.test_project_collection_plan import finish_running
    parent, child, run, selection = delivery
    config = tmp_path / "selection.yaml"
    write_yaml(config, selection)
    deny_model_open(monkeypatch)
    initial = plan_run_collection(parent, child, run_id=RUN, selection=selection)
    result = receive(parent, child, initial, selection)
    finish_running(run)
    args = ["--project-root", str(parent), "--child-root", str(child), "--run-id", RUN,
            "--selection-file", str(config), "--json"]
    preview = CliRunner().invoke(main, ["experiment", "update-plan", *args])
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.output)
    updated = CliRunner().invoke(main, ["experiment", "update-run", *args, *[
        argument for key in ("parent_sha256", "child_sha256", "new_evidence_sha256", "local_receipt_sha256")
        for argument in ("--expected-" + key.replace("_", "-"), plan[key])]])
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["status"] == "updated"
    assert not (parent / result["destination"] / "artifacts/model.safetensors").exists()


def test_required_run_cli_reports_deferred_result_as_partial(delivery):
    from click.testing import CliRunner

    from scholar_workflow.cli import main
    parent, child, _run, selection = delivery
    selection["include"] = []
    selection["defer"] = [{"path": "artifacts/metrics.json", "reason": "Transfer explicitly deferred"}]
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    result = CliRunner().invoke(main, ["experiment", "collected", "--project-root", str(parent),
        "--child-project-id", CHILD, "--require-run", RUN, "--json"])
    assert result.exit_code == 6, result.output
    assert json.loads(result.output)["status"] == "partial"


def test_selection_update_cannot_remove_previously_received_metrics(delivery):
    from scholar_workflow.project.updates import plan_run_update
    parent, child, _run, selection = delivery
    receive(parent, child, plan_run_collection(parent, child, run_id=RUN, selection=selection), selection)
    before = snapshot(parent)
    selection["include"] = []
    selection["defer"] = [{"path": "artifacts/metrics.json", "reason": "Must not remove received bytes"}]
    with pytest.raises(ValueError, match="cannot be removed"):
        plan_run_update(parent, child, run_id=RUN, selection=selection)
    assert snapshot(parent) == before
