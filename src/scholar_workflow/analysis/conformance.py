"""Hard conformance checks for analysis Markdown/Canvas bundles."""
from __future__ import annotations

import re
from itertools import pairwise
from typing import Any

from scholar_workflow.analysis.models import (
    AnalysisDocument,
    AnalysisRole,
    ConformanceFinding,
    ConformanceReport,
)
from scholar_workflow.analysis.rendering import (
    ROLE_LABELS,
    AnalysisBundle,
    claim_canvas_text,
    claim_markdown_lines,
    evidence_text,
    render_analysis,
)
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload

_CLAIM_MARKER = re.compile(
    r'<!--\s*sw-analysis-claim\s+id="(?P<id>[a-z0-9][a-z0-9-]{0,63})"'
    r'\s+role="(?P<role>[a-z]+)"\s*-->'
)
_SEPARATE_EVIDENCE_HEADING = re.compile(
    r"(?im)^#{1,6}\s+(?:evidence|证据)(?:\s*[:：].*)?\s*$"
)
_SEPARATE_EVIDENCE_FIELD = re.compile(r"(?im)^\s*[-*]\s*\*\*(?:evidence|证据)[:：]\*\*")
_CANVAS_NODE_CONTENT_FIELDS = {
    "text": "text",
    "file": "file",
    "link": "url",
    "group": None,
}


def _finding(
    code: str,
    path: str,
    message: str,
    *,
    repairable: bool = True,
) -> ConformanceFinding:
    return ConformanceFinding(
        code=code,
        path=path,
        message=message,
        repairable=repairable,
    )


