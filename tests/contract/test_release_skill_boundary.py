"""Exercise release packaging in an isolated synthetic Git repository only."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FILES = {
    ".agents/plugins/marketplace.json": '{"plugins": []}\n',
    ".claude-plugin/plugin.json": '{"name": "fixture"}\n',
    ".codex-plugin/plugin.json": '{"name": "fixture", "skills": "./skills/"}\n',
    ".mcp.json": (
        '{"mcpServers":{"fixture-source":{"type":"http",'
        '"url":"https://example.org/mcp"}}}\n'
    ),
    "agents/intake.md": "Runtime intake fixture.\n",
    "bin/scholar-workflow": "#!/bin/sh\nexit 0\n",
    "contracts/fixture.json": '{}\n',
    "hooks/hooks.json": '{}\n',
    "references/project-skills.md": "Runtime project skill contract fixture.\n",
    "skills/runtime-fixture/SKILL.md": (
        "---\nname: runtime-fixture\ndescription: Isolated runtime fixture.\n---\n"
    ),
    "src/scholar_workflow/__init__.py": "# Runtime source fixture.\n",
    "scripts/guard-sqlite.sh": "#!/bin/sh\nexit 0\n",
    ".gitignore": "*.pyc\n",
    "CHANGELOG.md": "# Fixture changelog\n",
    "README.md": "# Fixture runtime\n",
    "README.zh-CN.md": "# Fixture runtime\n",
    "pyproject.toml": '[project]\nname = "fixture"\nversion = "0.0.1"\n',
}
DEVELOPMENT_FILES = {
    "dev-guide/skills/project-backlog/SKILL.md": "Developer backlog fixture.\n",
    "planning/BACKLOG.md": "Developer queue; never a research project plan.\n",
    "tests/expected.txt": "Independent packaging expectation.\n",
    "evals/routing.json": '{}\n',
    "AGENT.md": "Developer instructions.\n",
    "AGENTS.md": "Developer host entry.\n",
    "CLAUDE.md": "Developer host entry.\n",
}


def _run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(root.parent),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_NAME": "Packaging fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Packaging fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    })
    return subprocess.run(
        args, cwd=root, env=env, capture_output=True, text=True, check=check,
        timeout=30,
    )


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "packaging-fixture"
    root.mkdir()
    for relative, text in {**RUNTIME_FILES, **DEVELOPMENT_FILES}.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    shutil.copyfile(ROOT / "scripts/make-release.sh", root / "scripts/make-release.sh")
    _run(root, "git", "init", "-b", "codex/hotfix-packaging-fixture")
    _run(root, "git", "add", ".")
    _run(root, "git", "commit", "-m", "fixture: seed independent packaging inputs")
    return root


def _release_files(root: Path) -> set[str]:
    return set(_run(root, "git", "ls-tree", "-r", "--name-only", "release").stdout.splitlines())


def test_release_keeps_runtime_skills_and_excludes_developer_skills(tmp_path):
    root = _repository(tmp_path)
    source_head = _run(root, "git", "rev-parse", "HEAD").stdout

    result = _run(root, "bash", "scripts/make-release.sh")

    assert "release: committed runtime snapshot" in result.stdout
    assert _run(root, "git", "branch", "--show-current").stdout.strip() == (
        "codex/hotfix-packaging-fixture"
    )
    assert _run(root, "git", "rev-parse", "HEAD").stdout == source_head
    assert not _run(root, "git", "status", "--porcelain", "--untracked-files=all").stdout
    assert _release_files(root) == set(RUNTIME_FILES)
    assert (root / "dev-guide/skills/project-backlog/SKILL.md").read_text() == (
        DEVELOPMENT_FILES["dev-guide/skills/project-backlog/SKILL.md"]
    )
    for relative, expected in RUNTIME_FILES.items():
        assert _run(root, "git", "show", f"release:{relative}").stdout == expected

    release_head = _run(root, "git", "rev-parse", "release").stdout
    replay = _run(root, "bash", "scripts/make-release.sh")
    assert "release: no changes" in replay.stdout
    assert _run(root, "git", "rev-parse", "release").stdout == release_head


def test_release_refuses_a_developer_skill_copied_back_into_runtime(tmp_path):
    root = _repository(tmp_path)
    bad_skill = root / "skills/project-backlog/SKILL.md"
    bad_skill.parent.mkdir()
    bad_skill.write_text("Developer-only accidental runtime copy.\n", encoding="utf-8")
    _run(root, "git", "add", "skills/project-backlog")
    _run(root, "git", "commit", "-m", "fixture: accidental developer skill copy")
    source_head = _run(root, "git", "rev-parse", "HEAD").stdout

    result = _run(root, "bash", "scripts/make-release.sh", check=False)

    assert result.returncode != 0
    assert "development-only path in runtime snapshot: skills/project-backlog" in result.stderr
    assert _run(root, "git", "rev-parse", "HEAD").stdout == source_head
    assert _run(root, "git", "branch", "--show-current").stdout.strip() == (
        "codex/hotfix-packaging-fixture"
    )
    assert _run(root, "git", "show-ref", "--verify", "refs/heads/release", check=False).returncode != 0
    assert not _run(root, "git", "status", "--porcelain", "--untracked-files=all").stdout
