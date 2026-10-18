"""Independent expected cases for the parent/child declaration boundary."""
import copy
import json
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.management import (
    load_project_management,
    validate_management_pair,
    validate_project_management,
)

PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
PARENT_DOC = {
    "schema_version": 1, "project_id": PARENT, "kind": "research-parent",
    "children": [
        {"project_id": CHILD, "archive_segment": "main-method", "primary": True},
        {"project_id": OTHER, "archive_segment": "baseline", "primary": False},
    ],
}
CHILD_DOC = {
    "schema_version": 1, "project_id": CHILD, "kind": "execution-child",
    "parent_project_id": PARENT, "primary": True,
}
SCHEMA = Path(__file__).resolve().parents[2] / "contracts/project-management.schema.json"


def write_project(root, payload):
    root.mkdir()
    (root / "project-layout.json").write_text(json.dumps({
        "schema_version": 2, "project_id": payload["project_id"], "language": "python",
        "package": None, "source_profile": None, "addons": [],
    }))
    (root / "project-management.json").write_text(json.dumps(payload))


def test_roles_and_schema_agree():
    schema = json.loads(SCHEMA.read_text())
    for payload in (PARENT_DOC, CHILD_DOC, {**PARENT_DOC, "children": []}):
        jsonschema.validate(payload, schema)
        assert validate_project_management(payload).model_dump() == payload
    validate_management_pair(
        validate_project_management(PARENT_DOC), validate_project_management(CHILD_DOC),
    )


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"schema_version": 2}, {"project_id": "not-a-uuid"},
    {"kind": "parent"}, {"host": "/private/server"}, {"primary": True},
    {"children": [{"project_id": CHILD, "archive_segment": "../escape", "primary": True}]},
    {"children": [{"project_id": CHILD, "archive_segment": "profiles", "primary": True}]},
    {"children": [{"project_id": PARENT, "archive_segment": "self", "primary": False}]},
    {"children": [PARENT_DOC["children"][0], PARENT_DOC["children"][0]]},
    {"children": [PARENT_DOC["children"][0],
                  {"project_id": OTHER, "archive_segment": "baseline", "primary": True}]},
    {"children": [PARENT_DOC["children"][0],
                  {"project_id": OTHER, "archive_segment": "main-method", "primary": False}]},
])
def test_invalid_parent_is_rejected(change):
    with pytest.raises(ValueError):
        validate_project_management({**copy.deepcopy(PARENT_DOC), **change})


@pytest.mark.parametrize("change", [
    {"parent_project_id": CHILD}, {"parent_project_id": "bad"},
    {"primary": 1}, {"children": []}, {"cwd": "/tmp"},
])
def test_invalid_child_is_rejected(change):
    with pytest.raises(ValueError):
        validate_project_management({**CHILD_DOC, **change})


@pytest.mark.parametrize("change", [
    {"parent_project_id": OTHER}, {"primary": False}, {"project_id": PARENT},
])
def test_pair_must_match_both_declarations(change):
    with pytest.raises(ValueError):
        validate_management_pair(
            validate_project_management(PARENT_DOC),
            validate_project_management({**CHILD_DOC, **change}),
        )


def test_cli_pair_check_is_read_only(tmp_path, monkeypatch):
    parent, child = tmp_path / "parent", tmp_path / "child"
    write_project(parent, PARENT_DOC)
    write_project(child, CHILD_DOC)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.json")}

    def forbidden(*args, **kwargs):
        pytest.fail("Declaration checking must not launch tools or read host configuration")

    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    result = CliRunner().invoke(cli.main, [
        "project", "validate-management", "--project-root", str(child),
        "--parent-root", str(parent),
    ])
    assert result.exit_code == 0, result.output
    assert "Parent/child declarations agree" in result.output
    assert "not verified" in result.output
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_local_check_does_not_claim_pair_verification(tmp_path):
    write_project(tmp_path / "child", CHILD_DOC)
    result = CliRunner().invoke(cli.main, [
        "project", "validate-management", "--project-root", str(tmp_path / "child"),
    ])
    assert result.exit_code == 0
    assert "Counterpart declaration not checked" in result.output


def test_missing_declaration_does_not_infer_or_create_role(tmp_path):
    write_project(tmp_path / "child", CHILD_DOC)
    (tmp_path / "child/project-management.json").unlink()
    result = CliRunner().invoke(cli.main, [
        "project", "validate-management", "--project-root", str(tmp_path / "child"),
    ])
    assert result.exit_code == 2
    assert not (tmp_path / "child/project-management.json").exists()


def test_loader_rejects_identity_mismatch_duplicate_json_and_symlink(tmp_path):
    root = tmp_path / "child"
    write_project(root, CHILD_DOC)
    declaration = root / "project-management.json"
    declaration.write_text(json.dumps({**CHILD_DOC, "project_id": OTHER}))
    with pytest.raises(ValueError, match="identity"):
        load_project_management(root)
    declaration.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="duplicate"):
        load_project_management(root)
    declaration.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(CHILD_DOC))
    declaration.symlink_to(outside)
    with pytest.raises(ValueError, match="unsafe"):
        load_project_management(root)


def test_loader_rejects_symlink_root_and_oversized_declaration(tmp_path):
    root = tmp_path / "child"
    write_project(root, CHILD_DOC)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        load_project_management(alias)
    (root / "project-management.json").write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="bounded"):
        load_project_management(root)


def test_parent_option_rejects_reversed_roles(tmp_path):
    parent, child = tmp_path / "parent", tmp_path / "child"
    write_project(parent, PARENT_DOC)
    write_project(child, CHILD_DOC)
    result = CliRunner().invoke(cli.main, [
        "project", "validate-management", "--project-root", str(parent),
        "--parent-root", str(child),
    ])
    assert result.exit_code == 2
    assert "requires one research parent" in result.output
