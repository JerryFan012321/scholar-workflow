"""Shared fail-closed validation for JSON Canvas and a narrow Advanced Canvas envelope."""

from __future__ import annotations

from typing import Any


class CanvasValidationError(ValueError):
    """A payload violates the minimal cross-system JSON Canvas contract."""


def validate_canvas_payload(
    value: object,
) -> dict[str, Any]:
    """Validate structure shared by Knowledge, Hub, and Project boundaries."""
    if (
        not isinstance(value, dict)
        or not {"nodes", "edges"}.issubset(value)
        or set(value) - {"nodes", "edges", "metadata"}
    ):
        raise CanvasValidationError(
            "Canvas content must contain nodes and edges, with optional Advanced Canvas metadata"
        )
    metadata = value.get("metadata") if "metadata" in value else None
    if "metadata" in value and (
        not isinstance(metadata, dict)
        or set(metadata) != {"version", "frontmatter"}
        or not isinstance(metadata["version"], str)
        or not metadata["version"].strip()
        or len(metadata["version"]) > 64
        or not isinstance(metadata["frontmatter"], dict)
        or any(not isinstance(key, str) for key in metadata["frontmatter"])
    ):
        raise CanvasValidationError("Advanced Canvas metadata is invalid")
    raw_nodes = value["nodes"]
    raw_edges = value["edges"]
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise CanvasValidationError("Canvas nodes and edges must be lists")

    nodes: list[dict[str, object]] = []
    node_ids: set[str] = set()
    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise CanvasValidationError("Canvas contains an invalid node")
        node_id = raw_node.get("id")
        if (
            not isinstance(node_id, str)
            or not node_id.strip()
            or node_id in node_ids
        ):
            raise CanvasValidationError("Canvas node identity is invalid")
        node_type = raw_node.get("type")
        if node_type not in {"text", "file", "link", "group"}:
            raise CanvasValidationError("Canvas node type is invalid")
        for field in ("x", "y", "width", "height"):
            coordinate = raw_node.get(field)
            if not isinstance(coordinate, int) or isinstance(coordinate, bool):
                raise CanvasValidationError(f"Canvas node {field} must be an integer")
        if raw_node["width"] <= 0 or raw_node["height"] <= 0:
            raise CanvasValidationError(
                "Canvas node width and height must be positive"
            )
        required_field = {
            "text": "text",
            "file": "file",
            "link": "url",
        }.get(node_type)
        if required_field is not None:
            required_value = raw_node.get(required_field)
            if not isinstance(required_value, str) or (
                required_field != "text" and not required_value.strip()
            ):
                raise CanvasValidationError(
                    f"Canvas {node_type} node requires a valid {required_field}"
                )
        node_ids.add(node_id)
        nodes.append(raw_node)

    edges: list[dict[str, object]] = []
    edge_ids: set[str] = set()
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, dict):
            raise CanvasValidationError("Canvas contains an invalid edge")
        edge_id = raw_edge.get("id")
        from_node = raw_edge.get("fromNode")
        to_node = raw_edge.get("toNode")
        if isinstance(edge_id, str) and edge_id in node_ids:
            raise CanvasValidationError("Canvas edge identity collides with a node ID")
        if (
            not isinstance(edge_id, str)
            or not edge_id.strip()
            or edge_id in edge_ids
            or not isinstance(from_node, str)
            or from_node not in node_ids
            or not isinstance(to_node, str)
            or to_node not in node_ids
        ):
            raise CanvasValidationError("Canvas edge identity is invalid")
        edge_ids.add(edge_id)
        edges.append(raw_edge)
    result: dict[str, Any] = {"nodes": nodes, "edges": edges}
    if metadata is not None:
        result["metadata"] = metadata
    return result


__all__ = ["CanvasValidationError", "validate_canvas_payload"]
