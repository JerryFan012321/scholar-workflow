"""Pure rectangle and fixed square-route geometry shared by v5 layout and checks."""

from itertools import combinations, pairwise
from typing import Any

Point = tuple[float, float]
Segment = tuple[Point, Point]


def square_segments(edge: dict[str, Any], nodes: dict[str, Any]) -> list[Segment]:
    """Advanced Canvas right-center to left-center square route (getZPath)."""
    source, target = nodes[edge["fromNode"]], nodes[edge["toNode"]]
    start = (source["x"] + source["width"], source["y"] + source["height"] / 2)
    end = (target["x"], target["y"] + target["height"] / 2)
    middle = (start[0] + end[0]) / 2
    points = (start, (middle, start[1]), (middle, end[1]), end)
    return [(a, b) for a, b in pairwise(points) if a != b]


def segments_touch(left: Segment, right: Segment) -> bool:
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


def segment_hits_node(segment: Segment, node: dict[str, Any]) -> bool:
    a, b = segment
    x0, x1 = node["x"], node["x"] + node["width"]
    y0, y1 = node["y"], node["y"] + node["height"]
    if a[1] == b[1]:
        return y0 <= a[1] <= y1 and max(min(a[0], b[0]), x0) <= min(max(a[0], b[0]), x1)
    return x0 <= a[0] <= x1 and max(min(a[1], b[1]), y0) <= min(max(a[1], b[1]), y1)


def nodes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["x"] < right["x"] + right["width"]
        and right["x"] < left["x"] + left["width"]
        and left["y"] < right["y"] + right["height"]
        and right["y"] < left["y"] + left["height"]
    )


def square_tree_is_clear(nodes: dict[str, Any], edges: list[dict[str, Any]]) -> bool:
    """Check only generated fixed right-to-left routes, not arbitrary user graphs."""
    if any(nodes_overlap(a, b) for a, b in combinations(nodes.values(), 2)):
        return False
    routes = []
    for edge in edges:
        source_id, target_id = edge["fromNode"], edge["toNode"]
        source, target = nodes[source_id], nodes[target_id]
        if source["x"] + source["width"] >= target["x"]:
            return False
        segments = square_segments(edge, nodes)
        if any(
            segment_hits_node(segment, node)
            for node_id, node in nodes.items()
            if node_id not in {source_id, target_id}
            for segment in segments
        ):
            return False
        routes.append((source_id, segments))
    return not any(
        segments_touch(a, b)
        for (left_source, left), (right_source, right) in combinations(routes, 2)
        if left_source != right_source  # Siblings may share their source trunk.
        for a in left
        for b in right
    )
