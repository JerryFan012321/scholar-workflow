"""Hard conformance for the editable four-branch reference-tree projection."""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import Any

from scholar_workflow.analysis.models import (
    AnalysisDocument,
    ConformanceFinding,
    ConformanceReport,
)
from scholar_workflow.analysis.reference_rendering import (
    GROUPS,
    SECTION_LABELS,
    _visible_height,
    reference_canvas_inline_evidence,
    reference_inline_evidence,
    reference_point_canvas_text,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    canvas_node_id,
    point_anchor,
    render_analysis,
)
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload

_CLAIM_ANCHOR = re.compile(
    r"(?m)[ \t]\^claim-(?P<id>[a-z0-9][a-z0-9-]{0,63})[ \t]*$"
)
_HEADING = re.compile(r"(?m)^#{1,6} [^\r\n]*")
_DETACHED_EVIDENCE = re.compile(
    r"(?im)^#{1,6}\s+(?:evidence|证据)(?:\s*[:：].*)?\s*$"
)
_DETACHED_EVIDENCE_FIELD = re.compile(
    r"(?im)^\s*[-*]\s*\*\*(?:evidence|证据)[:：]\*\*"
)


def _finding(code: str, path: str, message: str, *, repairable: bool = True) -> ConformanceFinding:
    return ConformanceFinding(
        code=code,
        path=path,
        message=message,
        repairable=repairable,
    )


def _claim_blocks(
    markdown: str,
) -> tuple[dict[str, str], list[re.Match[str]], dict[str, int]]:
    """Locate each claim by its functional Obsidian block anchor and heading."""
    blocks: dict[str, str] = {}
    positions: dict[str, int] = {}
    headings = list(_HEADING.finditer(markdown))
    heading_starts = [heading.start() for heading in headings]
    anchors = list(_CLAIM_ANCHOR.finditer(markdown))
    for anchor in anchors:
        heading_index = bisect_right(heading_starts, anchor.start()) - 1
        claim_id = anchor.group("id")
        positions[claim_id] = heading_index
        if heading_index >= 0:
            start = headings[heading_index].start()
            end = (
                headings[heading_index + 1].start()
                if heading_index + 1 < len(headings)
                else len(markdown)
            )
            blocks[claim_id] = markdown[start:end]
    return blocks, anchors, positions


def _overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    return not (
        first["x"] + first["width"] <= second["x"]
        or second["x"] + second["width"] <= first["x"]
        or first["y"] + first["height"] <= second["y"]
        or second["y"] + second["height"] <= first["y"]
    )


