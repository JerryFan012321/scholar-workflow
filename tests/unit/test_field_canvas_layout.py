"""Synthetic exact-geometry checks; no installed-product or scientific acceptance."""

from __future__ import annotations

import builtins
import copy
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "skills/build-literature-tree/scripts/layout_canvas.py"
SPEC = importlib.util.spec_from_file_location("field_canvas_layout", SCRIPT)
layout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layout)


def _paper(key, text=None):
    return {"id": key, "text": text or f"**{key}**\n\nPrepared explanation.\n\n[[papers/{key}|Analysis]]"}


def _radial(view, counts=(2, 1, 3)):
    branches = []
    for index, count in enumerate(counts):
        papers = [_paper(f"paper-{index}-{j}") for j in range(count)]
        if view == "technical":
            children = papers
        else:
            children = [dict(_paper(f"solution-{index}-{j}"), children=[paper])
                        for j, paper in enumerate(papers)]
        branches.append(dict(_paper(f"branch-{index}"), children=children))
    return {"schema_version": 1, "view": view,
            "root": {"id": "root", "text": "Prepared topic and scope"}, "branches": branches}


def _lit_node(key, role, children=()):
    return {"id": key, "text": f"[[papers/{key}|{key}]]", "description": f"{key}: prepared improvement, evidence and limitation.",
            "role": role, "children": list(children)}


def _literature():
    return {"schema_version": 1, "view": "literature", "spine": [
        _lit_node("milestone-one", "milestone", [
            _lit_node("pipeline-one", "pipeline", [
                _lit_node("module-one", "local", [_lit_node("follow-up-one", "local")]),
                _lit_node("module-two", "local"),
            ]),
            _lit_node("pipeline-two", "pipeline", [_lit_node("module-three", "local")]),
        ]),
        _lit_node("milestone-two", "milestone", [_lit_node("pipeline-three", "pipeline")]),
        _lit_node("milestone-three", "milestone"),
    ]}


def _semantic(canvas):
    return [node for node in canvas["nodes"]
            if "junction" not in node.get("styleAttributes", {}).values()]


@pytest.mark.parametrize("view", ["technical", "challenge"])
@pytest.mark.parametrize("counts", [(1,), (1, 1), (2, 1, 3), (7, 2, 5, 1, 4, 3)])
def test_radial_small_large_and_unequal_branches_keep_every_leaf(view, counts):
    document = _radial(view, counts)
    before = copy.deepcopy(document)
    canvas = layout.render(document)
    assert document == before
    assert layout.validate_canvas(canvas) == []
    nodes = _semantic(canvas)
    leaves = [node for node in nodes if node["styleAttributes"]["swMind"] == "detail"]
    assert len(leaves) == sum(counts)
    assert len(nodes) == 1 + len(counts) + sum(counts) * (2 if view == "challenge" else 1)
    for index, count in enumerate(counts):
        for j in range(count):
            assert sum(f"[[papers/paper-{index}-{j}|Analysis]]" in node["text"] for node in leaves) == 1
    if len(counts) > 1:
        assert any(node["x"] < -160 for node in nodes)
        assert any(node["x"] > 160 for node in nodes)
    peers = [node for node in nodes if node["styleAttributes"]["swMind"] == "branch"]
    assert len({node["x"] for node in peers}) <= (4 if view == "challenge" else 2)
    for node in nodes:
        assert node["height"] >= layout._size(node["text"], node["width"])[1]


