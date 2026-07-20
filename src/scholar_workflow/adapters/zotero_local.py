"""Zotero Local API adapter (read-only in current Zotero versions).

Zotero is the authoritative library. This adapter only reads — existence checks
and metadata come from here; the plugin never writes to Zotero.
"""
from __future__ import annotations
import httpx


class ZoteroLocalAdapter:
    """Read-only queries against the Zotero Local API."""

    def __init__(self, base_url: str, client=None) -> None:
        self._base = base_url.rstrip("/")
        # client is injectable for tests; default is a real localhost HTTP client.
        self._client = client or httpx.Client(base_url=self._base, timeout=15)

    def get_collections(self) -> list[dict]:
        r = self._client.get("/users/0/collections?limit=100")
        r.raise_for_status()
        return r.json()

    def get_items(self, *, start: int = 0, limit: int = 100) -> list[dict]:
        """Page through top-level items (excludes attachments/notes). Read-only."""
        r = self._client.get(
            f"/users/0/items/top?start={start}&limit={limit}")
        r.raise_for_status()
        return r.json()

    def search_by_doi(self, doi: str) -> list[dict]:
        r = self._client.get(f"/users/0/items?q={doi}&qmode=everything&limit=10")
        r.raise_for_status()
        return r.json()

    def search_by_arxiv(self, arxiv_id: str) -> list[dict]:
        """Find items matching an arXiv id.

        Zotero has no native arXiv field, so a text search can false-positive on the
        digits appearing in a title. Verify each hit carries the id in an identifier
        field (DOI `10.48550/arXiv.<id>`, an arxiv.org URL, or the `extra` note).
        """
        r = self._client.get(
            f"/users/0/items?q={arxiv_id}&qmode=everything&limit=10")
        r.raise_for_status()
        return [it for it in r.json() if _carries_arxiv_id(it, arxiv_id)]

    def search_by_title(self, title: str) -> list[dict]:
        r = self._client.get(f"/users/0/items?q={title}&limit=10")
        r.raise_for_status()
        return r.json()

    def get_item(self, item_key: str) -> dict:
        r = self._client.get(f"/users/0/items/{item_key}")
        r.raise_for_status()
        return r.json()

    def get_attachments(self, item_key: str) -> list[dict]:
        r = self._client.get(f"/users/0/items/{item_key}/children")
        r.raise_for_status()
        return [i for i in r.json() if i.get("data", {}).get("itemType") == "attachment"]

    def close(self) -> None:
        self._client.close()


def _carries_arxiv_id(item: dict, arxiv_id: str) -> bool:
    """True if an identifier field of `item` actually carries `arxiv_id`."""
    data = item.get("data", {})
    doi = (data.get("DOI") or "").lower()
    url = (data.get("url") or "").lower()
    extra = (data.get("extra") or "").lower()
    needle = arxiv_id.lower()
    return (needle in doi) or (needle in url) or (needle in extra)
