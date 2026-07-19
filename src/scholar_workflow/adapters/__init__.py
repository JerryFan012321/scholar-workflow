"""ZoteroWriteAdapter: unified interface, backend-agnostic."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ZoteroWriteResult:
    item_key: str
    attachment_key: str
    version: int
    final_path: str


class ZoteroWriteAdapter(ABC):
    """All Zotero write operations must go through this interface."""

    @abstractmethod
    def health_check(self) -> bool: ...

    @abstractmethod
    def upsert_paper(self, payload: dict, idempotency_key: str) -> ZoteroWriteResult: ...

    @abstractmethod
    def link_attachment(self, item_key: str, file_path: str,
                        idempotency_key: str) -> ZoteroWriteResult: ...

    @abstractmethod
    def update_metadata(self, item_key: str, fields: dict,
                        idempotency_key: str) -> None: ...


def get_write_adapter(config) -> ZoteroWriteAdapter:
    """Capability probe: prefer local_api if capable, else bridge; never SQLite."""
    from scholar_workflow.adapters.zotero_bridge import BridgeAdapter
    bridge = BridgeAdapter(config.zotero.bridge_url)
    if not bridge.health_check():
        raise RuntimeError(
            "ZoteroWriteAdapter: Bridge unavailable. "
            "Zotero writes are disabled until Bridge is healthy."
        )
    return bridge
