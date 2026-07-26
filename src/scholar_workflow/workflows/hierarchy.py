"""Hierarchical Obsidian projection: mirror a Zotero collection tree as a folder of
notes (option C). Each node becomes one file at `<parent>/<name>.md`; its children live
in `<parent>/<name>/`. A node's single managed block holds a MOC wikilink section (when
it has child collections) followed by a 10-column paper table (when it has direct papers).

The tree JSON is produced by the host LLM via zotero-mcp; the CLI owns all path
computation so rendering is deterministic and MCP-free (INV18). Content outside the
managed markers is never touched (INV4).
"""
from __future__ import annotations
from pathlib import PurePosixPath

from scholar_workflow.workflows.projection import render_table


def _safe_name(name: str) -> str:
    """Collection names are trusted (user's own Zotero) but strip separators and
    dot-segments so a stray name can never escape the mirror root."""
    cleaned = name.replace("/", "／").replace("\\", "＼").strip()
    if cleaned in ("", ".", ".."):
        return "_"
    return cleaned


def _moc_section(children: list[dict], child_dir: str) -> str:
    """Wikilink list pointing at each child node's file (Obsidian `[[path|alias]]`)."""
    lines = []
    for c in children:
        cname = _safe_name(c["name"])
        target = f"{child_dir}/{cname}"
        lines.append(f"- [[{target}|{c['name']}]]")
    return "\n".join(lines)


def _node_body(node: dict, child_dir: str, port: int) -> str:
    parts = []
    if node.get("children"):
        parts.append(_moc_section(node["children"], child_dir))
    if node.get("papers"):
        parts.append(render_table(node["papers"], port))
    return "\n\n".join(parts)


def _render_node(node: dict, parent_dir: str, adapter, port: int, stats: dict) -> None:
    name = _safe_name(node["name"])
    file_path = f"{parent_dir}/{name}.md"
    child_dir = f"{parent_dir}/{name}"
    adapter.ensure_managed_block(PurePosixPath(file_path), node["name"])
    adapter.update_managed_block(PurePosixPath(file_path), _node_body(node, child_dir, port))
    stats["files"] += 1
    stats["papers"] += len(node.get("papers") or [])
    for child in node.get("children") or []:
        _render_node(child, child_dir, adapter, port, stats)


def project_tree(tree: dict, root: str, adapter, port: int) -> dict:
    """Render the whole collection tree under `root` (vault-relative). `tree` is the
    top node: {name, collection_key, papers[], children[]}. Returns {files, papers}."""
    stats = {"files": 0, "papers": 0}
    _render_node(tree, root.rstrip("/"), adapter, port, stats)
    return stats