def validate_reference_tree_bundle(
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    *,
    note_stem: str,
) -> ConformanceReport:
    """Validate exact managed content while retaining human layout and graph items."""
    if document.schema_version != 4 or document.profile.framework != "reference_tree":
        raise ValueError("reference-tree conformance requires IR v4")

    findings: list[ConformanceFinding] = []
    markdown = bundle.markdown
    canvas = bundle.canvas
    expected = render_analysis(document, note_stem=note_stem)
    expected_claims = {claim.claim_id: claim for claim in document.claims}
    language = document.language or "en"

    title = (
        f"# {document.paper_title}: Paper Analysis"
        if document.language == "en"
        else f"# {document.paper_title}：论文分析"
    )
    if title not in markdown.splitlines():
        findings.append(
            _finding(
                "markdown-paper-title-mismatch",
                "markdown/title",
                "The paper-analysis title differs from the versioned IR.",
            )
        )
    if "sw-analysis-claim" in markdown:
        findings.append(
            _finding(
                "visible-machine-marker",
                "markdown",
                "Managed claim identity must not appear as an HTML comment in readable Markdown.",
            )
        )
    if _DETACHED_EVIDENCE.search(markdown) or _DETACHED_EVIDENCE_FIELD.search(markdown):
        findings.append(
            _finding(
                "separate-evidence-section",
                "markdown",
                "Evidence must remain beside its claim or point.",
            )
        )
    for role in document.profile.roles:
        heading = f"## {SECTION_LABELS[role][language]}"
        if heading not in markdown.splitlines():
            findings.append(
                _finding(
                    "missing-role-heading",
                    f"markdown/{role.value}",
                    f"Missing {heading}.",
                )
            )
    # Match the image's complete hierarchy, including currently empty slots.
    for role in document.profile.roles:
        for group_path, en, zh in GROUPS[role]:
            label = en if language == "en" else zh
            prefix = "####" if group_path.count("/") > 1 else "###"
            heading = f"{prefix} {label}"
            if heading not in markdown.splitlines():
                findings.append(
                    _finding(
                        "missing-framework-heading",
                        f"markdown/{group_path}",
                        f"Missing reference-tree heading {heading}.",
                    )
                )
    heading_pattern = re.compile(r"^#{1,6} ")
    heading_lines = [line for line in markdown.splitlines() if heading_pattern.match(line)]
    expected_heading_lines = [
        line for line in expected.markdown.splitlines() if heading_pattern.match(line)
    ]
    if heading_lines != expected_heading_lines:
        findings.append(
            _finding(
                "framework-heading-order-mismatch",
                "markdown/framework",
                "The reference tree must retain its exact heading hierarchy, claim order, and no extra framework headings.",
            )
        )

    blocks, anchors, positions = _claim_blocks(markdown)
    _, _, expected_positions = _claim_blocks(expected.markdown)
    anchor_ids = [anchor.group("id") for anchor in anchors]
    if len(anchor_ids) != len(set(anchor_ids)):
        findings.append(
            _finding("duplicate-markdown-claim", "markdown", "Claim block anchors must be unique.")
        )
    for anchor in anchors:
        if anchor.group("id") not in expected_claims:
            findings.append(
                _finding(
                    "unexpected-markdown-claim",
                    f"markdown/claims/{anchor.group('id')}",
                    "The Markdown contains a claim absent from the IR.",
                )
            )
    for claim in document.claims:
        block = blocks.get(claim.claim_id, "")
        claim_path = f"markdown/claims/{claim.claim_id}"
        if anchor_ids.count(claim.claim_id) != 1:
            findings.append(
                _finding("missing-markdown-claim", claim_path, "Each claim needs one block anchor.")
            )
            continue
        if positions.get(claim.claim_id) != expected_positions.get(claim.claim_id):
            findings.append(
                _finding(
                    "markdown-claim-placement-mismatch",
                    claim_path,
                    "The claim anchor must remain under its IR-defined heading.",
                )
            )
        claim_suffix = (
            f"{claim.body} {reference_inline_evidence(claim.evidence, language, reader=document.reader)} "
            f"^claim-{claim.claim_id}"
        )
        if claim.title not in block or claim_suffix not in block:
            findings.append(
                _finding(
                    "markdown-claim-content-mismatch",
                    claim_path,
                    "Claim title, explanation, evidence, source links, or anchor differs from the IR.",
                )
            )
        for point in claim.points:
            point_line = (
                f"{point.text} {reference_inline_evidence(point.evidence, language, reader=document.reader)} "
                f"^{point_anchor(claim, point)}"
            )
            if point_line not in block or markdown.split().count(
                f"^{point_anchor(claim, point)}"
            ) != 1:
                findings.append(
                    _finding(
                        "markdown-point-attribution-mismatch",
                        f"{claim_path}/points/{point.point_id}",
                        "A point must retain its own evidence, source links, and unique anchor.",
                    )
                )

    if (
        not isinstance(canvas, dict)
        or not {"nodes", "edges"}.issubset(canvas)
        or set(canvas) - {"nodes", "edges", "metadata"}
        or not isinstance(canvas.get("nodes"), list)
        or not isinstance(canvas.get("edges"), list)
    ):
        findings.append(
            _finding(
                "invalid-canvas-shape",
                "canvas",
                "Canvas must contain nodes and edges arrays, with optional Advanced Canvas metadata.",
                repairable=False,
            )
        )
        return ConformanceReport(ok=False, findings=findings)
    try:
        validate_canvas_payload(canvas)
    except CanvasValidationError as exc:
        findings.append(
            _finding("invalid-json-canvas-contract", "canvas", str(exc), repairable=False)
        )
        # Keep collecting independent content and edge findings when the object
        # shape is still safe to inspect (for example, a dangling edge).
        if not all(
            isinstance(node, dict)
            and isinstance(node.get("id"), str)
            and all(isinstance(node.get(field), int) for field in ("x", "y", "width", "height"))
            for node in canvas["nodes"]
        ) or not all(
            isinstance(edge, dict) and isinstance(edge.get("id"), str)
            for edge in canvas["edges"]
        ):
            return ConformanceReport(ok=False, findings=findings)

    expected_nodes = {str(node["id"]): node for node in expected.canvas["nodes"]}
    expected_edges = {str(edge["id"]): edge for edge in expected.canvas["edges"]}
    actual_nodes = {str(node["id"]): node for node in canvas["nodes"]}
    actual_edges = {str(edge["id"]): edge for edge in canvas["edges"]}
    for index, edge in enumerate(canvas["edges"]):
        if edge.get("fromNode") not in actual_nodes or edge.get("toNode") not in actual_nodes:
            findings.append(
                _finding(
                    "dangling-canvas-edge",
                    f"canvas/edges/{index}",
                    "Every Canvas edge endpoint must exist.",
                    repairable=False,
                )
            )
    claim_node_ids = {
        canvas_node_id(document.artifact_id, f"role/{claim.role.value}/{claim.claim_id}")
        for claim in document.claims
    }
    detail_node_ids = {
        canvas_node_id(
            document.artifact_id, f"role/{claim.role.value}/{claim.claim_id}/details"
        )
        for claim in document.claims
        if claim.points
    }
    if len(expected_nodes) > 96:
        findings.append(
            _finding(
                "canvas-node-limit",
                "canvas/nodes",
                "The managed reference tree exceeds 96 total nodes.",
            )
        )
    if len(document.claims) + sum(bool(claim.points) for claim in document.claims) > 40:
        findings.append(
            _finding(
                "canvas-semantic-node-limit",
                "canvas/nodes",
                "The tree exceeds 40 generated claim/detail Canvas nodes.",
            )
        )

    for node_id, expected_node in expected_nodes.items():
        actual = actual_nodes.get(node_id)
        if actual is None:
            findings.append(
                _finding(
                    "missing-generated-canvas-node",
                    f"canvas/nodes/{node_id}",
                    "A root, branch, framework label, claim, or detail node is missing.",
                )
            )
            continue
        if actual.get("type") != "text" or actual.get("text") != expected_node.get("text"):
            code = (
                "canvas-claim-content-mismatch" if node_id in claim_node_ids
                else "canvas-point-content-mismatch" if node_id in detail_node_ids
                else "canvas-structure-content-mismatch"
            )
            findings.append(
                _finding(
                    code,
                    f"canvas/nodes/{node_id}",
                    "Managed node text differs from the IR or original framework.",
                )
            )
        width = actual.get("width")
        height = actual.get("height")
        text = actual.get("text")
        if (
            isinstance(width, int)
            and width > 0
            and isinstance(height, int)
            and isinstance(text, str)
            and height < _visible_height(text, minimum=0, width=width)
        ):
            findings.append(
                _finding(
                    "canvas-text-click-space",
                    f"canvas/nodes/{node_id}",
                    "Managed text nodes need one extra visible line for source-link clicks.",
                )
            )
    for claim in document.claims:
        claim_node_id = canvas_node_id(
            document.artifact_id,
            f"role/{claim.role.value}/{claim.claim_id}",
        )
        claim_text = actual_nodes.get(claim_node_id, {}).get("text")
        claim_backlink = f"#^claim-{claim.claim_id}"
        if isinstance(claim_text, str) and (
            reference_canvas_inline_evidence(claim.evidence, language, reader=document.reader) not in claim_text
            or claim_backlink not in claim_text
        ):
            findings.append(
                _finding(
                    "canvas-evidence-backlink-mismatch",
                    f"canvas/claims/{claim.claim_id}",
                    "Each claim node must carry its inline source evidence and Markdown backlink.",
                )
            )
        for point in claim.points:
            detail_node_id = canvas_node_id(
                document.artifact_id,
                f"role/{claim.role.value}/{claim.claim_id}/details",
            )
            point_text = actual_nodes.get(detail_node_id, {}).get("text")
            point_backlink = f"#^{point_anchor(claim, point)}"
            if isinstance(point_text, str) and (
                reference_canvas_inline_evidence(point.evidence, language, reader=document.reader) not in point_text
                or point_backlink not in point_text
                or point_text.count(
                    reference_point_canvas_text(
                        claim, point, note_stem, language, reader=document.reader
                    )
                ) != 1
            ):
                findings.append(
                    _finding(
                        "canvas-point-attribution-mismatch",
                        f"canvas/claims/{claim.claim_id}/points/{point.point_id}",
                        "Each grouped point must carry its own evidence and Markdown backlink.",
                    )
                )
    for edge_id, expected_edge in expected_edges.items():
        actual = actual_edges.get(edge_id)
        if actual is None or (
            actual.get("fromNode"), actual.get("toNode")
        ) != (expected_edge.get("fromNode"), expected_edge.get("toNode")):
            findings.append(
                _finding(
                    "missing-generated-canvas-edge",
                    f"canvas/edges/{edge_id}",
                    "The reference-tree parent-child connection is missing or changed.",
                )
            )
            continue
        if actual.get("toEnd") != "none" or (
            not isinstance(actual.get("styleAttributes"), dict)
            or actual["styleAttributes"].get("pathfindingMethod") != "square"
        ):
            findings.append(
                _finding(
                    "canvas-edge-routing-mismatch",
                    f"canvas/edges/{edge_id}",
                    "Managed reference-tree lines must remain straight and orthogonal.",
                )
            )

    for index, node in enumerate(canvas["nodes"]):
        text = node.get("text")
        if isinstance(text, str) and "sw-analysis-claim" in text:
            findings.append(
                _finding(
                    "visible-machine-marker",
                    f"canvas/nodes/{index}",
                    "Managed claim identity must not appear as an HTML comment in Canvas text.",
                )
            )

    managed_nodes = [node for node in canvas["nodes"] if node["id"] in expected_nodes]
    for index, left in enumerate(managed_nodes):
        for right in managed_nodes[index + 1 :]:
            if _overlap(left, right):
                findings.append(
                    _finding(
                        "overlapping-canvas-nodes",
                        f"canvas/nodes/{left['id']}:{right['id']}",
                        "Managed Canvas nodes must not overlap.",
                    )
                )

    return ConformanceReport(
        ok=not any(item.severity == "error" for item in findings),
        findings=findings,
    )


__all__ = ["validate_reference_tree_bundle"]
