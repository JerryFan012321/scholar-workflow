"""Role initialization expectations prepared independently of the helper."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/init-project/scripts/init_project.py"
PARENT = "11111111-1111-4111-8111-111111111111"


def invoke(root, mode="apply", *args):
    return subprocess.run([sys.executable, str(SCRIPT), mode, str(root), *args],
                          capture_output=True, text=True, check=False)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts}


def test_parent_plan_and_apply(tmp_path):
    from scholar_workflow.project.context import load_project_context
    from scholar_workflow.project.management import load_project_management

    root = tmp_path / "parent"
    planned = invoke(root, "plan", "--role", "research-parent")
    assert planned.returncode == 0, planned.stderr
    assert not root.exists()
    result = invoke(root, "apply", "--role", "research-parent")
    assert result.returncode == 0, result.stderr
    assert (root / ".git").is_dir()
    for entry in ("docs/notes", "docs/plan", "docs/report", "assets", ".agents/skills",
                  "experiments/profiles/targets", "backups/code"):
        assert (root / entry).is_dir()
    for entry in ("src", "configs", "env", "dataset", "tools", "tests", "SCHEDULE.md"):
        assert not (root / entry).exists()
    management = json.loads((root / "project-management.json").read_text())
    layout = json.loads((root / "project-layout.json").read_text())
    assert management == {"schema_version": 1, "project_id": layout["project_id"],
                          "kind": "research-parent", "children": []}
    assert json.loads((root / "project-context.json").read_text())["entries"] == []
    assert load_project_context(root).project_id == layout["project_id"]
    assert load_project_management(root).project_id == layout["project_id"]
    text = (root / "PROJECT.md").read_text()
    assert [line for line in text.splitlines() if line.startswith("## ")] == [
        "## Current state", "## Project plan", "## Experiments and results",
        "## Code and data flow", "## Papers and materials", "## Ownership and open questions",
    ]
    assert "<!--" not in text
    ignored = (root / ".gitignore").read_text().splitlines()
    assert "docs/" not in ignored and "experiments/" not in ignored
    assert "backups/code/" in ignored
    assert ".scholar-workflow/collection-transactions/" in ignored
    before = snapshot(root)
    again = invoke(root)
    assert again.returncode == 0, again.stderr
    assert snapshot(root) == before
    assert subprocess.run(["git", "-C", str(root), "remote"], capture_output=True,
                          text=True, check=True).stdout == ""
    tracked = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "PROJECT.md", "docs/notes/note.md",
         "experiments/main-method/run/metrics.json"], capture_output=True, text=True, check=False,
    )
    assert tracked.returncode == 1 and tracked.stdout == ""
    recovery = subprocess.run(["git", "-C", str(root), "check-ignore", "backups/code/a.bundle"],
                              capture_output=True, text=True, check=False)
    assert recovery.returncode == 0
    journal = subprocess.run(
        ["git", "-C", str(root), "check-ignore", ".scholar-workflow/collection-transactions/tx-example/journal.json"],
        capture_output=True, text=True, check=False,
    )
    assert journal.returncode == 0


def test_child_profile_identity_and_no_parent_mutation(tmp_path):
    root = tmp_path / "child"
    args = ("--role", "execution-child", "--parent-project-id", PARENT, "--primary",
            "--source-profile", "world-model", "--package", "demo")
    result = invoke(root, "apply", *args)
    assert result.returncode == 0, result.stderr
    for entry in ("src/demo/method/world_model", "configs/recipes", "env", "dataset",
                  "tools", "tests", "src/utils/dataset_toolkit", "experiments/profiles/targets"):
        assert (root / entry).is_dir()
    for entry in ("PROJECT.md", "project-context.json", "docs", "SCHEDULE.md", "backups"):
        assert not (root / entry).exists()
    declaration = json.loads((root / "project-management.json").read_text())
    assert declaration["parent_project_id"] == PARENT and declaration["primary"] is True
    assert declaration["kind"] == "execution-child"
    assert "remote" in (root / "AGENTS.md").read_text().lower()
    before = snapshot(root)
    assert invoke(root).returncode == 0
    assert snapshot(root) == before


@pytest.mark.parametrize("args", [
    ("--role", "execution-child"),
    ("--role", "execution-child", "--parent-project-id", "invalid"),
    ("--role", "research-parent", "--package", "demo"),
    ("--role", "research-parent", "--parent-project-id", PARENT),
    ("--primary",),
])
def test_invalid_role_request_writes_nothing(tmp_path, args):
    root = tmp_path / "invalid"
    assert invoke(root, "apply", *args).returncode == 2
    assert not root.exists()


def test_role_drift_and_legacy_conversion_refuse(tmp_path):
    root = tmp_path / "parent"
    assert invoke(root, "apply", "--role", "research-parent").returncode == 0
    before = snapshot(root)
    assert invoke(root, "apply", "--role", "generic").returncode == 2
    assert invoke(root, "apply", "--role", "execution-child",
                  "--parent-project-id", PARENT).returncode == 2
    assert snapshot(root) == before
    legacy = tmp_path / "legacy"
    assert invoke(legacy).returncode == 0
    before = snapshot(legacy)
    assert invoke(legacy, "apply", "--role", "research-parent").returncode == 2
    assert snapshot(legacy) == before


def test_roles_reject_nonempty_and_enclosing_git(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    (root / "PROJECT.md").write_text("Human plan\n")
    assert invoke(root, "apply", "--role", "research-parent").returncode == 2
    assert snapshot(root) == {"PROJECT.md": b"Human plan\n"}
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    nested = tmp_path / "nested"
    assert invoke(nested, "apply", "--role", "research-parent").returncode == 2
    assert not nested.exists()


def test_child_parent_change_and_symlink_root_refuse(tmp_path):
    root = tmp_path / "child"
    args = ("--role", "execution-child", "--parent-project-id", PARENT)
    assert invoke(root, "apply", *args).returncode == 0
    before = snapshot(root)
    assert invoke(root, "apply", "--parent-project-id",
                  "33333333-3333-4333-8333-333333333333").returncode == 2
    assert snapshot(root) == before
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert invoke(alias).returncode == 2
    assert snapshot(root) == before


def test_parent_cannot_register_remote_run_against_management_git(tmp_path):
    from scholar_workflow.project import ExperimentError, create_run

    root = tmp_path / "parent"
    assert invoke(root, "apply", "--role", "research-parent").returncode == 0
    before = snapshot(root)
    with pytest.raises(ExperimentError, match="execution child"):
        create_run(root, run_id="20261018-1200-demo", run_script="missing.sh",
                   resolved_config="missing.json", dataset_manifest="missing.json",
                   dataset_id="demo", dataset_version="1", dataset_split="test", seed=0,
                   environment_definition="missing.txt")
    assert snapshot(root) == before
    assert not (root / ".scholar-workflow").exists()


def test_parent_preserves_human_notes_and_does_not_recreate_duplicate_plan(tmp_path):
    root = tmp_path / "parent"
    assert invoke(root, "apply", "--role", "research-parent").returncode == 0
    (root / "PROJECT.md").write_text("Human PROJECT with existing plan\n")
    (root / "docs/notes/decision.md").write_text("Human decision\n")
    before = snapshot(root)
    assert invoke(root).returncode == 0
    assert snapshot(root) == before
    (root / "PROJECT.md").unlink()
    (root / "SCHEDULE.md").write_text("Human detailed plan\n")
    before = snapshot(root)
    assert invoke(root).returncode == 2
    assert snapshot(root) == before


def test_roles_reject_symlink_ancestor(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    assert invoke(alias / "new", "apply", "--role", "research-parent").returncode == 2
    assert not (actual / "new").exists()
