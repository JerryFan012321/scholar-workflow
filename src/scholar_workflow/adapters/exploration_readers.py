"""Session-only native PDF checks for explicitly referenced knowledge units."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import threading
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from scholar_workflow.adapters.obsidian_registry import resolve_obsidian_reader
from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
from scholar_workflow.adapters.zotflow import PdfRef, ZotFlowReaderAdapter
from scholar_workflow.config import DEFAULT_HOME
from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry
from scholar_workflow.workflows.exploration_references import ExplorationReferenceService

_KEY = re.compile(r"[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}\Z")
_VAULT = re.compile(r"[0-9a-f]{16}\Z")
_POSITIVE = re.compile(r"[1-9][0-9]*\Z")
_RESOURCE = re.compile(r"(?:paper|document):zotero:([1-9][0-9]*):([23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})\Z")


class ReaderUnavailable(RuntimeError):
    def __init__(self, message: str, code: str = "reader_unverified") -> None:
        super().__init__(message)
        self.code = code


def _reject(message: str, code: str = "identity_mismatch"):
    raise ReaderUnavailable(message, code)


def _key(value) -> bool:
    return isinstance(value, str) and _KEY.fullmatch(value) is not None


def _library(row) -> tuple[str, int]:
    value = row.get("library") if isinstance(row, dict) else None
    if (not isinstance(value, dict) or not isinstance(value.get("type"), str)
            or value["type"] not in {"user", "group"}
            or type(value.get("id")) is not int or value["id"] <= 0):
        _reject("The Zotero library identity could not be confirmed.")
    return value["type"], value["id"]


def _item(row, key: str, kind: str | None = None) -> dict:
    data = row.get("data") if isinstance(row, dict) else None
    if (not isinstance(row, dict) or row.get("key") != key or row.get("deleted")
            or not isinstance(data, dict) or data.get("deleted")
            or "key" in data and data["key"] != key):
        _reject("The Zotero item identity or active state changed.")
    item_type = data.get("itemType")
    if (not isinstance(item_type, str) or not item_type
            or kind is not None and item_type != kind
            or kind is None and item_type in {"attachment", "note", "annotation"}):
        _reject("The Zotero item type does not match this reading action.")
    return data


def _navigation(value: str) -> dict:
    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate navigation key")
            result[key] = item
        return result

    def invalid_constant(_value):
        raise ValueError("non-JSON navigation constant")

    try:
        navigation = json.loads(value, object_pairs_hook=unique_object,
                                parse_constant=invalid_constant)
    except (ValueError, TypeError, RecursionError):
        _reject("The ZotFlow navigation must be strict pageIndex JSON.", "invalid_reader_uri")
    if (not isinstance(navigation, dict) or set(navigation) != {"pageIndex"}
            or type(navigation["pageIndex"]) is not int or navigation["pageIndex"] < 0):
        _reject("The ZotFlow navigation must contain only a nonnegative integer pageIndex.",
                "invalid_reader_uri")
    return navigation


def parse_reading_uri(uri: str) -> dict:
    """Parse an exact reader URI; ownership, PDF bytes and local mode remain separate checks.

    The original URI is returned unchanged. ``page`` retains its one-based meaning;
    ``navigation`` retains ZotFlow's zero-based JSON and is never approximated as a page query.
    """
    if (not isinstance(uri, str) or len(uri) > 4096 or "\\" in uri
            or any(ord(char) <= 32 or ord(char) == 127 for char in uri)
            or re.search(r"%(?![0-9a-fA-F]{2})", uri)):
        _reject("The reader URI is invalid.", "invalid_reader_uri")
    try:
        parsed = urlsplit(uri)
        values = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        params = dict(values)
    except (ValueError, UnicodeError):
        _reject("The reader URI is invalid.", "invalid_reader_uri")
    if parsed.fragment or len(params) != len(values):
        _reject("The reader URI has duplicate parameters or a fragment.", "invalid_reader_uri")
    if "page" in params and not _POSITIVE.fullmatch(params["page"]):
        _reject("The PDF page must be a positive physical page number.", "invalid_reader_uri")
    if "page" in params and "navigation" in params:
        _reject("Choose either page or navigation, not both.", "invalid_reader_uri")
    location = {"uri": uri, "page": int(params["page"]) if "page" in params else None,
                "navigation": None}
    if parsed.scheme == "zotero" and parsed.netloc == "open-pdf":
        match = re.fullmatch(r"/(library|groups/([1-9][0-9]*))/items/([23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8})", parsed.path)
        if match is None or set(params) - {"page", "annotation"}:
            _reject("The Zotero PDF URI is invalid.", "invalid_reader_uri")
        if "annotation" in params and not _key(params["annotation"]):
            _reject("The annotation identity is invalid.", "invalid_reader_uri")
        return {**location, "kind": "zotero", "key": match[3], "group": match[2],
                "annotation": params.get("annotation")}
    if parsed.scheme == "obsidian" and parsed.netloc == "zotflow" and parsed.path in {"", "/"}:
        if (set(params) - {"vault", "type", "libraryID", "key", "page", "navigation"}
                or not {"vault", "type", "libraryID", "key"} <= set(params)
                or params["type"] not in {"open-attachment", "open-annotation"}
                or _VAULT.fullmatch(params["vault"]) is None
                or _POSITIVE.fullmatch(params["libraryID"]) is None
                or not _key(params["key"])):
            _reject("The ZotFlow reading URI is invalid.", "invalid_reader_uri")
        if "navigation" in params:
            location["navigation"] = _navigation(params["navigation"])
        return {**location, "kind": "zotflow", "key": params["key"], "vault": params["vault"],
                "library": params["libraryID"], "annotation":
                    params["key"] if params["type"] == "open-annotation" else None}
    _reject("The reader URI is not a supported reading action.", "invalid_reader_uri")


def _parse(uri: str) -> dict:
    """Compatibility helper sharing the public reading-URI parser."""
    return parse_reading_uri(uri)


def _stamp(work, asset) -> tuple:
    ref = work.get("entity_ref") if isinstance(work, dict) else None
    if (not isinstance(ref, dict) or set(ref) != {"source_id", "object_id"}
            or not isinstance(asset, dict)):
        _reject("A current qualified knowledge unit is required.", "unit_unavailable")
    values = (work.get("id"), asset.get("id"), asset.get("uri"), ref["source_id"], ref["object_id"])
    if any(not isinstance(value, str) or not value for value in values):
        _reject("A current qualified knowledge unit and asset are required.", "unit_unavailable")
    return values


def _verify_bytes(locator, pdf_ref: PdfRef) -> None:
    path = Path(locator.path)
    if not path.is_absolute():
        _reject("The local PDF is unavailable.", "local_pdf_unavailable")
    algorithm, expected = pdf_ref.content_hash.split(":", 1)
    digest = hashlib.md5(usedforsecurity=False) if algorithm == "md5" else hashlib.sha256()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                _reject("The local PDF is not a regular file.", "local_pdf_unavailable")
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(stream.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, field) != getattr(after, field) for field in fields):
                _reject("The local PDF changed during verification; refresh the assets.", "pdf_changed")
    except (OSError, ValueError, TypeError):
        _reject("The local PDF could not be read safely.", "local_pdf_unavailable")
    if not hmac.compare_digest(digest.hexdigest(), expected):
        _reject("The local PDF bytes changed; refresh the assets.", "pdf_changed")


class ExplorationReaderGate:
    """Keep native-opening verification in memory for this browser session only."""

    def __init__(self, registry_path=None, reference_service=None,
                 adapter_factory=ZoteroLocalAdapter, reader_factory=ZotFlowReaderAdapter,
                 obsidian_config_path=None):
        self.registry_path = (Path(registry_path) if registry_path is not None else
                              Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)) /
                              "hub" / "sources.json")
        self.references = (reference_service if reference_service is not None else
                           ExplorationReferenceService(self.registry_path))
        self._adapter_factory = adapter_factory
        self._reader_factory = reader_factory
        self._obsidian_config_path = obsidian_config_path
        self._snapshots = {}
        self._lock = threading.RLock()

    @staticmethod
    def handles(uri) -> bool:
        if not isinstance(uri, str):
            return False
        try:
            parsed = urlsplit(uri)
            action = parsed.hostname
            return ((parsed.scheme == "zotero" and action == "open-pdf")
                    or (parsed.scheme == "obsidian" and (action == "zotflow"
                        or parsed.path.strip("/").split("/")[0] == "zotflow")))
        except ValueError:
            return uri.lower().startswith(("zotero://open-pdf", "obsidian://zotflow"))

    def _verify(self, work, asset):
        stamp = _stamp(work, asset)
        action = _parse(stamp[2])
        registry = KnowledgeSourceRegistry(self.registry_path)
        try:
            revision = registry.revision()
            source_root = registry.resolve(stamp[3], capability="read")
        except (RuntimeError, OSError, ValueError):
            _reject("The registered knowledge Source is currently unavailable.", "unit_unavailable")
        try:
            unit = self.references.current_unit(work["entity_ref"])
        except (RuntimeError, OSError, ValueError, TypeError, KeyError):
            _reject("The referenced knowledge unit is currently unavailable.", "unit_unavailable")
        resource = unit.get("catalog_resource") if isinstance(unit, dict) else None
        if (not isinstance(unit, dict) or unit.get("source_id") != stamp[3]
                or unit.get("resource_id") != stamp[4]
                or not isinstance(unit.get("ownership"), dict)
                or unit["ownership"].get("status") != "resolved"
                or not isinstance(resource, dict) or resource.get("resource_id") != stamp[4]):
            _reject("The current unit ownership could not be confirmed.", "unit_unavailable")
        zotero = resource.get("zotero")
        item_key = zotero.get("item_key") if isinstance(zotero, dict) else None
        if not _key(item_key):
            _reject("The unit has no confirmed Zotero parent identity.", "unit_unavailable")
        with self._adapter_factory() as local:
            parent = local.get_item(item_key)
            _item(parent, item_key)
            library = _library(parent)
            formal = _RESOURCE.fullmatch(stamp[4])
            if formal is not None and (formal[1] != str(library[1]) or formal[2] != item_key):
                _reject("The registered unit and Zotero library identities do not agree.")
            if action["kind"] == "zotero":
                if ((action["group"] is None and library[0] != "user")
                        or (action["group"] is not None and library != ("group", int(action["group"])) )):
                    _reject("The reader URI does not match the confirmed Zotero library.")
            elif action["library"] != str(library[1]):
                _reject("The ZotFlow URI does not match the confirmed Zotero library.")
            annotation_key = action["annotation"]
            attachment_key = action["key"]
            annotation = None
            if annotation_key:
                annotation = local.get_item(annotation_key)
                annotation_data = _item(annotation, annotation_key, "annotation")
                if _library(annotation) != library or not _key(annotation_data.get("parentItem")):
                    _reject("The annotation does not belong to the confirmed library.")
                if action["kind"] == "zotflow":
                    attachment_key = annotation_data["parentItem"]
                elif annotation_data["parentItem"] != attachment_key:
                    _reject("The annotation does not belong to this PDF.")
            attachment = local.get_item(attachment_key)
            data = _item(attachment, attachment_key, "attachment")
            if data.get("parentItem") != item_key or _library(attachment) != library:
                _reject("The PDF is not an attachment of this knowledge unit.")
            locator = local.resolve_attachment_locator(attachment_key)
            if locator.attachment_key != attachment_key or str(locator.library_id) != str(library[1]):
                _reject("The resolved PDF identity changed; refresh the assets.")
            pdf_ref = PdfRef.from_locator(locator)
            _verify_bytes(locator, pdf_ref)
        if action["kind"] == "zotflow":
            binding = resolve_obsidian_reader(source_root, config_path=self._obsidian_config_path)
            if binding.vault_id != action["vault"]:
                _reject("The ZotFlow URI targets a different registered Vault.")
            reader = self._reader_factory(binding.vault_root,
                obsidian_config_path=self._obsidian_config_path, zotero_factory=self._adapter_factory)
            capability = reader.probe_attachment(pdf_ref, verify_content=True)
            if not capability.available:
                _reject("ZotFlow local PDF mode or reader compatibility is unavailable.", "zotflow_unavailable")
        if registry.revision() != revision or registry.resolve(stamp[3], capability="read") != source_root:
            _reject("The registered Source changed; refresh the assets.", "refresh_required")
        return stamp, revision, pdf_ref.model_dump_json()

    def _check(self, work, asset):
        try:
            return self._verify(work, asset)
        except ReaderUnavailable:
            raise
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, AttributeError):
            _reject("The local reader could not be verified safely.", "local_pdf_unavailable")

    def availability(self, work, asset) -> dict:
        if not self.handles(asset.get("uri") if isinstance(asset, dict) else None):
            return {"native_available": True}
        key = (work.get("id"), asset.get("id")) if isinstance(work, dict) else (None, None)
        try:
            snapshot = self._check(work, asset)
        except ReaderUnavailable as error:
            with self._lock:
                self._snapshots.pop(key, None)
            return {"native_available": False, "native_reason": str(error),
                    "native_reason_code": error.code}
        with self._lock:
            self._snapshots[key] = snapshot
        return {"native_available": True}

    def require_current(self, work, asset) -> None:
        if not self.handles(asset.get("uri") if isinstance(asset, dict) else None):
            return
        stamp = _stamp(work, asset)
        key = stamp[:2]
        with self._lock:
            snapshot = self._snapshots.get(key)
        if snapshot is None:
            _reject("Refresh the asset list before opening this reader.", "refresh_required")
        if snapshot[0] != stamp:
            _reject("The selected unit or asset changed; refresh the assets.", "refresh_required")
        current = self._check(work, asset)
        if current[1] != snapshot[1]:
            _reject("The registered Source changed; refresh the assets.", "refresh_required")
        if current != snapshot:
            _reject("The PDF or Source changed; refresh the assets.", "pdf_changed")
        with self._lock:
            if self._snapshots.get(key) != snapshot:
                _reject("The reader snapshot changed; refresh the assets.", "refresh_required")
