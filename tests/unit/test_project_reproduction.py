"""Independent public-script checks; these are not installed-product acceptance."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills/init-project/scripts/example_project.py"
ASSETS = ROOT / "skills/init-project/assets/experiment-example"


def invoke(mode, target):
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def replay(target, *args):
    return subprocess.run(
        [sys.executable, str(target / "tools/replay.py"), *args],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def commit_example(target):
    subprocess.run(["git", "-C", str(target), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "Fixture",
        ],
        capture_output=True,
        check=True,
    )


def test_plan_is_zero_write_and_declare_outputs(tmp_path):
    target = tmp_path / "new-example"
    before = sorted(tmp_path.iterdir())
    result = invoke("plan", target)
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["experiment"] == "not-run" and plan["git_commit"] == "not-created"
    assert "tools/replay.py" in plan["files"]
    assert sorted(tmp_path.iterdir()) == before


def test_apply_prepares_but_does_not_commit_or_execute(tmp_path):
    target = tmp_path / "new-example"
    result = invoke("apply", target)
    assert result.returncode == 0, result.stderr
    layout = json.loads((target / "project-layout.json").read_text())
    context = json.loads((target / "project-context.json").read_text())
    assert context["project_id"] == layout["project_id"]
    assert {item["kind"] for item in context["entries"]} == {
        "code",
        "experiment",
        "result",
        "other",
    }
    assert not (target / "experiments/20261004-0000-sum-example").exists()
    assert not (target / "dataset/four-numbers").exists()
    assert (
        subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"], capture_output=True, check=False
        ).returncode
        != 0
    )
    assert (
        subprocess.run(
            ["git", "-C", str(target), "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        == ""
    )
    for relative, expected in json.loads((target / "reproduction-inputs.json").read_text())[
        "files"
    ].items():
        assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_existing_root_is_preserved(tmp_path, mode):
    target = tmp_path / "existing"
    target.mkdir()
    existing = target / "notes.md"
    existing.write_text("Human work\n")
    result = invoke(mode, target)
    assert result.returncode == 2
    assert existing.read_text() == "Human work\n"
    assert list(target.iterdir()) == [existing]


@pytest.mark.parametrize("ancestor", [False, True])
def test_symlink_is_rejected_without_writes(tmp_path, ancestor):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    target = link / "new" if ancestor else link
    assert invoke("apply", target).returncode == 2
    assert list(real.iterdir()) == []


def test_ancestor_git_is_rejected_without_write(tmp_path):
    parent = tmp_path / "existing-git"
    parent.mkdir()
    subprocess.run(["git", "init", str(parent)], capture_output=True, check=True)
    target = parent / "child"
    assert invoke("apply", target).returncode == 2
    assert not target.exists()


def test_traversal_is_rejected_without_write(tmp_path):
    assert invoke("apply", tmp_path / "child" / ".." / "escaped").returncode == 2
    assert not (tmp_path / "child").exists()
    assert not (tmp_path / "escaped").exists()


def test_uncommitted_source_cannot_create_formal_run(tmp_path):
    target = tmp_path / "new-example"
    assert invoke("apply", target).returncode == 0
    result = replay(target)
    assert result.returncode == 2
    assert "Git commit" in result.stderr
    assert not (target / "experiments/20261004-0000-sum-example").exists()


def test_public_replay_matches_independent_expected_and_preserves_failure(tmp_path):
    target = tmp_path / "new-example"
    assert invoke("apply", target).returncode == 0
    commit_example(target)
    result = replay(target)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["metrics"] == {"count": 4, "sum": 10, "mean": 2.5}
    assert [a["status"] for a in receipt["attempts"]] == ["failed", "succeeded", "succeeded"]
    assert [a["exit_code"] for a in receipt["attempts"]] == [2, 0, 0]
    assert receipt["replay_byte_identical"] and receipt["backup_state"] == "not-verified"
    run = target / "experiments/20261004-0000-sum-example"
    a = (run / "attempts/correct-cwd/metrics.json").read_bytes()
    assert a == (run / "attempts/replay/metrics.json").read_bytes()
    assert a == (run / "artifacts/metrics.json").read_bytes()
    assert "tools/summarize.py" in (run / "attempts/wrong-cwd/stderr.log").read_text()
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    assert replay(target).returncode == 2
    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before


def test_input_collision_is_preserved(tmp_path):
    target = tmp_path / "new-example"
    assert invoke("apply", target).returncode == 0
    dataset = target / "dataset/four-numbers/source/numbers.csv"
    dataset.parent.mkdir(parents=True)
    dataset.write_text("Human input\n")
    result = replay(target)
    assert result.returncode == 2 and "collision" in result.stderr
    assert dataset.read_text() == "Human input\n"
    assert not (target / "experiments/20261004-0000-sum-example").exists()


def test_invalid_run_id_is_rejected_before_writes(tmp_path):
    target = tmp_path / "new-example"
    assert invoke("apply", target).returncode == 0
    result = replay(target, "--run-id", "../../escaped")
    assert result.returncode == 2
    assert not (target / "dataset/four-numbers").exists()


def test_missing_cli_stops_without_writes(tmp_path):
    target = tmp_path / "new-example"
    assert invoke("apply", target).returncode == 0
    result = subprocess.run(
        [sys.executable, str(target / "tools/replay.py")],
        cwd=target,
        env={**os.environ, "PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "install Scholar Workflow" in result.stderr
    assert not (target / "dataset/four-numbers").exists()


def test_assets_are_generic_and_source_paths_are_portable():
    for path in ASSETS.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert "/Users/" not in text and "127.0.0.1:" not in text
            assert "17685951" not in text and "QR4ZU2S9" not in text


def test_unsupported_installed_launcher_fails_before_creation(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cli = bin_dir / "scholar-workflow"
    cli.write_text("#!/bin/sh\nexit 0\n")
    cli.chmod(0o755)
    target = tmp_path / "new-example"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "apply", str(target)],
        env={**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2 and "unsupported CLI launcher" in result.stderr
    assert not target.exists()


def test_system_python_wrapper_uses_installed_product_environment(tmp_path):
    target = tmp_path / "new-example"
    result = subprocess.run(
        [shutil.which("python3"), str(SCRIPT), "apply", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert Path(receipt["initializer_python"]).is_absolute()
    assert (target / "src/example_computation.py").is_file()
    assert not (target / "experiments/20261004-0000-sum-example").exists()
