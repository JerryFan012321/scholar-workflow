"""Zotero Local API adapter (read-only in current Zotero versions)."""
from __future__ import annotations
import httpx


class ZoteroLocalAdapter:
    """Read-only queries against the Zotero Local API."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base, timeout=15)

    def get_collections(self) -> list[dict]:
        r = self._client.get("/users/0/collections?limit=100")
        r.raise_for_status()
        return r.json()

    def search_by_doi(self, doi: str) -> list[dict]:
        r = self._client.get(f"/users/0/items?q={doi}&qmode=everything&limit=10")
        r.raise_for_status()
        return r.json()

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
