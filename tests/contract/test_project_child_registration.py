"""Prepared registration expectations; no servers or real project mutations."""
import fcntl
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from click.testing import CliRunner

from scholar_workflow import cli
from scholar_workflow.project.management import load_project_management, validate_management_pair
from scholar_workflow.project.registration import plan_child_registration, register_child

PARENT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


def write_root(root, declaration):
    root.mkdir()
    (root / "project-management.json").write_text(json.dumps(declaration))
    (root / "project-layout.json").write_text(json.dumps({
        "schema_version": 2, "project_id": declaration["project_id"], "language": "python",
        "package": None, "source_profile": None, "addons": [],
    }))
    (root / "notes.md").write_text("Human note; preserve bytes.\n")


@pytest.fixture
def roots(tmp_path):
    parent, child = tmp_path / "parent", tmp_path / "child"
    write_root(parent, {"schema_version": 1, "project_id": PARENT,
                        "kind": "research-parent", "children": []})
    write_root(child, {"schema_version": 1, "project_id": CHILD, "kind": "execution-child",
                       "parent_project_id": PARENT, "primary": True})
    return parent, child


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def apply_plan(parent, child, plan):
    return register_child(parent, child, archive_segment=plan["archive_segment"],
                          expected_parent_sha256=plan["parent_sha256"],
                          expected_child_sha256=plan["child_sha256"])


def test_preview_apply_and_repeat_preserve_everything_else(roots):
    parent, child = roots
    before_parent, before_child = snapshot(parent), snapshot(child)
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    assert plan["status"] == "planned"
    assert plan["parent_sha256"] == hashlib.sha256(before_parent["project-management.json"]).hexdigest()
    assert plan["child_sha256"] == hashlib.sha256(before_child["project-management.json"]).hexdigest()
    assert snapshot(parent) == before_parent and snapshot(child) == before_child
    result = apply_plan(parent, child, plan)
    assert result["status"] == "registered"
    assert set(snapshot(parent)) == set(before_parent)
    assert snapshot(child) == before_child
    for name in before_parent.keys() - {"project-management.json"}:
        assert (parent / name).read_bytes() == before_parent[name]
    validate_management_pair(load_project_management(parent), load_project_management(child))
    assert load_project_management(parent).children[0].archive_segment == "main-method"
    after = snapshot(parent)
    replay = plan_child_registration(parent, child, archive_segment="main-method")
    assert apply_plan(parent, child, replay)["status"] == "unchanged"
    assert snapshot(parent) == after


@pytest.mark.parametrize("changed", ["parent", "child"])
def test_any_changed_bytes_refuse_before_write(roots, changed):
    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    path = (parent if changed == "parent" else child) / "project-management.json"
    path.write_bytes(path.read_bytes() + b"\n")
    before_parent, before_child = snapshot(parent), snapshot(child)
    with pytest.raises(ValueError, match="changed|stale"):
        apply_plan(parent, child, plan)
    assert snapshot(parent) == before_parent and snapshot(child) == before_child


@pytest.mark.parametrize("segment", ["../bad", "profiles", "A", ""])
def test_unsafe_segment_refuses(roots, segment):
    with pytest.raises(ValueError):
        plan_child_registration(*roots, archive_segment=segment)


def test_conflicts_do_not_rename_or_replace_existing_child(roots, tmp_path):
    parent, child = roots
    apply_plan(parent, child, plan_child_registration(parent, child, archive_segment="main-method"))
    before = snapshot(parent)
    with pytest.raises(ValueError):
        plan_child_registration(parent, child, archive_segment="renamed")
    other = tmp_path / "other"
    write_root(other, {"schema_version": 1, "project_id": OTHER, "kind": "execution-child",
                       "parent_project_id": PARENT, "primary": True})
    for segment in ("main-method", "another-primary"):
        with pytest.raises(ValueError):
            plan_child_registration(parent, other, archive_segment=segment)
    assert snapshot(parent) == before


def test_concurrent_same_baseline_has_one_winner(roots, tmp_path):
    parent, child = roots
    other = tmp_path / "other"
    write_root(other, {"schema_version": 1, "project_id": OTHER, "kind": "execution-child",
                       "parent_project_id": PARENT, "primary": False})
    plans = [(child, plan_child_registration(parent, child, archive_segment="main-method")),
             (other, plan_child_registration(parent, other, archive_segment="baseline"))]

    def attempt(pair):
        try:
            return apply_plan(parent, *pair)["status"]
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(attempt, plans)) == ["conflict", "registered"]
    assert len(load_project_management(parent).children) == 1
    assert set(snapshot(parent)) == {"project-layout.json", "project-management.json", "notes.md"}


