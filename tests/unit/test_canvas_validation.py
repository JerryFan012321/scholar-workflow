"""Obsidian's Advanced Canvas may add metadata when a standard Canvas is opened."""

from __future__ import annotations

import pytest

from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload


def _canvas() -> dict[str, object]:
    return {
        "nodes": [
            {"id": "a", "type": "text", "x": 0, "y": 0, "width": 100, "height": 60, "text": "A"}
        ],
        "edges": [],
    }


def test_canvas_accepts_and_preserves_advanced_canvas_metadata() -> None:
    canvas = _canvas()
    canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {"tags": ["test"]}}
    assert validate_canvas_payload(canvas) == canvas


def test_canvas_rejects_edge_id_reusing_a_node_id() -> None:
    canvas = _canvas()
    canvas["edges"] = [{"id": "a", "fromNode": "a", "toNode": "a"}]
    with pytest.raises(CanvasValidationError, match="edge identity"):
        validate_canvas_payload(canvas)


@pytest.mark.parametrize(
    "extra",
    [
        {"sw_artifact_id": "analysis:paper:fake"},
        {"metadata": {"version": "1.0-1.0", "frontmatter": "not-a-map"}},
        {"metadata": {"version": "1.0-1.0", "frontmatter": {}, "owner": "forged"}},
    ],
)
def test_canvas_rejects_unrecognized_top_level_identity_or_malformed_metadata(
    extra: dict[str, object],
) -> None:
    with pytest.raises(CanvasValidationError):
        validate_canvas_payload({**_canvas(), **extra})
