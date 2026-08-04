"""Novelty-tree projection: a literature tree grouped by novelty.

Renders a variable-depth concept tree as ONE self-contained Obsidian note per tree: an
inline Mermaid overview followed by nested concept sections, each carrying its novelty
anchor, an optional 内容简介 (summary), and a 论文列表 subpaperlist. No H1 — the note
filename is the title. Two isomorphic tree types share this renderer, keyed off node kind:
a technical tree is 里程碑任务(task, ##) → pipeline(###) → module(####, optional) → 论文;
a challenge tree is challenge(##) → insight(###) → 论文. The flat 全集 paper list lives in
a separate 01-Paperlist.md ledger.

Internal nodes are abstract concepts; papers are leaves referenced by resource_id and
resolved against `paper_list` (the single metadata ledger). Each concept records its
novelty anchor = the first paper that proposed that task/pipeline. Multiple trees can
coexist under one topic folder as numbered index files (02-…, 03-…), assigned by the
skill; only the 01-Paperlist.md slot is fixed. Content outside the managed markers is
never touched (INV4); the same input re-renders byte-identically. The tree JSON is
assembled by the host LLM; the CLI owns all path/label computation so rendering is
MCP-free (INV18).
"""
from __future__ import annotations
from pathlib import PurePosixPath

from scholar_workflow.workflows.projection import render_table


_ANCHOR_LABEL = {
    "topic": "novelty",
    "task": "task novelty", "pipeline": "pipeline novelty", "module": "module novelty",
    "challenge": "challenge", "insight": "insight novelty",
}


def _by_id(doc: dict) -> dict:
    return {p["resource_id"]: p for p in doc.get("paper_list", [])}


def _resolve(refs: list[str], by_id: dict) -> list[dict]:
    """Map resource_id refs to their paper_list entries (skip unknown ids)."""
    return [by_id[r] for r in refs if r in by_id]


def _mermaid_label(text: str) -> str:
    """Quote-safe Mermaid label: strip newlines and swap the quote that would close
    the label string. Brackets are fine inside a quoted label."""
    return text.replace("\n", " ").replace('"', "'").strip()


_MERMAID_CLASSDEFS = (
    "  classDef task fill:#e8eaf6,stroke:#3949ab,stroke-width:2px;",
    "  classDef pipeline fill:#e0f2f1,stroke:#00897b;",
    "  classDef module fill:#f3e5f5,stroke:#8e24aa;",
    "  classDef challenge fill:#fce4ec,stroke:#c2185b,stroke-width:2px;",
    "  classDef insight fill:#e8f5e9,stroke:#43a047;",
    "  classDef paper fill:#ffffff,stroke:#bbbbbb;",
    "  classDef anchor fill:#fff3e0,stroke:#e65100,stroke-width:3px;",
)

# Node shape per kind. Top-level branches (task / challenge) are stadiums `([...])`;
# methods and ideas (pipeline / module / insight) are rectangles `[...]`. Papers are
# always rectangles, styled by the paper / anchor class instead.
_KIND_SHAPE = {
    "task": ('(["', '"])'),
    "challenge": ('(["', '"])'),
    "pipeline": ('["', '"]'),
    "module": ('["', '"]'),
    "insight": ('["', '"]'),
}


def render_mermaid(doc: dict) -> str:
    """A fenced ```mermaid flowchart of the concept tree (topic → … → paper). Membership
    edges only (not technical relations). Recurses to arbitrary concept depth, so a module
    under a pipeline — or an insight under a challenge — is drawn, not dropped. The
    novelty-anchor paper of each concept is marked with a ⭐ prefix and the `anchor` class.
    Deterministic in tree order — re-runs are identical."""
    by_id = _by_id(doc)
    lines = ["```mermaid", "flowchart TD", *_MERMAID_CLASSDEFS]
    counter = [0]

    def _node_id() -> str:
        nid = f"n{counter[0]}"
        counter[0] += 1
        return nid

    def _paper_nodes(node: dict, parent_id: str) -> None:
        anchor = node.get("novelty_anchor")
        for rid in node.get("papers") or []:
            entry = by_id.get(rid)
            title = entry.get("title") if entry else rid
            is_anchor = rid == anchor
            label = ("⭐ " if is_anchor else "") + _mermaid_label(title or rid)
            pid = _node_id()
            lines.append(f'  {pid}["{label}"]:::{"anchor" if is_anchor else "paper"}')
            lines.append(f"  {parent_id} --> {pid}")

    def _emit_concept(node: dict, parent_id: str | None) -> None:
        kind = node.get("kind", "")
        open_, close_ = _KIND_SHAPE.get(kind, ('["', '"]'))
        nid = _node_id()
        lines.append(f'  {nid}{open_}{_mermaid_label(node["name"])}{close_}:::{kind or "pipeline"}')
        if parent_id is not None:
            lines.append(f"  {parent_id} --> {nid}")
        for child in node.get("children") or []:
            _emit_concept(child, nid)
        _paper_nodes(node, nid)

    tree = doc.get("tree") or {}
    # The topic root is not drawn (the note filename is the title); its branch children
    # are edge-less roots. A doc whose root is already a branch (a bare task/challenge) is
    # emitted directly as the root.
    if tree.get("kind") == "topic":
        for child in tree.get("children") or []:
            _emit_concept(child, None)
    else:
        _emit_concept(tree, None)
    lines.append("```")
    return "\n".join(lines)


