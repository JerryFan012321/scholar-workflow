"""Independent, hand-calculated expectations for compact aligned Canvas routes.

Geometry-only trees and one synthetic public-render case cover all five first-level
branches. No Vault, native reader or installation calls occur. Expected coordinates
are fixed below; no production geometry checker is used as an oracle.
"""

from copy import deepcopy
from itertools import combinations, pairwise

import pytest

from scholar_workflow.analysis import complete_reference
from scholar_workflow.analysis.complete_reference import TemplateNode, _layout_tree
from scholar_workflow.analysis.models import AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import create_baseline, plan_analysis_update

BRANCHES = ("Abstract", "Introduction", "Method", "Experiments", "Limitation")


def _node(path, kind, width, height, label="Synthetic"):
    return TemplateNode(path, label, kind, None, label, width, height)


def _regular_tree(*, leaf_height=100, wide_width=1000, wide_height=100):
    root = _node("root", "root", 200, 70, "Paper")
    for index, label in enumerate(BRANCHES):
        prefix = f"branch-{index}"
        section = _node(prefix, "section", 200, 70, label)
        parent = _node(f"{prefix}/parent", "group", 200, 70)
        parent.children = [
            _node(f"{prefix}/leaf-{child}", "point", 280, leaf_height)
            for child in range(4)
        ]
        section.children = [
            _node(f"{prefix}/wide", "claim", wide_width, wide_height),
            parent,
        ]
        root.children.append(section)
    return root


def _nodes_with_depth(root, depth=0):
    yield root, depth
    for child in root.children:
        yield from _nodes_with_depth(child, depth + 1)


def _nodes(root):
    return {node.path: node for node, _ in _nodes_with_depth(root)}


def _edges(root):
    return tuple(
        (parent.path, child.path)
        for parent, _ in _nodes_with_depth(root)
        for child in parent.children
    )


def _unchanged_fields(root):
    return {
        node.path: (
            node.text, node.kind, node.role, node.label, node.width, node.height,
            node.claim, node.point, tuple(child.path for child in node.children),
        )
        for node, _ in _nodes_with_depth(root)
    }


def _regular_positions(
    columns, *, root_y, section_y, parent_y, child_y, child_stride, branch_stride
):
    """Transcribe fixed arithmetic, without measuring or laying out the tree."""
    positions = {"root": (columns[0], root_y)}
    for index in range(5):
        prefix = f"branch-{index}"
        offset = index * branch_stride
        positions[prefix] = (columns[1], section_y + offset)
        positions[f"{prefix}/wide"] = (columns[2], offset)
        positions[f"{prefix}/parent"] = (columns[2], parent_y + offset)
        for child in range(4):
            positions[f"{prefix}/leaf-{child}"] = (
                columns[3], child_y + child * child_stride + offset,
            )
    return positions


def _put_at(root, positions):
    assert set(positions) == set(_nodes(root))
    for path, node in _nodes(root).items():
        node.x, node.y = positions[path]


def _positions(root):
    return {path: (node.x, node.y) for path, node in _nodes(root).items()}


def _bounds(root):
    nodes = tuple(_nodes(root).values())
    return (
        max(node.x + node.width for node in nodes) - min(node.x for node in nodes),
        max(node.y + node.height for node in nodes) - min(node.y for node in nodes),
    )


def _boxes_overlap(left, right):
    return (
        max(left.x, right.x) < min(left.x + left.width, right.x + right.width)
        and max(left.y, right.y) < min(left.y + left.height, right.y + right.height)
    )


def _square_segments(source, target):
    """Calculate right-center to left-center square paths from actual boxes."""
    start = (source.x + source.width, source.y + source.height / 2)
    finish = (target.x, target.y + target.height / 2)
    middle = (start[0] + finish[0]) / 2
    points = (start, (middle, start[1]), (middle, finish[1]), finish)
    return tuple((a, b) for a, b in pairwise(points) if a != b)


def _segments_touch(left, right):
    a, b = left
    c, d = right
    left_horizontal, right_horizontal = a[1] == b[1], c[1] == d[1]
    if left_horizontal == right_horizontal:
        fixed, moving = (1, 0) if left_horizontal else (0, 1)
        return a[fixed] == c[fixed] and max(
            min(a[moving], b[moving]), min(c[moving], d[moving])
        ) <= min(max(a[moving], b[moving]), max(c[moving], d[moving]))
    horizontal, vertical = (left, right) if left_horizontal else (right, left)
    h1, h2 = horizontal
    v1, v2 = vertical
    return (
        min(h1[0], h2[0]) <= v1[0] <= max(h1[0], h2[0])
        and min(v1[1], v2[1]) <= h1[1] <= max(v1[1], v2[1])
    )


