"""Readable projections of zero-write knowledge previews."""

from __future__ import annotations

import html

from scholar_workflow.knowledge.fields import FieldPreview


def _text(value: str) -> str:
    value = html.escape(value, quote=False)
    for character in ("\\", "`", "*", "_", "[", "]", "|", "#"):
        value = value.replace(character, "\\" + character)
    return value


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
