"""Contract test for ObsidianAdapter (AGENT.md: pin adapter interface before change).

The adapter is a *dumb* managed-block writer: the caller owns the entire block body
(a paper table, a MOC wikilink list, or both). The adapter only (a) replaces the
inter-marker region verbatim and (b) never touches content outside the markers (INV4).
"""
from __future__ import annotations
import pytest
from scholar_workflow.adapters.obsidian import ObsidianAdapter

START, END = "<!-- scholar-workflow:start -->", "<!-- scholar-workflow:end -->"


def _adapter(tmp_path):
    return ObsidianAdapter(tmp_path, START, END)


def test_ensure_creates_empty_block_under_heading(tmp_path):
    a = _adapter(tmp_path)
    a.ensure_managed_block("dir/idx.md", "My Heading")
    text = (tmp_path / "dir/idx.md").read_text(encoding="utf-8")
    assert "# My Heading" in text
    assert START in text and END in text
    # empty block: nothing but whitespace between the markers, no hardcoded table
    body = text.split(START, 1)[1].split(END, 1)[0]
    assert body.strip() == ""


def test_update_replaces_body_verbatim(tmp_path):
    a = _adapter(tmp_path)
    a.ensure_managed_block("idx.md", "H")
    a.update_managed_block("idx.md", "arbitrary\nlines\n- [[child]]")
    body = (tmp_path / "idx.md").read_text(encoding="utf-8").split(START, 1)[1].split(END, 1)[0]
    assert body == "\narbitrary\nlines\n- [[child]]\n"


def test_update_preserves_content_outside_markers(tmp_path):
    a = _adapter(tmp_path)
    a.ensure_managed_block("idx.md", "H")
    full = tmp_path / "idx.md"
    full.write_text(full.read_text() + "\n## human notes\nkeep me\n", encoding="utf-8")
    a.update_managed_block("idx.md", "new body")
    text = full.read_text(encoding="utf-8")
    assert "keep me" in text and "# H" in text


def test_update_is_idempotent(tmp_path):
    a = _adapter(tmp_path)
    a.ensure_managed_block("idx.md", "H")
    a.update_managed_block("idx.md", "body")
    first = (tmp_path / "idx.md").read_text(encoding="utf-8")
    a.update_managed_block("idx.md", "body")
    assert (tmp_path / "idx.md").read_text(encoding="utf-8") == first


def test_update_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        _adapter(tmp_path).update_managed_block("nope.md", "x")


def test_update_raises_when_markers_absent(tmp_path):
    (tmp_path / "bare.md").write_text("# no markers here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _adapter(tmp_path).update_managed_block("bare.md", "x")
