"""Explicit, reviewed recommendation-to-Zotero bibliography operations.

The recommendation pool owns plans and receipts. Zotero continues to own the
bibliography; this interface neither downloads PDFs nor creates Vault units.
"""
from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from scholar_workflow.adapters.zotero_local import (
    ZoteroAuthorizationError,
    ZoteroLocalAdapter,
    ZoteroLocalError,
    ZoteroLocalUnavailable,
)
from scholar_workflow.research.models import ResearchError, channel_url_identity
from scholar_workflow.research.recommendations.store import _arxiv_id, _digest
from scholar_workflow.workflows.zotero import (
    ZoteroIdentityConflict,
    ZoteroPartialCompletion,
    _data,
    _exact_match,
    ingest_item,
)

_SCOPE = "zotero_bibliography"
_KEY = re.compile(r"^[A-Z0-9]{8}$")
_PLAN_LIFETIME = timedelta(minutes=15)
_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


def _now() -> datetime:
    return datetime.now(UTC)


def _resource_metadata(resource: dict[str, Any]) -> dict[str, Any]:
    kind = resource["kind"]
    authors = resource.get("authors", [])
    if kind == "paper" and not authors:
        raise ResearchError("Paper authors are missing; complete verified metadata before ingestion.", 2)
    item_type = "preprint" if kind == "paper" and resource.get("arxiv_id") else {
        "paper": "document", "blog": "blogPost", "project": "webpage"}[kind]
    metadata: dict[str, Any] = {"itemType": item_type, "title": resource["title"], "url": resource["url"]}
    if authors:
        # Preserve source names rather than guessing personal-name components.
        metadata["creators"] = [{"creatorType": "author", "name": author} for author in authors]
    if resource.get("arxiv_id"):
        identifier, version = _arxiv_id(resource["arxiv_id"])
        metadata["repository"] = "arXiv"
        metadata["archiveID"] = identifier + (f"v{version}" if version else "")
        metadata["url"] = "https://arxiv.org/abs/" + metadata["archiveID"]
    if resource.get("doi"):
        metadata["DOI"] = resource["doi"]
    if resource.get("published_at"):
        metadata["date"] = resource["published_at"][:10]
    original = resource.get("abstract_original") if kind == "paper" else resource.get("description_original")
    if original:
        metadata["abstractNote"] = original
    return metadata


def _provider_identity(adapter) -> str:
    info = adapter.probe()
    if not isinstance(info.server_id, str) or not info.server_id:
        raise ResearchError("Zotero provider identity is unavailable.", 3)
    return _digest({"server_id": info.server_id, "api_version": info.api_version,
                    "schema_version": info.schema_version})


def _collection(adapter, collection_key: str) -> dict:
    if not isinstance(collection_key, str) or not _KEY.fullmatch(collection_key):
        raise ResearchError("Choose one existing Zotero collection.", 2)
    matches = [row for row in adapter.get_collections(limit=None)
               if row.get("key", _data(row).get("key")) == collection_key]
    if len(matches) != 1:
        raise ResearchError("The chosen Zotero collection is unavailable or ambiguous.", 5)
    row = matches[0]
    data = _data(row)
    version = row.get("version", data.get("version"))
    if type(version) is not int or version < 0 or not isinstance(data.get("name"), str):
        raise ResearchError("The Zotero collection omitted its current name or version.", 3)
    return {"collection_key": collection_key, "name": data["name"],
            "parent_key": data.get("parentCollection") or None, "version": version}


def _stored_arxiv(row: dict) -> tuple[str, int | None] | None:
    data = _data(row)
    for name in ("archiveID", "archiveLocation"):
        text = data.get(name)
        if isinstance(text, str):
            try:
                return _arxiv_id(re.sub(r"^arxiv:\s*", "", text.strip(), flags=re.I))
            except ResearchError:
                pass
    url = data.get("url")
    if isinstance(url, str):
        parsed = urlsplit(url)
        if parsed.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            for prefix in ("/abs/", "/pdf/", "/html/"):
                if parsed.path.startswith(prefix):
                    try:
                        return _arxiv_id(parsed.path[len(prefix):].removesuffix(".pdf").rstrip("/"))
                    except ResearchError:
                        pass
    extra = data.get("extra")
    if isinstance(extra, str):
        match = re.search(r"(?:^|\n)arxiv:\s*([^\s]+)", extra, flags=re.I)
        if match:
            try:
                return _arxiv_id(match[1])
            except ResearchError:
                pass
    return None