def test_literature_has_distinct_descriptions_and_horizontal_spine():
    document = _literature()
    before = copy.deepcopy(document)
    canvas = layout.render(document)
    assert document == before
    assert layout.validate_canvas(canvas) == []
    nodes = _semantic(canvas)
    descriptions = [node for node in nodes if node["styleAttributes"]["swLit"] == "desc"]
    titles = [node for node in nodes if node not in descriptions]
    assert len(descriptions) == len(titles) == 10
    milestones = [node for node in titles if node["styleAttributes"]["swLit"] == "milestone"]
    assert {node["y"] + node["height"] // 2 for node in milestones} == {0}
    assert [node["x"] for node in milestones] == sorted(node["x"] for node in milestones)
    for title in titles:
        matching = [node for node in descriptions if node["x"] == title["x"]
                    and node["y"] == title["y"] + title["height"] + layout._DESC_GAP]
        assert len(matching) == 1


@pytest.mark.parametrize("role", ["milestone", "pipeline", "local"])
def test_timeline_long_title_reserves_real_font_lines_and_click_space(role):
    # 15 full-width glyphs cannot fit the 22px title content width on one line.
    # Two title lines, three metadata/link lines, one spare 32px line and 24px
    # vertical padding require at least 216px, rounded up, independent of _size().
    # This boundary input is supported text, not the default compact card content.
    uri = "https://example.org/source/" + "x" * 600
    text = "## [[papers/example|" + "高" * 15 + "]]\nFirst preprint 2023-10-16\nVenue 2024\n[Source](" + uri + ")"
    node = _lit_node("long-title", role)
    node["text"] = text
    if role == "milestone":
        spine = [node]
    elif role == "pipeline":
        spine = [_lit_node("parent", "milestone", [node])]
    else:
        spine = [_lit_node("parent", "milestone", [_lit_node("branch", "pipeline", [node])])]
    canvas = layout.render({"schema_version": 1, "view": "literature", "spine": spine})
    title = next(n for n in canvas["nodes"] if uri in n["text"])
    assert title["height"] >= 224
    assert title["text"] == text
    assert layout.validate_canvas(canvas) == []
    node["text"] = text.replace(uri, "https://example.org/short")
    short = layout.render({"schema_version": 1, "view": "literature", "spine": spine})
    assert next(n for n in short["nodes"] if "[Source]" in n["text"])["height"] == title["height"]


def test_compact_timeline_title_does_not_reserve_a_bibliography_block():
    paper = _lit_node("compact", "milestone")
    paper["text"] = "[[papers/example|Short Name · 2024 ↗]]"
    canvas = layout.render({"schema_version": 1, "view": "literature", "spine": [paper]})
    title = next(n for n in canvas["nodes"] if n["styleAttributes"]["swLit"] == "milestone")
    assert 80 <= title["height"] <= 96  # 22px title + spare line + compact padding.
    assert title["text"] == paper["text"]
    assert layout.validate_canvas(canvas) == []


@pytest.mark.parametrize("view", ["technical", "challenge"])
def test_left_and_right_root_buses_have_distinct_stable_ids_and_fixed_anchors(view):
    canvas = layout.render(_radial(view, (1, 1)))
    root = next(node for node in canvas["nodes"]
                if node["styleAttributes"].get("swMind") == "root")
    exits = [edge for edge in canvas["edges"] if edge["fromNode"] == root["id"]]
    assert len(exits) == 2
    assert {edge["fromSide"] for edge in exits} == {"left", "right"}
    assert len({edge["toNode"] for edge in exits}) == 2
    points = {node["id"]: node for node in canvas["nodes"]}
    assert {points[edge["toNode"]]["x"] + 1 for edge in exits} == {-200, 200}
    assert all(edge["fromFloating"] is False and edge["toFloating"] is False
               for edge in canvas["edges"])
    assert layout.validate_canvas(canvas) == []


@pytest.mark.parametrize("view", ["literature", "technical", "challenge"])
def test_empty_view_does_not_invent_nodes(view):
    doc = {"schema_version": 1, "view": view}
    if view == "literature":
        doc["spine"] = []
    else:
        doc.update(root={"id": "empty-topic", "text": "No classified papers yet."}, branches=[])
    canvas = layout.render(doc)
    assert len(canvas["nodes"]) == (0 if view == "literature" else 1)
    assert canvas["edges"] == []


def test_long_english_display_words_wrap_without_modifying_link_destinations():
    document = _radial("technical", (2,))
    uri = "obsidian://zotflow?key=" + "B" * 100
    original = "**" + "LongScientificRepresentation" * 8 + f"**\n\n[PDF source]({uri})"
    document["branches"][0]["children"][0]["text"] = original
    canvas = layout.render(document)
    leaf = next(node for node in _semantic(canvas) if uri in node["text"])
    assert "\u200b" in leaf["text"]
    assert leaf["text"].replace("\u200b", "") == original
    assert uri in leaf["text"]
    assert layout.validate_canvas(canvas) == []


def test_nested_parentheses_url_is_byte_preserved_while_visible_words_wrap():
    document = _radial("technical", (1, 1))
    uri = "https://example.org/a(b)/LongScientificRepresentationLongScientificRepresentation"
    original = "**" + "VisibleScientificRepresentation" * 8 + f"**\n\n[PDF]({uri})"
    document["branches"][0]["children"][0]["text"] = original
    canvas = layout.render(document)
    leaf = next(node for node in _semantic(canvas) if "example.org" in node["text"])
    assert uri in leaf["text"]
    assert "\u200b" in leaf["text"].split("\n\n", 1)[0]
    assert leaf["text"].replace("\u200b", "") == original
    assert layout.validate_canvas(canvas) == []


@pytest.mark.parametrize("view", ["literature", "technical", "challenge"])
def test_repeat_render_is_byte_deterministic_and_ids_are_unique(view):
    document = _literature() if view == "literature" else _radial(view)
    first = json.dumps(layout.render(document), ensure_ascii=False)
    second = json.dumps(layout.render(document), ensure_ascii=False)
    assert first == second
    canvas = json.loads(first)
    ids = [row["id"] for row in canvas["nodes"] + canvas["edges"]]
    assert len(ids) == len(set(ids))
    assert all(len(identifier) == 16 and all(c in "0123456789abcdef" for c in identifier) for identifier in ids)


@pytest.mark.parametrize("field", ["path", "cwd", "file", "url", "config", "destination"])
def test_external_path_or_execution_fields_are_rejected(field):
    document = _radial("technical")
    document[field] = "unrequested external input"
    with pytest.raises(ValueError, match="unknown"):
        layout.render(document)
    document.pop(field)
    document["branches"][0][field] = "unrequested external input"
    with pytest.raises(ValueError, match="unknown"):
        layout.render(document)


@pytest.mark.parametrize("case", ["duplicate", "path-key", "depth", "role", "version", "text-limit", "count-limit"])
def test_invalid_inputs_fail_without_reclassification_or_truncation(case):
    document = _radial("technical", (1,))
    if case == "duplicate":
        document["branches"][0]["children"][0]["id"] = "root"
    elif case == "path-key":
        document["root"]["id"] = "../outside"
    elif case == "depth":
        document["branches"][0]["children"][0]["children"] = [_paper("too-deep")]
    elif case == "role":
        document = _literature()
        document["spine"][0]["children"][0]["role"] = "milestone"
    elif case == "version":
        document["schema_version"] = True
    elif case == "text-limit":
        document["root"]["text"] = "x" * (layout.MAX_TEXT + 1)
    elif case == "count-limit":
        document = _radial("technical", (layout.MAX_NODES,))
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        layout.render(document)
    assert document == before


def _node(index, x, y):
    return {"id": f"{index:016x}", "type": "text", "text": "Node", "x": x, "y": y,
            "width": 20, "height": 20}


def _edge(index, source, target, from_side="right", to_side="left"):
    return {"id": f"{index:016x}", "fromNode": f"{source:016x}", "toNode": f"{target:016x}",
            "fromSide": from_side, "toSide": to_side, "fromEnd": "none", "toEnd": "none",
            "styleAttributes": {"pathfindingMethod": "square"}}


@pytest.mark.parametrize("frontmatter", [{}, {"tags": ["test"], "nested": {"label": "原样保留"}}])
def test_validator_preserves_observed_advanced_canvas_metadata(frontmatter):
    canvas = layout.render(_literature())
    metadata = {"version": "1.0-1.0", "frontmatter": frontmatter}
    canvas["metadata"] = metadata
    before = json.dumps(canvas, ensure_ascii=False)
    assert layout.validate_canvas(canvas) == []
    assert canvas["metadata"] is metadata
    assert canvas["metadata"]["frontmatter"] is frontmatter
    assert json.dumps(canvas, ensure_ascii=False) == before


@pytest.mark.parametrize("metadata", [
    None,
    [],
    {},
    {"version": "1.0-1.0"},
    {"frontmatter": {}},
    {"version": 1, "frontmatter": {}},
    {"version": "   ", "frontmatter": {}},
    {"version": "v" * 65, "frontmatter": {}},
    {"version": "1.0-1.0", "frontmatter": []},
    {"version": "1.0-1.0", "frontmatter": {1: "not a string key"}},
    {"version": "1.0-1.0", "frontmatter": {}, "owner": "forged"},
])
def test_validator_rejects_invalid_or_forged_advanced_canvas_metadata(metadata):
    canvas = layout.render(_radial("technical"))
    canvas["metadata"] = metadata
    before = copy.deepcopy(canvas)
    assert layout.validate_canvas(canvas) == ["Advanced Canvas metadata is invalid"]
    assert canvas == before


@pytest.mark.parametrize("field", ["owner", "source_id", "unexpected"])
def test_metadata_does_not_allow_unknown_top_level_identity_fields(field):
    canvas = layout.render(_radial("technical"))
    canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {"owner": "display only"}}
    canvas[field] = "forged"
    assert layout.validate_canvas(canvas)


