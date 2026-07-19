"""Notion adapter: machine-field upsert only."""
from __future__ import annotations
import httpx


class NotionAdapter:
    def __init__(self, token: str, api_version: str = "2022-06-28") -> None:
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": api_version,
                "Content-Type": "application/json",
            },
            timeout=20,
        )

    def upsert_page(self, database_id: str, resource_id: str,
                    machine_fields: dict) -> str:
        """Upsert by Resource ID. Returns Notion page_id."""
        existing = self._find_by_resource_id(database_id, resource_id)
        if existing:
            self._update_properties(existing, machine_fields)
            return existing
        return self._create_page(database_id, resource_id, machine_fields)

    def _find_by_resource_id(self, database_id: str, resource_id: str) -> str | None:
        r = self._client.post(
            f"/databases/{database_id}/query",
            json={"filter": {"property": "Resource ID",
                             "rich_text": {"equals": resource_id}}},
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0]["id"] if results else None

    def _update_properties(self, page_id: str, props: dict) -> None:
        r = self._client.patch(f"/pages/{page_id}", json={"properties": props})
        r.raise_for_status()

    def _create_page(self, database_id: str, resource_id: str, props: dict) -> str:
        props["Resource ID"] = {"rich_text": [{"text": {"content": resource_id}}]}
        r = self._client.post(
            "/pages",
            json={"parent": {"database_id": database_id}, "properties": props},
        )
        r.raise_for_status()
        return r.json()["id"]

    def close(self) -> None:
        self._client.close()
