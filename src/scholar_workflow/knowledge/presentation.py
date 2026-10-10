"""Readable projections of zero-write knowledge previews."""

from __future__ import annotations

import html
from urllib.parse import quote

from scholar_workflow.knowledge.fields import FieldPreview


def _text(value: str) -> str:
    value = html.escape(value, quote=False)
    for character in ("\\", "`", "*", "_", "[", "]", "|", "#"):
        value = value.replace(character, "\\" + character)
    return value


def references_markdown(references: list[dict], *, language: str) -> list[str]:
    """Show selections and observed states, not machine identities or fake links."""
    if not references:
        return []
    zh = language == "zh"
    lines = ["### 引用资料" if zh else "### Referenced material", ""]
    states = ({"resolved": "已定位", "not_found": "未找到", "conflict": "归属冲突", "incomplete": "核验不完整"}
              if zh else {"resolved": "Resolved", "not_found": "Not found", "conflict": "Conflict",
                          "incomplete": "Incomplete"})
    file_states = ({"available": "存在", "missing": "缺失", "unsafe": "不安全", "not_checked": "未检查"}
                   if zh else {"available": "Available", "missing": "Missing", "unsafe": "Unsafe",
                               "not_checked": "Not checked"})
    for reference in references:
        lines += [f"- {'用途' if zh else 'Purpose'}: {_text(reference['purpose'])}"]
        result = reference.get("resolution")
        if result is None:
            lines += ["  - 归属与文件：尚未核验。" if zh else "  - Ownership and files: not checked.", ""]
            continue
        lines += [f"  - {'归属' if zh else 'Ownership'}: {states[result['status']]}"]
        for location in result["locations"]:
            lines += [
                f"  - {'所属领域' if zh else 'Owning Field'}: {_text(location['field_title'])}",
                (f"  - {'文件' if zh else 'File'}: {_text(location['relative_path'])} "
                 f"({file_states[location['file_state']]})"),
            ]
        for owner in result["owner_candidates"]:
            if owner["owner_path"] != next((row["relative_path"] for row in result["locations"]
                                            if row["source_id"] == owner["source_id"]), None):
                lines += [(f"  - {'主资料文件' if zh else 'Primary owner file'}: {_text(owner['owner_path'])} "
                           f"({file_states[owner['file_state']]})")]
        if result["issues"]:
            lines += ["  - 部分声明不可用、发生变化或目标不匹配；不要据此认定归属完整。" if zh else
                      "  - Some declarations are unavailable, changed or target-mismatched; ownership is incomplete."]
        lines += ["  - 阅读器：未核验；本次没有打开应用。" if zh else
                  "  - Reader: unverified; no application was opened.", ""]
    return lines


