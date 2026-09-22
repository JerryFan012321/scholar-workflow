"""Deterministic human-readable Markdown and JSON Canvas projections."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    ProfileKind,
)

ROLE_LABELS = {
    AnalysisRole.TASK: "任务",
    AnalysisRole.INPUT: "输入",
    AnalysisRole.WORKFLOW: "分步流程",
    AnalysisRole.OUTPUT: "输出",
    AnalysisRole.BOUNDARY: "边界",
}
ROLE_COLORS = {
    AnalysisRole.TASK: "1",
    AnalysisRole.INPUT: "2",
    AnalysisRole.WORKFLOW: "3",
    AnalysisRole.OUTPUT: "4",
    AnalysisRole.BOUNDARY: "5",
}


@dataclass(frozen=True)
class AnalysisBundle:
    markdown: str
    canvas: dict[str, list[dict[str, Any]]]


def evidence_text(evidence: Evidence) -> str:
    if evidence.kind is EvidenceKind.AUTHOR_STATED:
        return f"作者明确陈述 · {evidence.anchor}"
    if evidence.kind is EvidenceKind.ANALYSIS_INFERENCE:
        return f"分析推断 · {evidence.detail}"
    if evidence.kind is EvidenceKind.NOT_REPORTED:
        return "论文未报告"
    if evidence.kind is EvidenceKind.UNVERIFIABLE:
        return f"当前正文通道无法核实 · {evidence.detail}"
    return f"不适用 · {evidence.detail}"


def _safe_note_stem(note_stem: str) -> None:
    if not note_stem or len(note_stem) > 240:
        raise ValueError("note_stem must contain 1-240 characters")
    if any(token in note_stem for token in ("/", "\\", "#", "^", "[", "]")):
        raise ValueError("note_stem must be a plain filename stem")


def _node_id(artifact_id: str, path: str) -> str:
    return sha256(f"{artifact_id}\n{path}".encode()).hexdigest()[:16]


def _edge_id(artifact_id: str, source: str, target: str) -> str:
    return sha256(f"edge\n{artifact_id}\n{source}\n{target}".encode()).hexdigest()[:16]


def claim_marker(claim: AnalysisClaim) -> str:
    return f'<!-- sw-analysis-claim id="{claim.claim_id}" role="{claim.role.value}" -->'


def claim_markdown_lines(claim: AnalysisClaim, *, workflow: bool) -> list[str]:
    supported = f"{claim.body} 〔{evidence_text(claim.evidence)}〕 ^claim-{claim.claim_id}"
    if workflow:
        return [f"{claim.order}. **{claim.title}。** {supported}", claim_marker(claim)]
    return [f"### {claim.title}", supported, claim_marker(claim)]


def _render_markdown(document: AnalysisDocument) -> str:
    roles = document.profile.roles
    scope = (
        "全文（任务、输入、分步流程、输出、边界）"
        if document.profile.kind is ProfileKind.WHOLE
        else "局部（" + "、".join(ROLE_LABELS[role] for role in roles) + "）"
    )
    lines = [
        "---",
        "sw_schema: 2",
        "sw_kind: paper-analysis",
        f"sw_catalog_id: {json.dumps(document.artifact_id, ensure_ascii=False)}",
        f"sw_analysis_profile: {document.profile.kind.value}",
        "---",
        "",
        f"# {document.paper_title}：论文分析",
        "",
        f"> 分析范围：{scope}",
    ]
    for role in roles:
        claims = [claim for claim in document.claims if claim.role is role]
        if role is AnalysisRole.WORKFLOW:
            claims.sort(key=lambda claim: claim.order or 0)
        lines.extend(["", f"## {ROLE_LABELS[role]}", ""])
        for index, claim in enumerate(claims):
            if index:
                lines.append("")
            lines.extend(claim_markdown_lines(claim, workflow=role is AnalysisRole.WORKFLOW))
    return "\n".join(lines).rstrip() + "\n"


def claim_canvas_text(claim: AnalysisClaim, note_stem: str) -> str:
    return "\n".join(
        [
            f"### {claim.title}",
            f"{claim.body} 〔{evidence_text(claim.evidence)}〕",
            f"↩ [[{note_stem}#^claim-{claim.claim_id}|正文]]",
            claim_marker(claim),
        ]
    )


def _node_height(text: str, *, minimum: int = 140) -> int:
    visible = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    wrapped_lines = sum(max(1, math.ceil(len(line) / 42)) for line in visible.splitlines())
    return max(minimum, 52 + wrapped_lines * 28)


def _render_canvas(document: AnalysisDocument, note_stem: str) -> dict[str, list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    root_path = "root"
    root_id = _node_id(document.artifact_id, root_path)
    root = {
        "id": root_id,
        "type": "text",
        "x": 0,
        "y": 0,
        "width": 420,
        "height": 160,
        "text": f"# 论文解析树\n[[{note_stem}]]\n{document.paper_title}",
    }
    nodes.append(root)

    band_y = 0
    for role in document.profile.roles:
        role_path = f"role/{role.value}"
        role_id = _node_id(document.artifact_id, role_path)
        role_node = {
            "id": role_id,
            "type": "text",
            "x": 520,
            "y": band_y,
            "width": 380,
            "height": 140,
            "color": ROLE_COLORS[role],
            "text": f"## {ROLE_LABELS[role]}",
        }
        nodes.append(role_node)
        edges.append(
            {
                "id": _edge_id(document.artifact_id, root_path, role_path),
                "fromNode": root_id,
                "toNode": role_id,
                "fromSide": "right",
                "toSide": "left",
                "toEnd": "arrow",
            }
        )

        claims = [claim for claim in document.claims if claim.role is role]
        if role is AnalysisRole.WORKFLOW:
            claims.sort(key=lambda claim: claim.order or 0)
        previous_id = role_id
        previous_path = role_path
        max_height = 140
        next_vertical_y = band_y
        for index, claim in enumerate(claims):
            claim_path = f"{role_path}/{claim.claim_id}"
            claim_id = _node_id(document.artifact_id, claim_path)
            text = claim_canvas_text(claim, note_stem)
            height = _node_height(text, minimum=160)
            if role is AnalysisRole.WORKFLOW:
                x = 1000 + index * 500
                y = band_y
            else:
                x = 1000
                y = next_vertical_y
            nodes.append(
                {
                    "id": claim_id,
                    "type": "text",
                    "x": x,
                    "y": y,
                    "width": 420,
                    "height": height,
                    "color": ROLE_COLORS[role],
                    "text": text,
                }
            )
            edges.append(
                {
                    "id": _edge_id(document.artifact_id, previous_path, claim_path),
                    "fromNode": previous_id,
                    "toNode": claim_id,
                    "fromSide": "right",
                    "toSide": "left",
                    "toEnd": "arrow",
                }
            )
            if role is AnalysisRole.WORKFLOW:
                previous_id = claim_id
                previous_path = claim_path
            else:
                next_vertical_y = y + height + 60
            max_height = max(max_height, y - band_y + height)
        band_y += max_height + 100

    root["y"] = max(0, (band_y - root["height"]) // 2)
    return {"nodes": nodes, "edges": edges}


def render_analysis(document: AnalysisDocument, *, note_stem: str) -> AnalysisBundle:
    """Render one validated IR without reading or writing external stores."""
    _safe_note_stem(note_stem)
    return AnalysisBundle(
        markdown=_render_markdown(document),
        canvas=_render_canvas(document, note_stem),
    )
