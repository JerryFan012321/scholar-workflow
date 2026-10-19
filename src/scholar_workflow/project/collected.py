"""Read-only, rebuildable projection of registered child execution archives."""
from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from urllib.parse import quote

from .collection import (
    _MAX_BYTES,
    COLLECTION_RESERVED,
    CollectionPlanError,
    _relative,
    _sha,
    validate_run_evidence,
)
from .layout import _unique_json_object, is_project_id, open_project_root, read_project_bytes
from .management import PROJECT_MANAGEMENT, load_project_management
from .models import RUN_ID
from .reception import ReceptionError, _directory, _read_file, require_no_pending_update

_HASH = re.compile(r"[0-9a-f]{64}")
_RECEIPT_KEYS = {"schema_version", "parent_project_id", "child_project_id", "run_id",
                 "source_commit", "recipe_hash", "evidence_sha256", "files", "directories",
                 "execution_verification"}


class CollectedArchiveError(ValueError):
    """A collected archive cannot be safely indexed or interpreted."""

    def __init__(self, message, *, path=None):
        super().__init__(message)
        self.relative_path = path


def _validate_receipt(receipt, parent_id, child_id, run_id):
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_KEYS:
        raise CollectedArchiveError("Invalid collection receipt fields")
    if type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1:
        raise CollectedArchiveError("Invalid collection receipt version")
    if not is_project_id(receipt["parent_project_id"]) or not is_project_id(receipt["child_project_id"]):
        raise CollectedArchiveError("Invalid collection identity")
    if (receipt["parent_project_id"], receipt["child_project_id"], receipt["run_id"]) != (parent_id, child_id, run_id):
        raise CollectedArchiveError("Collection identity differs from its registered location")
    if receipt["execution_verification"] != "records_only":
        raise CollectedArchiveError("Receipt cannot certify actual execution")
    for key in ("recipe_hash", "evidence_sha256"):
        if not isinstance(receipt[key], str) or not _HASH.fullmatch(receipt[key]):
            raise CollectedArchiveError("Invalid collection checksum")
    if not isinstance(receipt["source_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", receipt["source_commit"]):
        raise CollectedArchiveError("Invalid child source commit")
    if not isinstance(receipt["directories"], list) or not isinstance(receipt["files"], list):
        raise CollectedArchiveError("Invalid collection inventory")
    directories = [_relative(value) for value in receipt["directories"]]
    if directories != sorted(set(directories)):
        raise CollectedArchiveError("Collection directories must be unique and sorted")
    for directory in directories:
        pieces = directory.split("/")
        if any("/".join(pieces[:index]) not in directories for index in range(1, len(pieces))):
            raise CollectedArchiveError("A collection directory parent is undeclared")
    sources, destinations = [], []
    total = 0
    for row in receipt["files"]:
        if not isinstance(row, dict) or set(row) != {"source_path", "destination_path", "sha256", "size", "mode"}:
            raise CollectedArchiveError("Invalid collection file inventory")
        source, destination = _relative(row["source_path"]), _relative(row["destination_path"])
        expected = {"report.md": "execution-report.md", "notes.md": "execution-notes.md"}.get(source, source)
        if destination != expected or destination in {"report.md", "notes.md"} or destination.split("/", 1)[0] in COLLECTION_RESERVED or destination in directories:
            raise CollectedArchiveError("Invalid execution/local-analysis ownership mapping")
        if not isinstance(row["sha256"], str) or not _HASH.fullmatch(row["sha256"]):
            raise CollectedArchiveError("Invalid evidence checksum")
        if type(row["size"]) is not int or row["size"] < 0 or type(row["mode"]) is not int or not 0 <= row["mode"] <= 0o777:
            raise CollectedArchiveError("Invalid evidence size or permissions")
        total += row["size"]
        if total > _MAX_BYTES:
            raise CollectedArchiveError("Collection exceeds the supported inspection size")
        for value in (source, destination):
            pieces = value.split("/")
            if any("/".join(pieces[:index]) not in directories for index in range(1, len(pieces))):
                raise CollectedArchiveError("Required collection parent directory is not declared")
        sources.append(source)
        destinations.append(destination)
    if sources != sorted(set(sources)) or len(destinations) != len(set(destinations)):
        raise CollectedArchiveError("Collection file mappings must be unique and sorted")
    expected_hash = _sha(json.dumps({"files": receipt["files"], "directories": directories},
                                    sort_keys=True, separators=(",", ":")).encode())
    if expected_hash != receipt["evidence_sha256"]:
        raise CollectedArchiveError("Collection inventory checksum differs")


def read_collected_evidence(namespace_fd, parent_id, child_id, run_id):
    """Read checked original source-keyed evidence with byte and location boundaries."""
    with _directory(namespace_fd, run_id) as run_fd:
        require_no_pending_update(run_fd)
        raw_receipt, _ = _read_file(run_fd, ".collection.json", 1024 * 1024)
        receipt = json.loads(raw_receipt, object_pairs_hook=_unique_json_object)
        _validate_receipt(receipt, parent_id, child_id, run_id)
        files = {}
        for directory in receipt["directories"]:
            with _directory(run_fd, directory):
                pass
        for row in receipt["files"]:
            try:
                data, mode = _read_file(run_fd, row["destination_path"], row["size"])
            except (OSError, ValueError):
                raise CollectedArchiveError("Execution file is unavailable or unsafe", path=row["destination_path"]) from None
            if len(data) != row["size"] or _sha(data) != row["sha256"] or mode != row["mode"]:
                raise CollectedArchiveError("Local execution evidence checksum, size or mode differs", path=row["destination_path"])
            files[row["source_path"]] = data
        run, attempts, artifacts = validate_run_evidence(files, set(receipt["directories"]), run_id)
        if run.source.commit != receipt["source_commit"] or run.recipe_hash != receipt["recipe_hash"]:
            raise CollectedArchiveError("Receipt differs from its original child recipe")
        # Observe owned bytes again; do not call an in-progress update a valid mixed snapshot.
        for row in receipt["files"]:
            data, mode = _read_file(run_fd, row["destination_path"], row["size"])
            if data != files[row["source_path"]] or mode != row["mode"]:
                raise CollectedArchiveError("Collected evidence changed during inspection")
        if _read_file(run_fd, ".collection.json", 1024 * 1024)[0] != raw_receipt:
            raise CollectedArchiveError("Collection receipt changed during inspection")
        current, opened = os.stat(run_id, dir_fd=namespace_fd, follow_symlinks=False), os.fstat(run_fd)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise CollectedArchiveError("Run location changed during inspection")
        require_no_pending_update(run_fd)
        return raw_receipt, receipt, files, run, attempts, artifacts


def _read_run(namespace_fd, parent_id, child_id, segment, run_id):
    _, receipt, _, run, attempts, artifacts = read_collected_evidence(namespace_fd, parent_id, child_id, run_id)
    base = f"experiments/{segment}/{run_id}"
    mapping = {row["source_path"]: f"{base}/{row['destination_path']}" for row in receipt["files"]}
    prefix = f"experiments/{run_id}/"
    def snapshot_path(value):
        return mapping[value.path.removeprefix(prefix)]
    metrics = [{"source_attempt_id": item.source_attempt_id,
                "state": "local_unreviewed" if item.relative_path else "remote_only",
                "path": mapping[item.relative_path] if item.relative_path else None}
               for item in artifacts.artifacts if item.role == "metrics"]
    return {
        "run_id": run_id, "child_project_id": child_id, "state": "verified_archive",
        "source_commit": run.source.commit, "recipe_hash": run.recipe_hash,
        "dataset": {key: getattr(run.dataset, key) for key in ("dataset_id", "version", "split")},
        "seed": run.seed, "config_path": snapshot_path(run.config),
        "environment_path": snapshot_path(run.environment), "record_path": mapping["run.yaml"],
        "execution_report_path": mapping["report.md"], "execution_notes_path": mapping["notes.md"],
        "attempts": [{**row, "record_path": mapping[f"attempts/{row['attempt_id']}/attempt.yaml"]}
                     for row in attempts],
        "metrics": metrics, "execution_verification": "records_only", "issues": [],
    }


def collected_overview(parent_root: str | Path, *, child_project_id: str | None = None,
                       required_run_ids: tuple[str, ...] = ()):
    """Index registered namespaces only; never discover children or write a derived index."""
    if required_run_ids:
        if child_project_id is None:
            raise CollectedArchiveError("Required Runs need an explicit registered child selector")
        if any(not isinstance(value, str) or not re.fullmatch(RUN_ID, value)
               for value in required_run_ids):
            raise CollectedArchiveError("Invalid required Run ID")
        if len(set(required_run_ids)) != len(required_run_ids):
            raise CollectedArchiveError("Required Run IDs must be unique")
    baseline = [read_project_bytes(parent_root, name) for name in (PROJECT_MANAGEMENT, "project-layout.json")]
    parent = load_project_management(parent_root)
    if parent.kind != "research-parent":
        raise CollectedArchiveError("Collected overview requires a research parent")
    children = [row for row in parent.children if child_project_id is None or row.project_id == child_project_id]
    if child_project_id is not None and not children:
        raise CollectedArchiveError("Child selector is not registered in this parent")
    output = []
    with open_project_root(parent_root) as root_fd:
        for child in children:
            row = {"child_project_id": child.project_id, "archive_segment": child.archive_segment,
                   "state": "not_received", "runs": [], "issues": [], "unindexed_entries": []}
            try:
                with _directory(root_fd, f"experiments/{child.archive_segment}") as namespace:
                    names = sorted(os.listdir(namespace))
                    for name in names:
                        if re.fullmatch(RUN_ID, name):
                            try:
                                run = _read_run(namespace, parent.project_id, child.project_id,
                                                child.archive_segment, name)
                            except (OSError, ValueError, RecursionError) as exc:
                                detail = str(exc) if isinstance(exc, (CollectedArchiveError, CollectionPlanError, ReceptionError)) else "Archive record is unavailable, malformed or unsafe"
                                run = {"run_id": name, "child_project_id": child.project_id,
                                       "state": "pending_update" if isinstance(exc, ReceptionError) and exc.exit_code == 6 else "invalid", "issues": [detail],
                                       "problem_path": getattr(exc, "relative_path", None)}
                            row["runs"].append(run)
                        else:
                            row["unindexed_entries"].append(name)
                            row["issues"].append("Staging or unrecognized entry is not a completed Run")
                    if names != sorted(os.listdir(namespace)):
                        raise CollectedArchiveError("Archive namespace changed during inspection")
                    with _directory(root_fd, f"experiments/{child.archive_segment}") as current_fd:
                        current, opened = os.fstat(current_fd), os.fstat(namespace)
                        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                            raise CollectedArchiveError("Archive namespace location changed")
                    row["state"] = "available" if row["runs"] else "empty"
            except FileNotFoundError:
                pass
            except (OSError, ValueError):
                row["state"] = "unavailable"
                for run in row["runs"]:
                    run["state"] = "invalid"
                row["issues"].append("Registered archive namespace is unsafe, changed or unavailable")
            output.append(row)
        with open_project_root(parent_root) as current_fd:
            current, opened = os.fstat(current_fd), os.fstat(root_fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise CollectedArchiveError("Project root location changed during inspection")
    if [read_project_bytes(parent_root, name) for name in (PROJECT_MANAGEMENT, "project-layout.json")] != baseline:
        raise CollectedArchiveError("Parent declaration changed during inspection")
    found = {run["run_id"] for row in output for run in row["runs"]}
    missing = [run_id for run_id in required_run_ids if run_id not in found]
    partial = bool(missing) or any(row["issues"] or row["state"] == "unavailable" or
                  any(run["state"] != "verified_archive" for run in row["runs"]) for row in output)
    result = {"schema_version": 1, "parent_project_id": parent.project_id,
              "status": "partial" if partial else "complete", "children": output,
              "scope": {"registered_children_only": True, "child_project_id": child_project_id},
              "execution_verification": "records_only"}
    if required_run_ids:
        result["required_runs"] = {"requested": list(required_run_ids), "missing": missing}
    return result


def _text(value):
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", html.escape(str(value)).replace("\n", " ").replace("\r", " "))


def _link(label, path):
    return f"[{label}]({quote(path, safe='/')})"


def render_collected_overview(result, *, language="en"):
    if language not in {"en", "zh"}:
        raise CollectedArchiveError("Unsupported presentation language")
    zh = language == "zh"
    labels = (["实验／执行", "记录时间", "目的", "条件／配置快照", "记录结果／结果文件", "档案检查"] if zh else
              ["Experiment / Attempt", "Recorded time", "Purpose", "Conditions / captured config",
               "Recorded outcome / result files", "Archive check"])
    lines = ["# 已收集实验" if zh else "# Collected experiments", "",
             "只读导航索引，不是科学比较；状态来自记录，执行未独立验证。" if zh else
             "Read-only navigation index, not a scientific comparison; execution status comes from records.", "",
             "| " + " | ".join(labels) + " |", "|" + "---|" * len(labels)]
    if result["status"] == "partial":
        lines[3:3] = ["部分档案未通过检查，问题行保留。" if zh else
                      "Some archives did not pass inspection; affected rows are retained.", ""]
    missing = result.get("required_runs", {}).get("missing", [])
    if missing:
        lines[3:3] = [("要求的实验档案尚未接收：" if zh else "Required Run archives not received: ")
                      + ", ".join(_text(run_id) for run_id in missing), ""]
    states = {"planned": "待执行", "running": "运行中", "succeeded": "记录为成功",
              "failed": "失败", "interrupted": "中断"}
    for child in result["children"]:
        segment = _text(child["archive_segment"])
        if not child["runs"]:
            state = ("尚未接收" if child["state"] in {"not_received", "empty"} else "不可读取") if zh else child["state"].replace("_", " ")
            lines.append(f"| {segment} | — | — | — | {state} | — |")
        for run in child["runs"]:
            title = f"{segment} / {_text(run['run_id'])}"
            if run["state"] != "verified_archive":
                problem = ("更新／恢复未收尾" if zh else "Update/recovery pending") if run["state"] == "pending_update" else ("证据缺失或冲突" if zh else "Missing or conflicted evidence")
                if run.get("problem_path"):
                    problem += ": " + _text(run["problem_path"])
                lines.append(f"| {title} | — | — | — | {problem} | {'未通过' if zh else 'Invalid'} |")
                continue
            title = f"{segment} / {_link(_text(run['run_id']), run['record_path'])}"
            data = run["dataset"]
            seed_label = "随机种子" if zh else "seed"
            condition = f"{_text(data['dataset_id'])} / {_text(data['version'])} / {_text(data['split'])}; {seed_label}={run['seed']}; "
            condition += _link("配置" if zh else "Config", run["config_path"])
            condition += "; " + _link("环境" if zh else "Environment", run["environment_path"])
            purpose = _link("查看执行报告；未提取" if zh else "See execution report; not extracted", run["execution_report_path"])
            attempts = run["attempts"] or [{"attempt_id": None, "started_at": None, "status": None}]
            for attempt in attempts:
                entry = _link(_text(attempt["attempt_id"]) if attempt["attempt_id"] else ("配方" if zh else "Recipe"),
                              attempt["record_path"] if attempt["attempt_id"] else run["record_path"])
                metrics = [item for item in run["metrics"] if item["source_attempt_id"] == attempt["attempt_id"]]
                outcome = (states[attempt["status"]] if zh else attempt["status"]) if attempt["status"] else ("暂无执行记录" if zh else "No Attempt recorded")
                if attempt.get("exit_code") is not None:
                    outcome += f" ({'退出码' if zh else 'exit'} {attempt['exit_code']})"
                for item in metrics:
                    outcome += "; " + (_link("指标（未解读）" if zh else "Metrics (unreviewed)", item["path"]) if item["path"] else
                                       ("指标仅在远端" if zh else "Metrics remote only"))
                if not metrics:
                    outcome += "; " + ("未登记指标" if zh else "No metric registered")
                time = ("开始：" if zh else "Start: ") + _text(attempt["started_at"]) if attempt["started_at"] else ("开始时间未记录" if zh else "Start not recorded")
                if attempt["started_at"] and not re.search(r"(?:Z|[+-][0-9]{2}:[0-9]{2})$", attempt["started_at"]):
                    time += "（时区未记录）" if zh else " (timezone not recorded)"
                if attempt.get("finished_at"):
                    time += ("；结束：" if zh else "; End: ") + _text(attempt["finished_at"])
                lines.append(f"| {title} / {entry} | {time} | {purpose} | {condition} | {outcome} | {'完整性通过；仅记录' if zh else 'Integrity checked; records only'} |")
        if child["unindexed_entries"]:
            lines.extend(["", f"{segment}: " + ("存在未完成暂存或未识别条目，未作为完成实验入表。" if zh else
                                                "Staging/unrecognized entries remain; not counted as completed Runs."), ""])
        if child["state"] == "unavailable":
            lines.extend(["", f"{segment}: " + ("归档目录不可用、不安全或在读取时发生变化。" if zh else
                                                "Archive namespace is unavailable, unsafe or changed during inspection."), ""])
    return "\n".join(lines) + "\n"
