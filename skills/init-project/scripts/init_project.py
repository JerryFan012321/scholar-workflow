#!/usr/bin/env python3
"""Plan or apply the v2 project layout without overwriting existing content."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = SKILL_ROOT / "references" / "source-profiles.json"
PROJECT_LAYOUT = "project-layout.json"
LEGACY_PATHS = ("dataset/raw", "dataset/metadata", "dataset_toolkits", "env/server")
PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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

# Scholar Workflow local-first state
dataset/
docs/
experiments/
"""

AGENT_POINTER = """\
# Compatibility Pointer

Canonical project instructions live in [AGENTS.md](AGENTS.md). Update AGENTS.md instead of
duplicating project rules here.
"""

CLAUDE_STUB = """\
@AGENTS.md

# Instruction source

Project instructions are maintained in AGENTS.md. Add or change project rules there.
"""


@dataclass(frozen=True)
class Finding:
    level: str
    path: str
    detail: str


@dataclass(frozen=True)
class Selection:
    package: str | None
    source_profile: str | None
    addons: tuple[str, ...]


def _load_catalog() -> dict[str, Any]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported source profile catalog schema")
    return data


def _validate_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ValueError(f"unsafe catalog path: {value}")


def _project_id_is_valid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def _validate_layout(data: object, catalog: dict[str, Any]) -> Selection:
    required = {
        "schema_version",
        "project_id",
        "language",
        "package",
        "source_profile",
        "addons",
    }
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError("project-layout.json has unknown or missing fields")
    if data["schema_version"] != 2:
        raise ValueError("project-layout.json must use schema_version 2")
    if not _project_id_is_valid(data["project_id"]):
        raise ValueError("project-layout.json project_id must be a canonical UUIDv4")
    if data["language"] != "python":
        raise ValueError("project-layout.json language must be python")
    package = data["package"]
    if package is not None and (
        not isinstance(package, str) or not PACKAGE_RE.fullmatch(package)
    ):
        raise ValueError("project-layout.json package is not a Python identifier")

    profile_data = data["source_profile"]
    profile: str | None
    if profile_data is None:
        profile = None
    elif (
        isinstance(profile_data, dict)
        and set(profile_data) == {"id", "version"}
        and profile_data.get("id") in catalog["profiles"]
        and profile_data.get("version")
        == catalog["profiles"][profile_data["id"]]["version"]
    ):
        profile = profile_data["id"]
    else:
        raise ValueError("project-layout.json has an unknown source profile or version")

    addon_ids: list[str] = []
    if not isinstance(data["addons"], list):
        raise TypeError("project-layout.json addons must be a list")
    for addon in data["addons"]:
        if (
            not isinstance(addon, dict)
            or set(addon) != {"id", "version"}
            or addon.get("id") not in catalog["addons"]
            or addon.get("version") != catalog["addons"][addon["id"]]["version"]
        ):
            raise ValueError("project-layout.json has an unknown addon or version")
        addon_ids.append(addon["id"])
    if addon_ids != sorted(set(addon_ids)):
        raise ValueError("project-layout.json addons must be unique and sorted by id")
    if (profile is not None or addon_ids) and package is None:
        raise ValueError("project-layout.json requires package with a profile or addon")
    return Selection(package=package, source_profile=profile, addons=tuple(addon_ids))


def _layout_payload(selection: Selection, project_id: str) -> dict[str, Any]:
    catalog = _load_catalog()
    return {
        "schema_version": 2,
        "project_id": project_id,
        "language": "python",
        "package": selection.package,
        "source_profile": (
            None
            if selection.source_profile is None
            else {
                "id": selection.source_profile,
                "version": catalog["profiles"][selection.source_profile]["version"],
            }
        ),
        "addons": [
            {"id": addon, "version": catalog["addons"][addon]["version"]}
            for addon in selection.addons
        ],
    }


