"""Persistence boundary for rebuildable HubCatalog snapshots."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from scholar_workflow.hub.models import HubCatalog


class CatalogProvider(Protocol):
    def load(self) -> HubCatalog: ...


class StaticCatalogProvider:
    """Small in-memory provider used by tests and embedded callers."""

    def __init__(self, catalog: HubCatalog) -> None:
        self._catalog = catalog

    def load(self) -> HubCatalog:
        return self._catalog


class CatalogSnapshotStore:
    """Atomic JSON snapshot store; the file is a cache, never a source of truth."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> HubCatalog:
        if not self.path.exists():
            return HubCatalog(
                generated_at=datetime.now(timezone.utc),
                resources=[],
                topics=[],
                artifacts=[],
            )
        return HubCatalog.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, catalog: HubCatalog) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            catalog.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
