"""Deterministic identity checks and writes for the Zotero Local API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol

from scholar_workflow.adapters.zotero_local import MAX_UPLOAD_BYTES
from scholar_workflow.identity import normalize_doi, normalize_title


class ZoteroIdentityConflict(RuntimeError):
    """More than one library item has the same exact identity."""


class ZoteroPartialCompletion(RuntimeError):
    """The parent item exists but its attachment upload failed."""

    def __init__(self, item_key: str, attachment_key: str | None = None) -> None:
        self.item_key = item_key
        self.attachment_key = attachment_key
        attachment = f" and attachment {attachment_key}" if attachment_key else ""
        super().__init__(
            f"Zotero item {item_key}{attachment} exists, but its PDF upload failed; "
            "rerun the same ingest payload to resume"
        )


class ZoteroWriter(Protocol):
    def search_items(
        self, query: str, *, qmode: str, limit: int | None
    ) -> list[dict[str, Any]]: ...

    def ensure_write_authorization(self, *, require_remembered: bool = False) -> Any: ...

    def get_children(self, item_key: str) -> list[dict[str, Any]]: ...

    def create_item(self, item: Mapping[str, Any]) -> str: ...

    def update_item(
        self,
        item_key: str,
        changes: Mapping[str, Any],
        *,
        version: int,
    ) -> None: ...

    def import_file(self, parent_key: str, path: Path) -> dict[str, Any]: ...

    def upload_file(self, attachment_key: str, path: Path) -> dict[str, Any]: ...


def _data(item: Mapping[str, Any]) -> Mapping[str, Any]:
    data = item.get("data")
    return data if isinstance(data, Mapping) else item


def _creators(data: Mapping[str, Any]) -> tuple[str, ...]:
    signatures: list[str] = []
    for creator in data.get("creators", []) or []:
        if not isinstance(creator, Mapping):
            continue
        if creator.get("creatorType", "author") != "author":
            continue
        name = creator.get("name") or " ".join(
            str(creator.get(part, "")) for part in ("firstName", "lastName")
        )
        signatures.append(normalize_title(str(name)))
    return tuple(signatures)


def _doi(data: Mapping[str, Any]) -> str | None:
    value = data.get("DOI")
    return normalize_doi(str(value)) if value else None


def _exact_match(candidate: Mapping[str, Any], metadata: Mapping[str, Any]) -> bool:
    candidate_data = _data(candidate)
    expected_doi = _doi(metadata)
    if expected_doi:
        return _doi(candidate_data) == expected_doi
    return (
        normalize_title(str(candidate_data.get("title", "")))
        == normalize_title(str(metadata.get("title", "")))
        and _creators(candidate_data) == _creators(metadata)
    )


def _stored_pdf_attachments(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for child in children:
        data = _data(child)
        if data.get("itemType") != "attachment":
            continue
        if data.get("linkMode") not in {"imported_file", "imported_url"}:
            continue
        filename = str(data.get("filename") or data.get("title") or "")
        if data.get("contentType") != "application/pdf" and not filename.lower().endswith(".pdf"):
            continue
        attachments.append(child)
    return attachments


def _attachment_key(attachment: Mapping[str, Any]) -> str:
    data = _data(attachment)
    key = attachment.get("key") or data.get("key")
    if not isinstance(key, str) or not key:
        raise ValueError("Zotero attachment result omitted its key")
    return key


def ingest_item(
    adapter: ZoteroWriter,
    *,
    metadata: Mapping[str, Any],
    collection_keys: list[str] | None = None,
    pdf_path: Path | None = None,
) -> dict[str, Any]:
    """Reuse one exact item or create it and optionally upload one attachment."""
    title_value = metadata.get("title")
    title = title_value.strip() if isinstance(title_value, str) else ""
    item_type = metadata.get("itemType")
    if not isinstance(item_type, str) or not item_type or not title:
        raise ValueError("metadata requires non-empty itemType and title")
    if pdf_path is not None:
        if not pdf_path.is_file():
            raise ValueError("pdf_path must point to an existing file")
        if pdf_path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("pdf_path exceeds the Local API limit (must be under 4 GiB)")
        with pdf_path.open("rb") as handle:
            if b"%PDF-" not in handle.read(1024):
                raise ValueError("pdf_path must point to a valid PDF")
    doi = _doi(metadata)
    query = doi or title
    qmode = "everything" if doi else "titleCreatorYear"
    candidates = adapter.search_items(query, qmode=qmode, limit=None)
    matches = [candidate for candidate in candidates if _exact_match(candidate, metadata)]
    if len(matches) > 1:
        keys = ", ".join(str(match.get("key", "?")) for match in matches)
        raise ZoteroIdentityConflict(f"multiple exact Zotero matches: {keys}")
    if matches:
        match = matches[0]
        item_key = str(match["key"])
        requested = list(dict.fromkeys(collection_keys or []))
        current = list(_data(match).get("collections", []) or [])
        merged = list(dict.fromkeys([*current, *requested]))
        status = "existing"

        complete_attachments: list[dict[str, Any]] = []
        incomplete_attachments: list[dict[str, Any]] = []
        if pdf_path is not None:
            attachments = _stored_pdf_attachments(adapter.get_children(item_key))
            complete_attachments = [item for item in attachments if _data(item).get("md5")]
            incomplete_attachments = [item for item in attachments if not _data(item).get("md5")]
            if len(incomplete_attachments) > 1 and not complete_attachments:
                keys = ", ".join(_attachment_key(item) for item in incomplete_attachments)
                raise ZoteroIdentityConflict(
                    f"multiple incomplete PDF attachments on Zotero item {item_key}: {keys}"
                )
            if not complete_attachments:
                adapter.ensure_write_authorization(require_remembered=True)

        if merged != current:
            version = match.get("version")
            if not isinstance(version, int) or isinstance(version, bool):
                raise ValueError("Zotero search result omitted a valid item version")
            adapter.update_item(
                item_key,
                {"collections": merged},
                version=version,
            )
            status = "existing_updated"

        if pdf_path is None:
            return {"status": status, "item_key": item_key}
        if complete_attachments:
            return {
                "status": status,
                "item_key": item_key,
                "attachment_key": _attachment_key(complete_attachments[0]),
                "uploaded": False,
            }
        try:
            if incomplete_attachments:
                attachment = adapter.upload_file(
                    _attachment_key(incomplete_attachments[0]),
                    pdf_path,
                )
            else:
                attachment = adapter.import_file(item_key, pdf_path)
        except Exception as exc:
            raise ZoteroPartialCompletion(
                item_key,
                getattr(exc, "attachment_key", None),
            ) from exc
        return {"status": "existing_updated", "item_key": item_key, **attachment}

    if pdf_path is not None:
        adapter.ensure_write_authorization(require_remembered=True)
    # The Zotero Local API write surface accepts partial item JSON, while some
    # Zotero 10 releases do not expose the Web API's /items/new template route.
    # Submit the authoritative fields directly instead of making creation
    # depend on that optional schema helper.
    item = dict(metadata)
    item.setdefault("tags", [])
    item.setdefault("relations", {})
    if collection_keys:
        item["collections"] = list(dict.fromkeys(collection_keys))
    item_key = adapter.create_item(item)
    if pdf_path is None:
        return {"status": "created", "item_key": item_key}
    try:
        attachment = adapter.import_file(item_key, pdf_path)
    except Exception as exc:
        raise ZoteroPartialCompletion(item_key, getattr(exc, "attachment_key", None)) from exc
    return {"status": "created", "item_key": item_key, **attachment}
