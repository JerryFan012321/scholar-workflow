"""Unit coverage for Local-API annotation export and its legacy script wrapper."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator
from scholar_workflow.workflows import annotations as workflow

_SCRIPT = Path(__file__).resolve().parents[2] / "bin" / "zotero-annotations.py"


class FakeAdapter:
    def __init__(self, *, search_rows=None, children=None, annotations=None) -> None:
        self.search_rows = search_rows or []
        self.children = children or []
        self.annotations = annotations or []

    def search_items(self, query, *, qmode, limit):
        assert qmode == "titleCreatorYear"
        assert limit == 100
        return self.search_rows

    def get_item(self, item_key):
        return {"key": item_key, "data": {"title": "Selected Paper"}}

    def get_children(self, _item_key):
        return self.children

    def resolve_attachment_locator(self, attachment_key):
        return ZoteroAttachmentLocator(
            attachment_key=attachment_key,
            library_id="1",
            content_hash="sha256:" + "a" * 64,
            path=Path("/not/read/by-ir.pdf"),
            filename="paper.pdf",
        )

    def get_annotations(self, _attachment_key):
        return self.annotations


def paper(key: str, title: str) -> dict:
    return {"key": key, "data": {"itemType": "journalArticle", "title": title}}


def pdf(key: str) -> dict:
    return {
        "key": key,
        "data": {
            "itemType": "attachment",
            "contentType": "application/pdf",
            "filename": "paper.pdf",
        },
    }


def annotation(
    key: str,
    *,
    text: str,
    comment: str,
    sort_index: str,
    page_label: str | None = None,
    page_index: int = 0,
) -> dict:
    return {
        "key": key,
        "data": {
            "annotationType": "highlight",
            "annotationText": text,
            "annotationComment": comment,
            "annotationColor": "#ffd400",
            "annotationPageLabel": page_label,
            "annotationPosition": f'{{"pageIndex": {page_index}}}',
            "annotationSortIndex": sort_index,
        },
    }


def test_title_search_filters_non_title_quicksearch_hits_and_sorts() -> None:
    adapter = FakeAdapter(
        search_rows=[
            paper("ABCD2345", "World Model Z"),
            paper("EFGH6789", "Creator matched only"),
            paper("JKLM2345", "World Model A"),
        ]
    )

    matches = workflow.find_items(adapter, "world model")

    assert [(row.item_key, row.title) for row in matches] == [
        ("JKLM2345", "World Model A"),
        ("ABCD2345", "World Model Z"),
    ]


def test_ambiguous_title_requires_stable_item_key() -> None:
    adapter = FakeAdapter(
        search_rows=[paper("ABCD2345", "JEPA A"), paper("EFGH6789", "JEPA B")]
    )

    with pytest.raises(workflow.AnnotationAmbiguous, match="--item ITEM_KEY"):
        workflow.select_item(adapter, "JEPA", None)


def test_pdf_selection_uses_local_api_children() -> None:
    adapter = FakeAdapter(
        children=[
            {"key": "ABCD2345", "data": {"itemType": "note"}},
            pdf("EFGH6789"),
        ]
    )

    assert workflow.select_pdf_attachment(adapter, "JKLM2345") == "EFGH6789"


def test_export_builds_sorted_annotation_ir_and_strips_translation() -> None:
    adapter = FakeAdapter(
        children=[pdf("EFGH6789")],
        annotations=[
            annotation(
                "JKLM2345",
                text="second 🔤machine🔤",
                comment="comment two",
                sort_index="00002",
                page_label="iii",
            ),
            annotation(
                "NPQR6789",
                text="first",
                comment="comment one",
                sort_index="00001",
                page_index=4,
            ),
        ],
    )

    exported = workflow.extract_annotation_export(adapter, item_key="ABCD2345")

    assert exported["item_key"] == "ABCD2345"
    assert exported["attachment_key"] == "EFGH6789"
    assert [row["annotation_key"] for row in exported["annotations"]] == [
        "NPQR6789",
        "JKLM2345",
    ]
    assert exported["annotations"][0]["page"] == "5"
    assert exported["annotations"][1]["page"] == "iii"
    assert exported["annotations"][1]["text"] == "second"
    assert exported["annotations"][0]["source_link"].startswith("zotero://open-pdf/")


def test_markdown_preserves_comments_quotes_and_inline_page() -> None:
    rendered = workflow.to_markdown(
        [
            {
                "type": "highlight",
                "page": "7",
                "text": "paper words",
                "comment": "my words",
                "source_link": "zotero://open-pdf/library/items/EFGH6789",
            }
        ]
    )

    assert "highlight (p.7)" in rendered
    assert "HL: paper words" in rendered
    assert "ME: my words" in rendered
    assert "## Page" not in rendered


def test_legacy_script_uses_package_adapter_and_never_imports_sqlite() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "zotero.sqlite" not in source
    spec = importlib.util.spec_from_file_location("zotero_annotations", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.ZoteroLocalAdapter is not None
