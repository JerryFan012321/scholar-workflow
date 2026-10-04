"""Read-only checks of an explicitly selected, existing analysis package."""

from __future__ import annotations

import html
import json
import os
import stat
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import AnalysisBaseline, ConformanceFinding
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import create_baseline

MAX_FILE_BYTES = 4 * 1024 * 1024


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("package JSON contains a duplicate key")
        result[key] = value
    return result


def _no_constant(value: str) -> None:
    raise ValueError("package JSON contains a non-finite constant")


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def check_package(
    root: Path, *, markdown: str, canvas: str, sidecar: str, require_ir: int | None = None,
) -> dict[str, Any]:
    """Check three named files; never discover, repair, register or publish content."""
    names = (markdown, canvas, sidecar)
    if len(set(names)) != 3:
        raise ValueError("package requires three distinct files")
    for name, suffix in zip(names, (".md", ".canvas", ".json"), strict=True):
        if (
            not name or PurePosixPath(name).name != name or name in {".", ".."}
            or "\\" in name or not name.endswith(suffix)
            or any(ord(char) < 32 for char in name)
        ):
            raise ValueError("package filenames must be direct relative files of the expected type")
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("package root must be an absolute non-symlink directory")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        root_identity = _identity(os.fstat(descriptor))[:2]
        contents: dict[str, bytes] = {}
        identities: dict[str, tuple[int, ...]] = {}
        for name in names:
            fd = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor,
            )
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE_BYTES:
                    raise ValueError("package inputs must be bounded nonempty regular files")
                with os.fdopen(fd, "rb", closefd=False) as stream:
                    payload = stream.read(MAX_FILE_BYTES + 1)
                after = os.fstat(fd)
                if _identity(before) != _identity(after) or len(payload) != after.st_size:
                    raise ValueError("package input changed while reading")
                contents[name], identities[name] = payload, _identity(after)
            finally:
                os.close(fd)
        # Bind the complete read set, not merely each file independently.
        for name in names:
            named = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(named.st_mode) or _identity(named) != identities[name]:
                raise ValueError("package input changed during inspection")
        current_root = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(current_root.st_mode) or _identity(current_root)[:2] != root_identity:
            raise ValueError("package directory changed during inspection")
    finally:
        os.close(descriptor)
    canvas_data = json.loads(
        contents[canvas].decode("utf-8"), object_pairs_hook=_json_pairs, parse_constant=_no_constant,
    )
    baseline_data = json.loads(
        contents[sidecar].decode("utf-8"), object_pairs_hook=_json_pairs, parse_constant=_no_constant,
    )
    if not isinstance(canvas_data, dict):
        raise TypeError("package Canvas root must be an object")
    baseline = AnalysisBaseline.model_validate(baseline_data)
    bundle = AnalysisBundle(markdown=contents[markdown].decode("utf-8"), canvas=canvas_data)
    document = baseline.document
    report = validate_bundle(document, bundle, note_stem=baseline.note_stem)
    findings = list(report.findings)
    if require_ir is not None and document.schema_version != require_ir:
        findings.append(ConformanceFinding(
            code="required-ir-version-mismatch", path="sidecar/document/schema_version",
            message="The actual IR version differs from the explicitly required version.",
            repairable=False,
        ))
    if markdown != baseline.note_stem + ".md":
        findings.append(ConformanceFinding(
            code="markdown-backlink-filename-mismatch", path="markdown/filename",
            message="The displayed Markdown filename differs from the sidecar backlink stem.",
            repairable=False,
        ))
    if report.ok:
        recomputed = create_baseline(document, bundle, note_stem=baseline.note_stem)
        if recomputed != baseline:
            findings.append(ConformanceFinding(
                code="package-baseline-mismatch", path="sidecar",
                message="The sidecar does not match the actual conformant artifact pair.",
                repairable=False,
            ))
    return {
        "schema_version": 1,
        "status": "conformant" if not findings else "nonconformant",
        "read_only": True,
        "paper_title": document.paper_title,
        "ir_version": document.schema_version,
        "framework": document.profile.framework,
        "scope": document.profile.kind.value,
        "language": document.language,
        "roles": [role.value for role in document.profile.roles],
        "content_records": sum(not claim.container for claim in document.claims)
        + sum(len(claim.points) for claim in document.claims),
        "canvas_nodes": len(canvas_data.get("nodes", [])),
        "canvas_edges": len(canvas_data.get("edges", [])),
        "files": {name: "sha256:" + sha256(contents[name]).hexdigest() for name in names},
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "not_checked": ["source_fidelity", "live_reader", "human_visual_review", "canonical_registration"],
    }


def _text(value: str) -> str:
    value = html.escape(value, quote=False).replace("\n", " ").replace("\r", " ")
    for character in ("\\", "`", "*", "_", "[", "]", "|", "#"):
        value = value.replace(character, "\\" + character)
    return value


def package_check_markdown(report: dict[str, Any], *, language: str) -> str:
    zh = language == "zh"
    role_labels = {
        "abstract": "摘要", "introduction": "引言", "method": "方法",
        "experiments": "实验", "limitation": "局限", "task": "任务", "input": "输入",
        "workflow": "流程", "output": "输出", "boundary": "边界",
    } if zh else {
        "abstract": "Abstract", "introduction": "Introduction", "method": "Method",
        "experiments": "Experiments", "limitation": "Limitation", "task": "Task", "input": "Input",
        "workflow": "Workflow", "output": "Output", "boundary": "Boundary",
    }
    ok = report["status"] == "conformant"
    lines = [
        "# 论文资料包检查" if zh else "# Paper package check", "",
        ("结果：自动格式检查通过。" if ok else "结果：自动格式检查不通过。") if zh else
        ("Result: automated format checks passed." if ok else "Result: automated format checks failed."),
        "",
        "只读检查：没有改写、重新生成或登记。" if zh else
        "Read-only inspection: no rewrite, regeneration or registration.", "",
        f"## {_text(report['paper_title'])}", "",
        f"- {'格式版本' if zh else 'Format version'}: {report['ir_version']}",
        f"- {'范围' if zh else 'Scope'}: " + (
            ("全文" if report["scope"] == "whole" else "局部") if zh else report["scope"]
        ),
        f"- {'已声明分支' if zh else 'Declared branches'}: " + " → ".join(
            role_labels.get(role, role) for role in report["roles"]
        ),
        f"- {'独立内容记录' if zh else 'Independent content records'}: {report['content_records']}",
        (f"- {'可编辑节点 / 连线' if zh else 'Editable nodes / edges'}: "
         f"{report['canvas_nodes']} / {report['canvas_edges']}"), "",
        "## 文件" if zh else "## Files", "",
        *[f"- {_text(name)}" for name in report["files"]], "",
        "## 问题（工具原始诊断）" if zh else "## Findings (original tool diagnostics)", "",
    ]
    lines += [f"- {_text(row['code'])}: {_text(row['message'])}" for row in report["findings"]] or [
        "无。" if zh else "None."
    ]
    lines += ["", "## 未由本次检查证明" if zh else "## Not established by this check", "",
        ("原文是否支持论点、阅读器当前是否可用、人工审美/编辑评鉴、正式登记均未检查。"
         "通过只绑定本次读取的三份文件；修改后须重新检查。" if zh else
         "Source support, live reader availability, human visual/editing assessment and canonical "
         "registration were not checked. Passing binds only these inspected bytes; recheck after edits."),
        "",
    ]
    return "\n".join(lines)
