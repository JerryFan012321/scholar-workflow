"""Backward-compatible entry point for the loopback Hub/PDF service.

Historically this module exposed only ``/open/paper/<attachment-key>``. The
same listener now also serves the local research Hub; keeping this wrapper
preserves existing links and callers while the product-facing name changes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.hub.server import HubHTTPServer, start_hub_server


def start_link_server(
    port: int = 23128,
    storage_root: Path | None = None,
    *,
    vault_root: Path | None = None,
    catalog_provider: Any | None = None,
    action_executor: Any | None = None,
) -> HubHTTPServer:
    """Start the unified Hub while preserving the former adapter interface."""
    if catalog_provider is None:
        catalog_provider = StaticCatalogProvider(
            HubCatalog(
                generated_at=datetime.now(timezone.utc),
                resources=[],
                topics=[],
                artifacts=[],
            )
        )
    return start_hub_server(
        port=port,
        storage_root=storage_root or Path.home() / "Zotero" / "storage",
        vault_root=vault_root or Path.cwd(),
        catalog_provider=catalog_provider,
        action_executor=action_executor,
    )


__all__ = ["start_link_server"]
