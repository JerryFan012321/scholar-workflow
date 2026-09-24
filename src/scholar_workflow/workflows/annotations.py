"""Read-only Zotero annotation export through the Local API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scholar_workflow.hub.zotflow import AnnotationIR, load_annotation_ir


@dataclass(frozen=True)
class AnnotationCandidate:
    item_key: str
    title: str


class AnnotationExportError(RuntimeError):
    """A paper or attachment could not be selected for annotation export."""


class AnnotationNotFound(AnnotationExportError):
    """No title match exists in the current Zotero library."""


class AnnotationAmbiguous(AnnotationExportError):
    """A title query matched more than one Zotero item."""

    def __init__(self, candidates: list[AnnotationCandidate]) -> None:
        self.candidates = candidates
        listing = ", ".join(
            f"{candidate.item_key} ({candidate.title})" for candidate in candidates
        )
        super().__init__(f"multiple matches; rerun with --item ITEM_KEY: {listing}")


class AnnotationAttachmentMissing(AnnotationExportError):
    """The selected Zotero item has no PDF attachment."""


def _item_title(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("title"), str):
        return data["title"].strip()
    return ""


def _item_key(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    key = payload.get("key")
    if not isinstance(key, str):
        data = payload.get("data")
        key = data.get("key") if isinstance(data, dict) else None
    return key.strip() if isinstance(key, str) else ""


def find_items(adapter: Any, query: str) -> list[AnnotationCandidate]:
    """Return title-fragment matches from Local API quicksearch results."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("title query must not be empty")
    folded = clean_query.casefold()
    candidates: list[AnnotationCandidate] = []
    for payload in adapter.search_items(
        clean_query,
        qmode="titleCreatorYear",
        limit=100,
    ):
        title = _item_title(payload)
        key = _item_key(payload)
        if key and title and folded in title.casefold():
            candidates.append(AnnotationCandidate(item_key=key, title=title))
    return sorted(candidates, key=lambda row: (row.title.casefold(), row.item_key))


def select_item(adapter: Any, query: str | None, item_key: str | None) -> AnnotationCandidate:
    if item_key:
        payload = adapter.get_item(item_key)
        return AnnotationCandidate(
            item_key=_item_key(payload) or item_key,
            title=_item_title(payload),
        )
    if query is None:
        raise ValueError("provide a title fragment or --item ITEM_KEY")
    candidates = find_items(adapter, query)
    if not candidates:
        raise AnnotationNotFound(f"no Zotero title match for {query!r}")
    if len(candidates) > 1:
        raise AnnotationAmbiguous(candidates)
    return candidates[0]


def select_pdf_attachment(adapter: Any, item_key: str) -> str:
    for payload in adapter.get_children(item_key):
        if not isinstance(payload, dict):
            continue
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("itemType") != "attachment":
            continue
        content_type = str(data.get("contentType") or "").casefold()
        filename = str(data.get("filename") or "").casefold()
        key = _item_key(payload)
        if key and (content_type == "application/pdf" or filename.endswith(".pdf")):
            return key
    raise AnnotationAttachmentMissing(f"no PDF attachment for Zotero item {item_key}")


def _page_label(annotation: AnnotationIR) -> str:
    if annotation.page_label:
        return annotation.page_label
    if annotation.page_index is not None:
        return str(annotation.page_index + 1)
    return "?"


def annotation_rows(annotations: list[AnnotationIR]) -> list[dict[str, Any]]:
    """Convert AnnotationIR to the compact, human-projection input format."""
    rows: list[dict[str, Any]] = []
    for annotation in annotations:
        if not annotation.quoted_text and not annotation.comment:
            continue
        rows.append(
            {
                "annotation_key": annotation.annotation_id,
                "type": annotation.type,
                "page": _page_label(annotation),
                "text": annotation.quoted_text,
                "comment": annotation.comment,
                "color": annotation.color,
                "sort": annotation.sort_index,
                "source_link": annotation.source_link,
            }
        )
    return rows


def extract_annotation_export(
    adapter: Any,
    *,
    query: str | None = None,
    item_key: str | None = None,
) -> dict[str, Any]:
    """Select one paper and return its Local-API-backed AnnotationIR projection."""
    item = select_item(adapter, query, item_key)
    attachment_key = select_pdf_attachment(adapter, item.item_key)
    annotations = load_annotation_ir(adapter, attachment_key)
    rows = annotation_rows(annotations)
    return {
        "item_key": item.item_key,
        "attachment_key": attachment_key,
        "title": item.title,
        "count": len(rows),
        "annotations": rows,
    }


def to_markdown(rows: list[dict[str, Any]]) -> str:
    """Render a flat reading-order handoff; page stays inline, never a heading."""
    lines: list[str] = []
    for index, row in enumerate(rows, 1):
        lines.append(f"[{index}] {row['type']} (p.{row['page']})")
        if row.get("text"):
            lines.append(f"  HL: {row['text']}")
        if row.get("comment"):
            lines.append(f"  ME: {row['comment']}")
        if row.get("source_link"):
            lines.append(f"  SRC: {row['source_link']}")
    return "\n".join(lines)


__all__ = [
    "AnnotationAmbiguous",
    "AnnotationAttachmentMissing",
    "AnnotationCandidate",
    "AnnotationExportError",
    "AnnotationNotFound",
    "annotation_rows",
    "extract_annotation_export",
    "find_items",
    "select_item",
    "select_pdf_attachment",
    "to_markdown",
]
