"""Version-4 projection of the reference-image paper analysis tree."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from html import escape
from typing import Any
from urllib.parse import quote

from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisReader,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    VaultMarkdownSpan,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    _edge_id,
    canvas_node_id,
    point_anchor,
)

SECTION_LABELS = {
    AnalysisRole.ABSTRACT: {"en": "Abstract", "zh": "摘要"},
    AnalysisRole.INTRODUCTION: {"en": "Introduction", "zh": "引言"},
    AnalysisRole.METHOD: {"en": "Method", "zh": "方法"},
    AnalysisRole.LIMITATION: {"en": "Limitation", "zh": "局限"},
}
GROUPS: dict[AnalysisRole, tuple[tuple[str, str, str], ...]] = {
    AnalysisRole.ABSTRACT: (
        ("abstract/task", "Task", "任务"),
        ("abstract/previous_methods", "Technical challenge for previous methods", "既有方法的技术挑战"),
        ("abstract/insight", "Key insight / motivation", "关键洞见与动机"),
        ("abstract/contributions", "Technical contributions", "技术贡献"),
        ("abstract/experiment", "Experiment", "实验"),
    ),
    AnalysisRole.INTRODUCTION: (
        ("introduction/task_application", "Task and application", "任务与应用"),
        ("introduction/previous_methods", "Technical challenge for previous methods", "既有方法的技术挑战"),
        ("introduction/our_pipeline", "Our pipeline", "本文方案"),
        ("introduction/our_pipeline/insight", "Key innovation / insight", "关键创新与洞见"),
        ("introduction/our_pipeline/contributions", "Technical contributions", "技术贡献"),
    ),
    AnalysisRole.METHOD: (
        ("method/overview", "Overview", "概览"),
        ("method/modules", "Pipeline modules", "流程模块"),
    ),
    AnalysisRole.LIMITATION: (
        ("limitation/explanation", "Reasoned limitations", "局限及原因"),
    ),
}
POINT_LABELS = {
    "motivation": ("Motivation", "动机"),
    "advantage": ("Advantage / insight", "优势与洞见"),
    "summary": ("What it does", "做法概述"),
    "previous-method": ("Previous method", "既有方法"),
    "limitation": ("Limitation", "局限"),
    "technical-reason": ("Technical reason", "技术原因"),
    "purpose": ("Problem addressed", "所解决的问题"),
    "how": ("How it is done", "具体做法"),
    "method": ("Method", "方法"),
    "why-it-works": ("Why it works", "有效原因"),
    "technical-advantage": ("Technical advantage", "技术优势"),
}
POINT_ORDER = {
    path: tuple(slots)
    for path, slots in {
        "abstract/insight": ("motivation", "advantage"),
        "abstract/contributions": ("summary", "advantage"),
        "introduction/previous_methods": ("previous-method", "limitation", "technical-reason"),
        "introduction/our_pipeline/contributions": ("purpose", "how", "advantage"),
        "method/modules": ("motivation", "method", "why-it-works", "technical-advantage"),
    }.items()
}
ROLE_COLORS = {
    AnalysisRole.ABSTRACT: "#e3978d",
    AnalysisRole.INTRODUCTION: "#d9ad51",
    AnalysisRole.METHOD: "#8ba866",
    AnalysisRole.LIMITATION: "#76a99d",
}
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_WIKILINK = re.compile(r"\[\[[^\]|]+\|([^\]]+)\]\]")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def reference_evidence_text(evidence: Evidence, language: str) -> str:
    if language == "zh":
        labels = {
            EvidenceKind.AUTHOR_STATED: f"作者明确陈述 · {evidence.anchor}",
            EvidenceKind.ANALYSIS_INFERENCE: f"分析推断 · {evidence.detail}",
            EvidenceKind.NOT_REPORTED: "论文未报告",
            EvidenceKind.UNVERIFIABLE: f"当前正文通道无法核实 · {evidence.detail}",
            EvidenceKind.NOT_APPLICABLE: f"不适用 · {evidence.detail}",
        }
    else:
        labels = {
            EvidenceKind.AUTHOR_STATED: f"Author-stated · {evidence.anchor}",
            EvidenceKind.ANALYSIS_INFERENCE: f"Analysis inference · {evidence.detail}",
            EvidenceKind.NOT_REPORTED: "Not reported in the paper",
            EvidenceKind.UNVERIFIABLE: f"Unavailable in the current text channel · {evidence.detail}",
            EvidenceKind.NOT_APPLICABLE: f"Not applicable · {evidence.detail}",
        }
    return labels[evidence.kind]


def reference_source_link(
    span: ZoteroPdfSpan | VaultMarkdownSpan,
    language: str,
    *,
    compact: bool = False,
    reader: AnalysisReader | None = None,
) -> str:
    if isinstance(span, ZoteroPdfSpan):
        page = span.page_index + 1
        opens_zotflow_page = reader is not None and reader.kind == "zotflow_library"
        if opens_zotflow_page:
            navigation = quote(json.dumps({"pageIndex": span.page_index}, separators=(",", ":")), safe="")
            # Name-only projections remain readable for old v4 drafts, but the
            # commit boundary requires a host-verified Vault ID.
            vault_target = reader.vault_id or reader.vault_name or ""
            uri = (
                f"obsidian://zotflow?vault={quote(vault_target, safe='')}"
                f"&type=open-attachment&libraryID={span.library_id}"
                f"&key={span.attachment_key}&navigation={navigation}"
            )
        else:
            collection = "library" if span.library_type == "personal" else f"groups/{span.library_id}"
            uri = f"zotero://open-pdf/{collection}/items/{span.attachment_key}?page={page}"
            if span.annotation_key:
                uri += f"&annotation={span.annotation_key}"
        if compact:
            label = f"PDF·{page}" if language == "zh" else f"PDF p.{page}"
        elif language == "zh":
            source = "原批注" if span.annotation_key and not opens_zotflow_page else "原文"
            label = f"{source}·PDF 第 {page} 页"
        else:
            source = "Source annotation" if span.annotation_key and not opens_zotflow_page else "Source"
            label = f"{source} · PDF page {page}"
        return f"[{label}]({uri})"
    note_path = span.vault_path[:-3]
    label = (
        ("原文" if language == "zh" else "Source")
        if compact else
        ("原文·段落" if language == "zh" else "Source · paragraph")
    )
    return f"[[{note_path}#^{span.block_id}|{label}]]"


def reference_inline_evidence(
    evidence: Evidence, language: str, *, reader: AnalysisReader | None = None
) -> str:
    suffix = f"〔{reference_evidence_text(evidence, language)}〕"
    if evidence.source_spans:
        suffix += " " + " ".join(
            reference_source_link(span, language, reader=reader)
            for span in evidence.source_spans
        )
    return suffix


def reference_canvas_inline_evidence(
    evidence: Evidence, language: str, *, reader: AnalysisReader | None = None,
    unique_sources: bool = False,
) -> str:
    """Keep an evidence signal and live source link without drowning the tree."""
    labels = (
        {
            EvidenceKind.AUTHOR_STATED: "作者",
            EvidenceKind.ANALYSIS_INFERENCE: "推断",
            EvidenceKind.NOT_REPORTED: "未报告",
            EvidenceKind.UNVERIFIABLE: "待核实",
            EvidenceKind.NOT_APPLICABLE: "不适用",
        }
        if language == "zh"
        else {
            EvidenceKind.AUTHOR_STATED: "Author",
            EvidenceKind.ANALYSIS_INFERENCE: "Inference",
            EvidenceKind.NOT_REPORTED: "Not reported",
            EvidenceKind.UNVERIFIABLE: "Unverified",
            EvidenceKind.NOT_APPLICABLE: "N/A",
        }
    )
    result = f"〔{labels[evidence.kind]}〕"
    if evidence.source_spans:
        links = [
            reference_source_link(span, language, compact=True, reader=reader)
            for span in evidence.source_spans
        ]
        if unique_sources:
            links = list(dict.fromkeys(links))
        result += " " + " ".join(links)
    return result


def reference_point_label(point_id: str, language: str) -> str:
    if point_id.startswith("challenge-"):
        number = point_id.removeprefix("challenge-")
        return f"Challenge {number}" if language == "en" else f"挑战 {number}"
    if point_id.startswith("finding-"):
        number = point_id.removeprefix("finding-")
        return f"Finding {number}" if language == "en" else f"结果 {number}"
    if point_id.startswith("reason-"):
        number = point_id.removeprefix("reason-")
        return f"Reason {number}" if language == "en" else f"原因 {number}"
    return POINT_LABELS[point_id][0 if language == "en" else 1]


def reference_points(claim: AnalysisClaim) -> list[AnalysisPoint]:
    path = claim.outline_path or ""
    matching = next(
        (slots for prefix, slots in POINT_ORDER.items() if path.startswith(prefix)),
        (),
    )
    rank = {point_id: index for index, point_id in enumerate(matching)}
    return sorted(
        claim.points,
        key=lambda point: (
            int(point.point_id.removeprefix("challenge-"))
            if point.point_id.startswith("challenge-")
            else rank.get(point.point_id, 100),
            point.point_id,
        ),
    )


def reference_source_quote_lines(
    evidence: Evidence,
    language: str,
    *,
    reader: AnalysisReader | None = None,
    indent: str = "",
) -> list[str]:
    """Render supplied verbatim excerpts as literal Markdown, never as Canvas text.

    Source authenticity is checked separately; rendering does not verify a quote.
    Escape source syntax so quotations cannot create links, HTML, or block identities.
    """
    label = "原文摘录" if language == "zh" else "Original excerpt"
    lines: list[str] = []
    for span in evidence.source_spans:
        if span.quote is None:
            continue
        lines.extend([
            "",
            f"{indent}> **{label}** · {reference_source_link(span, language, reader=reader)}",
            f"{indent}>",
        ])
        for line in span.quote.splitlines():
            literal = re.sub(r"([\\`*_{}\[\]()#+.!|~^$-])", r"\\\1", escape(line, quote=False))
            lines.append(f"{indent}> {literal}")
    return lines


def reference_claim_markdown_lines(
    claim: AnalysisClaim,
    language: str,
    *,
    heading_level: int = 4,
    reader: AnalysisReader | None = None,
    markdown_quotes: bool = False,
) -> list[str]:
    lines = [
        f"{'#' * heading_level} {claim.title}",
        f"{claim.body} {reference_inline_evidence(claim.evidence, language, reader=reader)} ^claim-{claim.claim_id}",
    ]
    if markdown_quotes:
        lines.extend(reference_source_quote_lines(claim.evidence, language, reader=reader))
    for point in reference_points(claim):
        label = reference_point_label(point.point_id, language)
        lines.extend(
            [
                "",
                (
                    f"- **{label}.** {point.text} "
                    f"{reference_inline_evidence(point.evidence, language, reader=reader)} "
                    f"^{point_anchor(claim, point)}"
                ),
            ]
        )
        if markdown_quotes:
            lines.extend(reference_source_quote_lines(
                point.evidence, language, reader=reader, indent="  "
            ))
    return lines


def reference_claim_canvas_text(
    claim: AnalysisClaim,
    note_stem: str,
    language: str,
    *,
    reader: AnalysisReader | None = None,
) -> str:
    summary = claim.canvas_summary if claim.canvas_summary is not None else claim.body
    backlink = "正文" if language == "zh" else "Analysis"
    return "\n".join(
        [
            f"### {claim.title}",
            f"{summary} {reference_canvas_inline_evidence(claim.evidence, language, reader=reader)}",
            f"↩ [[{note_stem}#^claim-{claim.claim_id}|{backlink}]]",
        ]
    )


def reference_point_canvas_text(
    claim: AnalysisClaim,
    point: AnalysisPoint,
    note_stem: str,
    language: str,
    *,
    reader: AnalysisReader | None = None,
) -> str:
    summary = point.canvas_summary if point.canvas_summary is not None else point.text
    backlink = "正文" if language == "zh" else "Analysis"
    label = reference_point_label(point.point_id, language)
    return (
        f"- **{label}:** {summary} "
        f"{reference_canvas_inline_evidence(point.evidence, language, reader=reader)} "
        f"↩ [[{note_stem}#^{point_anchor(claim, point)}|{backlink}]]"
    )


def reference_detail_canvas_text(
    claim: AnalysisClaim,
    note_stem: str,
    language: str,
    *,
    reader: AnalysisReader | None = None,
) -> str:
    """Keep point-level provenance in one editable detail card per claim."""
    return "\n".join(
        reference_point_canvas_text(claim, point, note_stem, language, reader=reader)
        for point in reference_points(claim)
    )


def _group_label(path: str, language: str) -> str:
    for role_groups in GROUPS.values():
        for group_path, en, zh in role_groups:
            if path == group_path:
                return en if language == "en" else zh
    raise KeyError(path)


def _render_markdown(document: AnalysisDocument) -> str:
    language = document.language or "zh"
    is_en = language == "en"
    scope = (
        "Whole paper" if document.profile.kind.value == "whole" else
        "Focused: " + ", ".join(SECTION_LABELS[role][language] for role in document.profile.roles)
    )
    lines = [
        "---",
        "sw_schema: 2",
        "sw_kind: paper-analysis",
        f"sw_catalog_id: {json.dumps(document.artifact_id, ensure_ascii=False)}",
        f"sw_analysis_profile: {document.profile.kind.value}",
        "sw_analysis_framework: reference_tree",
        f"sw_analysis_language: {language}",
        "---",
        "",
        f"# {document.paper_title}{': Paper Analysis' if is_en else '：论文分析'}",
        "",
        f"> {'Scope' if is_en else '分析范围'}: {scope}",
    ]
    for role in document.profile.roles:
        lines.extend(["", f"## {SECTION_LABELS[role][language]}"])
        role_claims = [claim for claim in document.claims if claim.role is role]
        for group_path, _, _ in GROUPS[role]:
            if group_path.count("/") > 1:
                continue
            lines.extend(["", f"### {_group_label(group_path, language)}"])
            if role is AnalysisRole.INTRODUCTION and group_path == "introduction/our_pipeline":
                for child_path in (
                    "introduction/our_pipeline/insight",
                    "introduction/our_pipeline/contributions",
                ):
                    lines.extend(["", f"#### {_group_label(child_path, language)}"])
                    for claim in role_claims:
                        if claim.outline_path == child_path or (
                            claim.outline_path or ""
                        ).startswith(child_path + "/"):
                            lines.extend(
                                [
                                    "",
                                    *reference_claim_markdown_lines(
                                        claim, language, heading_level=5, reader=document.reader,
                                        markdown_quotes=document.profile.markdown_quotes,
                                    ),
                                ]
                            )
            else:
                for claim in role_claims:
                    if claim.outline_path == group_path or (
                        claim.outline_path or ""
                    ).startswith(group_path + "/"):
                        lines.extend([
                            "", *reference_claim_markdown_lines(
                                claim, language, reader=document.reader,
                                markdown_quotes=document.profile.markdown_quotes,
                            )
                        ])
    return "\n".join(lines).rstrip() + "\n"


@dataclass
class _TreeNode:
    path: str
    text: str
    kind: str
    role: AnalysisRole | None
    width: int
    height: int
    children: list[_TreeNode] = field(default_factory=list)
    x: int = 0
    y: int = 0


def _visible_height(text: str, *, minimum: int, width: int) -> int:
    visible = _HTML_COMMENT.sub("", text)
    visible = _LINK_TARGET.sub("]", visible)
    visible = _WIKILINK.sub(r"\1", visible)
    # A CJK glyph occupies roughly twice the width of a Latin glyph in Canvas.
    # Reserve one full additional line below the estimated text for link clicks.
    columns = max(20, (width - 28) // 9)
    wrapped = sum(
        max(
            1,
            math.ceil(
                sum(2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1 for char in line)
                / columns
            ),
        )
        for line in visible.splitlines()
    )
    return max(minimum, 24 + (wrapped + 1) * 21)


def _reference_tree(document: AnalysisDocument, note_stem: str) -> _TreeNode:
    language = document.language or "zh"
    root_text = f"# {document.paper_title}"
    root = _TreeNode(
        "root", root_text, "root", None, 200,
        _visible_height(root_text, minimum=80, width=200),
    )
    groups: dict[str, _TreeNode] = {}
    for role in document.profile.roles:
        section_text = f"## {SECTION_LABELS[role][language]}"
        section = _TreeNode(
            f"role/{role.value}",
            section_text,
            "section",
            role,
            190,
            _visible_height(section_text, minimum=64, width=190),
        )
        root.children.append(section)
        for group_path, _, _ in GROUPS[role]:
            group_text = f"**{_group_label(group_path, language)}**"
            group = _TreeNode(
                f"tree/{group_path}",
                group_text,
                "group",
                role,
                260,
                _visible_height(group_text, minimum=50, width=260),
            )
            groups[group_path] = group
            parent_path = group_path.rpartition("/")[0]
            if parent_path in groups:
                groups[parent_path].children.append(group)
            else:
                section.children.append(group)

    for claim in document.claims:
        path = claim.outline_path or ""
        parent_path = path if path in groups else path.rpartition("/")[0]
        parent = groups[parent_path]
        claim_text = reference_claim_canvas_text(
            claim, note_stem, language, reader=document.reader
        )
        claim_node = _TreeNode(
            f"role/{claim.role.value}/{claim.claim_id}",
            claim_text,
            "claim",
            claim.role,
            430,
            _visible_height(claim_text, minimum=118, width=430),
        )
        parent.children.append(claim_node)
        if claim.points:
            detail_text = reference_detail_canvas_text(
                claim, note_stem, language, reader=document.reader
            )
            claim_node.children.append(
                _TreeNode(
                    f"role/{claim.role.value}/{claim.claim_id}/details",
                    detail_text,
                    "details",
                    claim.role,
                    920,
                    _visible_height(detail_text, minimum=100, width=920),
                )
            )
    return root


def _layout_tree(root: _TreeNode) -> None:
    heights: dict[str, int] = {}
    gap = 6

    def measure(node: _TreeNode) -> int:
        children = sum(measure(child) for child in node.children)
        if node.children:
            children += gap * (len(node.children) - 1)
        result = max(node.height, children)
        heights[node.path] = result
        return result

    def place(node: _TreeNode, *, top: int, x: int) -> None:
        subtree = heights[node.path]
        node.x = x
        node.y = top + (subtree - node.height) // 2
        child_total = sum(heights[child.path] for child in node.children)
        child_total += gap * max(0, len(node.children) - 1)
        next_top = top + (subtree - child_total) // 2
        for child in node.children:
            place(child, top=next_top, x=x + node.width + 56)
            next_top += heights[child.path] + gap

    measure(root)
    place(root, top=0, x=0)


def _render_canvas(document: AnalysisDocument, note_stem: str) -> dict[str, list[dict[str, Any]]]:
    tree = _reference_tree(document, note_stem)
    _layout_tree(tree)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def visit(node: _TreeNode, parent: _TreeNode | None = None) -> None:
        node_id = canvas_node_id(document.artifact_id, node.path)
        payload: dict[str, Any] = {
            "id": node_id,
            "type": "text",
            "x": node.x,
            "y": node.y,
            "width": node.width,
            "height": node.height,
            "text": node.text,
        }
        if node.kind == "root":
            payload["color"] = "#287dba"
        else:
            payload["color"] = "#edf0ed" if node.kind == "group" else ROLE_COLORS[node.role]
            payload["styleAttributes"] = {"border": "invisible"}
        nodes.append(payload)
        if parent is not None:
            edges.append(
                {
                    "id": _edge_id(document.artifact_id, parent.path, node.path),
                    "fromNode": canvas_node_id(document.artifact_id, parent.path),
                    "fromSide": "right",
                    "toNode": node_id,
                    "toSide": "left",
                    "toEnd": "none",
                    "color": ROLE_COLORS[node.role],
                    "styleAttributes": {"pathfindingMethod": "square"},
                }
            )
        for child in node.children:
            visit(child, node)

    visit(tree)
    left = min(node["x"] for node in nodes)
    top = min(node["y"] for node in nodes)
    width = max(node["x"] + node["width"] for node in nodes) - left
    height = max(node["y"] + node["height"] for node in nodes) - top
    if any(node["height"] > 420 for node in nodes):
        raise ValueError("reference-tree Canvas has an oversized node; shorten its summary")
    if max(width / height, height / width) > 2:
        raise ValueError(
            f"reference-tree Canvas is too elongated ({width}x{height}); "
            "narrow the analysis outline"
        )
    return {"nodes": nodes, "edges": edges}


def render_reference_analysis(
    document: AnalysisDocument, *, note_stem: str
) -> AnalysisBundle:
    return AnalysisBundle(
        markdown=_render_markdown(document),
        canvas=_render_canvas(document, note_stem),
    )
