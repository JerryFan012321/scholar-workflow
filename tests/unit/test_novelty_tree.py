"""Unit tests for the novelty-tree projection (INV22/INV25; reuses INV4/INV18 machinery).

One tree = one self-contained note (Mermaid + nested concept sections with 内容简介 /
论文列表); the flat 全集 ledger is a separate 01-Paperlist.md. A variable-depth technical
tree (task/pipeline/module) and an isomorphic challenge tree (challenge/insight) share the
same renderer, keyed off node kind.
"""
from __future__ import annotations
from scholar_workflow.adapters.obsidian import ObsidianAdapter
from scholar_workflow.workflows.novelty_tree import (
    plan_novelty_tree, project_novelty_tree, plan_paperlist, project_paperlist,
    render_tree_note, render_paperlist, render_mermaid,
)

START, END = "<!-- s -->", "<!-- e -->"
PORT = 23128
ROOT = "世界模型 (World Models)"
TREE_FILE = "02-世界模型文献树.md"


def _paper(rid, title, classified, **extra):
    return {"resource_id": rid, "title": title, "classified": classified, **extra}


NERF = _paper("arxiv:2003.08934", "NeRF", True, attachment_key="S6LZUS6S",
              authors=["B. Mildenhall"], year=2020, importance="founding",
              asset_note="paper_assets/2020-Mildenhall-NeRF.md")
MIP = _paper("arxiv:2103.13415", "Mip-NeRF", True, year=2021, importance="representative")
GS = _paper("arxiv:2308.04079", "3D Gaussian Splatting", True, year=2023, importance="milestone")
UNCLASSIFIED = _paper("arxiv:2401.00001", "some collected follow-up", False)

