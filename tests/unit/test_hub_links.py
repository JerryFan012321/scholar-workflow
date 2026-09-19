"""Notion page IDs are a relationship map, not a second metadata store."""
from __future__ import annotations

from datetime import datetime, timezone

from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.links import LinkedCatalogProvider, ProjectionLinkStore
from scholar_workflow.hub.models import HubCatalog, HubResource


def test_projection_link_store_round_trips_ids_only(tmp_path):
    store = ProjectionLinkStore(tmp_path / "projection-links.json")
    store.record_notion_pages({"paper:one": "01234567-89ab-cdef-0123-456789abcdef"})
    assert store.notion_pages() == {
        "paper:one": "01234567-89ab-cdef-0123-456789abcdef"
    }
    text = store.path.read_text(encoding="utf-8")
    assert "title" not in text
    assert "body" not in text


def test_linked_provider_overlays_page_id_without_changing_authoritative_metadata(tmp_path):
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[HubResource(resource_id="paper:one", kind="paper", title="From Zotero")],
        topics=[], artifacts=[],
    )
    links = ProjectionLinkStore(tmp_path / "projection-links.json")
    links.record_notion_pages({"paper:one": "01234567-89ab-cdef-0123-456789abcdef"})

    linked = LinkedCatalogProvider(StaticCatalogProvider(catalog), links).load()

    assert linked.resources[0].title == "From Zotero"
    assert linked.resources[0].projections.notion_page_id == (
        "01234567-89ab-cdef-0123-456789abcdef"
    )
