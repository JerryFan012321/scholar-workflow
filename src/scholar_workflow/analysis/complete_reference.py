"""Editable five-branch analysis projection, independent of the v4 renderer."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from scholar_workflow.analysis.models import (
    FIVE_TREE_ROLES,
    AnalysisClaim,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisReader,
    AnalysisRole,
    CanvasImage,
)
from scholar_workflow.analysis.reference_rendering import (
    _visible_height,
    reference_canvas_inline_evidence,
    reference_inline_evidence,
    reference_source_link,
    reference_source_quote_lines,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    _edge_id,
    _safe_note_stem,
    canvas_node_id,
    point_anchor,
)

SECTION_LABELS = {
    AnalysisRole.ABSTRACT: {"en": "Abstract", "zh": "摘要"},
    AnalysisRole.INTRODUCTION: {"en": "Introduction", "zh": "引言"},
    AnalysisRole.METHOD: {"en": "Method", "zh": "方法"},
    AnalysisRole.EXPERIMENTS: {"en": "Experiments", "zh": "实验"},
    AnalysisRole.LIMITATION: {"en": "Limitation", "zh": "局限"},
}
ROLE_COLORS = {
    AnalysisRole.ABSTRACT: "#e3978d",
    AnalysisRole.INTRODUCTION: "#d9ad51",
    AnalysisRole.METHOD: "#d5c858",
    AnalysisRole.EXPERIMENTS: "#a5ba73",
    AnalysisRole.LIMITATION: "#76a99d",
}
_GROUP_LABELS = {
    "abstract/task": ("Task", "任务"),
    "abstract/previous_methods": ("Technical challenge for previous methods", "既有方法的技术挑战"),
    "abstract/insight": ("Key insight / motivation", "关键洞见与动机"),
    "abstract/contributions": ("Technical contributions", "技术贡献"),
    "abstract/experiment": ("Experiment", "摘要中的实验概述"),
    "introduction/task_application": ("Task and application", "任务与应用"),
    "introduction/previous_methods": (
        "Technical challenge for previous methods",
        "既有方法的技术挑战",
    ),
    "introduction/our_pipeline": ("Our pipeline", "本文方案"),
    "introduction/our_pipeline/insight": (
        "One-sentence key innovation / insight / contribution",
        "一句话概括关键创新、洞见或贡献",
    ),
    "introduction/demos_application": ("Demos / applications", "演示与应用"),
    "method/overview": ("Overview", "概览"),
    "experiments/comparison": ("Comparison experiments", "对比实验"),
    "experiments/ablation": ("Ablation studies", "消融研究"),
    "limitation/explanation": ("Reasoned limitations", "局限及原因"),
}
_SLOTS = {
    "abstract/insight": ("motivation", "advantage"),
    "abstract/contributions": ("summary", "advantage"),
    "introduction/previous_methods": ("previous-method", "limitation", "technical-reason"),
    "introduction/our_pipeline/contributions": ("purpose", "how", "advantage"),
    "method/overview": ("task-io", "steps"),
    "method/modules": ("motivation", "method", "why-it-works", "technical-advantage"),
    "experiments/ablation": ("components", "design-choices"),
}
_POINT_LABELS = {
    "previous-method": ("Previous method", "既有方法"),
    "limitation": ("Failure cases (Limitation)", "失败案例与局限"),
    "technical-reason": ("Technical reason", "技术原因"),
    "purpose": ("Problem addressed", "所解决的问题"),
    "how": ("How it is done", "具体做法"),
    "advantage": ("Advantage / insight", "优势与洞见"),
    "motivation": ("Motivation", "动机"),
    "method": ("Method", "方法"),
    "why-it-works": ("Why it works", "有效原因"),
    "technical-advantage": ("Technical advantage", "技术优势"),
    "task-io": ("Task / input / output", "任务、输入与输出"),
    "steps": ("Method / steps", "方法与步骤"),
    "components": (
        "Effects of core contributions / important components",
        "核心贡献与重要组件的影响",
    ),
    "design-choices": (
        "Effects of design choices in each pipeline module",
        "各流程模块设计选择的影响",
    ),
}
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WIKILINK = re.compile(r"\[\[[^\]|]+\|([^\]]+)\]\]")
_IMAGE_EMBED = re.compile(r"(?m)^!\[[^\]\r\n]*\|([1-9][0-9]*)x([1-9][0-9]*)\]\(\./attachments/[^\r\n)]+\.png\)$")


def canvas_visible_height(text: str, *, width: int) -> int:
    """Account for declared embedded-image pixels as well as editable prose."""
    return _visible_height(_IMAGE_EMBED.sub("", text), minimum=0, width=width) + sum(
        int(match[2]) for match in _IMAGE_EMBED.finditer(text)
    )


def canvas_image_width(text: str) -> int:
    return max((int(match[1]) + 28 for match in _IMAGE_EMBED.finditer(text)), default=0)


def _label(labels: tuple[str, str], language: str) -> str:
    return labels[0 if language == "en" else 1]


def _slot_prefix(path: str) -> str | None:
    return next(
        (prefix for prefix in _SLOTS if path == prefix or path.startswith(prefix + "/")),
        None,
    )


def complete_point_label(claim: AnalysisClaim, point_id: str, language: str) -> str:
    """Use the reference-image label in its own framework context."""
    prefix = _slot_prefix(claim.outline_path or "")
    if prefix == "abstract/insight":
        labels = {
            "motivation": ("One-sentence insight / motivation", "一句话概括洞见与动机"),
            "advantage": ("Benefit of the insight / motivation", "洞见与动机的益处"),
        }
        return _label(labels[point_id], language)
    if prefix == "abstract/contributions":
        labels = {
            "summary": ("One-sentence technical contribution", "一句话概括技术贡献"),
            "advantage": ("Benefit of the technical contribution", "技术贡献的益处"),
        }
        return _label(labels[point_id], language)
    for token, labels in (
        ("challenge-", ("Technical challenge", "技术挑战")),
        ("finding-", ("Finding", "结果")),
        ("reason-", ("Reason", "原因")),
    ):
        if point_id.startswith(token):
            return f"{_label(labels, language)} {point_id.removeprefix(token)}"
    return _label(_POINT_LABELS[point_id], language)


def complete_points(claim: AnalysisClaim) -> list[AnalysisPoint]:
    prefix = _slot_prefix(claim.outline_path or "")
    ranks = {slot: index for index, slot in enumerate(_SLOTS.get(prefix or "", ()))}

    def order(point: AnalysisPoint) -> tuple[int, int, str]:
        match = re.fullmatch(r"(?:challenge|finding|reason)-([1-9][0-9]*)", point.point_id)
        return (
            ranks.get(point.point_id, 100),
            int(match.group(1)) if match else 0,
            point.point_id,
        )

    return sorted(claim.points, key=order)


def complete_claim_label(claim: AnalysisClaim, language: str, *, number: int = 1) -> str:
    path = claim.outline_path or ""
    if path in _GROUP_LABELS:
        return _label(_GROUP_LABELS[path], language)
    repeated = (
        ("abstract/contributions/", ("Technical contribution", "技术贡献")),
        ("introduction/previous_methods/", ("Technical challenge", "技术挑战")),
        ("introduction/our_pipeline/contributions/", ("Contribution", "贡献")),
        ("method/modules/", ("Pipeline module", "流程模块")),
        ("abstract/previous_methods/", ("Previous method", "既有方法")),
        ("abstract/experiment/", ("Experiment", "实验概述")),
        ("experiments/comparison/", ("Comparison experiment", "对比实验")),
        ("experiments/ablation/", ("Ablation study", "消融研究")),
        ("limitation/explanation/", ("Reasoned limitation", "局限及原因")),
    )
    for prefix, labels in repeated:
        if path.startswith(prefix):
            return f"{_label(labels, language)} {number}"
    raise ValueError(f"Unknown complete-analysis outline path: {path}")


def _claim_statement(claim: AnalysisClaim, *, summary: bool, label: str) -> str:
    text = claim.canvas_summary if summary and claim.canvas_summary is not None else claim.body
    if claim.title != label:
        return f"**{claim.title}.** {text}"
    return text


def complete_claim_canvas_text(
    claim: AnalysisClaim,
    note_stem: str,
    language: str,
    *,
    reader: AnalysisReader | None = None,
    label: str | None = None,
    unique_sources: bool = False,
) -> str:
    label = label or complete_claim_label(claim, language)
    if claim.container:
        return f"**{label}**"
    statement = _claim_statement(claim, summary=True, label=label)
    backlink = "Analysis" if language == "en" else "正文"
    evidence = reference_canvas_inline_evidence(
        claim.evidence, language, reader=reader, unique_sources=unique_sources,
    )
    return (
        f"**{label}**\n{statement}\n{evidence} ↩ [[{note_stem}#^claim-{claim.claim_id}|{backlink}]]"
    )


def complete_point_canvas_text(
    claim: AnalysisClaim,
    point: AnalysisPoint,
    note_stem: str,
    language: str,
    *,
    reader: AnalysisReader | None = None,
    unique_sources: bool = False,
) -> str:
    label = complete_point_label(claim, point.point_id, language)
    statement = point.canvas_summary if point.canvas_summary is not None else point.text
    backlink = "Analysis" if language == "en" else "正文"
    evidence = reference_canvas_inline_evidence(
        point.evidence, language, reader=reader, unique_sources=unique_sources,
    )
    return (
        f"**{label}**\n{statement}\n"
        f"{evidence} ↩ [[{note_stem}#^{point_anchor(claim, point)}|{backlink}]]"
    )


def complete_claim_markdown_lines(
    claim: AnalysisClaim,
    language: str,
    *,
    heading_level: int = 4,
    reader: AnalysisReader | None = None,
    markdown_quotes: bool = True,
    label: str | None = None,
    include_points: bool = True,
) -> list[str]:
    """Containers have headings, not fabricated statements or claim anchors."""
    label = label or complete_claim_label(claim, language)
    lines = [f"{'#' * heading_level} {label}"]
    if not claim.container:
        lines.extend(
            [
                "",
                (
                    f"{_claim_statement(claim, summary=False, label=label)} "
                    f"{reference_inline_evidence(claim.evidence, language, reader=reader)} "
                    f"^claim-{claim.claim_id}"
                ),
            ]
        )
        if markdown_quotes:
            lines.extend(reference_source_quote_lines(claim.evidence, language, reader=reader))
    if include_points:
        points = {point.point_id: point for point in complete_points(claim)}
        slots = _SLOTS.get(_slot_prefix(claim.outline_path or "") or "", tuple(points))
        for slot in slots:
            lines.extend(
                ["", f"{'#' * (heading_level + 1)} {complete_point_label(claim, slot, language)}"]
            )
            if point := points.get(slot):
                lines.extend(["", _point_markdown_line(claim, point, language, reader=reader)])
                if markdown_quotes:
                    lines.extend(
                        reference_source_quote_lines(point.evidence, language, reader=reader)
                    )
    return lines


def _point_markdown_line(
    claim: AnalysisClaim,
    point: AnalysisPoint,
    language: str,
    *,
    reader: AnalysisReader | None,
) -> str:
    return (
        f"{point.text} {reference_inline_evidence(point.evidence, language, reader=reader)} "
        f"^{point_anchor(claim, point)}"
    )


@dataclass
class TemplateNode:
    """One actual editable node in the complete framework."""

    path: str
    text: str
    kind: str
    role: AnalysisRole | None
    label: str
    width: int
    height: int
    children: list[TemplateNode] = field(default_factory=list)
    claim: AnalysisClaim | None = None
    point: AnalysisPoint | None = None
    x: int = 0
    y: int = 0


def _visible_lines(text: str) -> list[str]:
    visible = _MD_LINK.sub(r"\1", text)
    visible = _WIKILINK.sub(r"\1", visible)
    return [re.sub(r"[*_#`]+", "", line) for line in visible.splitlines()]


def _dimensions(text: str, kind: str) -> tuple[int, int]:
    if kind == "image":
        width = canvas_image_width(text)
        return width, canvas_visible_height(text, width=width)
    units = max(
        (
            sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in line)
            for line in _visible_lines(text)
        ),
        default=0,
    )
    maximum = 1000 if kind in {"claim", "point"} else 440 if kind == "group" else 280
    minimum = 280 if kind in {"claim", "point"} else 104
    width = min(maximum, max(minimum, math.ceil((28 + units * 9) / 8) * 8))
    # The shared estimator reserves a full visible line for clicking links.
    height = _visible_height(text, minimum=0, width=width)
    return width, height


def _node(
    path: str,
    label: str,
    kind: str,
    role: AnalysisRole | None,
    *,
    text: str | None = None,
    claim: AnalysisClaim | None = None,
    point: AnalysisPoint | None = None,
) -> TemplateNode:
    content = text if text is not None else f"**{label}**"
    width, height = _dimensions(content, kind)
    return TemplateNode(path, content, kind, role, label, width, height, claim=claim, point=point)


def template_tree(document: AnalysisDocument, note_stem: str) -> TemplateNode:
    """Build the named tree without conflating structure and scientific facts."""
    _safe_note_stem(note_stem)
    if document.schema_version != 5 or document.profile.framework != "reference_tree_v5":
        raise ValueError("Complete-reference projection requires IR v5")
    backlink_target = note_stem
    if note_path := document.profile.canvas_note_path:
        if note_path.rsplit("/", 1)[-1] != note_stem + ".md":
            raise ValueError("Canvas companion filename must match the paired Markdown")
        backlink_target = note_path[:-3]
    language = document.language or "en"
    root = _node("root", document.paper_title, "root", None)
    selected = set(document.profile.roles)

    def claims_at(prefix: str) -> list[AnalysisClaim]:
        return [
            claim
            for claim in document.claims
            if claim.outline_path == prefix or (claim.outline_path or "").startswith(prefix + "/")
        ]

    def claim_node(claim: AnalysisClaim, label: str) -> TemplateNode:
        path = f"role/{claim.role.value}/{claim.claim_id}"
        node = _node(
            path,
            label,
            "container" if claim.container else "claim",
            claim.role,
            text=complete_claim_canvas_text(
                claim, backlink_target, language, reader=document.reader, label=label,
                unique_sources=document.profile.canvas_unique_sources,
            ),
            claim=claim,
        )
        points = {point.point_id: point for point in complete_points(claim)}

        def image_node(image: CanvasImage, parent_path: str, anchor: str) -> TemplateNode:
            scale = min(880 / image.pixel_width, 240 / image.pixel_height, 1)
            width, height = round(image.pixel_width * scale), round(image.pixel_height * scale)
            backlink = "Analysis" if language == "en" else "正文"
            text = (
                f"**{image.caption}**\n\n"
                f"![{image.caption}|{width}x{height}](./{quote(image.image_path, safe='/')})\n\n"
                f"{reference_source_link(image.source, language, compact=True, reader=document.reader)} "
                f"↩ [[{backlink_target}#^{anchor}|{backlink}]]"
            )
            return _node(parent_path + "/image", image.caption, "image", claim.role, text=text)

        slots = _SLOTS.get(_slot_prefix(claim.outline_path or "") or "", tuple(points))
        for slot in slots:
            label = complete_point_label(claim, slot, language)
            point = points.get(slot)
            point_node = _node(
                    f"{path}/point/{slot}",
                    label,
                    "point" if point else "empty-slot",
                    claim.role,
                    text=complete_point_canvas_text(
                        claim, point, backlink_target, language, reader=document.reader,
                        unique_sources=document.profile.canvas_unique_sources,
                    )
                    if point
                    else None,
                    claim=claim,
                    point=point,
                )
            if point is not None and point.canvas_image is not None:
                point_node.children.append(image_node(point.canvas_image, point_node.path, point_anchor(claim, point)))
            node.children.append(point_node)
        if claim.canvas_image is not None:
            node.children.append(image_node(claim.canvas_image, path, f"claim-{claim.claim_id}"))
        return node

    def group(role: AnalysisRole, path: str) -> TemplateNode:
        return _node(f"tree/{path}", _label(_GROUP_LABELS[path], language), "group", role)

    def singleton(role: AnalysisRole, path: str) -> TemplateNode:
        items = claims_at(path)
        if len(items) == 1:
            return claim_node(items[0], _label(_GROUP_LABELS[path], language))
        node = group(role, path)
        if items:
            node.children.extend(
                claim_node(claim, complete_claim_label(claim, language, number=index))
                for index, claim in enumerate(items, 1)
            )
        elif slots := _SLOTS.get(path):
            # No record is not a "not reported" statement. Only the empty labels exist.
            for slot in slots:
                labels = (
                    {
                        "motivation": ("One-sentence insight / motivation", "一句话概括洞见与动机"),
                        "advantage": ("Benefit of the insight / motivation", "洞见与动机的益处"),
                    }
                    if path == "abstract/insight"
                    else _POINT_LABELS
                )
                node.children.append(
                    _node(
                        f"tree/{path}/empty/{slot}",
                        _label(labels[slot], language),
                        "empty-slot",
                        role,
                    )
                )
        return node

    def repeated(role: AnalysisRole, prefix: str) -> list[TemplateNode]:
        return [
            claim_node(claim, complete_claim_label(claim, language, number=index))
            for index, claim in enumerate(claims_at(prefix), 1)
        ]

    for role in FIVE_TREE_ROLES:
        if role not in selected:
            continue
        section = _node(f"role/{role.value}", SECTION_LABELS[role][language], "section", role)
        root.children.append(section)
        if role is AnalysisRole.ABSTRACT:
            section.children.extend(
                [
                    singleton(role, "abstract/task"),
                    singleton(role, "abstract/previous_methods"),
                    singleton(role, "abstract/insight"),
                ]
            )
            contributions = group(role, "abstract/contributions")
            contributions.children.extend(repeated(role, "abstract/contributions"))
            section.children.extend([contributions, singleton(role, "abstract/experiment")])
        elif role is AnalysisRole.INTRODUCTION:
            previous = group(role, "introduction/previous_methods")
            previous.children.extend(repeated(role, "introduction/previous_methods"))
            pipeline = group(role, "introduction/our_pipeline")
            pipeline.children.append(singleton(role, "introduction/our_pipeline/insight"))
            pipeline.children.extend(repeated(role, "introduction/our_pipeline/contributions"))
            section.children.extend(
                [
                    singleton(role, "introduction/task_application"),
                    previous,
                    pipeline,
                    singleton(role, "introduction/demos_application"),
                ]
            )
        elif role is AnalysisRole.METHOD:
            section.children.append(singleton(role, "method/overview"))
            section.children.extend(repeated(role, "method/modules"))
        elif role is AnalysisRole.EXPERIMENTS:
            section.children.extend(
                [
                    singleton(role, "experiments/comparison"),
                    singleton(role, "experiments/ablation"),
                ]
            )
        else:
            section.children.extend(repeated(role, "limitation/explanation"))
    return root


def template_relations(document: AnalysisDocument, note_stem: str) -> list[tuple[str, str]]:
    """Expose exact semantic parent-child paths to paired conformance."""
    result: list[tuple[str, str]] = []

    def visit(node: TemplateNode) -> None:
        for child in node.children:
            result.append((node.path, child.path))
            visit(child)

    visit(template_tree(document, note_stem))
    return result


def _render_markdown(document: AnalysisDocument, tree: TemplateNode) -> str:
    language = document.language or "en"
    is_en = language == "en"
    scope = "Whole paper" if is_en else "全文"
    if document.profile.kind.value == "focused":
        prefix = "Focused: " if is_en else "局部："
        scope = prefix + ", ".join(SECTION_LABELS[child.role][language] for child in tree.children)
    lines = [
        "---",
        "sw_schema: 2",
        "sw_kind: paper-analysis",
        f"sw_catalog_id: {json.dumps(document.artifact_id, ensure_ascii=False)}",
        f"sw_analysis_profile: {document.profile.kind.value}",
        "sw_analysis_framework: reference_tree_v5",
        f"sw_analysis_language: {language}",
        "---",
        "",
        f"# {document.paper_title}{': Paper Analysis' if is_en else '：论文分析'}",
        "",
        f"> {'Scope' if is_en else '分析范围'}: {scope}",
    ]

    def visit(node: TemplateNode, level: int) -> None:
        if node.kind == "image":
            return  # A Canvas supplement is not another Markdown heading or fact.
        if level > 6:
            raise ValueError("Complete-reference Markdown exceeds six heading levels")
        lines.append("")
        if node.point is not None:
            lines.extend(
                [
                    f"{'#' * level} {node.label}",
                    "",
                    _point_markdown_line(node.claim, node.point, language, reader=document.reader),
                ]
            )
            lines.extend(
                reference_source_quote_lines(node.point.evidence, language, reader=document.reader)
            )
        elif node.claim is not None and node.kind != "empty-slot":
            lines.extend(
                complete_claim_markdown_lines(
                    node.claim,
                    language,
                    heading_level=level,
                    reader=document.reader,
                    markdown_quotes=document.profile.markdown_quotes,
                    label=node.label,
                    include_points=False,
                )
            )
        else:
            lines.append(f"{'#' * level} {node.label}")
        for child in node.children:
            visit(child, level + 1)

    for section in tree.children:
        visit(section, 2)
    return "\n".join(lines).rstrip() + "\n"


def _layout_tree(root: TemplateNode, *, expanded: bool = False) -> None:
    """Keep all five sections on one trunk; do not mirror or make dashboards."""
    heights: dict[str, int] = {}
    layer_widths: dict[int, int] = {}
    sibling_gap = 8
    branch_gap = 32

    def measure(node: TemplateNode, depth: int) -> int:
        layer_widths[depth] = max(layer_widths.get(depth, 0), node.width)
        gap = branch_gap if node.kind == "root" else sibling_gap
        height = sum(measure(child, depth + 1) for child in node.children)
        height += gap * max(0, len(node.children) - 1)
        heights[node.path] = max(node.height, height)
        return heights[node.path]

    layer_x = {0: 0}

    def place(node: TemplateNode, depth: int, top: int) -> None:
        subtree = heights[node.path]
        node.x = layer_x[depth]
        gap = branch_gap if node.kind == "root" else sibling_gap
        total = sum(heights[child.path] for child in node.children)
        total += gap * max(0, len(node.children) - 1)
        next_top = top + (subtree - total) // 2
        for child in node.children:
            place(child, depth + 1, next_top)
            next_top += heights[child.path] + gap
        if node.children:
            first, last = node.children[0], node.children[-1]
            center = (first.y + first.height // 2 + last.y + last.height // 2) // 2
            node.y = center - node.height // 2
        else:
            node.y = top + (subtree - node.height) // 2

    measure(root, 0)
    for depth in range(1, len(layer_widths)):
        layer_x[depth] = layer_x[depth - 1] + layer_widths[depth - 1] + 64
    place(root, 0, 0)

    if expanded and len(layer_widths) > 1:
        # Fit dense trees by distributing a bounded gutter across aligned layers.
        # Keep text boxes, vertical bands and fixed endpoints unchanged; do not
        # create oversized empty boxes or unbounded whitespace to pass geometry.
        visible = []
        pending = [root]
        while pending:
            node = pending.pop()
            visible.append(node)
            pending.extend(node.children)
        width = max(node.x + node.width for node in visible) - min(node.x for node in visible)
        height = max(node.y + node.height for node in visible) - min(node.y for node in visible)
        if height > 2 * width:
            intervals = len(layer_widths) - 1
            gutter = min(344, 64 + math.ceil((math.ceil(height / 2) - width) / intervals))
            for depth in range(1, len(layer_widths)):
                layer_x[depth] = layer_x[depth - 1] + layer_widths[depth - 1] + gutter
            place(root, 0, 0)

    # A sparse focused result can be one chain rather than a branching tree.
    # Stagger its boxes, not their contents or sizes, to avoid a long thin strip.
    chain = [root]
    while len(chain[-1].children) == 1:
        chain.append(chain[-1].children[0])
    if chain[-1].children or len(chain) < 2:
        return
    width = chain[-1].x + chain[-1].width - root.x
    height = max(node.y + node.height for node in chain) - min(node.y for node in chain)
    if width <= 2 * height:
        return
    span = max(0, math.ceil(width / 2) - chain[-1].height)
    step = math.ceil(span / (len(chain) - 1))
    for depth, node in enumerate(chain):
        node.y = depth * step


def _render_canvas(
    document: AnalysisDocument, tree: TemplateNode, *, enforce_limits: bool
) -> dict[str, Any]:
    _layout_tree(tree, expanded=document.capacity == "expanded")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def visit(node: TemplateNode, parent: TemplateNode | None = None) -> None:
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
            payload["styleAttributes"] = {"border": "invisible"}
            if node.kind not in {"claim", "point"}:
                payload["color"] = "#edf0ed"
        nodes.append(payload)
        if parent is not None:
            edges.append(
                {
                    "id": _edge_id(document.artifact_id, parent.path, node.path),
                    "fromNode": canvas_node_id(document.artifact_id, parent.path),
                    "fromSide": "right",
                    "fromEnd": "none",
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
    if not enforce_limits:
        # Review candidates still require the independent conformance gate before saving.
        return {"nodes": nodes, "edges": edges}
    if len(nodes) > document.managed_node_limit:
        raise ValueError(
            f"Complete-reference Canvas exceeds {document.managed_node_limit} actual managed nodes: {len(nodes)}"
        )
    facts = sum(not claim.container for claim in document.claims) + sum(
        len(claim.points) for claim in document.claims
    )
    if facts > document.fact_node_limit:
        raise ValueError(
            f"Complete-reference Canvas exceeds {document.fact_node_limit} independently rendered fact nodes: {facts}"
        )
    if any(node["height"] > 420 for node in nodes):
        raise ValueError(
            "Complete-reference Canvas has a node taller than 420 px; supply a faithful concise summary"
        )
    width = max(node["x"] + node["width"] for node in nodes) - min(node["x"] for node in nodes)
    height = max(node["y"] + node["height"] for node in nodes) - min(node["y"] for node in nodes)
    if max(width / height, height / width) > 2:
        raise ValueError(
            f"Complete-reference Canvas cannot satisfy the 2:1 geometry limit ({width}x{height}); "
            "required slots have not been merged, hidden, or dropped"
        )
    return {"nodes": nodes, "edges": edges}


def render_complete_analysis(
    document: AnalysisDocument, *, note_stem: str, enforce_limits: bool = True
) -> AnalysisBundle:
    """Render v5 without external reads, writes, or source-verification claims."""
    tree = template_tree(document, note_stem)
    return AnalysisBundle(
        markdown=_render_markdown(document, tree),
        canvas=_render_canvas(document, tree, enforce_limits=enforce_limits),
    )


__all__ = [
    "ROLE_COLORS",
    "SECTION_LABELS",
    "TemplateNode",
    "complete_claim_canvas_text",
    "complete_claim_label",
    "complete_claim_markdown_lines",
    "complete_point_canvas_text",
    "complete_point_label",
    "complete_points",
    "render_complete_analysis",
    "template_relations",
    "template_tree",
]
