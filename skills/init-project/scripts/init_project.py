#!/usr/bin/env python3
"""Plan or apply the standard project skeleton without overwriting existing content."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path


DIRECTORIES = (
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
)

GITIGNORE = """\
.DS_Store
.env
.env.*
!.env.example
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
"""

AGENT_POINTER = """\
# Compatibility Pointer

Canonical project instructions live in [AGENTS.md](AGENTS.md). Update `AGENTS.md` instead of
duplicating project rules here.
"""

CLAUDE_STUB = """\
@AGENTS.md

# Instruction source

Project instructions are maintained in `AGENTS.md`. Add or change project rules there.
"""


def agents_template(project_name: str) -> str:
    return textwrap.dedent(
        f"""\
        # {project_name} Project Instructions

        ## Project Context

        ### Overview

        <!-- init-project: describe the project goal and core approach -->

        ### Development Commands

        <!-- init-project: list the verified setup, test, lint, and run commands -->

        ## Directory Responsibilities

        | Path | Responsibility |
        |---|---|
        | `assets/` | Images, videos, and other assets used by README or reports |
        | `configs/` | Pipeline parameter files, normally JSON |
        | `dataset/metadata/` | Dataset index, provenance, checksums, and split metadata |
        | `dataset/raw/` | Downloaded or materialized data, kept separate from metadata |
        | `dataset_toolkits/` | Dataset download and preprocessing programs |
        | `docs/notes/` | Human experiment notes; agents preserve them |
        | `docs/plan/` | Project strategy, schedule, and plans |
        | `docs/report/` | Material prepared for external reporting |
        | `env/` | Environment configuration and reproducible setup scripts |
        | `env/server/` | Per-server setup notes and known issues; never credentials |
        | `experiments/` | One self-contained reproducibility bundle per experiment |
        | `src/` | Cohesive implementation modules |
        | `src/pipeline/` | End-to-end pipeline integration, including optional post-processing |
        | `.agents/skills/` | Project-scoped, host-neutral skills |

        ## Data and Experiment Contract

        Keep dataset metadata and actual data separate. Changes to download or preprocessing
        programs must leave the metadata index consistent with their outputs.

        Each `experiments/<id>/` is the source of truth for one run. Account for its report,
        environment/server, data and splits, method and parameters, referenced config, exact
        command, run script, outputs, metrics, figures, logs, warnings, and affected pipeline
        files. Human experiment notes are preserved.

        ### Artifact Git Policy

        <!-- init-project: decide which raw data, outputs, logs, and figures are tracked -->

        ## Behavior Boundaries

        ### Always Do

        - Keep this project under Git management.
        - Preserve existing files and human experiment notes during initialization or migration.
        - Keep `dataset/metadata/` and `dataset_toolkits/` consistent with materialized data.
        - Keep pipeline parameters in `configs/` where the project uses JSON-driven configuration.

        ### Ask First

        - Overwriting, renaming, or deleting an existing file or directory.
        - Changing the role or canonical name of a standard directory.
        - Adding project-specific ignore rules for datasets, experiment outputs, logs, or figures.

        ### Never Do

        - Commit credentials, private keys, local environment files, or `.DS_Store`.
        - Delete or rewrite human experiment notes as generated output.
        - Create a parallel `docs/plans`, `docs/reports`, or `scripts/data` hierarchy for the
          same responsibilities.

        ### Additional Project Boundaries

        <!-- init-project: add only project-specific rules that change agent behavior -->

        ## Agent Runtime

        Project-specific skills live in `.agents/skills/`. This initializer does not install
        custom agents or hooks; add either only when the user explicitly requests them.
        """
    )


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    detail: str


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _nearest_existing(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _git_root(path: Path) -> Path | None:
    probe = _nearest_existing(path)
    result = subprocess.run(
        ["git", "-C", str(probe), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def _unsafe_component(root: Path, relative: str, *, final_directory: bool) -> Finding | None:
    parts = Path(relative).parts
    current = root
    for index, part in enumerate(parts):
        current = current / part
        is_final = index == len(parts) - 1
        if current.is_symlink():
            return Finding("conflict", relative, f"symlink component: {current}")
        if not current.exists():
            continue
        if (not is_final or final_directory) and not current.is_dir():
            return Finding("conflict", relative, f"non-directory component: {current}")
        if is_final and not final_directory and current.is_dir():
            return Finding("conflict", relative, "directory exists where a file is required")
    return None


def inspect(root: Path) -> tuple[list[Finding], bool]:
    findings: list[Finding] = []
    blocked = False

    if root.is_symlink():
        return [Finding("conflict", ".", "target root is a symlink")], True
    if root.exists() and not root.is_dir():
        return [Finding("conflict", ".", "target root is not a directory")], True

    for relative in DIRECTORIES:
        conflict = _unsafe_component(root, relative, final_directory=True)
        if conflict:
            findings.append(conflict)
            blocked = True
        elif (root / relative).is_dir():
            findings.append(Finding("keep", relative + "/", "existing directory"))
        else:
            findings.append(Finding("create", relative + "/", "standard directory"))

    expected_files = {
        ".gitignore": GITIGNORE,
        "AGENTS.md": agents_template(root.name or "Project"),
        "AGENT.md": AGENT_POINTER,
        "CLAUDE.md": CLAUDE_STUB,
    }
    for relative in expected_files:
        conflict = _unsafe_component(root, relative, final_directory=False)
        if conflict:
            findings.append(conflict)
            blocked = True

    agents_path = root / "AGENTS.md"
    agent_path = root / "AGENT.md"
    claude_path = root / "CLAUDE.md"
    gitignore_path = root / ".gitignore"

    if not blocked:
        if agents_path.exists():
            content = _read_text(agents_path)
            if content is None or not content.strip():
                findings.append(
                    Finding("conflict", "AGENTS.md", "canonical file is empty or unreadable")
                )
                blocked = True
            else:
                findings.append(Finding("keep", "AGENTS.md", "existing canonical instructions"))
        else:
            findings.append(Finding("create", "AGENTS.md", "canonical project instructions"))

        if agent_path.exists():
            content = _read_text(agent_path)
            if content == AGENT_POINTER:
                findings.append(Finding("keep", "AGENT.md", "existing compatibility pointer"))
            else:
                findings.append(
                    Finding(
                        "conflict",
                        "AGENT.md",
                        "must be migrated to AGENTS.md before becoming a pointer",
                    )
                )
                blocked = True
        else:
            findings.append(Finding("create", "AGENT.md", "compatibility pointer"))

        if claude_path.exists():
            content = _read_text(claude_path)
            imports_agents = content is not None and any(
                line.strip() == "@AGENTS.md" for line in content.splitlines()
            )
            if imports_agents:
                findings.append(Finding("keep", "CLAUDE.md", "existing canonical import"))
            else:
                findings.append(
                    Finding("conflict", "CLAUDE.md", "does not import canonical AGENTS.md")
                )
                blocked = True
        else:
            findings.append(Finding("create", "CLAUDE.md", "Claude Code compatibility entry"))

        if gitignore_path.exists():
            findings.append(
                Finding("keep", ".gitignore", "existing file; review baseline gaps manually")
            )
        else:
            findings.append(Finding("create", ".gitignore", "minimal universal ignores"))

    for relative in DIRECTORIES:
        keep_path = root / relative / ".gitkeep"
        conflict = _unsafe_component(root, str(Path(relative) / ".gitkeep"), final_directory=False)
        if conflict:
            findings.append(conflict)
            blocked = True
        elif keep_path.exists():
            findings.append(Finding("keep", str(Path(relative) / ".gitkeep"), "existing marker"))
        else:
            findings.append(
                Finding(
                    "create",
                    str(Path(relative) / ".gitkeep"),
                    "track empty directory",
                )
            )

    repository = _git_root(root)
    if repository is None:
        findings.append(Finding("create", ".git/", "initialize Git repository"))
    else:
        findings.append(Finding("keep", ".git/", f"managed by {repository}"))

    return findings, blocked


def print_findings(root: Path, findings: list[Finding], mode: str) -> None:
    print(f"{mode}: {root}")
    for finding in findings:
        print(f"[{finding.level}] {finding.path} — {finding.detail}")
    counts = {
        level: sum(1 for finding in findings if finding.level == level)
        for level in ("create", "keep", "conflict")
    }
    print(
        "summary: "
        + ", ".join(f"{level}={count}" for level, count in counts.items())
    )


def apply(root: Path, findings: list[Finding], blocked: bool) -> int:
    if blocked:
        print_findings(root, findings, "apply")
        print("error: resolve every conflict before apply; nothing was written", file=sys.stderr)
        return 2
    if shutil.which("git") is None:
        print("error: git is required; nothing was written", file=sys.stderr)
        return 3

    root.mkdir(parents=True, exist_ok=True)

    for relative in DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)

    files = {
        "AGENTS.md": agents_template(root.name or "Project"),
        "AGENT.md": AGENT_POINTER,
        "CLAUDE.md": CLAUDE_STUB,
        ".gitignore": GITIGNORE,
    }
    for relative, content in files.items():
        path = root / relative
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    for relative in DIRECTORIES:
        keep_path = root / relative / ".gitkeep"
        if not keep_path.exists():
            keep_path.write_text("", encoding="utf-8")

    if _git_root(root) is None:
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)

    print_findings(root, findings, "apply")
    print("result: missing paths created; existing files preserved; nothing staged or committed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("target", nargs="?", default=".")
    args = parser.parse_args()

    raw_root = Path(args.target).expanduser()
    if raw_root.is_symlink():
        root = raw_root.absolute()
        findings = [Finding("conflict", ".", "target root is a symlink")]
        blocked = True
    else:
        root = raw_root.resolve(strict=False)
        findings, blocked = inspect(root)

    if args.mode == "plan":
        print_findings(root, findings, "plan")
        if blocked:
            print("result: conflicts require user decisions before apply")
        else:
            print("result: safe to apply; plan made no changes")
        return 0
    return apply(root, findings, blocked)


if __name__ == "__main__":
    raise SystemExit(main())
