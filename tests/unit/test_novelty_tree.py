"""Unit tests for the novelty-tree projection (INV22; reuses INV4/INV18 machinery)."""
from __future__ import annotations
from scholar_workflow.adapters.obsidian import ObsidianAdapter
from scholar_workflow.workflows.novelty_tree import (
    plan_novelty_tree, project_novelty_tree, render_mermaid,
)

START, END = "<!-- s -->", "<!-- e -->"
PORT = 23128


def _paper(rid, title, classified, **extra):
    return {"resource_id": rid, "title": title, "classified": classified, **extra}


NERF = _paper("arxiv:2003.08934", "NeRF", True, attachment_key="S6LZUS6S",
              authors=["B. Mildenhall"], year=2020, importance="★★★")
MIP = _paper("arxiv:2103.13415", "Mip-NeRF", True, year=2021)  # non-anchor leaf
GS = _paper("arxiv:2308.04079", "3D Gaussian Splatting", True, year=2023)
UNCLASSIFIED = _paper("arxiv:2401.00001", "some collected follow-up", False)

DOC = {
    "generated_at": "2026-08-01T00:00:00Z",
    "topic": "novel view synthesis",
    "paper_list": [NERF, MIP, GS, UNCLASSIFIED],
    "tree": {
        "name": "novel view synthesis", "kind": "topic",
        "children": [{
            "name": "photorealistic reconstruction", "kind": "task",
            "novelty_anchor": "arxiv:2003.08934",
            "anchor_note": "first continuous volumetric field",
            "children": [
                {"name": "implicit neural field", "kind": "pipeline",
                 "novelty_anchor": "arxiv:2003.08934",
                 "papers": ["arxiv:2003.08934", "arxiv:2103.13415"]},
                {"name": "explicit gaussians", "kind": "pipeline",
                 "novelty_anchor": "arxiv:2308.04079", "papers": ["arxiv:2308.04079"]},
            ],
        }],
    },
}


def _adapter(tmp_path):
    return ObsidianAdapter(tmp_path, START, END)


def test_plan_is_pure(tmp_path):
    plan_novelty_tree(DOC, "35-literature-tree", PORT)
    assert not list(tmp_path.iterdir())


def test_path_mapping(tmp_path):
    plan = plan_novelty_tree(DOC, "35-literature-tree", PORT)
    paths = [p["path"] for p in plan]
    assert paths == [
        "35-literature-tree/novel view synthesis/index.md",
        "35-literature-tree/novel view synthesis/photorealistic reconstruction/index.md",
        "35-literature-tree/novel view synthesis/photorealistic reconstruction/implicit neural field.md",
        "35-literature-tree/novel view synthesis/photorealistic reconstruction/explicit gaussians.md",
    ]


def test_root_body_has_mermaid_moc_and_paperlist(tmp_path):
    project_novelty_tree(DOC, "35-literature-tree", _adapter(tmp_path), PORT)
    root = (tmp_path / "35-literature-tree/novel view synthesis/index.md").read_text(encoding="utf-8")
    assert "```mermaid" in root
    # MOC wikilink to the task hub (task has children -> /index)
    assert "- [[35-literature-tree/novel view synthesis/photorealistic reconstruction/index|photorealistic reconstruction]]" in root
    # flat paper list section + header + the unclassified paper still listed
    assert "全集论文" in root
    assert "| Title | Authors |" in root
    assert "some collected follow-up" in root


def test_pipeline_leaf_has_anchor_line_and_paper_row(tmp_path):
    project_novelty_tree(DOC, "35-literature-tree", _adapter(tmp_path), PORT)
    leaf = (tmp_path / "35-literature-tree/novel view synthesis/photorealistic reconstruction/implicit neural field.md").read_text(encoding="utf-8")
    assert "首创 (pipeline novelty)" in leaf and "NeRF" in leaf
    # render_table reuse: the PDF loopback link proves the shared row renderer ran
    assert "http://127.0.0.1:23128/open/paper/S6LZUS6S" in leaf


def test_task_hub_has_anchor_and_moc(tmp_path):
    project_novelty_tree(DOC, "35-literature-tree", _adapter(tmp_path), PORT)
    task = (tmp_path / "35-literature-tree/novel view synthesis/photorealistic reconstruction/index.md").read_text(encoding="utf-8")
    assert "首创 (task novelty)" in task
    assert "first continuous volumetric field" in task  # anchor_note appended
    assert "- [[35-literature-tree/novel view synthesis/photorealistic reconstruction/implicit neural field|implicit neural field]]" in task


def test_idempotent_and_preserves_outside(tmp_path):
    a = _adapter(tmp_path)
    project_novelty_tree(DOC, "35-literature-tree", a, PORT)
    leaf = tmp_path / "35-literature-tree/novel view synthesis/photorealistic reconstruction/explicit gaussians.md"
    leaf.write_text(leaf.read_text(encoding="utf-8") + "\n## my notes\nkeep\n", encoding="utf-8")
    first = leaf.read_text(encoding="utf-8")
    project_novelty_tree(DOC, "35-literature-tree", a, PORT)
    after = leaf.read_text(encoding="utf-8")
    assert "keep" in after
    assert after == first


def test_chinese_names_path_safe(tmp_path):
    doc = {
        "generated_at": "2026-08-01T00:00:00Z",
        "paper_list": [NERF],
        "tree": {
            "name": "三维重建", "kind": "topic",
            "children": [{
                "name": "神经辐射场", "kind": "task", "novelty_anchor": "arxiv:2003.08934",
                "children": [{"name": "隐式表示", "kind": "pipeline",
                              "papers": ["arxiv:2003.08934"]}],
            }],
        },
    }
    stats = project_novelty_tree(doc, "35-literature-tree", _adapter(tmp_path), PORT)
    assert stats["files"] == 3
    assert (tmp_path / "35-literature-tree/三维重建/神经辐射场/隐式表示.md").exists()


def test_render_mermaid_structure_and_determinism():
    m = render_mermaid(DOC)
    assert m.startswith("```mermaid\nflowchart TD")
    assert m.endswith("```")
    assert "classDef anchor" in m
    assert ":::task" in m and ":::pipeline" in m and ":::paper" in m
    assert "⭐ NeRF" in m  # anchor paper marked
    # membership edges only
    assert "-->" in m
    # deterministic
    assert render_mermaid(DOC) == m


def test_render_mermaid_escapes_labels():
    doc = {
        "generated_at": "2026-08-01T00:00:00Z",
        "paper_list": [_paper("x", 'Weird "quoted" [bracket] title', True)],
        "tree": {"name": "t", "kind": "topic", "children": [{
            "name": "task", "kind": "task", "novelty_anchor": "x", "papers": ["x"],
        }]},
    }
    m = render_mermaid(doc)
    assert 'quoted' in m
    # the closing-quote hazard is neutralized (no raw " inside the label)
    assert '"⭐ Weird \'quoted\' [bracket] title"' in m
