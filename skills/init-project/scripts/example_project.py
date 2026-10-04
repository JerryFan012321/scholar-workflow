#!/usr/bin/env python3
"""Prepare a portable example; never stage, commit, or execute its experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS = SKILL_ROOT / "assets" / "experiment-example"


def installed_python() -> str:
    """Use the installed console entry's Python, not an unrelated system environment."""
    cli = shutil.which("scholar-workflow")
    if cli is None:
        raise ValueError("install Scholar Workflow before applying the example")
    with Path(cli).open("rb") as stream:
        first_line = stream.readline(4096).decode("utf-8").strip()
    if not first_line.startswith("#!"):
        raise ValueError("installed CLI has no Python console entry; use its Python environment")
    candidate = Path(first_line[2:])
    if (
        not candidate.is_absolute()
        or not candidate.name.startswith("python")
        or not candidate.is_file()
    ):
        raise ValueError(
            "unsupported CLI launcher; use the Python environment of the installed CLI"
        )
    return str(candidate)


def preflight(target: Path) -> list[Path]:
    """Require a new, non-symlink destination outside every existing Git tree."""
    if ".." in target.parts:
        raise ValueError("target cannot contain parent traversal")
    for path in (target, *target.parents):
        if path.is_symlink():
            raise ValueError("target or ancestor cannot be a symlink")
        if path.exists() and not path.is_dir():
            raise ValueError("target or ancestor is not a directory")
    if target.exists():
        raise ValueError("example target already exists; choose a new directory")
    parent = next(path for path in target.parents if path.exists())
    result = subprocess.run(
        ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        raise ValueError("example target is inside an existing Git tree")
    if not ASSETS.is_dir() or ASSETS.is_symlink():
        raise ValueError("installed example assets are unavailable")
    files = []
    for path in sorted(ASSETS.rglob("*")):
        if path.is_symlink():
            raise ValueError("example assets cannot contain symlinks")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise ValueError("unsupported example asset")
    if not files:
        raise ValueError("example assets are empty")
    return files


def prepare(target: Path, *, apply: bool) -> dict:
    files = preflight(target)
    inventory = {
        p.relative_to(ASSETS).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    result = {
        "template": "four-numbers-v1",
        "state": "planned",
        "files": sorted(inventory),
        "git_commit": "not-created",
        "experiment": "not-run",
        "human_review": "pending",
    }
    if not apply:
        return result
    interpreter = installed_python()
    completed = subprocess.run(
        [interpreter, str(SKILL_ROOT / "scripts/init_project.py"), "apply", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(completed.stderr or completed.stdout)
    for source in files:
        destination = target / source.relative_to(ASSETS)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(source.read_bytes())
    identity = json.loads((target / "project-layout.json").read_text(encoding="utf-8"))
    entries = [
        (
            "code",
            "code",
            "计算代码",
            "计算固定数据的数量、总和与均值。",
            "src/example_computation.py",
        ),
        (
            "experiment",
            "experiment",
            "实验报告",
            "查看真实失败、成功和重放；执行前文件尚不存在。",
            "experiments/20261004-0000-sum-example/report.md",
        ),
        (
            "result",
            "result",
            "指标成果",
            "查看核对后的结果；执行前文件尚不存在。",
            "experiments/20261004-0000-sum-example/artifacts/metrics.json",
        ),
        (
            "replay",
            "other",
            "复现入口",
            "通过安装版公开 CLI 执行这个明确的小型示例。",
            "tools/replay.py",
        ),
    ]
    context = {
        "schema_version": 1,
        "project_id": identity["project_id"],
        "title": "可复现科研项目示例",
        "summary": "确定性工作流样例，不是论文训练复现。",
        "language": "zh",
        "entries": [
            {
                "entry_id": item_id,
                "kind": kind,
                "title": title,
                "purpose": purpose,
                "ref": {"kind": "project-file", "relative_path": relative},
            }
            for item_id, kind, title, purpose, relative in entries
        ],
    }
    for name, content in (
        ("project-context.json", context),
        (
            "reproduction-inputs.json",
            {
                "schema_version": 1,
                "template": "four-numbers-v1",
                "minimum_product_version": "0.32.3",
                "files": inventory,
            },
        ),
    ):
        with (target / name).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    result.update(
        state="prepared", project_id=identity["project_id"], initializer_python=interpreter
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        result = prepare(args.target.expanduser().absolute(), apply=args.mode == "apply")
    except (OSError, ValueError) as exc:
        print(f"example preparation stopped: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
