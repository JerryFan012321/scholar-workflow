"""Novelty-tree projection (per 彭思达 GAMES003 literature tree).

Renders a 3-level classification tree — 里程碑任务(task) → pipeline/representation
→ 论文(leaf) — as ONE self-contained Obsidian note per tree: an inline Mermaid overview
followed by nested task(##)/pipeline(###) sections, each carrying its novelty anchor, an
optional 内容简介 (summary), and a 论文列表 subpaperlist. No H1 — the note filename is the
title. The flat 全集 paper list lives in a separate 01-Paperlist.md ledger.

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


_ANCHOR_LABEL = {"topic": "novelty", "task": "task novelty", "pipeline": "pipeline novelty"}


def _by_id(doc: dict) -> dict:
    return {p["resource_id"]: p for p in doc.get("paper_list", [])}


def _resolve(refs: list[str], by_id: dict) -> list[dict]:
    """Map resource_id refs to their paper_list entries (skip unknown ids)."""
    return [by_id[r] for r in refs if r in by_id]


def _mermaid_label(text: str) -> str:
    """Quote-safe Mermaid label: strip newlines and swap the quote that would close
    the label string. Brackets are fine inside a quoted label."""
    return text.replace("\n", " ").replace('"', "'").strip()


def render_mermaid(doc: dict) -> str:
    """A fenced ```mermaid flowchart of task → pipeline → paper. Membership edges only
    (not technical relations). The novelty-anchor paper of each concept is marked with a
    ⭐ prefix and the `anchor` class. Deterministic in tree order — re-runs are identical."""
    by_id = _by_id(doc)
    lines = [
        "```mermaid",
        "flowchart TD",
        "  classDef task fill:#e8eaf6,stroke:#3949ab,stroke-width:2px;",
        "  classDef pipeline fill:#e0f2f1,stroke:#00897b;",
        "  classDef paper fill:#ffffff,stroke:#bbbbbb;",
        "  classDef anchor fill:#fff3e0,stroke:#e65100,stroke-width:3px;",
    ]
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

    def _emit_pipeline(node: dict, task_id: str) -> None:
        nid = _node_id()
        lines.append(f'  {nid}["{_mermaid_label(node["name"])}"]:::pipeline')
        lines.append(f"  {task_id} --> {nid}")
        _paper_nodes(node, nid)

    def _emit_task(node: dict) -> None:
        nid = _node_id()
        lines.append(f'  {nid}(["{_mermaid_label(node["name"])}"]):::task')
        for child in node.get("children") or []:
            _emit_pipeline(child, nid)
        _paper_nodes(node, nid)

    tree = doc.get("tree") or {}
    if tree.get("kind") == "task":
        _emit_task(tree)
    else:  # topic root → descend into its task children
        for child in tree.get("children") or []:
            _emit_task(child)
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
# emits no heading (the filename is the title); tasks are ##, pipelines are ###, and a
# pipeline's inner sections (内容简介 / 论文列表) are ####.
_KIND_DEPTH = {"task": 2, "pipeline": 3}


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
