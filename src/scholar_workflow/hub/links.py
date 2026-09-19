"""Stable cross-system IDs used to assemble Hub actions.

This file intentionally stores only source/target identifiers.  Bibliography,
note content, filenames, and URLs remain in their authoritative systems.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.hub.models import HubCatalog


def default_projection_link_path() -> Path:
    home = Path(
        os.environ.get(
            "SCHOLAR_WORKFLOW_HOME",
            Path.home() / ".config" / "scholar-workflow",
        )
    )
    return home / "hub" / "projection-links.json"


class ProjectionLinkStore:
    """Atomic mapping store for projection IDs only."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or default_projection_link_path())

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "notion_pages": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported projection-link schema")
        pages = payload.get("notion_pages")
        if not isinstance(pages, dict) or any(
            not isinstance(key, str) or not key
            or not isinstance(value, str) or not value
            for key, value in pages.items()
        ):
            raise ValueError("invalid Notion projection-link mapping")
        return {"schema_version": 1, "notion_pages": pages}

    def notion_pages(self) -> dict[str, str]:
        return dict(self._load()["notion_pages"])

    def record_notion_pages(self, pages: dict[str, str]) -> None:
        if any(not key or not value for key, value in pages.items()):
            raise ValueError("projection links require non-empty IDs")
        payload = self._load()
        payload["notion_pages"].update(pages)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)


class LinkedCatalogProvider:
    """Overlay relationship IDs on a rebuilt catalog without changing its sources."""

    def __init__(self, catalog: CatalogProvider, links: ProjectionLinkStore) -> None:
        self._catalog = catalog
        self._links = links

    def load(self) -> HubCatalog:
        catalog = self._catalog.load()
        page_ids = self._links.notion_pages()
        if not page_ids:
            return catalog
        payload = catalog.model_dump()
        changed = False
        for resource in payload["resources"]:
            page_id = page_ids.get(resource["resource_id"])
            if page_id is not None:
                resource["projections"]["notion_page_id"] = page_id
                changed = True
        if not changed:
            return catalog
        payload["revision"] = ""
        return HubCatalog.model_validate(payload)
