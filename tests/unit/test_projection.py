"""Unit tests for Obsidian projection rendering (GOALS INV4/INV17/INV18)."""
from __future__ import annotations
from pathlib import Path
from scholar_workflow.adapters.obsidian import ObsidianAdapter
from scholar_workflow.workflows.projection import format_row, project_obsidian

START, END = "<!-- s -->", "<!-- e -->"
ENTRY = {
    "title": "Text2CAD", "authors": ["A. One", "B. Two"], "year": 2024,
    "venue": "NeurIPS", "importance": "milestone", "zotero_key": "8USWVHLD",
    "attachment_key": "S6LZUS6S", "arxiv": "2409.17106", "doi": "10.1/x",
    "synced": "2026-07-26", "asset_note": "paper_assets/2024-One-Text2CAD.md",
}


def _adapter(tmp_path):
    return ObsidianAdapter(tmp_path, START, END)


def test_format_row_links_and_columns():
    row = format_row(ENTRY, port=23128)
    assert row.count("|") == 10  # 9 cells (DOI dropped) -> 10 pipes
    assert "http://127.0.0.1:23128/open/paper/S6LZUS6S" in row
    assert "zotero://select/items/@8USWVHLD" in row
    assert "A. One; B. Two" in row
    assert "milestone ★★" in row  # importance text + star badge
    assert "10.1/x" not in row  # DOI is no longer a column


def test_format_row_assets_column():
    plain = format_row(ENTRY, port=1)
    withassets = format_row(ENTRY, port=1, assets=True)
    assert withassets.count("|") == plain.count("|") + 1  # one extra column
    assert "[[paper_assets/2024-One-Text2CAD.md]]" in withassets
    assert "[[paper_assets" not in plain  # not present without the flag


def test_importance_badge_idempotent_and_passthrough():
    # already-starred or unknown values pass through unchanged (no double badge)
    assert "★★ ★★" not in format_row({**ENTRY, "importance": "milestone ★★"}, port=1)
    assert format_row({"title": "x", "importance": "misc"}, port=1).count("misc") == 1


def test_format_row_escapes_pipe():
    row = format_row({**ENTRY, "title": "A | B"}, port=1)
    assert "A \\| B" in row


def test_format_row_tolerates_missing_fields():
    row = format_row({"title": "Bare"}, port=1)
    assert row.startswith("| Bare |")  # no crash, empty cells for the rest


def test_project_creates_file_and_preserves_outside(tmp_path):
    idx = "31-paper/index.md"
    n = project_obsidian([ENTRY], idx, "Papers", _adapter(tmp_path), 23128)
    assert n == 1
    full = tmp_path / idx
    # append a manual note outside the managed block, then re-project
    full.write_text(full.read_text() + "\n## notes\nkeep me\n")
    project_obsidian([ENTRY], idx, "Papers", _adapter(tmp_path), 23128)
    assert "keep me" in full.read_text()


def test_project_is_idempotent(tmp_path):
    idx = "31-paper/index.md"
    a = _adapter(tmp_path)
    project_obsidian([ENTRY], idx, "Papers", a, 23128)
    first = (tmp_path / idx).read_text()
    project_obsidian([ENTRY], idx, "Papers", a, 23128)
    assert (tmp_path / idx).read_text() == first