def test_failed_replace_keeps_original_and_cleans_temporary(roots, monkeypatch):
    from scholar_workflow.project import registration

    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    before = snapshot(parent)

    def failed(*args, **kwargs):
        raise OSError("Synthetic write failure")

    monkeypatch.setattr(registration.os, "replace", failed)
    with pytest.raises(ValueError):
        apply_plan(parent, child, plan)
    assert snapshot(parent) == before


def test_cli_defaults_to_preview_and_requires_both_baselines(roots):
    parent, child = roots
    args = ["project", "register-child", "--project-root", str(parent),
            "--child-root", str(child), "--archive-segment", "main-method", "--json"]
    before = snapshot(parent)
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert plan["status"] == "planned" and snapshot(parent) == before
    assert CliRunner().invoke(cli.main, [*args, "--apply"]).exit_code == 2
    result = CliRunner().invoke(cli.main, [*args, "--apply", "--expected-parent-sha256",
                                         plan["parent_sha256"], "--expected-child-sha256",
                                         plan["child_sha256"]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "registered"
    stale = CliRunner().invoke(cli.main, [*args, "--apply", "--expected-parent-sha256",
                                         plan["parent_sha256"], "--expected-child-sha256",
                                         plan["child_sha256"]])
    assert stale.exit_code == 5


@pytest.mark.parametrize("changed", ["parent", "child"])
def test_change_during_staging_is_rejected_and_not_overwritten(roots, monkeypatch, changed):
    from scholar_workflow.project import registration

    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    original = registration.os.fsync
    path = (parent if changed == "parent" else child) / "project-management.json"
    expected = path.read_bytes() + b"\n"

    def intervene(descriptor):
        original(descriptor)
        path.write_bytes(expected)

    monkeypatch.setattr(registration.os, "fsync", intervene)
    with pytest.raises(ValueError, match="changed"):
        apply_plan(parent, child, plan)
    assert path.read_bytes() == expected
    assert len(snapshot(parent)) == 3 and len(snapshot(child)) == 3


def test_declaration_symlink_is_never_followed(roots, tmp_path):
    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    path = parent / "project-management.json"
    outside = tmp_path / "outside.json"
    original = path.read_bytes()
    outside.write_bytes(original)
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        apply_plan(parent, child, plan)
    assert outside.read_bytes() == original and path.is_symlink()


def test_post_replace_durability_failure_is_partial_not_false_failure(roots, monkeypatch):
    from scholar_workflow.project import registration

    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    original = registration.os.fsync
    calls = 0

    def fail_directory_fsync(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic directory fsync failure")
        original(descriptor)

    monkeypatch.setattr(registration.os, "fsync", fail_directory_fsync)
    with pytest.raises(registration.ProjectRegistrationError) as caught:
        apply_plan(parent, child, plan)
    assert caught.value.exit_code == 6
    assert len(load_project_management(parent).children) == 1


def test_append_preserves_existing_child_and_rejects_wrong_parent(roots):
    parent, child = roots
    existing = {"project_id": OTHER, "archive_segment": "baseline", "primary": False}
    path = parent / "project-management.json"
    declaration = json.loads(path.read_text())
    declaration["children"] = [existing]
    path.write_text(json.dumps(declaration))
    apply_plan(parent, child, plan_child_registration(parent, child, archive_segment="main-method"))
    assert json.loads(path.read_text())["children"][0] == existing
    child_path = child / "project-management.json"
    declaration = json.loads(child_path.read_text())
    declaration["parent_project_id"] = OTHER
    child_path.write_text(json.dumps(declaration))
    before = snapshot(parent)
    with pytest.raises(ValueError, match="different parent"):
        plan_child_registration(parent, child, archive_segment="main-method")
    assert snapshot(parent) == before


def test_busy_writer_refuses_without_waiting_or_writing(roots):
    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    before = snapshot(parent)
    with (parent / "project-management.json").open("rb") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        with pytest.raises(ValueError, match="busy"):
            apply_plan(parent, child, plan)
    assert snapshot(parent) == before


def test_replaced_parent_inode_refuses_even_with_identical_bytes(roots, monkeypatch):
    from scholar_workflow.project import registration

    parent, child = roots
    plan = plan_child_registration(parent, child, archive_segment="main-method")
    before = snapshot(parent)
    original = registration.os.fsync

    def replace_declaration(descriptor):
        original(descriptor)
        replacement = parent / ".external-edit"
        replacement.write_bytes(before["project-management.json"])
        replacement.replace(parent / "project-management.json")

    monkeypatch.setattr(registration.os, "fsync", replace_declaration)
    with pytest.raises(ValueError, match="replaced"):
        apply_plan(parent, child, plan)
    assert snapshot(parent) == before