def _preview_identity(adapter, resource: dict, metadata: dict) -> str | None:
    query = metadata.get("DOI") or metadata["title"]
    rows = adapter.search_items(query, qmode="everything" if metadata.get("DOI") else "titleCreatorYear", limit=None)
    expected_arxiv = _arxiv_id(resource["arxiv_id"]) if resource.get("arxiv_id") else None
    if expected_arxiv:
        additional = adapter.search_items(expected_arxiv[0], qmode="everything", limit=None)
        by_key = {str(row.get("key")): row for row in [*rows, *additional]}
        rows = list(by_key.values())
    exact = [row for row in rows if _exact_match(row, metadata)]
    if len(exact) > 1:
        raise ResearchError("Multiple exact Zotero items require identity review.", 5)
    for row in rows:
        stored = _stored_arxiv(row)
        matches = _exact_match(row, metadata)
        if expected_arxiv and stored:
            if stored[0] == expected_arxiv[0]:
                if (not matches or (stored[1] and expected_arxiv[1] and stored[1] != expected_arxiv[1])):
                    raise ResearchError("An existing arXiv work has different metadata or version; review it before ingestion.", 5)
            elif matches:
                raise ResearchError("An exact title/author match has a different arXiv identity.", 5)
        if matches and resource["kind"] != "paper":
            try:
                same_url = channel_url_identity(_data(row).get("url", "")) == channel_url_identity(metadata["url"])
            except (ResearchError, ValueError, TypeError, AttributeError):
                same_url = False
            if not same_url:
                raise ResearchError("A matching document title has a different source URL; review its identity.", 5)
    if exact:
        key = exact[0].get("key")
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ResearchError("Zotero identity preview omitted a valid item key.", 3)
        return key
    return None


def _failure(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, (ZoteroLocalUnavailable, ZoteroAuthorizationError)):
        return "Zotero Local API or write authorization is unavailable.", 3
    if isinstance(exc, (ZoteroIdentityConflict,)):
        return "Zotero identity is ambiguous; inspect existing items before retrying.", 5
    if isinstance(exc, ZoteroLocalError):
        return "Zotero rejected the operation; inspect its current state before retrying.", 8
    if isinstance(exc, ResearchError):
        return str(exc), exc.exit_code
    return "The external result could not be confirmed; retry this same plan after inspection.", 6