def _segment_touches_box(segment, node):
    a, b = segment
    left, right = node.x, node.x + node.width
    top, bottom = node.y, node.y + node.height
    if a[1] == b[1]:
        return top <= a[1] <= bottom and max(min(a[0], b[0]), left) <= min(
            max(a[0], b[0]), right
        )
    assert a[0] == b[0], "Square routes must be orthogonal."
    return left <= a[0] <= right and max(min(a[1], b[1]), top) <= min(
        max(a[1], b[1]), bottom
    )


def _assert_safe_geometry(root):
    nodes = _nodes(root)
    columns = {}
    for node, depth in _nodes_with_depth(root):
        columns.setdefault(depth, set()).add(node.x)
    assert all(len(left_edges) == 1 for left_edges in columns.values())
    for left, right in combinations(nodes.values(), 2):
        assert not _boxes_overlap(left, right), (left.path, right.path)
    routes = []
    for source_path, target_path in _edges(root):
        source, target = nodes[source_path], nodes[target_path]
        assert source.x + source.width < target.x
        segments = _square_segments(source, target)
        for path, node in nodes.items():
            if path not in (source_path, target_path):
                assert not any(_segment_touches_box(part, node) for part in segments), (
                    source_path, target_path, path,
                )
        routes.append((source_path, target_path, segments))
    for left, right in combinations(routes, 2):
        if left[0] != right[0]:  # Siblings may share their source trunk.
            assert not any(_segments_touch(a, b) for a in left[2] for b in right[2]), (
                left[:2], right[:2],
            )


@pytest.mark.parametrize("expanded", [False, True])
def test_wide_terminal_nodes_do_not_lengthen_unrelated_parent_routes(expanded):
    root = _regular_tree()
    before = _unchanged_fields(root)
    topology = _edges(root)
    assert len(before) == 36 and len(topology) == 35
    assert tuple(node.label for node in root.children) == BRANCHES
    # Each band is 100 + 8 + (4*100 + 3*8) = 532; 5*532 + 4*32 = 2788.
    vertical = {
        "root_y": 1278, "section_y": 150, "parent_y": 285, "child_y": 108,
        "child_stride": 108, "branch_stride": 564,
    }
    old = deepcopy(root)
    _put_at(old, _regular_positions((0, 264, 528, 1592), **vertical))
    assert _bounds(old) == (1872, 2788)
    _assert_safe_geometry(old)

    _layout_tree(root, expanded=expanded)

    assert _positions(root) == _regular_positions((0, 264, 528, 792), **vertical)
    assert _bounds(root) == (1528, 2788)
    assert 2788 <= 2 * 1528
    assert _unchanged_fields(root) == before and _edges(root) == topology
    assert {path: node.y for path, node in _nodes(root).items()} == {
        path: node.y for path, node in _nodes(old).items()
    }
    for index in range(5):
        parent = _nodes(root)[f"branch-{index}/parent"]
        leaf = _nodes(root)[f"branch-{index}/leaf-0"]
        old_parent = _nodes(old)[parent.path]
        old_leaf = _nodes(old)[leaf.path]
        assert old_leaf.x - old_parent.x - old_parent.width == 864
        assert leaf.x - parent.x - parent.width == 64
        # Fixed centers 320 and 158 differ by 162px; measure the routed polyline.
        assert sum(
            abs(a[0] - b[0]) + abs(a[1] - b[1])
            for a, b in _square_segments(old_parent, old_leaf)
        ) == 1026
        assert sum(
            abs(a[0] - b[0]) + abs(a[1] - b[1])
            for a, b in _square_segments(parent, leaf)
        ) == 226
    _assert_safe_geometry(root)


@pytest.mark.parametrize("expanded", [False, True])
def test_compaction_falls_back_when_two_to_one_bounds_would_fail(expanded):
    root = _regular_tree(leaf_height=128)
    before, topology = _unchanged_fields(root), _edges(root)
    # Each band is 100 + 8 + (4*128 + 3*8) = 644; 5*644 + 4*32 = 3348.
    vertical = {
        "root_y": 1530, "section_y": 178, "parent_y": 341, "child_y": 108,
        "child_stride": 136, "branch_stride": 676,
    }
    compact = deepcopy(root)
    _put_at(compact, _regular_positions((0, 264, 528, 792), **vertical))
    assert _bounds(compact) == (1528, 3348)
    assert 3348 > 2 * 1528
    _assert_safe_geometry(compact)  # Only the aspect bound makes this unsafe.

    _layout_tree(root, expanded=expanded)

    assert _positions(root) == _regular_positions((0, 264, 528, 1592), **vertical)
    assert _bounds(root) == (1872, 3348)
    assert 3348 <= 2 * 1872
    assert _unchanged_fields(root) == before and _edges(root) == topology
    _assert_safe_geometry(root)