def test_valid_metadata_does_not_bypass_exact_geometry_checks():
    canvas = {"nodes": [_node(1, 0, 100), _node(2, 200, 100), _node(3, 100, 0), _node(4, 100, 200)],
              "edges": [_edge(5, 1, 2), _edge(6, 3, 4, "bottom", "top")],
              "metadata": {"version": "1.0-1.0", "frontmatter": {}}}
    assert any("crossing" in error for error in layout.validate_canvas(canvas))


def test_validator_rejects_real_segment_crossing_despite_square_metadata():
    canvas = {"nodes": [_node(1, 0, 100), _node(2, 200, 100), _node(3, 100, 0), _node(4, 100, 200)],
              "edges": [_edge(5, 1, 2), _edge(6, 3, 4, "bottom", "top")]}
    assert any("crossing" in error for error in layout.validate_canvas(canvas))


@pytest.mark.parametrize("case", ["dangling", "diagonal", "overlap", "fractional", "through-node", "arrow", "duplicate-id", "wrong-side", "floating"])
def test_validator_rejects_geometry_failures(case):
    canvas = {"nodes": [_node(1, 0, 0), _node(2, 200, 0)], "edges": [_edge(3, 1, 2)]}
    assert layout.validate_canvas(canvas) == []
    if case == "dangling":
        canvas["edges"][0]["toNode"] = "ffffffffffffffff"
    elif case == "diagonal":
        canvas["nodes"][1]["y"] = 50
    elif case == "overlap":
        canvas["nodes"][1]["x"] = 10
    elif case == "fractional":
        canvas["nodes"][1]["x"] = 200.0
    elif case == "through-node":
        canvas["nodes"].append(_node(4, 100, 0))
    elif case == "arrow":
        canvas["edges"][0]["toEnd"] = "arrow"
    elif case == "duplicate-id":
        canvas["edges"][0]["id"] = canvas["nodes"][0]["id"]
    elif case == "wrong-side":
        canvas["edges"][0]["fromSide"] = "left"
    elif case == "floating":
        canvas["edges"][0]["toFloating"] = True
    assert layout.validate_canvas(canvas)


