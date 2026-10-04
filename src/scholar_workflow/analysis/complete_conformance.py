"""Fail-closed content, topology and geometric checks for the v5 reference tree.

These checks verify the projection of supplied evidence, not its scientific truth
or whether quoted text actually occurs in an external source.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from itertools import combinations, pairwise
from typing import Any

from scholar_workflow.analysis.models import AnalysisDocument, ConformanceFinding, ConformanceReport
from scholar_workflow.analysis.reference_rendering import (
    _visible_height,
    reference_source_quote_lines,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    canvas_node_id,
    point_anchor,
    render_analysis,
)
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload

_HEADING = re.compile(r"(?m)^#{1,6} [^\r\n]*$")
_DETACHED = re.compile(r"(?im)^#{1,6}\s+(?:evidence|证据)(?:\s*[:：].*)?\s*$")
_DETACHED_FIELD = re.compile(r"(?im)^\s*[-*]\s*\*\*(?:evidence|证据)[:：]\*\*")
Point = tuple[float, float]
Segment = tuple[Point, Point]


def _finding(code: str, path: str, message: str) -> ConformanceFinding:
    return ConformanceFinding(code=code, path=path, message=message)


def square_segments(edge: dict[str, Any], nodes: dict[str, Any]) -> list[Segment]:
    """Advanced Canvas right-to-left, arrowless square route (getZPath).

    Endpoint side centers and median X match the installed plugin's route; this
    intentionally does not infer routes for other styles/sides.
    """
    source, target = nodes[edge["fromNode"]], nodes[edge["toNode"]]
    start = (source["x"] + source["width"], source["y"] + source["height"] / 2)
    end = (target["x"], target["y"] + target["height"] / 2)
    middle = (start[0] + end[0]) / 2
    points = (start, (middle, start[1]), (middle, end[1]), end)
    return [(a, b) for a, b in pairwise(points) if a != b]


def _human_segments(edge: dict[str, Any], nodes: dict[str, Any]) -> list[Segment] | None:
    """Prove only forward square routes or collinear native connections.

    Other routes may detour beyond their endpoint boxes. Endpoint ownership or
    a disjoint endpoint bounding box alone cannot prove non-interference.
    """
    if (
        edge.get("fromFloating", False) is not False
        or edge.get("toFloating", False) is not False
        or edge.get("fromEnd", "none") != "none"
        or edge.get("toEnd", "arrow") != "none"
    ):
        return None
    source, target = nodes[edge["fromNode"]], nodes[edge["toNode"]]
    sides = (edge.get("fromSide"), edge.get("toSide"))
    centers = {
        "right": lambda n: (n["x"] + n["width"], n["y"] + n["height"] / 2),
        "left": lambda n: (n["x"], n["y"] + n["height"] / 2),
        "bottom": lambda n: (n["x"] + n["width"] / 2, n["y"] + n["height"]),
        "top": lambda n: (n["x"] + n["width"] / 2, n["y"]),
    }
    axis_direction = {
        ("right", "left"): (0, 1), ("left", "right"): (0, -1),
        ("bottom", "top"): (1, 1), ("top", "bottom"): (1, -1),
    }
    if sides not in axis_direction:
        return None
    axis, direction = axis_direction[sides]
    start, end = centers[sides[0]](source), centers[sides[1]](target)
    if direction * (end[axis] - start[axis]) <= 0:
        return None
    style = edge.get("styleAttributes")
    if style is not None and not isinstance(style, dict):
        return None
    method = (style or {}).get("pathfindingMethod")
    if method not in (None, "direct", "square"):
        return None
    if start[1 - axis] == end[1 - axis]:
        if method is None:
            # Native Canvas places Bezier controls along the two endpoint sides,
            # with clamp(distance / 2, 70, 150) offset. The collinear curve stays
            # within their convex hull, which may exceed the endpoint interval.
            distance = direction * (end[axis] - start[axis])
            offset = max(70, min(150, distance / 2))
            coordinates = (
                start[axis], end[axis],
                start[axis] + direction * offset, end[axis] - direction * offset,
            )
            first, second = list(start), list(end)
            first[axis], second[axis] = min(coordinates), max(coordinates)
            return [(tuple(first), tuple(second))]
        return [(start, end)]
    if method != "square":
        return None
    middle = (start[axis] + end[axis]) / 2
    first, second = list(start), list(end)
    first[axis] = second[axis] = middle
    points = (start, tuple(first), tuple(second), end)
    return [(a, b) for a, b in pairwise(points) if a != b]


def _segments_touch(left: Segment, right: Segment) -> bool:
    a, b = left
    c, d = right
    horizontal_left, horizontal_right = a[1] == b[1], c[1] == d[1]
    if horizontal_left == horizontal_right:
        fixed, moving = (1, 0) if horizontal_left else (0, 1)
        return a[fixed] == c[fixed] and max(
            min(a[moving], b[moving]), min(c[moving], d[moving])
        ) <= min(max(a[moving], b[moving]), max(c[moving], d[moving]))
    if not horizontal_left:
        a, b, c, d = c, d, a, b
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(c[1], d[1]) <= a[1] <= max(c[1], d[1])


def _segment_hits_node(segment: Segment, node: dict[str, Any]) -> bool:
    a, b = segment
    x0, x1 = node["x"], node["x"] + node["width"]
    y0, y1 = node["y"], node["y"] + node["height"]
    if a[1] == b[1]:
        return y0 <= a[1] <= y1 and max(min(a[0], b[0]), x0) <= min(max(a[0], b[0]), x1)
    return x0 <= a[0] <= x1 and max(min(a[1], b[1]), y0) <= min(max(a[1], b[1]), y1)


def geometry_findings(canvas: dict[str, Any], expected: dict[str, Any]) -> list[ConformanceFinding]:
    """Check actual managed geometry, including preserved manual layout."""
    findings: list[ConformanceFinding] = []
    expected_ids = {node["id"] for node in expected["nodes"]}
    nodes = {node["id"]: node for node in canvas["nodes"]}
    managed = {key: value for key, value in nodes.items() if key in expected_ids}
    edges = {edge["id"]: edge for edge in canvas["edges"]}
    if not managed:
        return findings
    for node in managed.values():
        if node["height"] > 420:
            findings.append(
                _finding(
                    "canvas-node-height-limit",
                    f"canvas/nodes/{node['id']}",
                    "A managed node exceeds 420 px.",
                )
            )
        text = node.get("text")
        if isinstance(text, str) and node["height"] < _visible_height(
            text, minimum=0, width=node["width"]
        ):
            findings.append(
                _finding(
                    "canvas-text-click-space",
                    f"canvas/nodes/{node['id']}",
                    "Text and source/backlinks require one extra visible line.",
                )
            )
    # Human nodes remain untouched, but cannot hide managed prose or its links.
    # Groups are visual containers, not opaque content boxes.
    visible_nodes = {
        node_id: node for node_id, node in nodes.items() if node.get("type") != "group"
    }
    for left, right in combinations(visible_nodes.values(), 2):
        if left["id"] not in managed and right["id"] not in managed:
            continue
        if (
            left["x"] < right["x"] + right["width"]
            and right["x"] < left["x"] + left["width"]
            and left["y"] < right["y"] + right["height"]
            and right["y"] < left["y"] + left["height"]
        ):
            findings.append(
                _finding(
                    "overlapping-canvas-nodes",
                    f"canvas/nodes/{left['id']}:{right['id']}",
                    "A managed node overlaps another visible node.",
                )
            )
    width = max(n["x"] + n["width"] for n in managed.values()) - min(
        n["x"] for n in managed.values()
    )
    height = max(n["y"] + n["height"] for n in managed.values()) - min(
        n["y"] for n in managed.values()
    )
    if max(width / height, height / width) > 2:
        findings.append(
            _finding(
                "canvas-aspect-limit",
                "canvas/geometry",
                f"Managed bounds {width}×{height} exceed the approved 2:1 aspect limit.",
            )
        )

    children: dict[str, list[str]] = defaultdict(list)
    targets: set[str] = set()
    for edge in expected["edges"]:
        children[edge["fromNode"]].append(edge["toNode"])
        targets.add(edge["toNode"])
    queue = deque((root, 0) for root in expected_ids - targets)
    levels: dict[int, set[int]] = defaultdict(set)
    while queue:
        node_id, depth = queue.popleft()
        if node_id in managed:
            levels[depth].add(managed[node_id]["x"])
        queue.extend((child, depth + 1) for child in children[node_id])
    for depth, positions in levels.items():
        if len(positions) > 1:
            findings.append(
                _finding(
                    "canvas-level-alignment",
                    f"canvas/geometry/depth-{depth}",
                    "Nodes at the same hierarchy depth must share a left edge.",
                )
            )

    routes: list[tuple[dict[str, Any], list[Segment], bool]] = []
    expected_edge_ids = {edge["id"] for edge in expected["edges"]}
    for edge in edges.values():
        source_id, target_id = edge.get("fromNode"), edge.get("toNode")
        if source_id not in nodes or target_id not in nodes:
            continue
        involves_managed = source_id in managed or target_id in managed
        if not involves_managed:
            segments = _human_segments(edge, nodes)
            if segments is None:
                findings.append(
                    _finding(
                        "canvas-edge-routing-unverifiable",
                        f"canvas/edges/{edge['id']}",
                        "A preserved human edge needs a provable route before non-interference can be established.",
                    )
                )
                continue
            routes.append((edge, segments, False))
            for node_id, node in visible_nodes.items():
                if node_id in managed and any(
                    _segment_hits_node(segment, node) for segment in segments
                ):
                    findings.append(
                        _finding(
                            "canvas-edge-through-node",
                            f"canvas/edges/{edge['id']}",
                            f"A human edge passes through managed node {node_id}.",
                        )
                    )
            continue
        if (
            edge["id"] not in expected_edge_ids
            and source_id in managed and target_id in managed
        ):
            findings.append(
                _finding(
                    "canvas-unexpected-edge",
                    f"canvas/edges/{edge['id']}",
                    "An extra edge changes the managed framework's parent-child topology.",
                )
            )
        if (
            edge.get("fromSide") != "right" or edge.get("toSide") != "left"
            or edge.get("fromFloating", False) is not False
            or edge.get("toFloating", False) is not False
            or edge.get("fromEnd", "none") != "none"
            or edge.get("toEnd", "arrow") != "none"
            or not isinstance(edge.get("styleAttributes"), dict)
            or edge["styleAttributes"].get("pathfindingMethod") != "square"
        ):
            findings.append(
                _finding(
                    "canvas-edge-routing-unverifiable",
                    f"canvas/edges/{edge['id']}",
                    "An edge involving managed content needs a provable square, right-to-left, arrowless route.",
                )
            )
            continue
        source, target = nodes[source_id], nodes[target_id]
        if source["x"] + source["width"] >= target["x"]:
            findings.append(
                _finding(
                    "canvas-edge-direction",
                    f"canvas/edges/{edge['id']}",
                    "Tree edges must travel right into a separate child column.",
                )
            )
        segments = square_segments(edge, nodes)
        routes.append((edge, segments, True))
        for node_id, node in visible_nodes.items():
            if node_id not in {edge["fromNode"], edge["toNode"]} and any(
                _segment_hits_node(segment, node) for segment in segments
            ):
                findings.append(
                    _finding(
                        "canvas-edge-through-node",
                        f"canvas/edges/{edge['id']}",
                        f"Tree edge passes through unrelated node {node_id}.",
                    )
                )
    for (
        (left_edge, left, left_managed), (right_edge, right, right_managed)
    ) in combinations(routes, 2):
        if not left_managed and not right_managed:
            continue  # Do not govern internal topology of an independent human graph.
        if left_edge["fromNode"] == right_edge["fromNode"]:
            continue  # Siblings may share the same trunk.
        if any(_segments_touch(a, b) for a in left for b in right):
            findings.append(
                _finding(
                    "canvas-crossing-edges",
                    f"canvas/edges/{left_edge['id']}:{right_edge['id']}",
                    "Different tree branches cross or share a segment.",
                )
            )
    return findings


def validate_complete_bundle(
    document: AnalysisDocument, bundle: AnalysisBundle, *, note_stem: str
) -> ConformanceReport:
    """Validate all observable managed output; unrelated human graph items survive."""
    if document.schema_version != 5 or document.profile.framework != "reference_tree_v5":
        raise ValueError("complete reference-tree conformance requires IR v5")
    from scholar_workflow.analysis.complete_reference import (
        complete_claim_markdown_lines,
        template_tree,
    )

    findings: list[ConformanceFinding] = []
    expected = render_analysis(document, note_stem=note_stem)
    markdown, canvas = bundle.markdown, bundle.canvas
    if "sw-analysis-claim" in markdown:
        findings.append(
            _finding(
                "visible-machine-marker",
                "markdown",
                "Readable Markdown cannot contain machine claim comments.",
            )
        )
    if _DETACHED.search(markdown) or _DETACHED_FIELD.search(markdown):
        findings.append(
            _finding(
                "separate-evidence-section",
                "markdown",
                "Evidence must remain inline with its claim or point.",
            )
        )
    if _HEADING.findall(markdown) != _HEADING.findall(expected.markdown):
        findings.append(
            _finding(
                "framework-heading-order-mismatch",
                "markdown/framework",
                "All five branches and nested template headings must retain their language and order.",
            )
        )
    # Extra ordinary human prose is allowed; managed lines must stay in order,
    # under the same heading, and preserve each point's precise attribution.
    actual_lines = [line for line in markdown.splitlines() if line.strip()]
    cursor = 0
    for line in (line for line in expected.markdown.splitlines() if line.strip()):
        try:
            cursor = actual_lines.index(line, cursor) + 1
        except ValueError:
            findings.append(
                _finding(
                    "markdown-managed-content-mismatch",
                    "markdown",
                    "Managed prose, quotes, links or block anchors are missing, modified or misplaced.",
                )
            )
            break
    claim_labels: dict[str, str] = {}
    pending = [template_tree(document, note_stem)]
    while pending:
        node = pending.pop()
        if node.claim is not None and node.point is None and node.kind != "empty-slot":
            claim_labels[node.claim.claim_id] = node.label
        pending.extend(node.children)
    expected_anchors: set[str] = set()
    for claim in document.claims:
        lines = complete_claim_markdown_lines(
            claim,
            document.language or "en",
            reader=document.reader,
            markdown_quotes=True,
            label=claim_labels[claim.claim_id],
        )
        for line in lines:
            if not line.strip() or line.startswith("#"):
                continue
            if "\n" + line + "\n" not in "\n" + markdown + "\n":
                findings.append(
                    _finding(
                        "markdown-claim-content-mismatch",
                        f"markdown/claims/{claim.claim_id}",
                        "Claim or point content, attribution, original excerpt or source link differs from IR.",
                    )
                )
                break
        anchors = [] if claim.container else [f"claim-{claim.claim_id}"]
        anchors += [point_anchor(claim, point) for point in claim.points]
        expected_anchors.update(anchors)
        for anchor in anchors:
            if len(re.findall(r"(?m)\^" + re.escape(anchor) + r"[ \t]*$", markdown)) != 1:
                findings.append(
                    _finding(
                        "markdown-record-anchor",
                        f"markdown/claims/{claim.claim_id}",
                        "Each factual/availability record needs one precise Markdown block anchor.",
                    )
                )
        records = [] if claim.container else [(f"claim-{claim.claim_id}", claim.evidence)]
        records += [(point_anchor(claim, point), point.evidence) for point in claim.points]
        for anchor, evidence in records:
            statement = next(line for line in lines if line.endswith(f"^{anchor}"))
            quotes = reference_source_quote_lines(
                evidence, document.language or "en", reader=document.reader
            )
            if quotes and statement + "\n" + "\n".join(quotes) not in markdown:
                findings.append(
                    _finding(
                        "markdown-source-quote-placement",
                        f"markdown/claims/{claim.claim_id}",
                        "The exact source excerpt must immediately follow its own statement and source link.",
                    )
                )
    actual_anchors = re.findall(r"(?m)(?<!\S)\^((?:claim|point)-[a-z0-9-]+)[ \t]*$", markdown)
    if set(actual_anchors) - expected_anchors:
        findings.append(
            _finding(
                "unexpected-markdown-record",
                "markdown",
                "A managed claim/point anchor is absent from the supplied IR.",
            )
        )

    try:
        validate_canvas_payload(canvas)
    except CanvasValidationError as exc:
        findings.append(_finding("invalid-json-canvas-contract", "canvas", str(exc)))
        return ConformanceReport(ok=False, findings=findings)
    expected_nodes = {node["id"]: node for node in expected.canvas["nodes"]}
    expected_edges = {edge["id"]: edge for edge in expected.canvas["edges"]}
    nodes = {node["id"]: node for node in canvas["nodes"]}
    edges = {edge["id"]: edge for edge in canvas["edges"]}
    if len(expected_nodes) > 96:
        findings.append(
            _finding(
                "canvas-node-limit",
                "canvas/nodes",
                "The complete tree exceeds 96 actual managed nodes.",
            )
        )
    record_paths = {}
    for claim in document.claims:
        base = f"role/{claim.role.value}/{claim.claim_id}"
        record_paths[canvas_node_id(document.artifact_id, base)] = f"canvas/claims/{claim.claim_id}"
        for point in claim.points:
            record_paths[canvas_node_id(document.artifact_id, f"{base}/point/{point.point_id}")] = (
                f"canvas/claims/{claim.claim_id}/points/{point.point_id}"
            )
    for node_id, expected_node in expected_nodes.items():
        node = nodes.get(node_id)
        path = record_paths.get(node_id, f"canvas/nodes/{node_id}")
        if node is None:
            findings.append(
                _finding(
                    "missing-generated-canvas-node",
                    path,
                    "A required framework slot or independent record is missing.",
                )
            )
        elif node.get("type") != "text" or node.get("text") != expected_node["text"]:
            findings.append(
                _finding(
                    "canvas-managed-content-mismatch",
                    path,
                    "Framework label, point-local attribution/source/backlink or text differs from IR; Canvas cannot add quotations.",
                )
            )
    for edge_id, expected_edge in expected_edges.items():
        edge = edges.get(edge_id)
        if edge is None or (edge.get("fromNode"), edge.get("toNode")) != (
            expected_edge["fromNode"],
            expected_edge["toNode"],
        ):
            findings.append(
                _finding(
                    "missing-generated-canvas-edge",
                    f"canvas/edges/{edge_id}",
                    "Required parent-child edge is missing or belongs to a different instance.",
                )
            )
        elif (
            any(
                edge.get(key) != value
                for key, value in {
                    "fromSide": "right",
                    "toSide": "left",
                    "fromEnd": "none",
                    "toEnd": "none",
                }.items()
            )
            or not isinstance(edge.get("styleAttributes"), dict)
            or edge["styleAttributes"].get("pathfindingMethod") != "square"
        ):
            findings.append(
                _finding(
                    "canvas-edge-routing-mismatch",
                    f"canvas/edges/{edge_id}",
                    "Connections must remain square-routed, straight and arrowless on both ends.",
                )
            )
    forbidden_ids = {
        canvas_node_id(document.artifact_id, f"role/{claim.role.value}/{claim.claim_id}/{suffix}")
        for claim in document.claims
        for suffix in ("details", "corresponding-challenge", "corresponding-contribution")
    }
    for node in canvas["nodes"]:
        if node["id"] in forbidden_ids:
            findings.append(
                _finding(
                    "canvas-forbidden-managed-axis",
                    f"canvas/nodes/{node['id']}",
                    "Grouped detail replacements and corresponding-challenge/contribution axes are not part of the template.",
                )
            )
        if isinstance(node.get("text"), str) and "sw-analysis-claim" in node["text"]:
            findings.append(
                _finding(
                    "visible-machine-marker",
                    f"canvas/nodes/{node['id']}",
                    "Canvas cannot contain machine claim comments.",
                )
            )
    findings.extend(geometry_findings(canvas, expected.canvas))
    return ConformanceReport(ok=not findings, findings=findings)


__all__ = ["geometry_findings", "square_segments", "validate_complete_bundle"]
