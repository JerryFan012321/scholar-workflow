"""Sync the local resources cache from the Zotero Local API.

The cache is a derived read-only mirror of Zotero (the authority). Syncing is
user-triggered — the plugin never auto-syncs. This fills the cache that dedup's
fast prefilter and the host-LLM catalog read from.
"""
from __future__ import annotations
import re
from scholar_workflow.identity import (
    normalize_arxiv, normalize_doi, normalize_title, make_resource_id,
)
from scholar_workflow.dedup import DependencyError

_ARXIV_IN_TEXT = re.compile(r"(\d{4}\.\d{4,5})")


def _extract_arxiv(data: dict) -> str | None:
    """Pull an arXiv base id from DOI (10.48550/arXiv.<id>), url, or extra note."""
    doi = (data.get("DOI") or "")
    if "arxiv" in doi.lower():
        if m := _ARXIV_IN_TEXT.search(doi):
            return m.group(1)
    for field in ("url", "extra"):
        val = data.get(field) or ""
        if "arxiv" in val.lower():
            if m := _ARXIV_IN_TEXT.search(val):
                return m.group(1)
    return None


def _first_author(data: dict) -> str:
    for c in data.get("creators", []):
        if c.get("creatorType") == "author":
            return c.get("lastName") or c.get("name") or ""
    return ""


def _year(data: dict) -> int | None:
    date = str(data.get("date") or "")
    m = re.search(r"\d{4}", date)
    return int(m.group()) if m else None


def _resource_from_item(item: dict) -> dict | None:
    """Map one Zotero item to cache-row kwargs, or None if it carries no identity."""
    data = item.get("data", {})
    doi = normalize_doi(data["DOI"]) if data.get("DOI") else None
    arxiv = _extract_arxiv(data)
    title = (data.get("title") or "").strip()
    if not (doi or arxiv or title):
        return None
    rid = make_resource_id("paper", {"doi": doi, "arxiv": arxiv, "title": title,
                                     "first_author": _first_author(data),
                                     "year": _year(data)})
    return {
        "resource_id": rid, "doi": doi, "arxiv": arxiv, "title": title,
        "title_norm": normalize_title(title), "abstract": data.get("abstractNote"),
        "first_author": _first_author(data), "year": _year(data),
        "zotero_item_key": item.get("key"), "status": "in_zotero",
    }


def sync_cache(zotero, store, *, page_size: int = 100) -> dict:
    """Page through Zotero top-level items and upsert them into the cache.

    Fail-closed: any Zotero error raises DependencyError (exit code 3 upstream).
    Returns a small summary {synced, skipped}.
    """
    synced = skipped = 0
    start = 0
    try:
        while True:
            items = zotero.get_items(start=start, limit=page_size)
            if not items:
                break
            for item in items:
                row = _resource_from_item(item)
                if row is None:
                    skipped += 1
                    continue
                store.upsert_resource(**row)
                synced += 1
            if len(items) < page_size:
                break
            start += page_size
    except DependencyError:
        raise
    except Exception as exc:
        raise DependencyError(f"Zotero Local API unavailable during sync: {exc}") from exc
    return {"synced": synced, "skipped": skipped}
