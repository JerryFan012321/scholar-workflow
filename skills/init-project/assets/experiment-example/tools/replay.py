"""Replay one small example using only installed Scholar Workflow public commands."""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(text)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="20261004-0000-sum-example")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cli = shutil.which("scholar-workflow")
    if cli is None:
        raise RuntimeError("install Scholar Workflow before replay")
    version = subprocess.run(
        [cli, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    match = re.fullmatch(r"scholar-workflow, version (\d+)\.(\d+)\.(\d+)", version)
    if match is None or tuple(map(int, match.groups())) < (0, 32, 3):
        raise RuntimeError(f"this example requires 0.32.3 or later, observed {version}")
    product_version = ".".join(match.groups())
    if not re.fullmatch(r"[0-9]{8}-[0-9]{4}-[a-z0-9][a-z0-9-]{0,47}", args.run_id):
        raise RuntimeError("invalid Run ID; nothing written")
    if (root / "experiments" / args.run_id).exists():
        raise RuntimeError("Run already exists; choose a new --run-id or a new clone; no overwrite")

    dataset = root / "dataset/four-numbers/source/numbers.csv"
    fixture = root / "assets/numbers.csv"
    if dataset.exists():
        if dataset.is_symlink() or digest(dataset) != digest(fixture):
            raise RuntimeError("dataset collision; existing content preserved")
    else:
        write_new(dataset, fixture.read_text(encoding="utf-8"))
    manifest = root / "dataset/four-numbers/metadata/manifest.json"
    payload = encode(
        {
            "dataset_id": "four-numbers",
            "version": "1",
            "split": "all",
            "files": [{"path": "source/numbers.csv", "sha256": digest(dataset)}],
        }
    )
    if manifest.exists():
        if manifest.is_symlink() or manifest.read_text(encoding="utf-8") != payload:
            raise RuntimeError("dataset manifest collision; existing content preserved")
    else:
        write_new(manifest, payload)

    receipts = []

    def command(name, *options):
        invocation = [cli, "experiment", name, "--project-root", str(root), *map(str, options)]
        result = subprocess.run(invocation, check=False, capture_output=True, text=True, cwd=root)
        receipts.append(
            {
                "argv": invocation,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return json.loads(result.stdout)

    target_spec = root / "dataset/four-numbers/metadata/target.json"
    target = {
        "schema_version": 1,
        "target_id": "local-example",
        "kind": "local",
        "server_alias": None,
        "project_root": str(root),
        "output_root": str(root / "experiments"),
        "executor": {"kind": "shell"},
        "environment_bindings": {"python": shutil.which("python3")},
    }
    target_text = encode(target)
    if target_spec.exists():
        if target_spec.is_symlink() or target_spec.read_text(encoding="utf-8") != target_text:
            raise RuntimeError("target input collision; existing content preserved")
    else:
        write_new(target_spec, target_text)
    command("target-add", "--spec", target_spec)
    run = command(
        "new-run",
        "--run-id",
        args.run_id,
        "--run-script",
        "tools/run.sh",
        "--resolved-config",
        "configs/recipes/sum.json",
        "--dataset-manifest",
        manifest.relative_to(root),
        "--dataset-id",
        "four-numbers",
        "--dataset-version",
        "1",
        "--dataset-split",
        "all",
        "--seed",
        "0",
        "--environment-definition",
        "env/python.json",
    )
    run_root = root / "experiments" / args.run_id
    observations = []
    results = []
    python_version = subprocess.run(
        [shutil.which("python3"), "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    for attempt_id, should_fail in [("wrong-cwd", True), ("correct-cwd", False), ("replay", False)]:
        command(
            "new-attempt",
            "--run-id",
            args.run_id,
            "--attempt-id",
            attempt_id,
            "--target-id",
            "local-example",
        )
        command("start-attempt", "--run-id", args.run_id, "--attempt-id", attempt_id)
        attempt = run_root / "attempts" / attempt_id
        cwd = attempt if should_fail else root
        completed = subprocess.run(
            ["/bin/sh", str(run_root / "run.sh")],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        write_new(attempt / "stdout.log", completed.stdout)
        write_new(attempt / "stderr.log", completed.stderr)
        actual = {
            "working_directory": str(cwd),
            "output_location": str(attempt),
            "log_location": str(attempt / "stderr.log"),
            "hostname": platform.node(),
            "os": platform.platform(),
            "python": python_version,
            "commit": run["source"]["commit"],
            "recipe_hash": run["recipe_hash"],
        }
        write_new(attempt / "actual.json", encode(actual))
        status = "succeeded" if completed.returncode == 0 else "failed"
        command(
            "finalize-attempt",
            "--run-id",
            args.run_id,
            "--attempt-id",
            attempt_id,
            "--status",
            status,
            "--exit-code",
            completed.returncode,
            "--actual-json",
            attempt / "actual.json",
        )
        if should_fail:
            if completed.returncode == 0 or "tools/summarize.py" not in completed.stderr:
                raise RuntimeError("wrong-cwd did not fail for the expected observed reason")
        else:
            if completed.returncode != 0:
                raise RuntimeError("correct-cwd computation failed; recorded as failed")
            result = json.loads(completed.stdout)
            if result != json.loads((root / "tests/expected.json").read_text(encoding="utf-8")):
                raise RuntimeError("actual metrics do not match independent expected.json")
            write_new(attempt / "metrics.json", completed.stdout)
            results.append(completed.stdout)
        observations.append(
            {"attempt_id": attempt_id, "status": status, "exit_code": completed.returncode}
        )
    if results[0] != results[1]:
        raise RuntimeError("successful executions are not byte-identical")
    artifact = command(
        "promote",
        "--run-id",
        args.run_id,
        "--attempt-id",
        "correct-cwd",
        "--source",
        run_root / "attempts/correct-cwd/metrics.json",
        "--destination",
        "metrics.json",
        "--role",
        "metrics",
        "--retention",
        "local-required",
    )
    if artifact["sha256"] != digest(run_root / "attempts/replay/metrics.json"):
        raise RuntimeError("promotion and replay checksums differ")
    if artifact["backup"]["state"] != "not-verified":
        raise RuntimeError("promotion must not claim verified backup")
    validation = command("validate")
    command("index")
    receipt = {
        "product_version": product_version,
        "project_id": json.loads((root / "project-layout.json").read_text())["project_id"],
        "run_id": args.run_id,
        "source_commit": run["source"]["commit"],
        "recipe_hash": run["recipe_hash"],
        "attempts": observations,
        "metrics": json.loads(results[0]),
        "metrics_sha256": artifact["sha256"],
        "replay_byte_identical": True,
        "backup_state": "not-verified",
        "validation": validation,
        "human_review": "pending",
    }
    write_new(run_root / "acceptance.json", encode(receipt))
    write_new(run_root / "cli-receipts.json", encode(receipts))
    report = (
        "# 四数求和实验\n\n结论：两次正确执行均得到总和 **10**、均值 **2.5**、数量 **4**；结果字节一致。\n\n"
        "这是工作流验证示例，不是 V-JEPA 2 训练复现，也不证明论文结论。\n\n"
        "## 目的、输入与方法\n\n目的：验证可追溯的执行与重放。数据为固定四个整数 1、2、3、4，全量使用，不分训练/测试集。\n"
        "方法：计算数量、总和及均值；配置仅启用这三项，无随机步骤。记录 seed=0 但算术不使用随机数。\n"
        "独立比较为先行固定的 expected.json 和第二次重放；没有训练、模型参数、消融或图像成果。\n"
        "[计算源码](../../src/example_computation.py) · [固定输入](../../assets/numbers.csv) · [独立预期](../../tests/expected.json)\n\n"
        "## 执行记录\n\n| 尝试 | 结果 | 原因 |\n|---|---|---|\n"
        "| 错误目录 | 失败 | 从尝试目录启动，相对代码路径不存在；真实错误已保留 |\n"
        "| 正确目录 | 成功 | 从项目根执行冻结配方 |\n| 重放 | 成功 | 同一配方再次执行，输出与上次完全一致 |\n\n"
        "## 阅读与核对\n\n[保留成果](artifacts/metrics.json) · [实际错误日志](attempts/wrong-cwd/stderr.log) · "
        "[正确执行日志](attempts/correct-cwd/stdout.log) · [重放日志](attempts/replay/stdout.log)\n\n"
        "机器输入、环境、执行位置、时间和校验记录另存，不塞入正文。成果已复制并核对，**没有验证独立备份**。\n\n"
        "## 复现\n\n在一个新克隆中运行 `python3 tools/replay.py`；原目录重复运行须选新 `--run-id`，不会覆盖旧实验。\n\n"
        "人工评鉴待确认：这份报告是否易读、代码/论文/实验入口是否方便调用。\n"
    )
    report_path = run_root / "report.md"
    if report_path.read_text(encoding="utf-8") != f"# Run {args.run_id}\n\n":
        raise RuntimeError("report was edited; preserve it and stop")
    report_path.write_text(report, encoding="utf-8")
    print(encode(receipt))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"replay stopped: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
