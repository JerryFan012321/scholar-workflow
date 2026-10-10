"""Development-only spacing proposal; never a paired analysis writer or runtime API."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from urllib.parse import unquote


def _tree(canvas: dict) -> tuple[dict, dict, str, dict]:
    nodes = {node["id"]: node for node in canvas["nodes"]}
    if len(nodes) != len(canvas["nodes"]):
        raise ValueError("Duplicate nodes")
    children: dict[str, list[str]] = defaultdict(list)
    incoming = {}
    for edge in canvas["edges"]:
        parent, child = edge["fromNode"], edge["toNode"]
        if parent not in nodes or child not in nodes or child in incoming:
            raise ValueError("Dangling edge or multiple parents")
        incoming[child] = edge
        children[parent].append(child)
    roots = set(nodes) - set(incoming)
    if len(roots) != 1:
        raise ValueError("Expected one tree root")
    root = roots.pop()
    seen = set()

    def visit(node_id):
        if node_id in seen:
            raise ValueError("Cycle")
        seen.add(node_id)
        for child in children[node_id]:
            visit(child)

    visit(root)
    if seen != set(nodes):
        raise ValueError("Disconnected graph")
    return nodes, children, root, incoming


def reflow(canvas: dict) -> dict:
    """Retain every field except Y placement and direct branch-label background."""
    result = deepcopy(canvas)
    nodes, children, root, incoming = _tree(result)
    sizes = {}

    def gap(node_id, depth):
        if depth == 0:
            return 96
        if depth == 1:
            return 40
        return 24 if any(children[child] for child in children[node_id]) else 16

    def measure(node_id, depth):
        size = sum(measure(child, depth + 1) for child in children[node_id])
        size += gap(node_id, depth) * max(0, len(children[node_id]) - 1)
        sizes[node_id] = max(nodes[node_id]["height"], size)
        return sizes[node_id]

    def place(node_id, depth, top):
        node = nodes[node_id]
        descendants = children[node_id]
        total = sum(sizes[child] for child in descendants)
        total += gap(node_id, depth) * max(0, len(descendants) - 1)
        child_top = top + (sizes[node_id] - total) // 2
        for child in descendants:
            place(child, depth + 1, child_top)
            child_top += sizes[child] + gap(node_id, depth)
        if descendants:
            first, last = nodes[descendants[0]], nodes[descendants[-1]]
            center = (first["y"] + first["height"] // 2
                      + last["y"] + last["height"] // 2) // 2
            node["y"] = center - node["height"] // 2
        else:
            node["y"] = top + (sizes[node_id] - node["height"]) // 2

    measure(root, 0)
    place(root, 0, 0)
    for child in children[root]:
        if "color" in incoming[child]:
            nodes[child]["color"] = incoming[child]["color"]
    return result


def section_frames(canvas: dict, *, separate=False, minimum_widths=None) -> dict:
    """Add native frames, optionally translating whole sections without local reflow."""
    result = deepcopy(canvas)
    nodes, children, root, incoming = _tree(result)
    for node_id, width in (minimum_widths or {}).items():
        if node_id not in nodes or not nodes[node_id]["width"] <= width <= 1000:
            raise ValueError("Unknown node or invalid width adjustment")
        nodes[node_id]["width"] = width
    groups = []
    previous_bottom = None
    for child in children[root]:
        band = []

        def collect(node_id, band=band):
            band.append(nodes[node_id])
            for descendant in children[node_id]:
                collect(descendant)

        collect(child)
        x = min(node["x"] for node in band) - 20
        y = min(node["y"] for node in band) - 20
        right = max(node["x"] + node["width"] for node in band) + 20
        bottom = max(node["y"] + node["height"] for node in band) + 12
        if separate and previous_bottom is not None:
            shift = max(0, previous_bottom + 24 - y)
            for node in band:
                node["y"] += shift
            y += shift
            bottom += shift
        previous_bottom = bottom
        groups.append({
            "id": sha256(f"review-section\n{root}\n{child}".encode()).hexdigest()[:16],
            "type": "group", "x": x, "y": y,
            "width": right - x, "height": bottom - y,
            "label": nodes[child]["text"].strip("*"),
            "color": incoming[child].get("color", "#a7b4b5"),
        })
        nodes[child]["color"] = groups[-1]["color"]
    if {group["id"] for group in groups} & set(nodes):
        raise ValueError("Review group identity collision")
    if separate:
        first, last = nodes[children[root][0]], nodes[children[root][-1]]
        center = (first["y"] + first["height"] // 2 + last["y"] + last["height"] // 2) // 2
        nodes[root]["y"] = center - nodes[root]["height"] // 2
    result["nodes"] = groups + result["nodes"]
    return result


def section_frame_findings(canvas: dict, original: dict) -> list[dict[str, str]]:
    """Check only the proposal's identified frames, never arbitrary user groups."""
    source_nodes, children, root, _ = _tree(original)
    nodes = {node["id"]: node for node in canvas["nodes"]}
    findings = []
    frames = []

    def fail(code, node_id, message):
        findings.append({"code": code, "path": f"canvas/nodes/{node_id}", "message": message})

    def overlaps(left, right):
        return (
            left["x"] < right["x"] + right["width"]
            and right["x"] < left["x"] + left["width"]
            and left["y"] < right["y"] + right["height"]
            and right["y"] < left["y"] + left["height"]
        )

    for child in children[root]:
        frame_id = sha256(f"review-section\n{root}\n{child}".encode()).hexdigest()[:16]
        frame = nodes.get(frame_id)
        if frame is None:
            fail("section-frame-missing", frame_id, "The identified section frame is missing.")
            continue
        if frame.get("type") != "group":
            fail("section-frame-type", frame_id, "A section frame must be a native group.")
            continue
        frames.append(frame)
        if frame.get("label") != source_nodes[child]["text"].strip("*"):
            fail("section-frame-label", frame_id, "The frame label differs from its section.")
        owned = set()
        pending = [child]
        while pending:
            node_id = pending.pop()
            owned.add(node_id)
            pending.extend(children[node_id])
        for node_id in sorted(owned):
            node = nodes.get(node_id)
            if node is None:
                fail("section-frame-content-missing", node_id, "A section descendant is missing.")
                continue
            if not (
                frame["x"] <= node["x"]
                and frame["y"] <= node["y"]
                and frame["x"] + frame["width"] >= node["x"] + node["width"]
                and frame["y"] + frame["height"] >= node["y"] + node["height"]
            ):
                fail("section-frame-incomplete", frame_id, f"Section node {node_id} extends outside its frame.")
            if node["y"] < frame["y"] + 20:
                fail("section-frame-title-space", frame_id, f"Section node {node_id} enters the frame title band.")
            if (
                node["x"] < frame["x"] + 20
                or node["x"] + node["width"] > frame["x"] + frame["width"] - 20
                or node["y"] + node["height"] > frame["y"] + frame["height"] - 12
            ):
                fail("section-frame-padding", frame_id, f"Section node {node_id} lacks the proposal's frame padding.")
        for node_id in sorted(source_nodes.keys() - owned):
            node = nodes.get(node_id)
            if node is not None and overlaps(frame, node):
                fail("section-frame-foreign-node", frame_id, f"Frame intersects another section or root node {node_id}.")
    for index, first in enumerate(frames):
        for second in frames[index + 1:]:
            if overlaps(first, second):
                fail("section-frame-overlap", first["id"], f"Section frame overlaps {second['id']}.")
    for first, second in pairwise(frames):
        if second["y"] - first["y"] - first["height"] < 24:
            fail("section-frame-gap", first["id"], f"Less than 24 px before section frame {second['id']}.")
    return findings


