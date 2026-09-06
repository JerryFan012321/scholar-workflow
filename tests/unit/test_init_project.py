import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "init-project" / "scripts" / "init_project.py"

EXPECTED_DIRECTORIES = {
    ".agents/skills",
    "assets",
    "configs",
    "dataset/metadata",
    "dataset/raw",
    "dataset_toolkits",
    "docs/notes",
    "docs/plan",
    "docs/report",
    "env/server",
    "experiments",
    "src/pipeline",
}


def run_init(mode: str, target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), mode, str(target)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_plan_is_read_only_for_missing_target(tmp_path):
    target = tmp_path / "new-project"

    result = run_init("plan", target)

    assert result.returncode == 0
    assert "safe to apply" in result.stdout
    assert not target.exists()


def test_apply_creates_host_neutral_git_managed_skeleton(tmp_path):
    target = tmp_path / "demo-project"

    result = run_init("apply", target)

    assert result.returncode == 0, result.stderr
    for relative in EXPECTED_DIRECTORIES:
        directory = target / relative
        assert directory.is_dir()
        assert (directory / ".gitkeep").is_file()

    assert (target / ".git").is_dir()
    assert "@AGENTS.md" in (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Canonical project instructions" in (target / "AGENT.md").read_text(encoding="utf-8")
    assert "dataset/metadata/" in (target / "AGENTS.md").read_text(encoding="utf-8")
    assert not (target / ".claude").exists()
    assert not (target / ".codex").exists()
    assert not (target / ".DS_Store").exists()

    staged = subprocess.run(
        ["git", "-C", str(target), "diff", "--cached", "--name-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert staged.stdout == ""


def test_apply_is_idempotent_and_preserves_existing_files(tmp_path):
    target = tmp_path / "existing-project"
    target.mkdir()
    agents = target / "AGENTS.md"
    gitignore = target / ".gitignore"
    agents.write_text("# Existing project rules\n", encoding="utf-8")
    gitignore.write_text("private-data/\n", encoding="utf-8")

    first = run_init("apply", target)
    snapshot = {
        path.relative_to(target): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    second = run_init("apply", target)
    second_snapshot = {
        path.relative_to(target): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert agents.read_text(encoding="utf-8") == "# Existing project rules\n"
    assert gitignore.read_text(encoding="utf-8") == "private-data/\n"
    assert snapshot == second_snapshot


def test_apply_refuses_incompatible_instruction_topology(tmp_path):
    target = tmp_path / "legacy-project"
    target.mkdir()
    legacy = target / "AGENT.md"
    legacy.write_text("# Legacy canonical rules\n", encoding="utf-8")

    result = run_init("apply", target)

    assert result.returncode == 2
    assert "nothing was written" in result.stderr
    assert legacy.read_text(encoding="utf-8") == "# Legacy canonical rules\n"
    assert not (target / "AGENTS.md").exists()
    assert not (target / "assets").exists()
    assert not (target / ".git").exists()


def test_apply_refuses_symlinked_skeleton_path(tmp_path):
    target = tmp_path / "symlink-project"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    (target / "assets").symlink_to(outside, target_is_directory=True)

    result = run_init("apply", target)

    assert result.returncode == 2
    assert not (outside / ".gitkeep").exists()
    assert not (target / "AGENTS.md").exists()


def test_apply_refuses_symlinked_target_root(tmp_path):
    real_project = tmp_path / "real-project"
    real_project.mkdir()
    project_link = tmp_path / "project-link"
    project_link.symlink_to(real_project, target_is_directory=True)

    result = run_init("apply", project_link)

    assert result.returncode == 2
    assert "target root is a symlink" in result.stdout
    assert not (real_project / "AGENTS.md").exists()