def _requested_selection(args: argparse.Namespace, catalog: dict[str, Any]) -> Selection:
    profile = args.source_profile
    addons = tuple(sorted(set(args.addon or [])))
    if profile is not None and profile not in catalog["profiles"]:
        raise ValueError(f"unknown source profile: {profile}")
    unknown_addons = [addon for addon in addons if addon not in catalog["addons"]]
    if unknown_addons:
        raise ValueError(f"unknown addon: {unknown_addons[0]}")
    package = args.package
    if package is not None and not PACKAGE_RE.fullmatch(package):
        raise ValueError("--package must be a valid Python package identifier")
    if (profile is not None or addons) and package is None:
        raise ValueError("--package is required with --source-profile or --addon")
    return Selection(package=package, source_profile=profile, addons=addons)


def _resolved_selection(
    root: Path,
    requested: Selection,
    request_is_explicit: bool,
    catalog: dict[str, Any],
) -> tuple[Selection, dict[str, Any] | None, Finding | None]:
    manifest_path = root / PROJECT_LAYOUT
    if not manifest_path.exists():
        return requested, None, None
    try:
        existing_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing = _validate_layout(existing_data, catalog)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return requested, None, Finding("conflict", PROJECT_LAYOUT, str(exc))
    if request_is_explicit and existing != requested:
        return existing, existing_data, Finding(
            "conflict",
            PROJECT_LAYOUT,
            "requested selection differs from the portable manifest; use migrate-plan",
        )
    return existing, existing_data, None


