"""Unit tests for the read-only annotation extractor (bin/zotero-annotations.py).

Loaded by file path since bin/ is not a package. No real Zotero DB is touched:
the annotations() query is exercised against an in-memory SQLite with a minimal
schema mirroring itemAnnotations.
"""
from __future__ import annotations
import importlib.util
import sqlite3
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "zotero-annotations.py"
_spec = importlib.util.spec_from_file_location("zotero_annotations", _SCRIPT)
za = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(za)


# ---- clean(): strips 🔤…🔤 machine translation, keeps original ----

def test_clean_strips_single_translation_block():
    assert za.clean("keep this🔤机器翻译🔤") == "keep this"


def test_clean_strips_multiline_and_multiple_blocks():
    # two 🔤…🔤 blocks removed (regex is DOTALL, so the first spans a newline)
    raw = "original🔤译文一\n跨行🔤 middle 🔤译文二🔤 tail"
    assert za.clean(raw) == "original middle  tail"


def test_clean_none_and_empty():
    assert za.clean(None) == ""
    assert za.clean("   ") == ""


def test_clean_no_marker_untouched():
    assert za.clean("plain highlight text") == "plain highlight text"


# ---- page(): prefers pageLabel, falls back to position.pageIndex+1 ----

def test_page_prefers_label():
    assert za.page("7", '{"pageIndex": 0}') == "7"


def test_page_falls_back_to_index_plus_one():
    assert za.page(None, '{"pageIndex": 4}') == "5"


def test_page_unparseable_position_returns_question_mark():
    assert za.page(None, "not-json") == "?"


def test_page_missing_index_defaults_to_zero_plus_one():
    # get("pageIndex", -1) + 1 -> 0 when key absent
    assert za.page(None, "{}") == "0"


# ---- TYPE map ----

def test_type_map_known_and_unknown():
    assert za.TYPE[1] == "highlight"
    assert za.TYPE[2] == "note"
    assert za.TYPE.get(99, f"type{99}") == "type99"


# ---- annotations(): reads itemAnnotations, sorts by sortIndex, cleans text ----

@pytest.fixture
def db_with_annotations():
    con = sqlite3.connect(":memory:")
    con.execute(
        """CREATE TABLE itemAnnotations (
            parentItemID INTEGER, type INTEGER, text TEXT, comment TEXT,
            color TEXT, pageLabel TEXT, position TEXT, sortIndex TEXT
        )"""
    )
    rows = [
        # out-of-order sortIndex; row B should come before row A after sort
        (10, 1, "second🔤机翻🔤", "cmt-A", "#ffd400", "3", None, "00002|000100|00010"),
        (10, 1, "first", "cmt-B", "#ff6666", "1", None, "00001|000050|00005"),
        (10, 2, "", "note-only", "#ffd400", "2", None, "00001|000900|00020"),
        (99, 1, "other paper", "", "#ffd400", "1", None, "00001|000001|00001"),
    ]
    con.executemany("INSERT INTO itemAnnotations VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return con


def test_annotations_filters_by_parent_and_sorts(db_with_annotations):
    anns = za.annotations(db_with_annotations, 10)
    assert len(anns) == 3  # parent 99 excluded
    # sorted ascending by sortIndex string
    assert [a["comment"] for a in anns] == ["cmt-B", "note-only", "cmt-A"]


def test_annotations_strips_translation_in_text(db_with_annotations):
    anns = za.annotations(db_with_annotations, 10)
    last = anns[-1]  # cmt-A row
    assert last["text"] == "second"
    assert last["comment"] == "cmt-A"


def test_annotations_maps_type_and_page(db_with_annotations):
    anns = za.annotations(db_with_annotations, 10)
    note = [a for a in anns if a["comment"] == "note-only"][0]
    assert note["type"] == "note"
    assert note["page"] == "2"