def paper_units_markdown(payload: dict, *, language: str) -> str:
    """Render local titles and observed file states without claiming reader success."""
    zh = language == "zh"

    def cell(value: str) -> str:
        return _text(" ".join(value.splitlines()))

    ownership_states = ({"resolved": "归属已定位", "not_found": "归属未找到",
                         "conflict": "归属冲突", "incomplete": "归属核验不完整"} if zh else
                        {"resolved": "Ownership resolved", "not_found": "Owner not found",
                         "conflict": "Ownership conflict", "incomplete": "Ownership incomplete"})
    file_states = ({"available": "存在", "missing": "缺失", "unsafe": "不安全",
                    "not_checked": "未检查"} if zh else
                   {"available": "Available", "missing": "Missing", "unsafe": "Unsafe",
                    "not_checked": "Not checked"})
    open_states = ({"file_unavailable": "文件不可打开", "ownership_unresolved": "归属未核清",
                    "reader_unavailable": "阅读器不可用", "unsupported_type": "不支持原生打开"} if zh else
                   {"file_unavailable": "File unavailable", "ownership_unresolved": "Ownership unresolved",
                    "reader_unavailable": "Reader unavailable", "unsupported_type": "Unsupported type"})

    def file_entry(row: dict) -> str:
        title_value = row["title"]
        if row["kind"] not in {"paper", "primary"} and title_value == row["object_id"]:
            roles = ({"analysis": "论文分析", "analysis_markdown": "论文分析",
                      "analysis_canvas": "解析树", "reading_note": "阅读笔记",
                      "annotations": "批注", "attachment": "附件", "analysis_sidecar": "分析附属文件"}
                     if zh else
                     {"analysis": "Paper analysis", "analysis_markdown": "Paper analysis",
                      "analysis_canvas": "Analysis Canvas", "reading_note": "Reading note",
                      "annotations": "Annotations", "attachment": "Attachment",
                      "analysis_sidecar": "Analysis sidecar"})
            title_value = roles.get(row["kind"], "附属文件" if zh else "Supporting file")
        title = cell(title_value)
        uri = row.get("uri")
        if row["open_state"] == "ready" and uri and uri.startswith("obsidian://open?"):
            title = f"[{title}](<{quote(uri, safe=':/?=&%')}>)"
        details = [file_states[row["file_state"]]]
        if row["open_state"] != "ready":
            details.append(open_states[row["open_state"]])
        return title + "（" + "；".join(details) + "）" if zh else title + " (" + "; ".join(details) + ")"

    def files_cell(unit: dict, kinds: set[str]) -> str:
        rows = [file_entry(row) for row in unit["files"] if row["kind"] in kinds]
        return "<br>".join(rows) if rows else ("未声明" if zh else "Undeclared")

    lines = [f"# {cell(payload['field_title'])} — {'论文资料' if zh else 'Paper material'}", "",
             (("导航部分可用。" if payload["status"] == "partial" else "已列出所选领域的论文资料。")
              if zh else ("Navigation is partially available." if payload["status"] == "partial" else
                          "Declared paper material for the selected Field is listed below.")), "",
             ("标题取自已有本地声明。链接仅是原生打开候选；本次未打开应用，也未验收论文分析。" if zh else
              "Titles come from existing local declarations. Links are native dispatch candidates; "
              "no application was opened and paper analyses were not assessed."), "",
             ("| 论文 | 所属领域 | 本领域用途 | 资料 | 分析 | Canvas | 笔记 | 状态 |" if zh else
              "| Paper | Owning Field | Purpose in this Field | Material | Analysis | Canvas | Notes | State |"),
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for unit in payload["paper_units"]:
        purposes = (["本领域自有资料" if zh else "Owned by this Field"]
                    if "owned" in unit["selected_by"] else [])
        purposes.extend(cell(purpose) for purpose in unit["purposes"])
        state = ownership_states[unit["ownership"]["status"]]
        unavailable = {row["open_state"] for row in unit["files"]
                       if row["open_state"] not in {"ready", "unsupported_type"}}
        if unavailable:
            state += ("；" if zh else "; ") + ("部分资料不可打开" if zh else "Some files unavailable")
        columns = [cell(unit["title"]), cell(unit["field_title"]), "<br>".join(purposes),
                   files_cell(unit, {"paper", "primary"}), files_cell(unit, {"analysis", "analysis_markdown"}),
                   files_cell(unit, {"analysis_canvas"}),
                   files_cell(unit, {"reading_note", "annotations"}), state]
        lines.append("| " + " | ".join(columns) + " |")
    if not payload["paper_units"]:
        lines += ["", "所选领域没有已声明或已定位的论文资料。" if zh else
                  "The selected Field has no declared or resolved paper material."]
    grouped_kinds = {"paper", "primary", "analysis", "analysis_markdown", "analysis_canvas",
                     "reading_note", "annotations"}
    other = [(unit, row) for unit in payload["paper_units"] for row in unit["files"]
             if row["kind"] not in grouped_kinds]
    if other:
        lines += ["", "## 其他附件" if zh else "## Other attachments", ""]
        for unit, row in other:
            lines.append(f"- {cell(unit['title'])}：{file_entry(row)}" if zh else
                         f"- {cell(unit['title'])}: {file_entry(row)}")
    reason_labels = ({"reference_target_not_paper": "目标不是论文资料",
                      "reference_ownership_not_found": "未找到目标归属",
                      "reference_ownership_conflict": "目标归属冲突",
                      "reference_ownership_incomplete": "目标归属核验不完整"} if zh else
                     {"reference_target_not_paper": "Target is not paper material",
                      "reference_ownership_not_found": "Target owner not found",
                      "reference_ownership_conflict": "Target ownership conflict",
                      "reference_ownership_incomplete": "Target ownership incomplete"})
    if payload["unresolved_references"]:
        lines += ["", "## 未定位引用" if zh else "## Unresolved references", ""]
        for reference in payload["unresolved_references"]:
            lines.append(f"- {cell(reference['purpose'])}：{reason_labels[reference['reason']]}" if zh else
                         f"- {cell(reference['purpose'])}: {reason_labels[reference['reason']]}")
    issue_labels = ({"registry_unavailable": "登记清单不可用", "source_disabled": "有来源未启用或无读取权限",
                     "source_declaration_unavailable": "有来源声明不可用",
                     "declaration_changed": "声明在查询期间变化", "source_binding_changed": "来源目录绑定变化",
                     "provider_binding_changed": "资料声明目录绑定变化", "file_changed": "文件在查询期间变化",
                     "asset_declaration_invalid": "附件声明存在无效条目或冲突，清单不完整",
                     "asset_declaration_unavailable": "附件声明不可安全读取，清单不完整",
                     "asset_declaration_changed": "附件声明在查询期间变化，请重新查询",
                     "asset_file_changed": "附件文件在查询期间变化，请重新查询",
                     "reader_unavailable": "阅读器登记不可用或不唯一", "reader_changed": "阅读器登记或绑定变化"}
                    if zh else
                    {"registry_unavailable": "Source registry unavailable", "source_disabled": "A Source is disabled or unreadable",
                     "source_declaration_unavailable": "A Source declaration is unavailable",
                     "declaration_changed": "A declaration changed during inspection",
                     "source_binding_changed": "A Source directory binding changed",
                     "provider_binding_changed": "A provider directory binding changed",
                     "file_changed": "A file changed during inspection",
                     "asset_declaration_invalid": "Asset declarations contain invalid or conflicting entries; inventory is incomplete",
                     "asset_declaration_unavailable": "Asset declarations cannot be read safely; inventory is incomplete",
                     "asset_declaration_changed": "Asset declarations changed during inspection; query again",
                     "asset_file_changed": "An asset file changed during inspection; query again",
                     "reader_unavailable": "Reader registration is unavailable or ambiguous",
                     "reader_changed": "Reader registration or binding changed"})
    if payload["issues"]:
        lines += ["", "## 诊断" if zh else "## Diagnostics", ""]
        for label in dict.fromkeys(issue_labels.get(row["code"], "声明核验不完整" if zh else
                                                   "Declaration verification incomplete")
                                   for row in payload["issues"]):
            lines.append(f"- {label}")
    return "\n".join([*lines, ""])


def preview_markdown(preview: FieldPreview, *, language: str) -> str:
    zh = language == "zh"
    lines = [
        "# 知识文件夹预览" if zh else "# Knowledge folder preview",
        "",
        (
            "只读预览：没有登记、改写或创建首页。"
            if zh
            else "Read-only preview: no registration, document rewrite or new homepage."
        ),
        "",
    ]
    if preview.registration_only:
        lines += [
            (
                "已有便携清单，但尚未在本机登记。下面列出原有领域；确认登记是另一项操作。"
                if zh
                else "An existing portable manifest is not registered on this host. Its Fields are listed below; "
                "registration is a separate operation."
            ),
            "",
        ]
    groups = [
        ("已有领域" if zh else "Existing Fields", preview.registered_fields),
        ("候选领域" if zh else "Candidate Fields", preview.fields),
    ]
    for title, fields in groups:
        lines += [f"## {title}", ""]
        if not fields:
            lines += [
                "没有可用候选或已有领域。" if zh else "No candidates or existing Fields available.",
                "",
            ]
        for field in fields:
            lines += [f"### {_text(field.title)}", ""]
            lines += [
                f"- {'相对目录' if zh else 'Relative root'}: {_text(field.relative_root)}",
                f"- {'已有入口文档' if zh else 'Existing home document'}: {_text(field.home)}",
                "",
            ]
            for group in field.navigation:
                lines += [f"#### {_text(group.label)}", ""]
                lines += [f"- {_text(item)}" for item in group.items]
                lines.append("")
            lines += references_markdown([row.model_dump(mode="json") for row in field.references],
                                         language=language)
    sections = [
        (
            "登记约束（工具原始诊断）" if zh else "Registration constraints (original tool diagnostics)",
            preview.conflicts,
        ),
        ("未纳入导航的正文" if zh else "Unmapped Markdown", preview.unmapped_markdown),
        ("忽略文件" if zh else "Ignored files", preview.ignored_files),
        (
            "外部工具管理的文档" if zh else "Externally managed documents",
            [f"{item.relative_path} ({item.owner})" for item in preview.external_managed_documents],
        ),
        (
            "旧链接建议（未改写）" if zh else "Legacy link proposals (not applied)",
            [
                f"{item.relative_path}: {item.occurrences} → {item.replacement}"
                for item in preview.legacy_link_changes
            ],
        ),
    ]
    for title, items in sections:
        lines += [f"## {title}", ""]
        lines += [f"- {_text(item)}" for item in items] if items else ["无。" if zh else "None."]
        lines.append("")
    lines += [
        "## 下一步" if zh else "## Next step",
        "",
        (
            "先审阅目录、导航和归属。预览不是确认凭证，也不证明论文内容或 Canvas 已验收；"
            "未登记的候选身份只是临时身份。正式登记/旧稿事务仍须另行审议。"
            if zh
            else "Review roots, navigation and ownership. This preview is not an approval credential or "
            "paper/Canvas acceptance. New candidate identities are provisional. Registration and "
            "existing-document transactions still require separate review."
        ),
        "",
    ]
    return "\n".join(lines)