def test_no_external_file_network_or_execution_access(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("pure layout attempted external access")

    with monkeypatch.context() as patch:
        for target, name in ((builtins, "open"), (io, "open"), (os, "open"),
                             (subprocess, "run"), (subprocess, "Popen"), (os, "system"),
                             (socket, "create_connection"), (socket, "getaddrinfo"),
                             (socket.socket, "connect")):
            patch.setattr(target, name, forbidden)
        for document in (_literature(), _radial("technical"), _radial("challenge")):
            assert layout.validate_canvas(layout.render(document)) == []


def test_cli_emits_only_complete_json_and_no_partial_failure(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_radial("technical"))))
    assert layout.main([]) == 0
    result = capsys.readouterr()
    assert layout.validate_canvas(json.loads(result.out)) == []
    assert result.err == ""
    document = _radial("technical")
    document["path"] = "outside"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(document)))
    assert layout.main([]) == 2
    result = capsys.readouterr()
    assert result.out == "" and "refused" in result.err


def test_cli_input_size_limit_has_no_json_output(monkeypatch, capsys):
    monkeypatch.setattr(layout, "MAX_INPUT_BYTES", 16)
    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * 17))
    assert layout.main([]) == 2
    result = capsys.readouterr()
    assert result.out == "" and "exceeds" in result.err
