"""Bridge adapter: calls the self-hosted Zotero plugin over local HTTP."""
from __future__ import annotations
import httpx
from scholar_workflow.adapters import ZoteroWriteAdapter, ZoteroWriteResult


class BridgeAdapter(ZoteroWriteAdapter):
    def __init__(self, base_url: str, token: str = "") -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._client = httpx.Client(
            base_url=self._base,
            headers={"X-Scholar-Token": token, "Content-Type": "application/json"},
            timeout=30,
        )

    def health_check(self) -> bool:
        try:
            r = self._client.get("/health")
            return r.status_code == 200
        except Exception:
            return False

    def upsert_paper(self, payload: dict, idempotency_key: str) -> ZoteroWriteResult:
        r = self._client.post(
            "/papers/upsert",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        r.raise_for_status()
        data = r.json()
        return ZoteroWriteResult(
            item_key=data["item_key"],
            attachment_key=data.get("attachment_key", ""),
            version=data.get("version", 0),
            final_path=data.get("final_path", ""),
        )

    def link_attachment(self, item_key: str, file_path: str,
                        idempotency_key: str) -> ZoteroWriteResult:
        r = self._client.post(
            "/attachments/link",
            json={"item_key": item_key, "file_path": file_path},
            headers={"Idempotency-Key": idempotency_key},
        )
        r.raise_for_status()
        data = r.json()
        return ZoteroWriteResult(
            item_key=item_key,
            attachment_key=data["attachment_key"],
            version=data.get("version", 0),
            final_path=data.get("final_path", file_path),
        )

    def update_metadata(self, item_key: str, fields: dict,
                        idempotency_key: str) -> None:
        r = self._client.post(
            "/items/update-metadata",
            json={"item_key": item_key, "fields": fields},
            headers={"Idempotency-Key": idempotency_key},
        )
        r.raise_for_status()
