"""Notion adapter: machine-field upsert only.

Targets the data-source API model (Notion breaking change 2025-09-03): rows live in
a *data source*, not a database. Query hits /data_sources/{id}/query; a new row's
parent is {"type": "data_source_id", ...}. The token is passed in by the caller,
which reads it from the SCHOLAR_WORKFLOW_NOTION_TOKEN env var (never from config/git).
"""
from __future__ import annotations
import httpx

DEFAULT_API_VERSION = "2026-03-11"


class NotionAdapter:
    def __init__(self, token: str, api_version: str = DEFAULT_API_VERSION) -> None:
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            },
            timeout=20,
        )

    def upsert_page(self, data_source_id: str, key_value: str,
                    machine_fields: dict, key_property: str = "Resource ID") -> str:
        """Upsert by a stable key property. Returns Notion page_id.

        Papers DB keys on "Resource ID" (Zotero identity); Related Docs DB keys on
        "Doc ID" (vault-relative path). The key property is injected on create so the
        caller never has to restate it in machine_fields.
        """
        existing = self._find_by_key(data_source_id, key_value, key_property)
        if existing:
            self._update_properties(existing, machine_fields)
            return existing
        return self._create_page(data_source_id, key_value, machine_fields, key_property)

    def _find_by_key(self, data_source_id: str, key_value: str,
                     key_property: str) -> str | None:
        r = self._client.post(
            f"/data_sources/{data_source_id}/query",
            json={"filter": {"property": key_property,
                             "rich_text": {"equals": key_value}}},
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0]["id"] if results else None

    def _update_properties(self, page_id: str, props: dict) -> None:
        r = self._client.patch(f"/pages/{page_id}", json={"properties": props})
        r.raise_for_status()

    def _create_page(self, data_source_id: str, key_value: str, props: dict,
                     key_property: str) -> str:
        props[key_property] = {"rich_text": [{"text": {"content": key_value}}]}
        r = self._client.post(
            "/pages",
            json={"parent": {"type": "data_source_id",
                             "data_source_id": data_source_id},
                  "properties": props},
        )
        r.raise_for_status()
        return r.json()["id"]

    def close(self) -> None:
        self._client.close()