def _anchor_line(node: dict, by_id: dict) -> str:
    rid = node.get("novelty_anchor")
    if not rid:
        return ""
    entry = by_id.get(rid)
    title = entry.get("title") if entry else rid
    label = _ANCHOR_LABEL.get(node.get("kind", ""), "novelty")
    line = f"> **首创 ({label})**: {title}"
    note = node.get("anchor_note")
    if note:
        line += f" — {note}"
    return line


# Concept kind -> markdown heading depth inside the single tree note. The topic root
# emits no heading (the filename is the title). Both isomorphic trees share these depths:
# task/challenge are ##, pipeline/insight are ###, module is ####; a node's inner sections
# (内容简介 / 论文列表) sit one level deeper. Module bottoms out at #### + ##### inner,
# one shy of markdown's h6 — so trees don't nest a module under a module.
_KIND_DEPTH = {"task": 2, "challenge": 2, "pipeline": 3, "insight": 3, "module": 4}


def _concept_sections(node: dict, by_id: dict, port: int, depth: int,
                      out: list[str]) -> None:
    """Append this concept's markdown block, then recurse into children. A concept emits:
    its heading (## task / ### pipeline), its novelty-anchor line, an optional 内容简介
    (summary), and — when it holds paper leaves — a 论文列表 subpaperlist table."""
    kind = node.get("kind", "")
    hashes = "#" * depth
    if depth:
        out.append(f"{hashes} {node['name']}")
    anchor = _anchor_line(node, by_id)
    if anchor:
        out.append(anchor)
    summary = node.get("summary")
    if summary:
        out.append(f"{'#' * (depth + 1)} 内容简介")
        out.append(summary.strip())
    papers = _resolve(node.get("papers") or [], by_id)
    if papers:
        out.append(f"{'#' * (depth + 1)} 论文列表")
        out.append(render_table(papers, port, assets=True))
    for child in node.get("children") or []:
        _concept_sections(child, by_id, port, _KIND_DEPTH.get(child.get("kind", ""), depth + 1), out)


def render_tree_note(doc: dict, port: int) -> str:
    """One literature tree = one managed-block body: a Mermaid overview, the topic-root
    novelty anchor, then nested task(##)/pipeline(###) sections each carrying an optional
    内容简介 and a 论文列表 subpaperlist. No H1 — the note filename is the title. The tree
    references paper_list entries by resource_id; the flat ledger lives in 01-Paperlist.md."""
    by_id = _by_id(doc)
    tree = doc.get("tree") or {}
    parts: list[str] = [render_mermaid(doc)]
    root_anchor = _anchor_line(tree, by_id)
    if root_anchor:
        parts.append(root_anchor)
    root_summary = tree.get("summary")
    if root_summary:
        parts.append("## 内容简介")
        parts.append(root_summary.strip())
    for child in tree.get("children") or []:
        _concept_sections(child, by_id, port, _KIND_DEPTH.get(child.get("kind", ""), 2), parts)
    return "\n\n".join(parts)


def render_paperlist(doc: dict, port: int) -> str:
    """Body of the flat 全集 paper-list ledger (01-Paperlist.md): the whole collected set
    as one table (Assets column on), including papers with classified=false."""
    return render_table(doc.get("paper_list", []), port, assets=True)


def _tree_paper_count(node: dict) -> int:
    return len(node.get("papers") or []) + sum(
        _tree_paper_count(c) for c in node.get("children") or [])


def plan_novelty_tree(doc: dict, root: str, port: int, filename: str) -> list[dict]:
    """Pure planner (no filesystem). Produce the writes for ONE tree note under `root`
    (the topic folder, vault-relative). `filename` is the numbered index file the skill
    assigns (e.g. '02-世界模型文献树.md'). Returns [{path, heading, body, papers}] — a
    single entry; the flat paper list (01-Paperlist.md) is planned separately."""
    tree = doc.get("tree") or {}
    return [{
        "path": f"{root.rstrip('/')}/{filename}",
        "heading": "",  # no H1 — filename is the title
        "body": render_tree_note(doc, port),
        "papers": _tree_paper_count(tree),
    }]


def plan_paperlist(doc: dict, root: str, port: int,
                   filename: str = "01-Paperlist.md") -> list[dict]:
    """Pure planner for the flat paper-list ledger. `filename` is fixed at 01-Paperlist.md
    by convention (the CLI enforces the 01 slot)."""
    return [{
        "path": f"{root.rstrip('/')}/{filename}",
        "heading": "",
        "body": render_paperlist(doc, port),
        "papers": len(doc.get("paper_list", [])),
    }]


def _apply(plan: list[dict], adapter) -> dict:
    for item in plan:
        adapter.ensure_managed_block(PurePosixPath(item["path"]), item["heading"])
        adapter.update_managed_block(PurePosixPath(item["path"]), item["body"])
    return {"files": len(plan), "papers": sum(p["papers"] for p in plan)}


def project_novelty_tree(doc: dict, root: str, adapter, port: int,
                         filename: str) -> dict:
    """Write ONE tree note (filename) under root via the adapter. Returns {files, papers}."""
    return _apply(plan_novelty_tree(doc, root, port, filename), adapter)


def project_paperlist(doc: dict, root: str, adapter, port: int,
                      filename: str = "01-Paperlist.md") -> dict:
    """Write the flat 01-Paperlist.md ledger under root via the adapter."""
    return _apply(plan_paperlist(doc, root, port, filename), adapter)
