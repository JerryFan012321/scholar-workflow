"""Portable execution-code references and explicit read-only location planning."""
import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.context import (
    ProjectContext,
    build_project_overview,
    render_project_overview,
)

PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
SCHEMA = json.loads((Path(__file__).parents[2] / "contracts/project-context.schema.json").read_text())


def payload():
    return {"schema_version": 1, "project_id": PARENT, "title": "Synthetic parent",
            "summary": "Connect selected code with project research.", "language": "zh", "entries": [
                {"entry_id": "method-code", "kind": "code", "title": "主要方法代码",
                 "purpose": "训练及评估项目方法。", "ref": {
                     "kind": "execution-code", "child_project_id": CHILD,
                     "relative_path": "src/train.py", "commit": "a" * 40,
                 }},
            ]}


def files(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def sample(tmp_path):
    parent, ledger = tmp_path / "parent", tmp_path / "private-ledger"
    parent.mkdir()
    ledger.mkdir(mode=0o700)
    (parent / "project-layout.json").write_text(json.dumps({
        "schema_version": 2, "project_id": PARENT, "language": "python", "package": None,
        "source_profile": None, "addons": [],
    }))
    (parent / "project-management.json").write_text(json.dumps({
        "schema_version": 1, "project_id": PARENT, "kind": "research-parent", "children": [
            {"project_id": CHILD, "archive_segment": "method", "primary": True},
        ],
    }))
    (parent / "project-context.json").write_text(json.dumps(payload()))
    profiles = parent / "experiments/profiles/targets"
    profiles.mkdir(parents=True)
    (profiles / "gpu.yaml").write_text(yaml.safe_dump({
        "schema_version": 1, "target_id": "gpu", "kind": "ssh", "server_alias": "lab-gpu",
        "project_root": "/srv/research/child project", "output_root": "/srv/outputs",
        "executor": {"kind": "shell"}, "environment_bindings": {},
    }))
    (ledger / "servers.yaml").write_text(yaml.safe_dump({"servers": [
        {"alias": "lab-gpu", "host": "gpu.research.invalid", "user": "researcher", "port": 2202,
         "key": "~/.ssh/id_research", "password": "SYNTHETIC-LEGACY-SECRET"},
    ]}))
    (ledger / "servers.yaml").chmod(0o600)
    return parent, ledger


def plan(parent, ledger):
    from scholar_workflow.project.remote_code import plan_remote_code
    return plan_remote_code(parent, entry_id="method-code", target_id="gpu", env_records_root=ledger)


def test_additive_reference_schema_and_human_overview_are_honest(sample):
    parent, ledger = sample
    model = ProjectContext.model_validate(payload())
    jsonschema.validate(model.model_dump(mode="json"), SCHEMA)
    before = files(parent), files(ledger)
    overview = build_project_overview(parent)
    assert overview.entries[0].state == "unverified"
    rendered = render_project_overview(overview)
    assert "主要方法代码" in rendered and "执行子项目" in rendered
    assert CHILD not in rendered and "a" * 40 not in rendered and "/srv/" not in rendered
    assert "未核验" in rendered and "vscode" not in rendered and "ssh://" not in rendered
    assert (files(parent), files(ledger)) == before


@pytest.mark.parametrize("path", ["/etc/passwd", "../secret", "src/../secret", "src//x", "./src", "src/", "src\\x", "src\nfile"])
def test_unsafe_portable_paths_are_rejected(path):
    value = payload()
    value["entries"][0]["ref"]["relative_path"] = path
    with pytest.raises(ValueError):
        ProjectContext.model_validate(value)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, SCHEMA)


@pytest.mark.parametrize("path", [".", "src/train.py", "模型/训练.py"])
def test_root_and_safe_unicode_locations_are_allowed(path):
    value = payload()
    value["entries"][0]["ref"]["relative_path"] = path
    assert ProjectContext.model_validate(value).entries[0].ref.relative_path == path
    jsonschema.validate(value, SCHEMA)


def test_unknown_child_is_not_adopted_or_hidden(sample):
    parent, _ledger = sample
    value = json.loads((parent / "project-management.json").read_text())
    value["children"] = []
    (parent / "project-management.json").write_text(json.dumps(value))
    overview = build_project_overview(parent)
    assert len(overview.entries) == 1 and overview.entries[0].state == "missing"