def _occlusion_tree():
    root = _node("root", "root", 200, 70, "Paper")
    for index, label in enumerate(BRANCHES):
        prefix = f"branch-{index}"
        section = _node(prefix, "section", 200, 70, label)
        parent = _node(f"{prefix}/parent", "group", 200, 70)
        tall = _node(f"{prefix}/tall", "claim", 200, 420)
        tall.children = [
            _node(f"{prefix}/short", "point", 280, 70),
            _node(f"{prefix}/long", "point", 280, 110),
        ]
        parent.children = [tall]
        section.children = [_node(f"{prefix}/wide", "claim", 1000, 100), parent]
        root.children.append(section)
    return root


def _occlusion_positions(columns):
    positions = {"root": (columns[0], 1264)}
    for index in range(5):
        prefix, offset = f"branch-{index}", index * 560
        positions.update({
            prefix: (columns[1], 144 + offset),
            f"{prefix}/wide": (columns[2], offset),
            f"{prefix}/parent": (columns[2], 273 + offset),
            f"{prefix}/tall": (columns[3], 98 + offset),
            f"{prefix}/short": (columns[4], 224 + offset),
            f"{prefix}/long": (columns[4], 302 + offset),
        })
    return positions


@pytest.mark.parametrize("expanded", [False, True])
def test_compaction_falls_back_for_hand_calculated_two_pixel_occlusion(expanded):
    root = _occlusion_tree()
    before, topology = _unchanged_fields(root), _edges(root)
    # The tall subtree reserves 420px. Its 70/110px children occupy 188px,
    # starting at 108 + (420-188)//2 = 224. Centers 259 and 357 place the
    # 420px card at y=98, overlapping the unrelated wide leaf's y=0..100.
    compact = deepcopy(root)
    _put_at(compact, _occlusion_positions((0, 264, 528, 792, 1056)))
    assert _bounds(compact) == (1528, 2758)
    assert 2758 <= 2 * 1528  # Aspect validation alone must not accept it.
    nodes = _nodes(compact)
    assert _boxes_overlap(nodes["branch-0/wide"], nodes["branch-0/tall"])
    assert nodes["branch-0/wide"].y + nodes["branch-0/wide"].height - nodes[
        "branch-0/tall"
    ].y == 2
    with pytest.raises(AssertionError):
        _assert_safe_geometry(compact)

    _layout_tree(root, expanded=expanded)

    assert _positions(root) == _occlusion_positions((0, 264, 528, 1592, 1856))
    assert _bounds(root) == (2136, 2758)
    assert _unchanged_fields(root) == before and _edges(root) == topology
    _assert_safe_geometry(root)


@pytest.mark.parametrize("expanded", [False, True])
def test_equal_terminal_and_parent_widths_keep_all_coordinates(expanded):
    root = _regular_tree(leaf_height=70, wide_width=200, wide_height=70)
    before, topology = _unchanged_fields(root), _edges(root)
    # Each band is 70 + 8 + (4*70 + 3*8) = 382; 5*382 + 4*32 = 2038.
    expected = _regular_positions(
        (0, 264, 528, 792), root_y=925, section_y=97, parent_y=195,
        child_y=78, child_stride=78, branch_stride=414,
    )

    _layout_tree(root, expanded=expanded)

    assert _positions(root) == expected
    assert _bounds(root) == (1072, 2038)
    assert 2038 <= 2 * 1072
    assert _unchanged_fields(root) == before and _edges(root) == topology
    _assert_safe_geometry(root)


def _public_render_document():
    # Five explicit N/A records cover the whole framework. The wide task has
    # 360 padding characters plus an explicit 168-character Canvas summary;
    # both exceed the 1000px width cap, with no source fact/external dependency.
    records = (
        ("wide-task", "abstract", "abstract/task", "Task"),
        ("application", "introduction", "introduction/task_application", "Task and application"),
        ("overview", "method", "method/overview", "Overview"),
        ("comparison", "experiments", "experiments/comparison/synthetic", "Comparison experiments"),
        ("limit", "limitation", "limitation/explanation/synthetic", "Reasoned limitation 1"),
    )
    return AnalysisDocument.model_validate({
        "schema_version": 5,
        "artifact_id": "analysis:paper:synthetic-compact-public-render",
        "paper_title": "Paper",
        "language": "en",
        "profile": {
            "kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True,
        },
        "claims": [
            {
                "claim_id": claim_id, "role": role, "outline_path": path, "title": title,
                "body": (
                    "Synthetic padding only. " * 15 if claim_id == "wide-task" else "Synthetic."
                ),
                **({"canvas_summary": "Synthetic padding only. " * 7}
                   if claim_id == "wide-task" else {}),
                "evidence": {
                    "kind": "not_applicable",
                    "detail": "Synthetic geometry fixture; no scientific claim.",
                },
            }
            for claim_id, role, path, title in records
        ],
    })


