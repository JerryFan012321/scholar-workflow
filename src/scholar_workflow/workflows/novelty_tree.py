"""Novelty-tree projection (per 彭思达 GAMES003 literature tree).

Renders a 3-level classification tree — 里程碑任务(task) → pipeline/representation
→ 论文(leaf) — into a folder of Obsidian managed-block notes, plus an inline Mermaid
overview and a flat 全集 paper list on the topic root note. Internal nodes are abstract
concepts; papers are leaves referenced by resource_id and resolved against `paper_list`
(the single metadata ledger). Each concept records its novelty anchor = the first paper
that proposed that task/pipeline.

Path layout matches hierarchy.py: a node with children is a hub → `<dir>/<name>/index.md`;
a leaf → `<parent>/<name>.md`. Content outside the managed markers is never touched
(INV4); the same input re-renders byte-identically. The tree JSON is assembled by the
host LLM; the CLI owns all path/label computation so rendering is MCP-free (INV18).
"""
from __future__ import annotations
from pathlib import PurePosixPath

from scholar_workflow.workflows.projection import render_table
from scholar_workflow.workflows.hierarchy import _safe_name


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


def _moc_section(children: list[dict], child_dir: str) -> str:
    """Wikilinks to child concept notes. A child with its own children is a hub at
    `<dir>/<name>/index`; a leaf child is at `<dir>/<name>`."""
    lines = []
    for c in children:
        cname = _safe_name(c["name"])
        base = f"{child_dir}/{cname}"
        target = f"{base}/index" if c.get("children") else base
        lines.append(f"- [[{target}|{c['name']}]]")
    return "\n".join(lines)


def _node_body(node: dict, child_dir: str, by_id: dict, port: int,
               is_root: bool, doc: dict) -> str:
    parts: list[str] = []
    if is_root:
        parts.append(render_mermaid(doc))
    anchor = _anchor_line(node, by_id)
    if anchor:
        parts.append(anchor)
    if node.get("children"):
        parts.append(_moc_section(node["children"], child_dir))
    papers = _resolve(node.get("papers") or [], by_id)
    if papers:
        parts.append(render_table(papers, port))
    if is_root:
        parts.append("### 全集论文（paper list）")
        parts.append(render_table(doc.get("paper_list", []), port))
    return "\n\n".join(parts)


def _walk(node: dict, parent_dir: str, by_id: dict, port: int,
          is_root: bool, doc: dict, plan: list[dict]) -> None:
    name = _safe_name(node["name"])
    child_dir = f"{parent_dir}/{name}"
    has_children = bool(node.get("children"))
    file_path = f"{child_dir}/index.md" if has_children else f"{parent_dir}/{name}.md"
    heading = node["name"] if has_children else f"{node['name']}相关论文"
    plan.append({
        "path": file_path,
        "heading": heading,
        "body": _node_body(node, child_dir, by_id, port, is_root, doc),
        "papers": len(node.get("papers") or []),
    })
    for child in node.get("children") or []:
        _walk(child, child_dir, by_id, port, False, doc, plan)


def plan_novelty_tree(doc: dict, root: str, port: int) -> list[dict]:
    """Pure planner (no filesystem): expand `doc` (literature-tree.schema.json) under
    `root` (vault-relative) into an ordered list of {path, heading, body, papers}. The
    topic root note carries the Mermaid overview and the flat paper list; each concept
    note carries its novelty anchor + MOC / paper table. Used by dry-run and apply."""
    by_id = _by_id(doc)
    plan: list[dict] = []
    tree = doc.get("tree") or {}
    _walk(tree, root.rstrip("/"), by_id, port, True, doc, plan)
    return plan


def project_novelty_tree(doc: dict, root: str, adapter, port: int) -> dict:
    """Apply plan_novelty_tree() to the vault via the adapter. Returns {files, papers}."""
    plan = plan_novelty_tree(doc, root, port)
    for item in plan:
        adapter.ensure_managed_block(PurePosixPath(item["path"]), item["heading"])
        adapter.update_managed_block(PurePosixPath(item["path"]), item["body"])
    return {"files": len(plan), "papers": sum(p["papers"] for p in plan)}