def _safe_existing_file(path: Path) -> None:
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Symlink input rejected")
    if not path.is_file():
        raise ValueError("Input file missing")


def main():
    from scholar_workflow.analysis.complete_conformance import geometry_findings
    from scholar_workflow.canvas import validate_canvas_payload

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--section-frames", action="store_true")
    parser.add_argument("--separate-sections", action="store_true")
    parser.add_argument("--minimum-width", action="append", default=[], metavar="NODE_ID:WIDTH")
    args = parser.parse_args()
    source, destination = args.source.absolute(), args.destination.absolute()
    _safe_existing_file(source)
    if destination.exists() or any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("Use a new non-symlink review directory; never overwrite")
    source_bytes = source.read_bytes()
    original = json.loads(source_bytes)
    widths = {name: int(width) for name, width in (value.split(":") for value in args.minimum_width)}
    if (args.separate_sections or widths) and not args.section_frames:
        raise ValueError("Section options require --section-frames")
    candidate = section_frames(original, separate=args.separate_sections, minimum_widths=widths) if args.section_frames else reflow(original)
    validate_canvas_payload(candidate)
    findings = [finding.model_dump() for finding in geometry_findings(candidate, original)]
    if args.section_frames:
        findings.extend(section_frame_findings(candidate, original))
    if findings:
        print(json.dumps({"status": "failed", "findings": findings}, ensure_ascii=False))
        raise SystemExit(1)
    assets = {}
    for node in candidate["nodes"]:
        for match in re.finditer(r"!\[[^\]\r\n]*\]\(\./(attachments/[^\r\n)]+\.png)\)", node.get("text", "")):
            relative = Path(unquote(match[1]))
            if ".." in relative.parts or relative.is_absolute():
                raise ValueError("Unsafe image path")
            file = source.parent / relative
            _safe_existing_file(file)
            assets[str(relative)] = file.read_bytes()
    if source.read_bytes() != source_bytes:
        raise ValueError("Source changed; stop")
    destination.mkdir(parents=True, exist_ok=False)
    suffix = "-分区修正候选.canvas" if args.separate_sections else ("-分区候选.canvas" if args.section_frames else "-间距候选.canvas")
    output = destination / (source.stem + suffix)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(candidate, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    for relative, data in assets.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        if path.read_bytes() != data:
            raise ValueError("Copied image drift")
    nodes = candidate["nodes"]
    width = max(n["x"] + n["width"] for n in nodes) - min(n["x"] for n in nodes)
    height = max(n["y"] + n["height"] for n in nodes) - min(n["y"] for n in nodes)
    report = {
        "status": "static-layout-only", "nodes": len(nodes), "edges": len(candidate["edges"]),
        "bounds": [width, height], "geometry_findings": 0,
        "source_sha256": sha256(source_bytes).hexdigest(),
        "assets": {name: sha256(data).hexdigest() for name, data in assets.items()},
        "native_and_human": "pending", "runtime_default_changed": False,
    }
    with (destination / "检查数据.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in report.items() if key not in {"source_sha256", "assets"}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
