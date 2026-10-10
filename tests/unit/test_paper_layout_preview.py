"""Hand-calculated layout checks for a development-only visual proposal."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "dev-guide/scripts/preview-paper-layout.py"


def _module():
    spec = importlib.util.spec_from_file_location("paper_layout_preview", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canvas():
    nodes = [
        {"id": name, "type": "text", "x": x, "y": 0, "width": 120,
         "height": 66, "text": name}
        for name, x in [("R", 0), ("S", 400), ("T", 400),
                        ("A", 900), ("B", 900), ("C", 900), ("D", 900)]
    ]
    edges = [
        {"id": left + right, "fromNode": left, "toNode": right,
         "color": "#e3978d", "fromSide": "right", "toSide": "left",
         "fromEnd": "none", "toEnd": "none",
         "styleAttributes": {"pathfindingMethod": "square"}}
        for left, right in [("R", "S"), ("R", "T"), ("S", "A"),
                            ("S", "B"), ("T", "C"), ("T", "D")]
    ]
    return {"nodes": nodes, "edges": edges, "metadata": {"version": "1.0"}}


def test_hand_calculated_band_placement():
    result = _module().reflow(_canvas())
    # Two 66+40+66 section bands and a 96 px gap occupy 440 px.
    assert {n["id"]: n["y"] for n in result["nodes"]} == {
        "R": 187, "S": 53, "T": 321,
        "A": 0, "B": 106, "C": 268, "D": 374,
    }


def test_only_y_and_direct_branch_color_may_change():
    source = _canvas()
    before = deepcopy(source)
    result = _module().reflow(source)
    assert source == before
    assert result["edges"] == before["edges"]
    assert result["metadata"] == before["metadata"]
    for original, changed in zip(before["nodes"], result["nodes"], strict=True):
        expected = deepcopy(original)
        expected["y"] = changed["y"]
        if expected["id"] in {"S", "T"}:
            expected["color"] = "#e3978d"
        assert changed == expected


def test_section_frames_preserve_original_placement_and_semantic_tree():
    source = _canvas()
    before = deepcopy(source)
    result = _module().section_frames(source)
    assert source == before
    assert result["edges"] == before["edges"]
    assert result["metadata"] == before["metadata"]
    assert len(result["nodes"]) == len(before["nodes"]) + 2
    groups = result["nodes"][:2]
    assert all(group["type"] == "group" for group in groups)
    assert [group["label"] for group in groups] == ["S", "T"]
    for original, candidate in zip(before["nodes"], result["nodes"][2:], strict=True):
        expected = deepcopy(original)
        if original["id"] in {"S", "T"}:
            expected["color"] = "#e3978d"
        assert candidate == expected


def test_separated_frames_keep_local_geometry_and_have_24_px_gap():
    source = _canvas()
    result = _module().section_frames(source, separate=True)
    groups = result["nodes"][:2]
    # Each original band is 66 + 20 + 12 = 98 px tall.
    assert [(g["y"], g["height"]) for g in groups] == [(-20, 98), (102, 98)]
    nodes = {node["id"]: node for node in result["nodes"][2:]}
    assert {key: node["y"] for key, node in nodes.items()} == {
        "R": 61, "S": 0, "T": 122, "A": 0, "B": 0, "C": 122, "D": 122,
    }
    assert result["edges"] == source["edges"]


def test_explicit_width_adjustments_only_affect_named_nodes():
    source = _canvas()
    result = _module().section_frames(source, minimum_widths={"A": 160})
    nodes = {node["id"]: node for node in result["nodes"] if node["type"] == "text"}
    assert nodes["A"]["width"] == 160
    assert all(nodes[n["id"]]["width"] == n["width"] for n in source["nodes"] if n["id"] != "A")
    assert source["nodes"][3]["width"] == 120


def test_unknown_or_shrinking_width_is_rejected():
    for overrides in ({"missing": 160}, {"A": 100}):
        with pytest.raises(ValueError):
            _module().section_frames(_canvas(), minimum_widths=overrides)


@pytest.mark.parametrize("mutation", ["cycle", "two-parents", "dangling"])
def test_ambiguous_graph_is_not_silently_reinterpreted(mutation):
    canvas = _canvas()
    left, right = {
        "cycle": ("D", "R"), "two-parents": ("T", "A"), "dangling": ("R", "absent"),
    }[mutation]
    canvas["edges"].append({"id": mutation, "fromNode": left, "toNode": right})
    with pytest.raises(ValueError):
        _module().reflow(canvas)


def _framed_fixture(gap=24):
    """Manual rectangles; never produced by the layout under test."""
    nodes = [
        {"id": name, "type": "text", "x": x, "y": y, "width": 120,
         "height": 66, "text": name}
        for name, x, y in [("R", 0, 61), ("S", 400, 0), ("A", 900, 0),
                           ("T", 400, 98 + gap), ("B", 900, 98 + gap)]
    ]
    original = {
        "nodes": nodes,
        "edges": [{"id": a + b, "fromNode": a, "toNode": b}
                  for a, b in [("R", "S"), ("R", "T"), ("S", "A"), ("T", "B")]],
        "metadata": {"version": "1.0", "frontmatter": {}},
    }
    candidate = deepcopy(original)
    candidate["nodes"] = [
        {"id": sha256(f"review-section\nR\n{name}".encode()).hexdigest()[:16],
         "type": "group", "x": 380, "y": y, "width": 660, "height": 98, "label": name}
        for name, y in [("S", -20), ("T", 78 + gap)]
    ] + candidate["nodes"]
    return original, candidate


@pytest.mark.parametrize("gap", [24, 36])
def test_manual_section_rectangles_pass_without_mutation(gap):
    original, candidate = _framed_fixture(gap)
    before = deepcopy((original, candidate))
    assert _module().section_frame_findings(candidate, original) == []
    assert (original, candidate) == before


@pytest.mark.parametrize(("mutation", "code"), [
    ("missing", "section-frame-missing"),
    ("wrong-type", "section-frame-type"),
    ("wrong-label", "section-frame-label"),
    ("descendant-outside", "section-frame-incomplete"),
    ("title-space", "section-frame-title-space"),
    ("foreign-full", "section-frame-foreign-node"),
    ("foreign-partial", "section-frame-foreign-node"),
    ("overlap-one", "section-frame-overlap"),
    ("gap-zero", "section-frame-gap"),
    ("gap-23", "section-frame-gap"),
    ("swapped-rectangles", "section-frame-incomplete"),
])
def test_manual_bad_frame_geometry_is_rejected(mutation, code):
    original, candidate = _framed_fixture()
    first, second = candidate["nodes"][:2]
    if mutation == "missing":
        candidate["nodes"].remove(first)
    elif mutation == "wrong-type":
        first.update(type="text", text="S")
    elif mutation == "wrong-label":
        first["label"] = "T"
    elif mutation == "descendant-outside":
        first["width"] = 639  # Right edge 1019, descendant ends at 1020.
    elif mutation == "title-space":
        first.update(y=-19, height=97)
    elif mutation == "foreign-full":
        first["height"] = 220  # Covers both T and B at y122..188.
    elif mutation == "foreign-partial":
        first["height"] = 143  # Bottom 123, intersects the other chapter by 1px.
    elif mutation == "overlap-one":
        first["height"] = 123  # Bottom 103, second starts at 102.
    elif mutation in {"gap-zero", "gap-23"}:
        first["height"] += 24 if mutation == "gap-zero" else 1
    elif mutation == "swapped-rectangles":
        first["y"], second["y"] = second["y"], first["y"]
    assert code in {f["code"] for f in _module().section_frame_findings(candidate, original)}


def test_unowned_user_group_is_not_mistaken_for_a_section_frame():
    original, candidate = _framed_fixture()
    candidate["nodes"].insert(0, {
        "id": "human", "type": "group", "x": -50, "y": -50,
        "width": 2000, "height": 1000, "label": "S",
    })
    assert _module().section_frame_findings(candidate, original) == []
    candidate["nodes"] = [node for node in candidate["nodes"] if node.get("label") != "S" or node["id"] == "human"]
    assert "section-frame-missing" in {
        f["code"] for f in _module().section_frame_findings(candidate, original)
    }


@pytest.mark.parametrize("side", ["left", "right", "bottom"])
def test_one_pixel_short_frame_padding_is_rejected(side):
    original, candidate = _framed_fixture()
    first = candidate["nodes"][0]
    if side == "left":
        first["x"] += 1
    elif side == "right":
        first["width"] -= 1
    else:
        first["height"] -= 1
    assert "section-frame-padding" in {
        f["code"] for f in _module().section_frame_findings(candidate, original)
    }


def test_missing_deeper_descendant_is_reported_from_original_tree():
    original, candidate = _framed_fixture()
    descendant = {"id": "C", "type": "text", "x": 900, "y": 80,
                  "width": 120, "height": 20, "text": "C"}
    original["nodes"].append(descendant)
    original["edges"].append({"id": "AC", "fromNode": "A", "toNode": "C"})
    for document in (original, candidate):
        for node in document["nodes"]:
            if node["id"] in {"T", "B"}:
                node["y"] = 156
    candidate["nodes"][0]["height"] = 132
    candidate["nodes"][1]["y"] = 136
    assert "section-frame-content-missing" in {
        f["code"] for f in _module().section_frame_findings(candidate, original)
    }


def test_bad_frames_fail_before_destination_creation(tmp_path, monkeypatch):
    original, _ = _framed_fixture()
    # Keep content boxes distinct but interleave the two chapter ranges.
    by_id = {node["id"]: node for node in original["nodes"]}
    by_id["A"]["y"], by_id["T"]["y"], by_id["B"]["y"] = 200, 100, 300
    source = tmp_path.resolve() / "input.canvas"
    source.write_text(json.dumps(original))
    destination = tmp_path.resolve() / "not-created"
    monkeypatch.setattr("scholar_workflow.analysis.complete_conformance.geometry_findings", lambda *args: [])
    monkeypatch.setattr("sys.argv", ["preview", str(source), str(destination), "--section-frames"])
    with pytest.raises(SystemExit, match="1"):
        _module().main()
    assert not destination.exists()
