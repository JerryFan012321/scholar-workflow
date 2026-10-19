"""Existing-project adoption inputs; no application, Git or SSH is executed."""

import json
import os
import stat

import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.management import load_project_management

PROJECT = "11111111-1111-4111-8111-111111111111"
PARENT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def legacy(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    (root / "project-layout.json").write_text(json.dumps({
        "schema_version": 2, "project_id": PROJECT, "language": "python",
        "package": None, "source_profile": None, "addons": [],
    }))
    (root / "AGENTS.md").write_text("Human instructions: retain the existing plan.\n")
    (root / "AGENT.md").write_text("Read AGENTS.md.\n")
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")
    (root / ".gitignore").write_text("dataset/\ndocs/\nexperiments/\n.env\n")
    (root / "project-context.json").write_text(json.dumps({"project_id": PROJECT}))
    (root / "docs/plan").mkdir(parents=True)
    (root / "docs/plan/existing.md").write_text("The one existing human plan.\n")
    (root / "docs/report").mkdir()
    (root / "docs/report/result.md").write_text("Results are still remote.\n")
    (root / "configs").mkdir()
    (root / "configs/current.json").write_text('{"retain":true}\n')
    return root


def invoke(root, role="research-parent", *extra):
    return CliRunner().invoke(cli.main, [
        "project", "adopt-role", "--project-root", str(root), "--role", role,
        *extra, "--json",
    ])


def preview(root, role="research-parent", *extra):
    result = invoke(root, role, *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


@pytest.mark.parametrize("role", ["research-parent", "execution-child"])
def test_preview_is_read_only_and_keeps_the_old_identity(legacy, monkeypatch, role):
    before = snapshot(legacy)

    def forbidden(*args, **kwargs):
        pytest.fail("Adoption preview must not launch tools or load host configuration")

    monkeypatch.setattr(cli, "_load_cfg", forbidden)
    monkeypatch.setattr(cli.subprocess, "run", forbidden)
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    extra = ("--parent-project-id", PARENT) if role == "execution-child" else ()
    plan = preview(legacy, role, *extra)
    assert plan["status"] == "planned"
    assert plan["project_id"] == PROJECT and plan["role"] == role
    assert plan["changes"] == [{"path": "project-management.json", "operation": "create"}]
    assert "guidance_and_git_policy" in plan["remaining_review"]
    assert "native_git_topology" in plan["remaining_review"]
    assert snapshot(legacy) == before
    assert "Human instructions" not in json.dumps(plan)


@pytest.mark.parametrize("role", ["research-parent", "execution-child"])
def test_apply_only_adds_the_declared_role_and_preserves_every_old_file(legacy, role):
    before = snapshot(legacy)
    extra = ("--parent-project-id", PARENT, "--primary") if role == "execution-child" else ()
    plan = preview(legacy, role, *extra)
    result = invoke(legacy, role, *extra, "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "adopted"
    after = snapshot(legacy)
    assert set(after) == set(before) | {"project-management.json"}
    assert {key: after[key] for key in before} == before
    management = load_project_management(legacy)
    assert management.kind == role and management.project_id == PROJECT
    if role == "execution-child":
        assert management.parent_project_id == PARENT and management.primary
    assert stat.S_IMODE((legacy / "project-management.json").stat().st_mode) == 0o600


@pytest.mark.parametrize("name", ["AGENTS.md", "project-layout.json", "project-context.json", ".gitignore"])
def test_stale_preview_refuses_without_changing_existing_content(legacy, name):
    plan = preview(legacy)
    with (legacy / name).open("ab") as stream:
        stream.write(b"\n")
    before = snapshot(legacy)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 5, result.output
    assert snapshot(legacy) == before


def test_same_role_retains_existing_child_registrations(legacy):
    original = {"schema_version": 1, "project_id": PROJECT, "kind": "research-parent",
                "children": [{"project_id": PARENT, "archive_segment": "baseline", "primary": True}]}
    (legacy / "project-management.json").write_text(json.dumps(original))
    before = snapshot(legacy)
    plan = preview(legacy)
    assert plan["status"] == "unchanged" and plan["changes"] == []
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "unchanged"
    assert snapshot(legacy) == before


def test_existing_different_role_is_not_overwritten(legacy):
    (legacy / "project-management.json").write_text(json.dumps({
        "schema_version": 1, "project_id": PROJECT, "kind": "execution-child",
        "parent_project_id": PARENT, "primary": False,
    }))
    before = snapshot(legacy)
    result = invoke(legacy)
    assert result.exit_code == 5, result.output
    assert snapshot(legacy) == before


@pytest.mark.parametrize("args", [
    ("research-parent", "--primary"),
    ("research-parent", "--parent-project-id", PARENT),
    ("execution-child",),
    ("execution-child", "--parent-project-id", PROJECT),
    ("execution-child", "--parent-project-id", "bad"),
    ("research-parent", "--apply"),
])
def test_invalid_requests_do_not_mutate_the_legacy_root(legacy, args):
    before = snapshot(legacy)
    result = invoke(legacy, args[0], *args[1:])
    assert result.exit_code == 2, result.output
    assert snapshot(legacy) == before


def test_parent_adoption_cannot_clear_an_existing_source_profile(legacy):
    path = legacy / "project-layout.json"
    layout = json.loads(path.read_text())
    layout.update(package="example", source_profile={"id": "python-library", "version": 1})
    path.write_text(json.dumps(layout))
    before = snapshot(legacy)
    result = invoke(legacy)
    assert result.exit_code == 5, result.output
    assert snapshot(legacy) == before


@pytest.mark.parametrize("name", ["AGENTS.md", "project-management.json"])
def test_protected_symlinks_are_not_followed(legacy, tmp_path, name):
    outside = tmp_path / "outside"
    outside.write_text("DO NOT READ OR REWRITE\n")
    path = legacy / name
    if path.exists():
        path.unlink()
    path.symlink_to(outside)
    result = invoke(legacy)
    assert result.exit_code == 7, result.output
    assert path.is_symlink() and outside.read_text() == "DO NOT READ OR REWRITE\n"


def test_conflicting_publication_preserves_the_other_writers_file(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.link
    collision = b"A different writer owns this file.\n"

    def competing(source, destination, **kwargs):
        (legacy / "project-management.json").write_bytes(collision)
        return original(source, destination, **kwargs)

    monkeypatch.setattr(role_adoption.os, "link", competing)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 5, result.output
    assert (legacy / "project-management.json").read_bytes() == collision


def test_post_publication_sync_failure_is_partial_not_rollback(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.fsync

    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("Synthetic directory synchronization failure")
        return original(descriptor)

    monkeypatch.setattr(role_adoption.os, "fsync", fail_directory)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 6, result.output
    assert load_project_management(legacy).project_id == PROJECT
    assert "durability" in result.output


def test_guidance_changed_during_staging_refuses_publication(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.fsync

    def change_guidance(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            (legacy / "AGENTS.md").write_text("Concurrent human rule.\n")
        return original(descriptor)

    monkeypatch.setattr(role_adoption.os, "fsync", change_guidance)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 5, result.output
    assert not (legacy / "project-management.json").exists()
    assert (legacy / "AGENTS.md").read_text() == "Concurrent human rule.\n"


def test_pre_publication_sync_failure_leaves_all_original_files(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    before = snapshot(legacy)

    def fail_sync(descriptor):
        raise OSError("Synthetic pre-publication synchronization failure")

    monkeypatch.setattr(role_adoption.os, "fsync", fail_sync)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 7, result.output
    assert snapshot(legacy) == before


def test_post_publication_verification_error_is_partial(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption
    from scholar_workflow.project.reception import ReceptionError

    plan = preview(legacy)
    original = role_adoption._read_file

    def fail_read(descriptor, name, limit):
        if name == "project-management.json":
            raise ReceptionError("Synthetic post-publication verification failure", 5)
        return original(descriptor, name, limit)

    monkeypatch.setattr(role_adoption, "_read_file", fail_read)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 6, result.output
    assert load_project_management(legacy).project_id == PROJECT


def test_replaced_root_is_not_adopted(legacy, tmp_path, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.fsync
    saved = tmp_path / "saved-original"

    def replace_root(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode) and not saved.exists():
            legacy.rename(saved)
            legacy.mkdir()
            (legacy / "human.md").write_text("A new unrelated directory.\n")
        return original(descriptor)

    monkeypatch.setattr(role_adoption.os, "fsync", replace_root)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 7, result.output
    assert not (legacy / "project-management.json").exists()
    assert not (saved / "project-management.json").exists()
    assert snapshot(legacy) == {"human.md": b"A new unrelated directory.\n"}


def test_large_protected_entry_is_not_truncated_into_a_preview(legacy):
    (legacy / "AGENTS.md").write_bytes(b"x" * (1024 * 1024 + 1))
    before = snapshot(legacy)
    result = invoke(legacy)
    assert result.exit_code == 7, result.output
    assert snapshot(legacy) == before


def test_unknown_stage_content_is_preserved_without_publishing_it(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.fsync
    unknown = b"Unexpected local content; do not publish or delete.\n"

    def replace_stage_contents(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            for path in legacy.glob(".project-role-*.tmp"):
                path.write_bytes(unknown)
        return original(descriptor)

    monkeypatch.setattr(role_adoption.os, "fsync", replace_stage_contents)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 6, result.output
    assert not (legacy / "project-management.json").exists()
    retained = list(legacy.glob(".project-role-*.tmp"))
    assert len(retained) == 1 and retained[0].read_bytes() == unknown


def test_post_publication_guidance_change_remains_partial(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    plan = preview(legacy)
    original = role_adoption.os.link

    def change_after_link(source, destination, **kwargs):
        value = original(source, destination, **kwargs)
        (legacy / "AGENTS.md").write_text("Concurrent human change after publication.\n")
        return value

    monkeypatch.setattr(role_adoption.os, "link", change_after_link)
    result = invoke(legacy, "research-parent", "--apply", "--expected-plan-sha256", plan["plan_sha256"])
    assert result.exit_code == 6, result.output
    assert load_project_management(legacy).project_id == PROJECT
    assert (legacy / "AGENTS.md").read_text() == "Concurrent human change after publication.\n"


def test_protected_entry_permission_error_is_a_safe_refusal(legacy, monkeypatch):
    from scholar_workflow.project import role_adoption

    before = snapshot(legacy)
    original = role_adoption.os.stat

    def denied(name, *args, **kwargs):
        if name == "AGENTS.md" and kwargs.get("dir_fd") is not None:
            raise PermissionError("Synthetic protected-entry read denial")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(role_adoption.os, "stat", denied)
    result = invoke(legacy)
    assert result.exit_code == 7, result.output
    assert snapshot(legacy) == before