DOC = {
    "generated_at": "2026-08-01T00:00:00Z",
    "topic": "novel view synthesis",
    "paper_list": [NERF, MIP, GS, UNCLASSIFIED],
    "tree": {
        "name": "novel view synthesis", "kind": "topic",
        "summary": "Rendering novel views of a scene from posed images.",
        "novelty_anchor": "arxiv:2003.08934",
        "children": [{
            "name": "photorealistic reconstruction", "kind": "task",
            "novelty_anchor": "arxiv:2003.08934",
            "anchor_note": "first continuous volumetric field",
            "children": [
                {"name": "implicit neural field", "kind": "pipeline",
                 "summary": "MLP-encoded radiance fields.",
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


# --- planners are pure (no filesystem) ---

def test_plan_is_pure(tmp_path):
    plan_novelty_tree(DOC, ROOT, PORT, TREE_FILE)
    plan_paperlist(DOC, ROOT, PORT)
    assert not list(tmp_path.iterdir())


def test_tree_is_single_file(tmp_path):
    plan = plan_novelty_tree(DOC, ROOT, PORT, TREE_FILE)
    assert [p["path"] for p in plan] == [f"{ROOT}/{TREE_FILE}"]
    assert plan[0]["heading"] == ""  # no H1 — filename is the title
    assert plan[0]["papers"] == 3  # 2 in implicit field + 1 gaussian


def test_paperlist_is_01_ledger(tmp_path):
    plan = plan_paperlist(DOC, ROOT, PORT)
    assert plan[0]["path"] == f"{ROOT}/01-Paperlist.md"
    assert plan[0]["papers"] == 4  # whole set incl. unclassified


# --- tree note body ---

def test_tree_note_sections_and_no_h1(tmp_path):
    body = render_tree_note(DOC, PORT)
    assert "```mermaid" in body
    assert "## photorealistic reconstruction" in body  # task = ##
    assert "### implicit neural field" in body  # pipeline = ###
    assert "#### 内容简介" in body and "MLP-encoded radiance fields." in body
    assert "#### 论文列表" in body
    assert "首创 (task novelty)" in body and "first continuous volumetric field" in body
    # topic-level summary rendered at ## depth, no repeated H1 title
    assert "## 内容简介" in body
    assert not body.lstrip().startswith("# ")


def test_tree_note_uses_assets_column_not_doi(tmp_path):
    body = render_tree_note(DOC, PORT)
    assert "| Assets |" in body  # subpaperlist carries Assets column
    assert "[[paper_assets/2020-Mildenhall-NeRF.md]]" in body
    assert "| DOI |" not in body
    assert "http://127.0.0.1:23128/open/paper/S6LZUS6S" in body  # render_table reuse


# --- paper list ledger body ---

def test_paperlist_body_has_all_and_stars(tmp_path):
    body = render_paperlist(DOC, PORT)
    assert "some collected follow-up" in body  # unclassified still listed
    assert "founding ★★★" in body and "milestone ★★" in body
    assert "| Assets |" in body and "| DOI |" not in body


# --- apply: idempotent, preserves outside content ---

def test_project_writes_and_is_idempotent(tmp_path):
    a = _adapter(tmp_path)
    project_paperlist(DOC, ROOT, a, PORT)
    project_novelty_tree(DOC, ROOT, a, PORT, TREE_FILE)
    tree = tmp_path / ROOT / TREE_FILE
    tree.write_text(tree.read_text(encoding="utf-8") + "\n## my notes\nkeep\n", encoding="utf-8")
    first = tree.read_text(encoding="utf-8")
    project_novelty_tree(DOC, ROOT, a, PORT, TREE_FILE)
    after = tree.read_text(encoding="utf-8")
    assert "keep" in after and after == first


def test_chinese_topic_path_safe(tmp_path):
    doc = {
        "generated_at": "2026-08-01T00:00:00Z",
        "paper_list": [NERF],
        "topic": "三维重建",
        "tree": {
            "name": "三维重建", "kind": "topic",
            "children": [{
                "name": "神经辐射场", "kind": "task", "novelty_anchor": "arxiv:2003.08934",
                "children": [{"name": "隐式表示", "kind": "pipeline",
                              "papers": ["arxiv:2003.08934"]}],
            }],
        },
    }
    stats = project_novelty_tree(doc, "三维重建", _adapter(tmp_path), PORT, "02-三维重建文献树.md")
    assert stats["files"] == 1
    assert (tmp_path / "三维重建/02-三维重建文献树.md").exists()


# --- mermaid (unchanged renderer) ---

def test_render_mermaid_structure_and_determinism():
    m = render_mermaid(DOC)
    assert m.startswith("```mermaid\nflowchart TD")
    assert m.endswith("```")
    assert "classDef anchor" in m
    assert ":::task" in m and ":::pipeline" in m and ":::paper" in m
    assert "⭐ NeRF" in m  # anchor paper marked
    assert "-->" in m  # membership edges only
    assert render_mermaid(DOC) == m  # deterministic


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
    assert '"⭐ Weird \'quoted\' [bracket] title"' in m


# --- module level (类3/类4): the 4th concept depth must render, not be dropped ---

MODULE_DOC = {
    "generated_at": "2026-08-01T00:00:00Z",
    "topic": "novel view synthesis",
    "paper_list": [NERF, MIP, GS],
    "tree": {
        "name": "novel view synthesis", "kind": "topic",
        "children": [{
            "name": "photorealistic reconstruction", "kind": "task",
            "novelty_anchor": "arxiv:2003.08934",
            "children": [{
                "name": "implicit neural field", "kind": "pipeline",
                "novelty_anchor": "arxiv:2003.08934",
                "children": [{
                    "name": "anti-aliasing", "kind": "module",
                    "summary": "Cone-tracing to prefilter the radiance field.",
                    "novelty_anchor": "arxiv:2103.13415",  # 类3: module seminal work
                    "anchor_note": "first to prefilter",
                    "papers": ["arxiv:2103.13415", "arxiv:2003.08934"],  # 2nd = 类4 improver
                }],
            }],
        }],
    },
}


def test_module_level_renders_in_mermaid():
    m = render_mermaid(MODULE_DOC)
    assert ":::module" in m  # the module node is drawn, not dropped
    assert "anti-aliasing" in m
    # its papers hang off the module, including the 类4 improver
    assert "⭐ Mip-NeRF" in m  # module anchor (类3) starred
    assert "NeRF" in m  # 类4 improver present as ordinary leaf


def test_module_section_depth_and_anchor_label():
    body = render_tree_note(MODULE_DOC, PORT)
    assert "### implicit neural field" in body  # pipeline = ###
    assert "#### anti-aliasing" in body  # module = ####
    assert "##### 内容简介" in body  # module's inner sections one deeper
    assert "##### 论文列表" in body
    assert "首创 (module novelty)" in body and "first to prefilter" in body


# --- challenge tree: isomorphic to the technical tree, same renderer ---

CHALLENGE_DOC = {
    "generated_at": "2026-08-01T00:00:00Z",
    "topic": "world models",
    "paper_list": [NERF, GS],
    "tree": {
        "name": "world models", "kind": "topic",
        "children": [{
            "name": "long-horizon 3D consistency", "kind": "challenge",
            "children": [{
                "name": "persistent scene memory", "kind": "insight",
                "novelty_anchor": "arxiv:2003.08934",
                "papers": ["arxiv:2003.08934", "arxiv:2308.04079"],
            }],
        }],
    },
}


def test_challenge_tree_uses_same_renderer():
    m = render_mermaid(CHALLENGE_DOC)
    assert ":::challenge" in m and ":::insight" in m
    assert "long-horizon 3D consistency" in m and "persistent scene memory" in m
    body = render_tree_note(CHALLENGE_DOC, PORT)
    assert "## long-horizon 3D consistency" in body  # challenge = ## (same as task)
    assert "### persistent scene memory" in body  # insight = ### (same as pipeline)
    assert "首创 (insight novelty)" in body
    # same file/table machinery: a challenge tree renders its own numbered note
    plan = plan_novelty_tree(CHALLENGE_DOC, ROOT, PORT, "03-世界模型挑战洞见树.md")
    assert plan[0]["path"] == f"{ROOT}/03-世界模型挑战洞见树.md"


def test_paper_in_multiple_trees_shares_ledger():
    # INV25: the same resource_id may appear in both the technical and the challenge tree;
    # each renders independently against the shared paper_list, no collision.
    assert "arxiv:2003.08934" in {p["resource_id"] for p in MODULE_DOC["paper_list"]}
    tech = render_tree_note(MODULE_DOC, PORT)
    chal = render_tree_note(CHALLENGE_DOC, PORT)
    assert "NeRF" in tech and "NeRF" in chal  # same paper, two trees, both render
