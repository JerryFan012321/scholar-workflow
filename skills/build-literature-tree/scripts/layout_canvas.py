"""Lay out prepared field-view Markdown as editable JSON Canvas, without file I/O.

Read version 1 JSON from stdin and emit one complete Canvas to stdout. This tool
neither classifies papers nor verifies their sources. Unknown fields, unsafe
structure, resource-limit violations and invalid geometry fail with exit code 2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata

MAX_DEPTH = 8
MAX_TEXT = 12_000
MAX_INPUT_BYTES = 4 * 1024 * 1024
_GAP_X = 96
_GAP_Y = 48
_DESC_GAP = 16
_PAD = 24
_LINE = 28
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$")
_HEX = re.compile(r"^[0-9a-f]{16}$")
_SIDES = {"top", "right", "bottom", "left"}
_COLORS = ("#87aaa0", "#b69b6f", "#879bb9", "#a18dae", "#769eaa")


def _fields(value: object, allowed: set[str], required: set[str], where: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")  # noqa: TRY004 - Public input-error contract.
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{where} field names must be strings")
    unknown, missing = set(value) - allowed, required - set(value)
    if unknown or missing:
        raise ValueError(f"{where}: unknown fields {sorted(unknown)}; missing {sorted(missing)}")
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT:
        raise ValueError(f"{where} must contain 1..{MAX_TEXT} characters of prepared Markdown")
    if any(ord(char) < 32 and char not in "\n\t\r" for char in value):
        raise ValueError(f"{where} contains a control character")
    return value


def _input(doc: object) -> dict:
    value = _fields(doc, {"schema_version", "view", "root", "branches", "spine", "title", "legend"},
                    {"schema_version", "view"}, "input")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    view = value["view"]
    if view not in ("literature", "technical", "challenge"):
        raise ValueError("view must be literature, technical or challenge")
    seen: set[str] = set()

    def node(raw, depth, *, role=None):
        if depth > MAX_DEPTH:
            raise ValueError(f"input nesting exceeds {MAX_DEPTH}")
        fields = {"id", "text", "children"}
        if view == "literature":
            fields |= {"description", "role", "section_label"}
        required = {"id", "text"} | ({"description", "role"} if role else set())
        item = _fields(raw, fields, required, "node")
        key = item["id"]
        if not isinstance(key, str) or not _ID.fullmatch(key) or key in seen:
            raise ValueError("node id must be a unique, path-free layout key of at most 128 characters")
        seen.add(key)
        _text(item["text"], f"node {key} text")
        children = item.get("children", [])
        if not isinstance(children, list):
            raise ValueError(f"node {key} children must be an array")  # noqa: TRY004 - Public input-error contract.
        if view == "literature":
            if item.get("role") != role:
                raise ValueError(f"node {key} must have role {role}")
            _text(item["description"], f"node {key} description")
            if "section_label" in item:
                if depth != 0 or "title" not in value:
                    raise ValueError("section_label requires a framed literature spine entry")
                _text(item["section_label"], f"node {key} section_label")
            child_role = "pipeline" if role == "milestone" else "local"
        else:
            child_role = None
            leaf_depth = 2 if view == "technical" else 3
            if depth > leaf_depth or (depth == leaf_depth and children):
                raise ValueError(f"{view} has a fixed concept-to-paper depth of {leaf_depth}")
            if 0 < depth < leaf_depth and not children:
                raise ValueError(f"node {key} is missing its required descendants")
        for child in children:
            node(child, depth + 1, role=child_role)

    if view == "literature":
        base = {"schema_version", "view", "spine"}
        if set(value) not in (base, base | {"title", "legend"}):
            raise ValueError("literature requires spine, optionally with both title and legend")
        for name in ("title", "legend"):
            if name in value:
                _text(value[name], name)
        rows = value["spine"]
        if not isinstance(rows, list):
            raise ValueError("spine must be an array")
        for row in rows:
            node(row, 0, role="milestone")
    else:
        if set(value) != {"schema_version", "view", "root", "branches"}:
            raise ValueError("technical/challenge require root and branches, not spine")
        root = _fields(value["root"], {"id", "text"}, {"id", "text"}, "root")
        rows = value["branches"]
        if not isinstance(rows, list):
            raise ValueError("branches must be an array")
        node(dict(root, children=rows), 0)
    return value


def _stable(kind: str, view: str, key: str) -> str:
    return hashlib.sha256(f"field-canvas-v1:{kind}:{view}:{key}".encode()).hexdigest()[:16]


def _soft_wrap(text: str) -> str:
    """Add discretionary breaks to long display words, never to link destinations."""
    def words(value):
        return re.sub(r"[\w-]{31,}", lambda m: "\u200b".join(
            m[0][index:index + 24] for index in range(0, len(m[0]), 24)), value)

    def link_end(opening):
        depth, index = 1, opening + 1
        while index < len(text):
            char = text[index]
            if char in "\r\n":
                return None
            if char == "\\":
                index += 2
                continue
            if char == "<" or (char in "\"'" and text[index - 1].isspace()):
                closing = ">" if char == "<" else char
                end = text.find(closing, index + 1)
                if end < 0 or "\n" in text[index:end]:
                    return None
                index = end + 1
                continue
            depth += (char == "(") - (char == ")")
            if depth == 0:
                return index + 1
            index += 1
        return None

    pattern = re.compile(r"!?\[\[[^\]\n]+\]\]|`[^`\n]*`|[A-Za-z][A-Za-z0-9+.-]*://\S+|!?\[[^\]\n]*\]\(")
    parts, cursor = [], 0
    while match := pattern.search(text, cursor):
        parts.append(words(text[cursor:match.start()]))
        part, end = match[0], match.end()
        if part.endswith("]("):
            end = link_end(match.end() - 1)
            if end is None:
                # Unparsed complex Markdown is safer unchanged than with an altered target.
                end = text.find("\n", match.end())
                end = len(text) if end < 0 else end
                parts.append(text[match.start():end])
            else:
                label_end = match.end() - 2
                parts.append(words(text[match.start():label_end]) + text[label_end:end])
        elif part.startswith(("[[", "![[")) and "|" in part:
            target, label = part.rsplit("|", 1)
            parts.append(target + "|" + words(label[:-2]) + "]]")
        else:
            parts.append(part)
        cursor = end
    parts.append(words(text[cursor:]))
    return "".join(parts)


def _visible(text: str) -> str:
    text = re.sub(r"!?\[\[([^\]\n]+)\]\]", lambda m: m[1].split("|")[-1], text)
    text = re.sub(r"!?\[([^\]\n]*)\]\([^\n]*?\)", r"\1", text)
    return re.sub(r"[*_`#>]", "", text).replace("\u200b", "")


def _size(text: str, width: int, *, title: bool = False, header: bool = False) -> tuple[int, int]:
    # Timeline titles use 22px/1.45 typography and compact padding.
    padding, cjk, latin, line_height = (12, 22, 12, 32) if title else (_PAD, 20, 11, _LINE)
    lines = 0
    capacity = width - 2 * _PAD
    if header:
        height = _LINE  # One spare click line; the header's native padding is zero.
        for raw in text.split("\n"):
            if not raw.strip():
                height += 8
                continue
            cjk, latin, line_height = (40, 22, 52) if raw.startswith("# ") else (20, 11, 28)
            pixels = sum(cjk if unicodedata.east_asian_width(c) in "WF" else latin for c in _visible(raw))
            height += max(1, math.ceil(pixels / capacity)) * line_height
        return width, math.ceil(height / 16) * 16
    for line in _visible(text).split("\n"):
        pixels = sum(cjk if unicodedata.east_asian_width(c) in "WF" else latin for c in line)
        lines += max(1, math.ceil(pixels / capacity))
    height = math.ceil((2 * padding + (lines + 1) * line_height) / 16) * 16
    return width, height


class _Canvas:
    def __init__(self, view: str):
        self.view = view
        self.style = "swLit" if view == "literature" else "swMind"
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self.points: dict[tuple[int, int], str] = {}

    def card(self, key, text, x, y, width, height, role, color):
        namespace = "junction" if role == "junction" else "description" if role == "desc" else "node"
        if role in {"header", "legend", "label"}:
            namespace = "decoration:" + role
        identifier = _stable(namespace, self.view, key)
        self.nodes.append({"id": identifier, "type": "text", "text": _soft_wrap(text),
                           "x": x, "y": y, "width": width, "height": height,
                           "color": color, "styleAttributes": {self.style: role}})
        if role in {"header", "legend", "label"}:
            self.nodes[-1]["styleAttributes"]["border"] = "invisible"
        return self.nodes[-1]

    def point(self, key: str, x: int, y: int, color: str) -> dict:
        position = (x, y)
        if position in self.points:
            return self.by_id(self.points[position])
        point = self.card("routing:" + key, "", x - 1, y - 1, 2, 2, "junction", color)
        self.points[position] = point["id"]
        return point

    def by_id(self, identifier):
        return next(node for node in self.nodes if node["id"] == identifier)

    def edge(self, source, from_side, target, to_side, color):
        identifier = _stable("edge", self.view,
                             f"{source['id']}:{from_side}:{target['id']}:{to_side}")
        self.edges.append({"id": identifier, "fromNode": source["id"],
                           "fromSide": from_side, "toNode": target["id"],
                           "toSide": to_side, "fromEnd": "none", "toEnd": "none",
                           "fromFloating": False, "toFloating": False,
                           "color": color, "styleAttributes": {"pathfindingMethod": "square"}})

    def fan(self, parent, children, direction, color, *, bus=None):
        """Use a shared, explicit bus; each emitted edge is one exact straight segment."""
        if not children:
            return
        out_side, in_side = ("right", "left") if direction > 0 else ("left", "right")
        px, py = _anchor(parent, out_side)
        bus_x = px + direction * 40 if bus is None else bus
        route_key = parent["id"] + (":right" if direction > 0 else ":left")
        levels = {py: self.point(route_key + ":parent", bus_x, py, color)}
        for child in children:
            cy = _anchor(child, in_side)[1]
            if cy not in levels:
                levels[cy] = self.point(route_key + ":child:" + child["id"], bus_x, cy, color)
        self.edge(parent, out_side, levels[py], in_side, color)
        for upper, lower in zip(sorted(levels), sorted(levels)[1:]):
            self.edge(levels[upper], "bottom", levels[lower], "top", color)
        for child in children:
            cy = _anchor(child, in_side)[1]
            self.edge(levels[cy], out_side, child, in_side, color)

    def result(self):
        return {"nodes": self.nodes, "edges": self.edges}


def _anchor(node: dict, side: str) -> tuple[int, int]:
    x, y, width, height = (node[key] for key in ("x", "y", "width", "height"))
    return {"left": (x, y + height // 2), "right": (x + width, y + height // 2),
            "top": (x + width // 2, y), "bottom": (x + width // 2, y + height)}[side]


def _radial(doc: dict) -> dict:
    canvas = _Canvas(doc["view"])
    leaf_depth = 2 if doc["view"] == "technical" else 3
    widths = {depth: 370 if depth == leaf_depth else 340 for depth in range(4)}
    measures = {}

    def measure(item, depth):
        width, own = _size(item["text"], widths[depth])
        children = item.get("children", [])
        total = sum(measure(child, depth + 1) for child in children)
        total += max(0, len(children) - 1) * _GAP_Y
        measures[item["id"]] = (width, own, max(own, total))
        return max(own, total)

    sides = {1: [], -1: []}
    totals = {1: 0, -1: 0}
    for index, branch in enumerate(doc["branches"]):
        height = measure(branch, 1)
        side = 1 if totals[1] <= totals[-1] else -1
        sides[side].append((branch, _COLORS[index % len(_COLORS)]))
        totals[side] += height + (_GAP_Y if len(sides[side]) > 1 else 0)
    root_w, root_h = _size(doc["root"]["text"], widths[0])
    root = canvas.card(doc["root"]["id"], doc["root"]["text"], -root_w // 2,
                       -root_h // 2, root_w, root_h, "root", "#6c91ac")

    def place(item, depth, area_top, direction, color):
        width, height, span = measures[item["id"]]
        distance = root_w // 2 + _GAP_X + sum(widths[d] + _GAP_X for d in range(1, depth))
        x = distance if direction > 0 else -distance - width
        center = area_top + span // 2
        node = canvas.card(item["id"], item["text"], x, center - height // 2,
                           width, height, "detail" if depth >= 2 else "branch", color)
        rows = item.get("children", [])
        child_total = sum(measures[c["id"]][2] for c in rows) + max(0, len(rows) - 1) * _GAP_Y
        cursor = center - child_total // 2
        children = []
        for child in rows:
            children.append(place(child, depth + 1, cursor, direction, color))
            cursor += measures[child["id"]][2] + _GAP_Y
        canvas.fan(node, children, direction, color)
        return node

    for side in (1, -1):
        cursor = -totals[side] // 2
        children = []
        for branch, color in sides[side]:
            children.append(place(branch, 1, cursor, side, color))
            cursor += measures[branch["id"]][2] + _GAP_Y
        canvas.fan(root, children, side, "#7c909d")
    return canvas.result()


def _literature(doc: dict) -> dict:
    canvas = _Canvas("literature")
    if not doc["spine"]:
        _literature_framing(canvas, doc)
        return canvas.result()
    title_width, width = 300, 360
    measures = {}

    def measure(item):
        _, title_h = _size(item["text"], title_width, title=True)
        _, desc_h = _size(item["description"], width)
        own = title_h + _DESC_GAP + desc_h
        rows = item.get("children", [])
        children = sum(measure(child) for child in rows) + max(0, len(rows) - 1) * _GAP_Y
        depth = 1 + max((measures[child["id"]][4] for child in rows), default=0)
        measures[item["id"]] = (title_h, desc_h, own, max(own, children), depth)
        return max(own, children)

    for milestone in doc["spine"]:
        measure(milestone)
    forest_top = max(measures[item["id"]][0] // 2 + _DESC_GAP + measures[item["id"]][1]
                     for item in doc["spine"]) + _GAP_Y

    def cards(item, x, top):
        title_h, desc_h, _, _, _ = measures[item["id"]]
        role = item["role"]
        color = {"milestone": "#7d9db4", "pipeline": "#87aaa0", "local": "#b4916f"}[role]
        title = canvas.card(item["id"], item["text"], x, top, title_width, title_h, role, color)
        canvas.card("description:" + item["id"], item["description"], x,
                    top + title_h + _DESC_GAP, width, desc_h, "desc", "#a8b2ba")
        return title

    def place(item, x, top):
        _, _, own, span, _ = measures[item["id"]]
        block_top = top + (span - own) // 2
        title = cards(item, x, block_top)
        rows = item.get("children", [])
        total = sum(measures[c["id"]][3] for c in rows) + max(0, len(rows) - 1) * _GAP_Y
        cursor = top + (span - total) // 2
        children = []
        for child in rows:
            children.append(place(child, x + width + _GAP_X, cursor))
            cursor += measures[child["id"]][3] + _GAP_Y
        canvas.fan(title, children, 1, "#7c909d", bus=x + width + 40)
        return title

    previous = None
    x = 0
    for item in doc["spine"]:
        title_h, _, _, _, depth = measures[item["id"]]
        title = cards(item, x, -title_h // 2)
        if previous is not None:
            # Reuse a branch junction already on the spine rather than overlapping edges.
            canvas.edge(previous, "right", title, "left", "#7c909d")
        rows = item.get("children", [])
        cursor = forest_top
        children = []
        for child in rows:
            children.append(place(child, x + width + _GAP_X, cursor))
            cursor += measures[child["id"]][3] + _GAP_Y
        canvas.fan(title, children, 1, "#7c909d", bus=x + width + 40)
        previous = canvas.by_id(canvas.points[(x + width + 40, 0)]) if children else title
        x += depth * (width + _GAP_X)
    _literature_framing(canvas, doc)
    return canvas.result()


def _literature_framing(canvas: _Canvas, doc: dict) -> None:
    """Keep prepared reading context visible without changing paper topology."""
    if "title" not in doc:
        return
    for item in doc["spine"]:
        if "section_label" in item:
            title = canvas.by_id(_stable("node", "literature", item["id"]))
            width, height = _size(item["section_label"], 360)
            canvas.card("section:" + item["id"], item["section_label"], title["x"],
                        title["y"] - _GAP_Y - height, width, height, "label", "#7c8b98")
    left = min((node["x"] for node in canvas.nodes), default=0)
    right = max((node["x"] + node["width"] for node in canvas.nodes), default=600)
    top = min((node["y"] for node in canvas.nodes), default=0)
    bottom = max((node["y"] + node["height"] for node in canvas.nodes), default=0)
    width = max(600, min(1580, right - left))
    _, header_height = _size(doc["title"], width, header=True)
    _, legend_height = _size(doc["legend"], width)
    canvas.card("header", doc["title"], left, top - _GAP_Y - header_height,
                width, header_height, "header", "#6c91ac")
    canvas.card("legend", doc["legend"], left, bottom + _GAP_Y,
                width, legend_height, "legend", "#6a7c8d")


def _intersection(a, b):
    """Return a crossing/touch point, 'overlap', or None for exact axis-aligned segments."""
    p, q = a
    r, s = b
    ah, bh = p[1] == q[1], r[1] == s[1]
    if ah == bh:
        fixed, varying = (1, 0) if ah else (0, 1)
        if p[fixed] != r[fixed]:
            return None
        lo = max(min(p[varying], q[varying]), min(r[varying], s[varying]))
        hi = min(max(p[varying], q[varying]), max(r[varying], s[varying]))
        if lo > hi:
            return None
        if lo < hi:
            return "overlap"
        return (lo, p[1]) if ah else (p[0], lo)
    horizontal, vertical = (a, b) if ah else (b, a)
    point = (vertical[0][0], horizontal[0][1])
    if (min(horizontal[0][0], horizontal[1][0]) <= point[0] <= max(horizontal[0][0], horizontal[1][0])
            and min(vertical[0][1], vertical[1][1]) <= point[1] <= max(vertical[0][1], vertical[1][1])):
        return point
    return None


def validate_canvas(doc: object) -> list[str]:
    """Check actual segment endpoints, not an editor's approximate routing promise."""
    errors = []
    if (not isinstance(doc, dict) or not {"nodes", "edges"}.issubset(doc)
            or set(doc) - {"nodes", "edges", "metadata"}):
        return ["Canvas must contain nodes and edges, with optional Advanced Canvas metadata"]
    # Mirror the shared envelope without a package dependency; metadata is not identity.
    metadata = doc.get("metadata")
    if "metadata" in doc and (
        not isinstance(metadata, dict)
        or set(metadata) != {"version", "frontmatter"}
        or not isinstance(metadata["version"], str)
        or not metadata["version"].strip()
        or len(metadata["version"]) > 64
        or not isinstance(metadata["frontmatter"], dict)
        or any(not isinstance(key, str) for key in metadata["frontmatter"])
    ):
        return ["Advanced Canvas metadata is invalid"]
    nodes, edges = doc["nodes"], doc["edges"]
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["nodes and edges must be arrays"]
    by_id = {}
    identifiers = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("invalid node object")
            continue
        identifier = node.get("id")
        if not isinstance(identifier, str) or not _HEX.fullmatch(identifier) or identifier in identifiers:
            errors.append("invalid or duplicate node id")
            continue
        identifiers.add(identifier)
        geometry = all(type(node.get(k)) is int for k in ("x", "y", "width", "height"))
        if not geometry or node["width"] <= 0 or node["height"] <= 0:
            errors.append(f"{identifier}: geometry must use positive integer dimensions")
            continue
        if node["width"] % 2 or node["height"] % 2:
            errors.append(f"{identifier}: dimensions must give exact integer midpoint anchors")
            continue
        if node.get("type") != "text" or not isinstance(node.get("text"), str):
            errors.append(f"{identifier}: only editable text nodes are supported")
        by_id[identifier] = node
    rectangles = list(by_id.values())
    for index, node in enumerate(rectangles):
        for other in rectangles[index + 1:]:
            if (max(node["x"], other["x"]) < min(node["x"] + node["width"], other["x"] + other["width"])
                    and max(node["y"], other["y"]) < min(node["y"] + node["height"], other["y"] + other["height"])):
                errors.append(f"overlapping nodes: {node['id']} and {other['id']}")
    segments = []
    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("invalid edge object")
            continue
        identifier = edge.get("id")
        if not isinstance(identifier, str) or not _HEX.fullmatch(identifier) or identifier in identifiers:
            errors.append("invalid or duplicate edge id")
        identifiers.add(identifier) if isinstance(identifier, str) else None
        source_id, target_id = edge.get("fromNode"), edge.get("toNode")
        source = by_id.get(source_id) if isinstance(source_id, str) else None
        target = by_id.get(target_id) if isinstance(target_id, str) else None
        if source is None or target is None:
            errors.append(f"{identifier}: dangling edge")
            continue
        if (not isinstance(edge.get("fromSide"), str) or edge["fromSide"] not in _SIDES
                or not isinstance(edge.get("toSide"), str) or edge["toSide"] not in _SIDES):
            errors.append(f"{identifier}: explicit fixed sides are required")
            continue
        if edge.get("fromEnd") != "none" or edge.get("toEnd") != "none":
            errors.append(f"{identifier}: arrowless ends are required")
        if any(edge.get(key) is not None and edge[key] is not False
               for key in ("fromFloating", "toFloating")):
            errors.append(f"{identifier}: floating endpoints are not allowed")
        style = edge.get("styleAttributes")
        if not isinstance(style, dict) or style.get("pathfindingMethod") != "square":
            errors.append(f"{identifier}: square pathfinding is required")
        p, q = _anchor(source, edge["fromSide"]), _anchor(target, edge["toSide"])
        if p == q or (p[0] != q[0] and p[1] != q[1]):
            errors.append(f"{identifier}: actual segment is zero-length or nonorthogonal")
            continue
        def outward(side, origin, end):
            dx, dy = end[0] - origin[0], end[1] - origin[1]
            return {"left": dx < 0 and dy == 0, "right": dx > 0 and dy == 0,
                    "top": dy < 0 and dx == 0, "bottom": dy > 0 and dx == 0}[side]

        if not outward(edge["fromSide"], p, q) or not outward(edge["toSide"], q, p):
            errors.append(f"{identifier}: segment enters an endpoint node through its interior")
            continue
        segments.append((edge, (p, q)))
        for node in rectangles:
            if node["id"] in (source["id"], target["id"]):
                continue
            left, top, right, bottom = node["x"], node["y"], node["x"] + node["width"], node["y"] + node["height"]
            if p[1] == q[1]:
                blocked = top <= p[1] <= bottom and max(min(p[0], q[0]), left) <= min(max(p[0], q[0]), right)
            else:
                blocked = left <= p[0] <= right and max(min(p[1], q[1]), top) <= min(max(p[1], q[1]), bottom)
            if blocked:
                errors.append(f"{identifier}: segment intersects unrelated node {node['id']}")
    for index, (edge, segment) in enumerate(segments):
        for other, other_segment in segments[index + 1:]:
            hit = _intersection(segment, other_segment)
            if hit is None:
                continue
            shared = {edge["fromNode"], edge["toNode"]} & {other["fromNode"], other["toNode"]}
            if hit != "overlap" and shared and hit in segment and hit in other_segment:
                continue
            errors.append(f"crossing, touching or overlapping segments: {edge['id']} and {other['id']}")
    return errors


def render(doc: object) -> dict:
    """Return a deterministic complete Canvas, or fail without modifying the input."""
    checked = _input(doc)
    result = _literature(checked) if checked["view"] == "literature" else _radial(checked)
    errors = validate_canvas(result)
    if errors:
        raise ValueError("layout failed exact geometry checks: " + "; ".join(errors[:12]))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
        if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError(f"stdin exceeds {MAX_INPUT_BYTES} bytes")
        result = render(json.loads(raw))
    except (ValueError, TypeError, RecursionError) as exc:
        print(f"Canvas layout refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