def _marker_blocks(markdown: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    previous = 0
    for match in _CLAIM_MARKER.finditer(markdown):
        blocks[match.group("id")] = markdown[previous : match.start()]
        previous = match.end()
    return blocks


def _overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return not (
        first["x"] + first["width"] <= second["x"]
        or second["x"] + second["width"] <= first["x"]
        or first["y"] + first["height"] <= second["y"]
        or second["y"] + second["height"] <= first["y"]
    )


def _first_visible_line(text: str) -> str:
    return next(
        (line.strip().lstrip("#").strip() for line in text.splitlines() if line.strip()),
        "",
    )


def _expected_markdown_claim(claim: Any) -> str:
    return "\n".join(
        claim_markdown_lines(claim, workflow=claim.role is AnalysisRole.WORKFLOW)[:-1]
    )


def _expected_canvas_claim(claim: Any, note_stem: str) -> str:
    return claim_canvas_text(claim, note_stem)


def validate_bundle(
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    *,
    note_stem: str,
) -> ConformanceReport:
    """Validate observable structure without judging prose quality or reasoning."""
    findings: list[ConformanceFinding] = []
    markdown = bundle.markdown
    canvas = bundle.canvas
    expected_claim_ids = {claim.claim_id for claim in document.claims}
    expected_bundle = render_analysis(document, note_stem=note_stem)

    expected_title = f"# {document.paper_title}：论文分析"
    if expected_title not in markdown.splitlines():
        findings.append(
            _finding(
                "markdown-paper-title-mismatch",
                "markdown/title",
                "Markdown paper title differs from the validated analysis IR.",
            )
        )

    if _SEPARATE_EVIDENCE_HEADING.search(markdown) or _SEPARATE_EVIDENCE_FIELD.search(markdown):
        findings.append(
            _finding(
                "separate-evidence-section",
                "markdown",
                "Evidence must remain inline with its claim.",
            )
        )

    for role in document.profile.roles:
        heading = f"## {ROLE_LABELS[role]}"
        if heading not in markdown:
            findings.append(
                _finding("missing-role-heading", f"markdown/{role.value}", f"Missing {heading}")
            )

    markdown_blocks = _marker_blocks(markdown)
    markdown_matches = list(_CLAIM_MARKER.finditer(markdown))
    markdown_markers = [match.group("id") for match in markdown_matches]
    if len(markdown_markers) != len(set(markdown_markers)):
        findings.append(
            _finding("duplicate-markdown-claim", "markdown", "Claim markers must be unique.")
        )
    for claim_id in set(markdown_markers) - expected_claim_ids:
        findings.append(
            _finding(
                "unexpected-markdown-claim",
                f"markdown/claims/{claim_id}",
                "Markdown contains a generated claim absent from the analysis IR.",
            )
        )

    if (
        not isinstance(canvas, dict)
        or set(canvas) != {"nodes", "edges"}
        or not isinstance(canvas.get("nodes"), list)
        or not isinstance(canvas.get("edges"), list)
    ):
        findings.append(
            _finding(
                "invalid-canvas-shape",
                "canvas",
                "Canvas must contain only nodes and edges arrays.",
                repairable=False,
            )
        )
        return ConformanceReport(ok=False, findings=findings)

    nodes = canvas["nodes"]
    edges = canvas["edges"]
    try:
        validate_canvas_payload(canvas)
    except CanvasValidationError as exc:
        findings.append(
            _finding(
                "invalid-json-canvas-contract",
                "canvas",
                str(exc),
                repairable=False,
            )
        )
    expected_nodes = {node["id"]: node for node in expected_bundle.canvas["nodes"]}
    expected_edges = {edge["id"]: edge for edge in expected_bundle.canvas["edges"]}
    if len(expected_nodes) > 40:
        findings.append(
            _finding(
                "canvas-node-limit",
                "canvas/nodes",
                "Generated Canvas subgraph exceeds 40 semantic nodes.",
            )
        )

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            findings.append(
                _finding(
                    "invalid-canvas-node",
                    f"canvas/nodes/{index}",
                    "Canvas node must be an object.",
                )
            )
            continue
        node_type = node.get("type")
        if node_type not in _CANVAS_NODE_CONTENT_FIELDS:
            findings.append(
                _finding(
                    "invalid-canvas-node-type",
                    f"canvas/nodes/{index}/type",
                    "Canvas nodes must declare a standard text, file, link, or group type.",
                )
            )
            continue
        content_field = _CANVAS_NODE_CONTENT_FIELDS[node_type]
        if content_field is not None and not isinstance(node.get(content_field), str):
            findings.append(
                _finding(
                    "invalid-canvas-node-content",
                    f"canvas/nodes/{index}/{content_field}",
                    f"Canvas {node_type} nodes require a string {content_field} field.",
                )
            )
        if not all(
            isinstance(node.get(key), int) and not isinstance(node.get(key), bool)
            for key in ("x", "y", "width", "height")
        ):
            findings.append(
                _finding(
                    "invalid-canvas-node-geometry",
                    f"canvas/nodes/{index}",
                    "Canvas node geometry must contain integer x, y, width, and height fields.",
                )
            )
    node_ids = [
        node.get("id") if isinstance(node, dict) and isinstance(node.get("id"), str) else None
        for node in nodes
    ]
    if len(node_ids) != len(set(node_ids)) or any(not node_id for node_id in node_ids):
        findings.append(
            _finding("invalid-canvas-node-ids", "canvas/nodes", "Canvas node IDs must be unique.")
        )
    node_id_set = {node_id for node_id in node_ids if isinstance(node_id, str)}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            findings.append(
                _finding(
                    "invalid-canvas-edge",
                    f"canvas/edges/{index}",
                    "Canvas edge must be an object.",
                )
            )
    edge_ids = [
        edge.get("id") if isinstance(edge, dict) and isinstance(edge.get("id"), str) else None
        for edge in edges
    ]
    if len(edge_ids) != len(set(edge_ids)) or any(not edge_id for edge_id in edge_ids):
        findings.append(
            _finding("invalid-canvas-edge-ids", "canvas/edges", "Canvas edge IDs must be unique.")
        )
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        if edge.get("fromNode") not in node_id_set or edge.get("toNode") not in node_id_set:
            findings.append(
                _finding(
                    "dangling-canvas-edge",
                    f"canvas/edges/{index}",
                    "Canvas edge endpoint does not exist.",
                )
            )

    nodes_by_id = {
        node["id"]: node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    for node_id, expected_node in expected_nodes.items():
        actual = nodes_by_id.get(node_id)
        if actual is None:
            findings.append(
                _finding(
                    "missing-generated-canvas-node",
                    f"canvas/nodes/{node_id}",
                    "Canvas is missing a stable root, role, or claim node.",
                )
            )
            continue
        expected_text = expected_node["text"]
        if "sw-analysis-claim" not in expected_text and actual.get("text") != expected_text:
            findings.append(
                _finding(
                    "canvas-structure-content-mismatch",
                    f"canvas/nodes/{node_id}",
                    "Canvas root or role content differs from the analysis IR.",
                )
            )

    edges_by_id = {
        edge["id"]: edge
        for edge in edges
        if isinstance(edge, dict) and isinstance(edge.get("id"), str)
    }
    for expected_edge in expected_edges.values():
        edge = edges_by_id.get(expected_edge["id"])
        if edge is None or (
            edge.get("fromNode"), edge.get("toNode")
        ) != (expected_edge["fromNode"], expected_edge["toNode"]):
            findings.append(
                _finding(
                    "missing-generated-canvas-edge",
                    f"canvas/edges/{expected_edge['id']}",
                    "Canvas root, role, and claim nodes must remain connected.",
                )
            )

    canvas_claims: dict[str, list[dict[str, Any]]] = {}
    generated_first_lines: list[str] = []
    generated_geometry_nodes: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        path = f"canvas/nodes/{index}"
        if not isinstance(node, dict):
            continue

        text = node.get("text")
        marker = _CLAIM_MARKER.search(text) if isinstance(text, str) else None
        if marker:
            canvas_claims.setdefault(marker.group("id"), []).append(node)
            if marker.group("role") == AnalysisRole.WORKFLOW.value:
                title = _first_visible_line(text).casefold()
                if any(
                    term in title
                    for term in (
                        "对应挑战",
                        "对应贡献",
                        "corresponding challenge",
                        "corresponding contribution",
                    )
                ):
                    findings.append(
                        _finding(
                            "invented-workflow-node",
                            path,
                            "Workflow contains an invented challenge/contribution node.",
                        )
                    )

        # Only IDs produced by the deterministic renderer belong to the managed
        # subgraph. File, link, group, and free-form text nodes remain user-owned.
        if node.get("id") not in expected_nodes:
            continue
        if node.get("type") != "text" or not isinstance(text, str):
            findings.append(
                _finding(
                    "invalid-generated-canvas-node",
                    path,
                    "Generated Canvas nodes must be standard editable text nodes.",
                )
            )
            continue
        if not all(isinstance(node.get(key), int) for key in ("x", "y", "width", "height")):
            findings.append(
                _finding(
                    "invalid-canvas-geometry",
                    path,
                    "Generated Canvas geometry must use integers.",
                )
            )
            continue
        generated_geometry_nodes.append(node)
        if node["width"] < 360 or node["height"] < 140:
            findings.append(
                _finding(
                    "canvas-node-too-small",
                    path,
                    "Generated Canvas text nodes must be at least 360x140 for readable display.",
                )
            )
        generated_first_lines.append(_first_visible_line(text))

    for role in document.profile.roles:
        if ROLE_LABELS[role] not in generated_first_lines:
            findings.append(
                _finding(
                    "missing-canvas-role",
                    f"canvas/{role.value}",
                    f"Canvas is missing the {ROLE_LABELS[role]} role node.",
                )
            )
    for claim_id in set(canvas_claims) - expected_claim_ids:
        findings.append(
            _finding(
                "unexpected-canvas-claim",
                f"canvas/claims/{claim_id}",
                "Canvas contains a generated claim absent from the analysis IR.",
            )
        )

    for left_index, left in enumerate(generated_geometry_nodes):
        for right in generated_geometry_nodes[left_index + 1 :]:
            if _overlap(left, right):
                findings.append(
                    _finding(
                        "overlapping-canvas-nodes",
                        f"canvas/nodes/{left.get('id')}:{right.get('id')}",
                        "Generated Canvas nodes overlap.",
                    )
                )

    for claim in document.claims:
        path = f"claims/{claim.claim_id}"
        evidence = f"〔{evidence_text(claim.evidence)}〕"
        markdown_block = markdown_blocks.get(claim.claim_id)
        matching_markdown = [
            match for match in markdown_matches if match.group("id") == claim.claim_id
        ]
        if len(matching_markdown) != 1 or markdown_block is None:
            findings.append(
                _finding("missing-markdown-claim", f"markdown/{path}", "Claim marker is missing.")
            )
        else:
            if _expected_markdown_claim(claim) not in markdown_block:
                findings.append(
                    _finding(
                        "markdown-claim-content-mismatch",
                        f"markdown/{path}",
                        "Claim title or body differs from the validated analysis IR.",
                    )
                )
            if evidence not in markdown_block or f"^claim-{claim.claim_id}" not in markdown_block:
                findings.append(
                    _finding(
                        "markdown-evidence-not-inline",
                        f"markdown/{path}",
                        "Claim must carry inline evidence and a stable block anchor.",
                    )
                )
            if matching_markdown[0].group("role") != claim.role.value:
                findings.append(
                    _finding(
                        "markdown-claim-role-mismatch",
                        f"markdown/{path}",
                        "Claim marker role differs from the analysis IR.",
                    )
                )

        claim_nodes = canvas_claims.get(claim.claim_id, [])
        if len(claim_nodes) != 1:
            findings.append(
                _finding(
                    "missing-canvas-claim",
                    f"canvas/{path}",
                    "Each claim must have exactly one Canvas node.",
                )
            )
            continue
        node_text = claim_nodes[0]["text"]
        if node_text != _expected_canvas_claim(claim, note_stem):
            findings.append(
                _finding(
                    "canvas-claim-content-mismatch",
                    f"canvas/{path}",
                    "Canvas claim content differs from the validated analysis IR.",
                )
            )
        canvas_marker = _CLAIM_MARKER.search(node_text)
        if canvas_marker is not None and canvas_marker.group("role") != claim.role.value:
            findings.append(
                _finding(
                    "canvas-claim-role-mismatch",
                    f"canvas/{path}",
                    "Claim marker role differs from the analysis IR.",
                )
            )
        if evidence not in node_text:
            findings.append(
                _finding(
                    "canvas-evidence-not-inline",
                    f"canvas/{path}",
                    "Canvas claim must carry the same inline evidence state.",
                )
            )
        backlink = f"[[{note_stem}#^claim-{claim.claim_id}|正文]]"
        if backlink not in node_text:
            findings.append(
                _finding(
                    "missing-evidence-backlink",
                    f"canvas/{path}",
                    "Canvas claim must link back to its Markdown evidence block.",
                )
            )

    workflow = sorted(
        (claim for claim in document.claims if claim.role is AnalysisRole.WORKFLOW),
        key=lambda claim: claim.order or 0,
    )
    edge_pairs = {
        (edge.get("fromNode"), edge.get("toNode"))
        for edge in edges
        if isinstance(edge, dict)
    }
    for first, second in pairwise(workflow):
        first_nodes = canvas_claims.get(first.claim_id, [])
        second_nodes = canvas_claims.get(second.claim_id, [])
        if (
            len(first_nodes) == 1
            and len(second_nodes) == 1
            and (first_nodes[0].get("id"), second_nodes[0].get("id")) not in edge_pairs
        ):
            findings.append(
                _finding(
                    "workflow-edge-missing",
                    f"canvas/workflow/{first.claim_id}/{second.claim_id}",
                    "Consecutive Workflow steps must form one directed flow.",
                )
            )

    return ConformanceReport(
        ok=not any(item.severity == "error" for item in findings),
        findings=findings,
    )
