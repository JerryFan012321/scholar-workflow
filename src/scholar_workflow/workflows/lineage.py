"""Literature lineage graph builder (stub — Phase 5)."""
from __future__ import annotations
from scholar_workflow.models import Resource


def build_graph(resources: list[Resource], topic: str = "") -> dict:
    """
    Build a literature-graph.json structure.
    Evidence extraction and edge classification are implemented in Phase 5.
    """
    nodes = [
        {
            "resource_id": r.resource_id,
            "title": r.title,
            "year": r.year,
            "venue": None,
            "is_milestone": False,
        }
        for r in resources
    ]
    return {
        "topic": topic,
        "nodes": nodes,
        "edges": [],
    }
