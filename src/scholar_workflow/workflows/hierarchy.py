"""Hierarchical Obsidian projection: mirror a Zotero collection tree as a folder of
notes (option C). A hub node (has child collections) renders to `<parent>/<name>/index.md`
so its folder and its own note never appear as same-named siblings; a leaf node renders
to `<parent>/<name>.md`. A node's single managed block holds a MOC wikilink section (when
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


def _has_children(node: dict) -> bool:
    return bool(node.get("children"))


def _moc_section(children: list[dict], child_dir: str) -> str:
    """Wikilink list pointing at each child node's file (Obsidian `[[path|alias]]`).
    A child that is itself a hub lives at `<dir>/<name>/index.md`; a leaf child lives
    at `<dir>/<name>.md`, so the link target differs accordingly."""
    lines = []
    for c in children:
        cname = _safe_name(c["name"])
        base = f"{child_dir}/{cname}"
        target = f"{base}/index" if _has_children(c) else base
        lines.append(f"- [[{target}|{c['name']}]]")
    return "\n".join(lines)


def _node_body(node: dict, child_dir: str, port: int) -> str:
    parts = []
    if node.get("children"):
        parts.append(_moc_section(node["children"], child_dir))
    if node.get("papers"):
        parts.append(render_table(node["papers"], port))
    return "\n\n".join(parts)


def _walk(node: dict, parent_dir: str, port: int, plan: list[dict]) -> None:
    name = _safe_name(node["name"])
    child_dir = f"{parent_dir}/{name}"
    # Hub (has children) -> <dir>/<name>/index.md so the folder and its note don't
    # collide as same-named siblings in the file tree. Leaf -> <parent>/<name>.md.
    file_path = f"{child_dir}/index.md" if _has_children(node) else f"{parent_dir}/{name}.md"
    # Leaf (paper table) heading gets a "相关论文" suffix; hub (MOC) keeps the bare name.
    heading = node["name"] if _has_children(node) else f"{node['name']}相关论文"
    plan.append({
        "path": file_path,
        "heading": heading,
        "body": _node_body(node, child_dir, port),
        "papers": len(node.get("papers") or []),
    })
    for child in node.get("children") or []:
        _walk(child, child_dir, port, plan)


def plan_tree(tree: dict, root: str, port: int) -> list[dict]:
    """Pure planner (no filesystem): expand the collection tree under `root`
    (vault-relative) into an ordered list of node writes, each
    {path, heading, body, papers}. `tree` is the top node
    {name, collection_key, papers[], children[]}. Used by both dry-run and apply."""
    plan: list[dict] = []
    _walk(tree, root.rstrip("/"), port, plan)
    return plan


def project_tree(tree: dict, root: str, adapter, port: int) -> dict:
    """Apply plan_tree() to the vault via the adapter. Returns {files, papers}."""
    plan = plan_tree(tree, root, port)
    for item in plan:
        adapter.ensure_managed_block(PurePosixPath(item["path"]), item["heading"])
        adapter.update_managed_block(PurePosixPath(item["path"]), item["body"])
    return {"files": len(plan), "papers": sum(p["papers"] for p in plan)}
