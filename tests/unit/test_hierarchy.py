"""Unit tests for the hierarchical folder-mirror projection (option C, INV4/INV18)."""
from __future__ import annotations
from scholar_workflow.adapters.obsidian import ObsidianAdapter
from scholar_workflow.workflows.hierarchy import plan_tree, project_tree

START, END = "<!-- s -->", "<!-- e -->"
PAPER = {
    "title": "Text2CAD", "authors": ["M. Khan"], "year": 2024, "venue": "arXiv",
    "importance": "★★★", "zotero_key": "8USWVHLD", "attachment_key": "S6LZUS6S",
    "arxiv": "2409.17106", "doi": "10.1/x", "synced": "2026-07-26",
}
# 科研项目 > 上汽标注 > text2cad(叶,含 1 篇);上汽标注 是中间枢纽
TREE = {
    "name": "科研项目", "collection_key": "AAA", "papers": [],
    "children": [{
        "name": "上汽标注", "collection_key": "BBB", "papers": [],
        "children": [{
            "name": "text2cad", "collection_key": "XYCCNXRW",
            "papers": [PAPER], "children": [],
        }],
    }],
}


def _adapter(tmp_path):
    return ObsidianAdapter(tmp_path, START, END)


def test_mirrors_tree_to_files(tmp_path):
    stats = project_tree(TREE, "paper", _adapter(tmp_path), 23128)
    assert stats == {"files": 3, "papers": 1}
    # hubs -> nested index.md; leaf -> <name>.md (no same-named sibling folder)
    assert (tmp_path / "paper/科研项目/index.md").exists()
    assert (tmp_path / "paper/科研项目/上汽标注/index.md").exists()
    assert (tmp_path / "paper/科研项目/上汽标注/text2cad.md").exists()


def test_hub_has_moc_wikilink_leaf_has_table(tmp_path):
    project_tree(TREE, "paper", _adapter(tmp_path), 23128)
    hub = (tmp_path / "paper/科研项目/index.md").read_text(encoding="utf-8")
    # child 上汽标注 is itself a hub -> link points at its index
    assert "- [[paper/科研项目/上汽标注/index|上汽标注]]" in hub
    assert "| Title | Authors |" not in hub  # hub has no paper table
    mid = (tmp_path / "paper/科研项目/上汽标注/index.md").read_text(encoding="utf-8")
    # child text2cad is a leaf -> link points at the file directly
    assert "- [[paper/科研项目/上汽标注/text2cad|text2cad]]" in mid
    leaf = (tmp_path / "paper/科研项目/上汽标注/text2cad.md").read_text(encoding="utf-8")
    assert "| Importance |" in leaf and "★★★" in leaf
    assert "http://127.0.0.1:23128/open/paper/S6LZUS6S" in leaf


def test_plan_tree_is_pure_and_matches_apply(tmp_path):
    plan = plan_tree(TREE, "paper", 23128)
    # pure: nothing written
    assert not list(tmp_path.iterdir())
    # leaf heading gets the 相关论文 suffix; hub headings stay bare
    assert plan[-1]["heading"] == "text2cad相关论文"
    assert plan[0]["heading"] == "科研项目"
    paths = [p["path"] for p in plan]
    assert paths == [
        "paper/科研项目/index.md",
        "paper/科研项目/上汽标注/index.md",
        "paper/科研项目/上汽标注/text2cad.md",
    ]
    assert sum(p["papers"] for p in plan) == 1
    # the leaf plan body is exactly what apply writes into the managed block
    project_tree(TREE, "paper", _adapter(tmp_path), 23128)
    leaf = (tmp_path / "paper/科研项目/上汽标注/text2cad.md").read_text(encoding="utf-8")
    assert plan[-1]["body"] in leaf


def test_idempotent_and_preserves_outside(tmp_path):
    a = _adapter(tmp_path)
    project_tree(TREE, "paper", a, 23128)
    leaf = tmp_path / "paper/科研项目/上汽标注/text2cad.md"
    leaf.write_text(leaf.read_text(encoding="utf-8") + "\n## my notes\nkeep\n", encoding="utf-8")
    first = leaf.read_text(encoding="utf-8")
    project_tree(TREE, "paper", a, 23128)  # re-run
    after = leaf.read_text(encoding="utf-8")
    assert "keep" in after
    assert after == first  # managed block unchanged, human note intact