def _actual_canvas_tree(canvas):
    """Adapt actual public-render payloads, never reconstruct expected geometry."""
    nodes = {
        row["id"]: TemplateNode(
            row["id"], row["text"], "actual", None, "",
            row["width"], row["height"], x=row["x"], y=row["y"],
        )
        for row in canvas["nodes"]
    }
    targets = set()
    for edge in canvas["edges"]:
        assert edge["fromSide"] == "right" and edge["toSide"] == "left"
        assert edge["fromEnd"] == edge["toEnd"] == "none"
        assert edge["styleAttributes"]["pathfindingMethod"] == "square"
        nodes[edge["fromNode"]].children.append(nodes[edge["toNode"]])
        targets.add(edge["toNode"])
    roots = set(nodes) - targets
    assert len(roots) == 1
    root = nodes[roots.pop()]
    assert set(_nodes(root)) == set(nodes)
    return root


def test_public_v5_render_shortens_columns_without_reflowing_existing_pairs(monkeypatch):
    document, note = _public_render_document(), "Compact integration"
    assert len(document.claims) == 5 and len(document.claims[0].body) == 360
    assert len(document.claims[0].canvas_summary) == 168
    with monkeypatch.context() as previous:
        previous.setattr(complete_reference, "_compact_tree_columns", lambda layers: None)
        old = render_analysis(document, note_stem=note)
        baseline = create_baseline(document, old, note_stem=note)

    compact = render_analysis(document, note_stem=note)

    assert compact.markdown == old.markdown
    assert compact.canvas["edges"] == old.canvas["edges"]
    assert len(compact.canvas["nodes"]) == 26 and len(compact.canvas["edges"]) == 25
    old_nodes = {node["id"]: node for node in old.canvas["nodes"]}
    nodes = {node["id"]: node for node in compact.canvas["nodes"]}
    assert set(nodes) == set(old_nodes)
    for node_id, node in nodes.items():
        assert {key: value for key, value in node.items() if key != "x"} == {
            key: value for key, value in old_nodes[node_id].items() if key != "x"
        }
    for claim in document.claims:
        assert claim.body in compact.markdown
        assert f"^claim-{claim.claim_id}" in compact.markdown
        backlink = f"[[{note}#^claim-{claim.claim_id}|Analysis]]"
        matches = [node for node in nodes.values() if backlink in node["text"]]
        assert len(matches) == 1 and "〔N/A〕" in matches[0]["text"]

    old_tree, compact_tree = _actual_canvas_tree(old.canvas), _actual_canvas_tree(compact.canvas)
    old_columns, columns = {}, {}
    for node, depth in _nodes_with_depth(old_tree):
        old_columns.setdefault(depth, set()).add(node.x)
    for node, depth in _nodes_with_depth(compact_tree):
        columns.setdefault(depth, set()).add(node.x)
    # Paper=104px, section max=136px, terminal task=1000px, outgoing
    # Overview=280px. The last column's widest structural label is 440px.
    assert old_columns == {0: {0}, 1: {168}, 2: {368}, 3: {1432}}
    assert columns == {0: {0}, 1: {168}, 2: {368}, 3: {712}}
    assert _bounds(old_tree)[0] == 1872 and _bounds(compact_tree)[0] == 1368
    assert _bounds(old_tree)[1] == _bounds(compact_tree)[1]
    method = next(node for node in nodes.values() if "#^claim-overview|Analysis]]" in node["text"])
    child_ids = [
        edge["toNode"] for edge in compact.canvas["edges"]
        if edge["fromNode"] == method["id"]
    ]
    assert method["width"] == 280 and len(child_ids) == 2
    for child_id in child_ids:
        assert old_nodes[child_id]["x"] - old_nodes[method["id"]]["x"] - 280 == 784
        assert nodes[child_id]["x"] - method["x"] - 280 == 64
    _assert_safe_geometry(old_tree)
    _assert_safe_geometry(compact_tree)

    # A newer renderer must not rewrite an existing accepted pair's coordinates.
    plan = plan_analysis_update(
        current=old, baseline=baseline, update=document, note_stem=note,
    )
    assert plan.status == "ready" and plan.conflicts == ()
    assert plan.proposed == old
    _assert_safe_geometry(_actual_canvas_tree(plan.proposed.canvas))