class IngestionService:
    """Preview and execute one explicitly confirmed bibliography operation."""

    def __init__(self, store, profile: str = "personal", adapter_factory=ZoteroLocalAdapter):
        if profile not in {"personal", "test"}:
            raise ResearchError("Unknown recommendation profile.", 2)
        self.store = store
        self.profile = profile
        self.adapter_factory = adapter_factory

    @contextmanager
    def _adapter(self):
        if self.profile == "test" and self.adapter_factory is ZoteroLocalAdapter:
            raise ResearchError("Test recommendations cannot contact the native Zotero library.", 7)
        adapter = self.adapter_factory()
        if self.profile == "test" and isinstance(adapter, ZoteroLocalAdapter):
            adapter.close()
            raise ResearchError("Test recommendations require an isolated injected Zotero adapter.", 7)
        try:
            with adapter as opened:
                yield opened
        except (ZoteroLocalUnavailable, ZoteroAuthorizationError, ZoteroLocalError) as exc:
            message, code = _failure(exc)
            raise ResearchError(message, code) from None

    def targets(self) -> dict:
        with self._adapter() as adapter:
            _provider_identity(adapter)
            rows = adapter.get_collections(limit=None)
            targets = []
            for row in rows:
                key = row.get("key", _data(row).get("key"))
                data = _data(row)
                if isinstance(key, str) and _KEY.fullmatch(key) and isinstance(data.get("name"), str):
                    targets.append({"collection_key": key, "name": data["name"],
                                    "parent_key": data.get("parentCollection") or None})
        return {"scope": _SCOPE, "targets": targets}

    def plan(self, candidate_id: str, expected_revision: int, collection_key: str) -> dict:
        row = self.store.get_candidate(candidate_id)
        if type(expected_revision) is not int or expected_revision != row["revision"]:
            raise ResearchError("The candidate changed; review its current content before ingestion.", 5)
        if row["decision"] != "selected" or (row["review_required"] and not row["abstract_reviewed"]):
            raise ResearchError("Select and review the candidate's current reading content before ingestion.", 7)
        metadata = _resource_metadata(row["resource"])
        with self._adapter() as adapter:
            provider = _provider_identity(adapter)
            collection = _collection(adapter, collection_key)
            existing = _preview_identity(adapter, row["resource"], metadata)
        now = _now()
        plan = {"scope": _SCOPE, "candidate_id": candidate_id, "candidate_revision": expected_revision,
                "resource_digest": _digest(row["resource"]), "resource": row["resource"],
                "metadata": metadata, "collection_key": collection_key, "collection": collection,
                "provider_identity": provider, "collection_version": collection["version"],
                "existing_item_key": existing, "expires_at": (now + _PLAN_LIFETIME).isoformat(),
                "pdf_status": "not_requested", "knowledge_status": "not_requested"}
        return self.store.create_ingestion_plan(plan)

    def execute(self, plan_id: str, confirmed: bool, *, retry: bool = False) -> dict:
        if confirmed is not True or type(retry) is not bool:
            raise ResearchError("Explicitly confirm this ingestion preview before execution.", 7)
        plan = self.store.get_ingestion_plan(plan_id)
        if plan["status"] == "completed":
            return plan["receipt"]
        try:
            expiry = datetime.fromisoformat(plan["expires_at"])
            if expiry.tzinfo is None or expiry <= _now():
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise ResearchError("The ingestion preview expired; prepare and review a fresh plan.", 5) from None
        identity = (str(self.store.state_dir), plan["candidate_id"])
        with _LOCK_GUARD:
            lock = _LOCKS.setdefault(identity, threading.Lock())
        if not lock.acquire(blocking=False):
            raise ResearchError("This candidate already has an ingestion operation in progress.", 5)
        try:
            return self._execute_locked(plan_id, retry=retry)
        finally:
            lock.release()

    def _execute_locked(self, plan_id: str, *, retry: bool) -> dict:
        plan = self.store.claim_ingestion_plan(plan_id, retry=retry)
        if plan["status"] == "completed":
            return plan["receipt"]
        receipt: dict[str, Any] = {"plan_id": plan_id, "candidate_id": plan["candidate_id"],
            "title": plan["resource"]["title"], "collection": {
                "key": plan["collection_key"], "name": plan["collection"]["name"]},
            "scope": _SCOPE, "collection_key": plan["collection_key"],
            "pdf_status": "not_requested", "knowledge_status": "not_requested"}
        previous_key = (plan.get("receipt") or {}).get("item_key")
        if previous_key:
            receipt["item_key"] = previous_key
        try:
            with self._adapter() as adapter:
                if _provider_identity(adapter) != plan["provider_identity"]:
                    raise ResearchError("The Zotero provider changed; prepare a new ingestion preview.", 5)
                collection = _collection(adapter, plan["collection_key"])
                if collection != plan["collection"]:
                    raise ResearchError("The selected collection changed; prepare a new ingestion preview.", 5)
                current_key = _preview_identity(adapter, plan["resource"], plan["metadata"])
                if plan.get("existing_item_key") and current_key != plan["existing_item_key"]:
                    raise ResearchError("The previously matched Zotero item changed; review its identity.", 5)
                if previous_key and current_key != previous_key:
                    raise ResearchError("The previously written Zotero item cannot be safely resumed.", 5)
                result = ingest_item(adapter, metadata=plan["metadata"], collection_keys=[plan["collection_key"]])
                key = result.get("item_key")
                if not isinstance(key, str) or not _KEY.fullmatch(key):
                    raise ResearchError("Zotero ingestion omitted an observed item key.", 6)
                receipt["item_key"] = key
                actual = adapter.get_item(key)
                if not _exact_match(actual, plan["metadata"]):
                    raise ResearchError("The observed Zotero item does not match the requested bibliography.", 5)
                if plan["collection_key"] not in (_data(actual).get("collections") or []):
                    raise ResearchError("Zotero collection membership could not be confirmed.", 6)
                receipt.update(status="completed", result=result["status"], completed_at=_now().isoformat())
        except Exception as exc:
            message, code = _failure(exc)
            if isinstance(exc, ZoteroPartialCompletion):
                receipt["item_key"] = exc.item_key
                if exc.attachment_key:
                    receipt["attachment_key"] = exc.attachment_key
            receipt.update(status="conflict" if code == 5 else "needs_attention", error=message,
                           exit_code=code, checked_at=_now().isoformat())
            saved = self.store.finish_ingestion_plan(plan_id, receipt)
            if code == 5:
                raise ResearchError(message, code) from None
            return saved["receipt"]
        return self.store.finish_ingestion_plan(plan_id, receipt)["receipt"]

    def history(self) -> list[dict]:
        """Project readable targets/results without exposing provider or metadata snapshots."""
        result = []
        for plan in self.store.ingestion_history():
            row = {key: plan[key] for key in ("plan_id", "candidate_id", "status", "created_at", "expires_at",
                                             "collection_key", "scope", "receipt", "updated_at") if key in plan}
            row["title"] = plan["resource"]["title"]
            row["collection"] = {"key": plan["collection_key"], "name": plan["collection"]["name"]}
            for key in ("item_key", "attachment_key", "zotero_url", "error", "exit_code", "result",
                        "completed_at", "checked_at", "pdf_status", "knowledge_status"):
                if key in plan.get("receipt", {}):
                    row[key] = plan["receipt"][key]
            result.append(row)
        return result