def _layout_directories(
    selection: Selection,
    catalog: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    tracked = dict(catalog["common"]["tracked"])
    local = dict(catalog["common"]["local"])
    additions: list[dict[str, str]] = []
    if selection.source_profile is not None:
        additions.append(catalog["profiles"][selection.source_profile]["paths"])
    additions.extend(catalog["addons"][addon]["paths"] for addon in selection.addons)

    for paths in additions:
        for template, responsibility in paths.items():
            relative = template.format(package=selection.package)
            _validate_relative_path(relative)
            if relative.split("/", 1)[0] in {"dataset", "docs", "env", "experiments"}:
                raise ValueError(
                    f"source profile cannot claim outer project state: {relative}"
                )
            current = tracked.get(relative)
            if current is not None and current != responsibility:
                raise ValueError(f"conflicting responsibilities for {relative}")
            tracked[relative] = responsibility
    for path in (*tracked, *local):
        _validate_relative_path(path)
    return dict(sorted(tracked.items())), dict(sorted(local.items()))


def agents_template(
    project_name: str,
    tracked: dict[str, str],
    local: dict[str, str],
) -> str:
    rows = "\n".join(
        f"| {path}/ | {responsibility} |"
        for path, responsibility in {**tracked, **local}.items()
    )
    template = textwrap.dedent(
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
        __DIRECTORY_ROWS__

        project-layout.json carries the portable project UUID and source-layout selection.
        Host paths, servers, credentials, datasets, and experiment state do not belong there.

        ## Data and Experiment Contract

        Group materialized data under dataset/<dataset-id>/ using source/, intermediate/,
        prepared/, and metadata/. Keep producing code in src/utils/dataset_toolkit/;
        runtime Dataset/DataLoader code belongs to the project package.

        Each experiments/<run-id>/ is one Run recipe. Machine and retry observations live in
        Attempts, and execution destinations live in explicit Target profiles. Promotion verifies
        a local artifact copy; it is not a backup without an approved trusted-medium contract.

        ### Artifact Git Policy

        dataset/, docs/, and experiments/ are local-first and ignored in new projects. An
        existing project's tracked state is reported rather than changed automatically.

        ## Behavior Boundaries

        ### Always Do

        - Keep this project under Git management.
        - Preserve existing files and human experiment notes during initialization or migration.
        - Keep reusable configs machine-neutral; snapshot resolved inputs inside each Run.
        - Keep environment definitions separate from execution Targets.

        ### Ask First

        - Overwriting, renaming, deleting, moving, or untracking an existing path.
        - Changing a source profile, addon selection, or standard directory responsibility.
        - Promoting a selected remote artifact into local project storage.

        ### Never Do

        - Commit credentials, private keys, local environment files, or .DS_Store.
        - Store passwords, tokens, private keys, or arbitrary commands in Target profiles.
        - Treat local artifact promotion as proof of an independent backup.

        ### Additional Project Boundaries

        <!-- init-project: add only project-specific rules that change agent behavior -->

        ## Agent Runtime

        Project-specific skills live in .agents/skills/. This initializer does not install
        custom agents or hooks; add either only when the user explicitly requests them.
        """
    )
    return template.replace("__DIRECTORY_ROWS__", rows)


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


def inspect(
    root: Path,
    requested: Selection,
    request_is_explicit: bool,
    catalog: dict[str, Any],
) -> tuple[
    list[Finding],
    bool,
    Selection,
    dict[str, Any] | None,
    dict[str, str],
    dict[str, str],
]:
    findings: list[Finding] = []
    blocked = False
    if root.is_symlink():
        return (
            [Finding("conflict", ".", "target root is a symlink")],
            True,
            requested,
            None,
            {},
            {},
        )
    if root.exists() and not root.is_dir():
        return (
            [Finding("conflict", ".", "target root is not a directory")],
            True,
            requested,
            None,
            {},
            {},
        )

    selection, existing_layout, manifest_conflict = _resolved_selection(
        root, requested, request_is_explicit, catalog
    )
    if manifest_conflict:
        findings.append(manifest_conflict)
        blocked = True
    try:
        tracked, local = _layout_directories(selection, catalog)
    except ValueError as exc:
        findings.append(Finding("conflict", PROJECT_LAYOUT, str(exc)))
        return findings, True, selection, existing_layout, {}, {}

    for relative in (*tracked, *local):
        conflict = _unsafe_component(root, relative, final_directory=True)
        if conflict:
            findings.append(conflict)
            blocked = True
        elif (root / relative).is_dir():
            findings.append(Finding("keep", relative + "/", "existing directory"))
        else:
            kind = "tracked source" if relative in tracked else "local-first"
            findings.append(Finding("create", relative + "/", f"{kind} directory"))

    for relative in (".gitignore", "AGENTS.md", "AGENT.md", "CLAUDE.md", PROJECT_LAYOUT):
        conflict = _unsafe_component(root, relative, final_directory=False)
        if conflict:
            findings.append(conflict)
            blocked = True

    if not blocked:
        agents_path = root / "AGENTS.md"
        if agents_path.exists():
            content = _read_text(agents_path)
            if content is None or not content.strip():
                findings.append(
                    Finding("conflict", "AGENTS.md", "canonical file is empty or unreadable")
                )
                blocked = True
            else:
                findings.append(
                    Finding("keep", "AGENTS.md", "existing canonical instructions")
                )
        else:
            findings.append(
                Finding("create", "AGENTS.md", "canonical project instructions")
            )

        agent_path = root / "AGENT.md"
        if agent_path.exists() and _read_text(agent_path) != AGENT_POINTER:
            findings.append(
                Finding(
                    "conflict",
                    "AGENT.md",
                    "must be migrated before becoming a compatibility pointer",
                )
            )
            blocked = True
        else:
            findings.append(
                Finding(
                    "keep" if agent_path.exists() else "create",
                    "AGENT.md",
                    "compatibility pointer",
                )
            )

        claude_path = root / "CLAUDE.md"
        claude_content = _read_text(claude_path) if claude_path.exists() else None
        imports_agents = claude_content is not None and any(
            line.strip() == "@AGENTS.md" for line in claude_content.splitlines()
        )
        if claude_path.exists() and not imports_agents:
            findings.append(
                Finding("conflict", "CLAUDE.md", "does not import canonical AGENTS.md")
            )
            blocked = True
        else:
            findings.append(
                Finding(
                    "keep" if claude_path.exists() else "create",
                    "CLAUDE.md",
                    "canonical import",
                )
            )

        gitignore_path = root / ".gitignore"
        findings.append(
            Finding(
                "keep" if gitignore_path.exists() else "create",
                ".gitignore",
                (
                    "existing file; review local-first gaps manually"
                    if gitignore_path.exists()
                    else "baseline ignores"
                ),
            )
        )
        findings.append(
            Finding(
                "keep" if existing_layout is not None else "create",
                PROJECT_LAYOUT,
                "portable project identity and source layout",
            )
        )

    for relative in tracked:
        keep_relative = str(Path(relative) / ".gitkeep")
        conflict = _unsafe_component(root, keep_relative, final_directory=False)
        if conflict:
            findings.append(conflict)
            blocked = True
        elif (root / keep_relative).exists():
            findings.append(
                Finding("keep", keep_relative, "existing tracked marker")
            )
        else:
            findings.append(
                Finding("create", keep_relative, "track empty source directory")
            )

    for legacy in LEGACY_PATHS:
        if (root / legacy).exists():
            findings.append(
                Finding(
                    "diagnostic",
                    legacy,
                    "legacy path; classify manually, never move automatically",
                )
            )

    repository = _git_root(root)
    findings.append(
        Finding(
            "create" if repository is None else "keep",
            ".git/",
            "initialize Git repository" if repository is None else f"managed by {repository}",
        )
    )
    return findings, blocked, selection, existing_layout, tracked, local


def print_findings(root: Path, findings: list[Finding], mode: str) -> None:
    print(f"{mode}: {root}")
    for finding in findings:
        print(f"[{finding.level}] {finding.path} — {finding.detail}")
    counts = {
        level: sum(1 for finding in findings if finding.level == level)
        for level in ("create", "keep", "conflict", "diagnostic")
    }
    print("summary: " + ", ".join(f"{level}={count}" for level, count in counts.items()))


def apply(
    root: Path,
    findings: list[Finding],
    blocked: bool,
    selection: Selection,
    existing_layout: dict[str, Any] | None,
    tracked: dict[str, str],
    local: dict[str, str],
) -> int:
    if blocked:
        print_findings(root, findings, "apply")
        print("error: resolve every conflict before apply; nothing was written", file=sys.stderr)
        return 2
    if shutil.which("git") is None:
        print("error: git is required; nothing was written", file=sys.stderr)
        return 3

    root.mkdir(parents=True, exist_ok=True)
    for relative in (*tracked, *local):
        (root / relative).mkdir(parents=True, exist_ok=True)

    layout = existing_layout or _layout_payload(selection, str(uuid.uuid4()))
    files = {
        "AGENTS.md": agents_template(root.name or "Project", tracked, local),
        "AGENT.md": AGENT_POINTER,
        "CLAUDE.md": CLAUDE_STUB,
        ".gitignore": GITIGNORE,
        PROJECT_LAYOUT: json.dumps(layout, ensure_ascii=False, indent=2) + "\n",
    }
    for relative, content in files.items():
        path = root / relative
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    for relative in tracked:
        keep_path = root / relative / ".gitkeep"
        if not keep_path.exists():
            keep_path.write_text("", encoding="utf-8")
    if _git_root(root) is None:
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)

    print_findings(root, findings, "apply")
    print("result: missing paths created; existing files preserved; nothing staged or committed")
    return 0


def print_profiles(catalog: dict[str, Any]) -> None:
    print("source profiles:")
    for profile_id, profile in catalog["profiles"].items():
        print(f"  {profile_id} (v{profile['version']}): {profile['description']}")
    print("addons:")
    for addon_id, addon in catalog["addons"].items():
        print(f"  {addon_id} (v{addon['version']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply", "profiles", "migrate-plan"))
    parser.add_argument("target", nargs="?", default=".")
    parser.add_argument("--source-profile")
    parser.add_argument("--package")
    parser.add_argument("--addon", action="append", default=[])
    args = parser.parse_args()

    try:
        catalog = _load_catalog()
        if args.mode == "profiles":
            print_profiles(catalog)
            return 0
        requested = _requested_selection(args, catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    raw_root = Path(args.target).expanduser()
    root = raw_root.absolute() if raw_root.is_symlink() else raw_root.resolve(strict=False)
    explicit = bool(args.source_profile or args.package or args.addon)
    findings, blocked, selection, existing_layout, tracked, local = inspect(
        root, requested, explicit, catalog
    )
    if args.mode in {"plan", "migrate-plan"}:
        print_findings(root, findings, args.mode)
        if args.mode == "migrate-plan":
            print("result: diagnostic only; no paths were moved, removed, untracked, or written")
        elif blocked:
            print("result: conflicts require user decisions before apply")
        else:
            print("result: safe to apply; plan made no changes")
        return 0
    return apply(root, findings, blocked, selection, existing_layout, tracked, local)


if __name__ == "__main__":
    raise SystemExit(main())