def test_plan_uses_existing_target_and_ledger_without_secrets_or_writes(sample):
    parent, ledger = sample
    before = files(parent), files(ledger)
    result = plan(parent, ledger)
    assert result["status"] == "declared_not_remote_verified"
    assert result["child_project_id"] == CHILD
    assert result["remote_path"] == "/srv/research/child project/src/train.py"
    assert result["connection"] == {"server_alias": "lab-gpu", "host": "gpu.research.invalid",
                                    "user": "researcher", "port": 2202}
    assert result["verification"] == {
        "child_identity": "not_checked", "remote_path": "not_checked", "commit": "not_checked",
        "access": "not_checked", "ssh_config_alias": "not_checked",
    }
    assert "SYNTHETIC-LEGACY-SECRET" not in json.dumps(result)
    assert "id_research" not in json.dumps(result) and "environment_bindings" not in result
    assert (files(parent), files(ledger)) == before


@pytest.mark.parametrize("change", ["unknown-target", "wrong-target-id", "local-target", "escape", "symlink"])
def test_target_is_not_a_backdoor_to_arbitrary_locations(sample, change):
    parent, ledger = sample
    path = parent / "experiments/profiles/targets/gpu.yaml"
    if change == "unknown-target":
        path.unlink()
    elif change == "symlink":
        outside = parent.parent / "outside-target.yaml"
        path.rename(outside)
        path.symlink_to(outside)
    else:
        value = yaml.safe_load(path.read_text())
        if change == "wrong-target-id":
            value["target_id"] = "other"
        elif change == "local-target":
            value.update(kind="local", server_alias=None)
        else:
            value["project_root"] = "/srv/../other"
        path.write_text(yaml.safe_dump(value))
    before = files(parent), files(ledger)
    with pytest.raises(ValueError):
        plan(parent, ledger)
    assert (files(parent), files(ledger)) == before


def test_missing_server_registration_is_an_explicit_failure(sample):
    parent, ledger = sample
    (ledger / "servers.yaml").write_text("servers: []\n")
    with pytest.raises(ValueError):
        plan(parent, ledger)


def test_cli_plan_never_executes_or_loads_unrelated_config(sample, monkeypatch):
    parent, ledger = sample
    def forbidden(*args, **kwargs):
        pytest.fail("Explicit remote location preview must not launch tools or load unrelated config")
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    monkeypatch.setattr(cli, "_asset_server_root", forbidden)
    before = files(parent), files(ledger)
    result = CliRunner().invoke(cli.main, ["project", "remote-code-plan", "--project-root", str(parent),
                                         "--entry-id", "method-code", "--target-id", "gpu",
                                         "--env-records-root", str(ledger), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["verification"]["access"] == "not_checked"
    assert (files(parent), files(ledger)) == before


def test_remote_reference_cannot_carry_credentials_or_arbitrary_uri(sample):
    parent, _ledger = sample
    value = payload()
    value["entries"][0]["ref"].update(password="SYNTHETIC-DO-NOT-PRINT", uri="ssh://user:secret@host/root")
    (parent / "project-context.json").write_text(json.dumps(value))
    result = CliRunner().invoke(cli.main, ["project", "validate-context", "--project-root", str(parent)])
    assert result.exit_code == 2
    assert "SYNTHETIC-DO-NOT-PRINT" not in result.output and "user:secret" not in result.output


@pytest.mark.parametrize("change", ["target", "context", "management", "ledger"])
def test_changes_during_location_planning_are_not_reported_as_stable(sample, monkeypatch, change):
    from scholar_workflow.project import remote_code
    parent, ledger = sample
    original = remote_code.read_servers
    first = True
    def changing(root):
        nonlocal first
        result = original(root)
        if first:
            first = False
            path = {
                "target": parent / "experiments/profiles/targets/gpu.yaml",
                "context": parent / "project-context.json",
                "management": parent / "project-management.json",
                "ledger": ledger / "servers.yaml",
            }[change]
            path.write_bytes(path.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(remote_code, "read_servers", changing)
    with pytest.raises(ValueError, match="changed"):
        plan(parent, ledger)


def test_execution_code_cannot_be_another_material_type_or_parent_identity():
    for change in ("kind", "identity"):
        value = payload()
        if change == "kind":
            value["entries"][0]["kind"] = "paper"
        else:
            value["entries"][0]["ref"]["child_project_id"] = PARENT
        with pytest.raises(ValueError):
            ProjectContext.model_validate(value)
