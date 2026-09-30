"""Lazy paper-owned documents from explicit provider relationships.

Only declared resource/artifact links and Zotero child identities create rows.
Document names and paths never establish paper ownership.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from pathlib import Path, PurePosixPath
from typing import Any

from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter, ZoteroLocalError
from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.hub.actions import (
    ActionKind,
    CatalogActionService,
    RelatedObsidianLauncher,
    WorkspacePolicy,
    ZotFlowSourceNoteLauncher,
)
from scholar_workflow.hub.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    _open_directory_chain,
)
from scholar_workflow.hub.zotflow import PdfRef

_ITEM_KEY = re.compile(r"^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$")
_MAX_PREVIEW_BYTES = 2 * 1024 * 1024
_ROLE_NAMES = {
    "paper-hub": "resource-note",
    "paper-analysis": "analysis",
    "analysis-canvas": "analysis-canvas",
    "annotation-note": "annotations",
    "reading-note": "reading-note",
    "analysis_canvas": "analysis-canvas",
    "reading_note": "reading-note",
}


class PaperRelatedError(RuntimeError):
    """A paper relation or its registered document is no longer available."""


@dataclass(frozen=True)
class _Document:
    paper_key: str
    provider_id: str
    document_id: str
    title: str
    role: str
    format: str
    relative_path: str
    source_id: str | None
    source_name: str

    @property
    def identity(self) -> tuple[str, str]:
        return self.provider_id, self.document_id

    @property
    def ref(self) -> dict[str, str]:
        return {
            "provider_id": self.provider_id,
            "entity_type": "document",
            "entity_id": self.document_id,
        }


class PaperRelatedService:
    """Read related files on demand and keep action/preview paths server-side."""

    def __init__(
        self,
        catalog_provider: Any,
        action_service: CatalogActionService,
        vault_root: Path,
        *,
        source_registry: KnowledgeSourceRegistry | None = None,
        adapter_factory: Any = ZoteroLocalAdapter,
        snapshot_loader: Callable[[], Any] | None = None,
        zotflow_adapter: Any | None = None,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._actions = action_service
        self._vault_root = Path(vault_root)
        self._sources = source_registry
        self._adapter_factory = adapter_factory
        state_root = getattr(catalog_provider, "state_root", None)
        self._snapshot_loader = snapshot_loader or (
            (lambda: load_knowledge_provider_snapshot(state_root))
            if state_root is not None else None
        )
        self._zotflow = (
            ZotFlowSourceNoteLauncher(zotflow_adapter)
            if zotflow_adapter is not None else None
        )
        self._lock = threading.RLock()
        self._tokens: dict[str, _Document] = {}
        self._document_tokens: dict[tuple[str, str, str], str] = {}
        self._actions.add_launcher(
            ActionKind.OBSIDIAN_RELATED_FILE, RelatedObsidianLauncher(self.resolve_file)
        )
        if self._zotflow is not None:
            self._actions.add_launcher(ActionKind.ZOTFLOW_SOURCE_NOTE, self._zotflow)

    def public_related(self, item_key: str) -> dict[str, Any]:
        """Return safe rows for one paper; no global Vault scan is performed."""
        self._validate_key(item_key)
        documents, contexts, diagnostics = self._declared_documents(item_key)
        rows = [self._public_document(document) for document in documents]
        library_id, children, child_diagnostics = self._zotero_children(item_key)
        rows.extend(children)
        diagnostics.extend(child_diagnostics)
        if library_id is not None:
            rows.extend(self._source_note_rows(item_key, library_id))
        return {
            "paper_ref": {
                "provider_id": "zotero", "entity_type": "paper", "entity_id": item_key,
            },
            "documents": rows,
            "field_contexts": contexts,
            "diagnostics": diagnostics,
        }

    def read_preview(self, preview_id: str) -> dict[str, str]:
        document = self._current_document(preview_id)
        if document.format != "markdown":
            raise PaperRelatedError("Only registered Markdown documents have a Hub preview")
        descriptor, _path = self._open_document(document)
        try:
            with os.fdopen(descriptor, "rb") as handle:
                payload = handle.read(_MAX_PREVIEW_BYTES + 1)
        except OSError as exc:
            raise PaperRelatedError("Related document could not be read") from exc
        if len(payload) > _MAX_PREVIEW_BYTES:
            raise PaperRelatedError("Related document exceeds the preview size limit")
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PaperRelatedError("Related document is not UTF-8 Markdown") from exc
        return {
            "title": document.title,
            "content": content,
            "revision": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }

    def resolve_file(self, token: str) -> Path:
        document = self._current_document(token)
        descriptor, path = self._open_document(document)
        os.close(descriptor)
        return path

    def contains_ref(self, ref: Any) -> bool:
        """Validate a previously exposed document context against current ownership."""
        payload = ref.model_dump(mode="json") if hasattr(ref, "model_dump") else ref
        if not isinstance(payload, dict):
            return False
        identity = (payload.get("provider_id"), payload.get("entity_id"))
        if payload.get("entity_type") != "document":
            return False
        with self._lock:
            tokens = [
                token for token, document in self._tokens.items()
                if document.identity == identity
            ]
        for token in tokens:
            try:
                self.resolve_file(token)
                return True
            except PaperRelatedError:
                continue
        return False

    @staticmethod
    def _validate_key(item_key: str) -> None:
        if not isinstance(item_key, str) or not _ITEM_KEY.fullmatch(item_key):
            raise PaperRelatedError("Paper identity is not a Zotero item key")

    def _current_document(self, token: str) -> _Document:
        with self._lock:
            saved = self._tokens.get(token)
        if saved is None:
            raise PaperRelatedError("Related document identity is unknown; refresh the paper")
        documents, _contexts, _diagnostics = self._declared_documents(saved.paper_key)
        current = next((row for row in documents if row.identity == saved.identity), None)
        if current is None or current != saved:
            raise PaperRelatedError("Related document registration changed; refresh the paper")
        return current

    def _root(self, document: _Document) -> Path:
        if document.source_id is None:
            return self._vault_root
        if self._sources is None:
            raise PaperRelatedError("Knowledge Source is no longer registered")
        try:
            return self._sources.resolve(document.source_id, capability="read")
        except FieldRegistryError as exc:
            raise PaperRelatedError("Knowledge Source is unavailable or disabled") from exc

    def _open_document(self, document: _Document) -> tuple[int, Path]:
        relative = PurePosixPath(document.relative_path)
        if (
            not document.relative_path or relative.is_absolute()
            or document.relative_path != relative.as_posix()
            or any(part in {".", ".."} for part in relative.parts)
            or "\\" in document.relative_path
        ):
            raise PaperRelatedError("Related document path is invalid")
        root = self._root(document)
        parent_fd: int | None = None
        descriptor: int | None = None
        try:
            parent_fd = _open_directory_chain(root, relative.parts[:-1])
            descriptor = os.open(
                relative.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd,
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("document is not a regular file")
            expected_suffix = {"markdown": ".md", "canvas": ".canvas"}.get(document.format)
            if expected_suffix is not None and relative.suffix.lower() != expected_suffix:
                raise OSError("document format differs from its registered path")
            return descriptor, root.joinpath(*relative.parts)
        except (OSError, ValueError) as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise PaperRelatedError("Related file is missing or its path is unsafe") from exc
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

    def _public_document(self, document: _Document) -> dict[str, Any]:
        available, reason = True, None
        try:
            descriptor, _path = self._open_document(document)
            os.close(descriptor)
        except PaperRelatedError as exc:
            available, reason = False, str(exc)
        with self._lock:
            identity = (document.paper_key, *document.identity)
            token = self._document_tokens.get(identity)
            if token is None or self._tokens.get(token) != document:
                token = f"related_{secrets.token_urlsafe(24)}"
                self._document_tokens[identity] = token
                self._tokens[token] = document
        actions = []
        if document.format in {"markdown", "canvas"}:
            action = self._actions.register_related_action(
                kind=ActionKind.OBSIDIAN_RELATED_FILE,
                label="Open in Obsidian", target=token,
                available=available, reason=reason,
            )
            if action is not None:
                actions.append(action)
        row: dict[str, Any] = {
            "ref": document.ref, "title": document.title,
            "role": document.role, "format": document.format,
            "source_name": document.source_name,
            "available": available, "reason": reason, "actions": actions,
        }
        if document.format == "markdown" and available:
            row["preview_id"] = token
        return row

    def _registered_source(self, root: Path) -> tuple[str | None, str]:
        if self._sources is not None:
            registry = self._sources.load_document()
            folders = {row.folder_id: row for row in registry.folders}
            for source in registry.sources:
                try:
                    registered = folders[source.folder_id].root
                    if root.samefile(registered):
                        # Keep a disabled declaration visible; _root rejects its reads.
                        return source.source_id, registered.name
                except OSError:
                    continue
        return None, root.name

    def _declared_documents(
        self, item_key: str
    ) -> tuple[list[_Document], list[dict[str, str]], list[str]]:
        catalog = self._catalog_provider.load()
        resource_ids = {
            row.resource_id for row in catalog.resources if row.zotero.item_key == item_key
        }
        artifacts = {row.artifact_id: row for row in catalog.artifacts}
        artifact_ids = {
            artifact_id for row in catalog.resources if row.resource_id in resource_ids
            for artifact_id in row.artifact_ids
        }
        artifact_ids.update(
            row.artifact_id for row in catalog.artifacts
            if row.resource_id in resource_ids or row.parent_id in resource_ids
        )
        while True:
            descendants = {
                row.artifact_id for row in catalog.artifacts if row.parent_id in artifact_ids
            }
            if descendants.issubset(artifact_ids):
                break
            artifact_ids.update(descendants)
        diagnostics: list[str] = []
        contexts: list[dict[str, str]] = []
        documents: dict[tuple[str, str], _Document] = {}
        root = self._vault_root
        source_id, source_name = self._registered_source(root)
        manifest = None
        if self._snapshot_loader is not None:
            try:
                snapshot = self._snapshot_loader()
                binding = snapshot.vault_binding
                if binding is None:
                    raise PaperRelatedError("Knowledge provider has no trusted Vault binding")
                root = Path(binding.root_path)
                metadata = root.stat(follow_symlinks=False)
                if root.is_symlink() or (metadata.st_dev, metadata.st_ino) != (
                    binding.device, binding.inode
                ):
                    raise PaperRelatedError("Knowledge provider Vault binding changed")
                source_id, source_name = self._registered_source(root)
                if source_id is None:
                    raise PaperRelatedError("Knowledge provider Vault is not a registered Source")
                manifest = snapshot.manifest
            except (OSError, ValueError, RuntimeError) as exc:
                diagnostics.append(
                    str(exc) if isinstance(exc, PaperRelatedError)
                    else "Knowledge provider is unavailable or invalid"
                )
                return [], [], diagnostics
        provider_id = f"obsidian:{source_id}" if source_id else "knowledge"
        if manifest is not None:
            for resource in manifest.atomic_resources:
                if resource.resource_id not in resource_ids:
                    continue
                document = _Document(
                    item_key, provider_id, resource.resource_id,
                    resource.title, "resource-note", "markdown", resource.markdown_path,
                    source_id, source_name,
                )
                documents[document.identity] = document
            for supporting in manifest.supporting_documents:
                if supporting.owner_id not in resource_ids:
                    continue
                suffix = PurePosixPath(supporting.vault_path).suffix.lower()
                format_name = {".md": "markdown", ".canvas": "canvas"}.get(suffix, "file")
                document = _Document(
                    item_key, provider_id, supporting.document_id, supporting.title,
                    _ROLE_NAMES.get(supporting.kind.value, supporting.kind.value),
                    format_name, supporting.vault_path, source_id, source_name,
                )
                documents[document.identity] = document
        for artifact_id in sorted(artifact_ids):
            artifact = artifacts.get(artifact_id)
            if artifact is None:
                diagnostics.append(f"Declared related artifact is missing: {artifact_id}")
                continue
            if artifact.resource_id is not None and artifact.resource_id not in resource_ids:
                diagnostics.append("A related artifact has conflicting paper ownership")
                continue
            if (provider_id, artifact_id) in documents:
                continue
            document = _Document(
                item_key, provider_id, artifact_id,
                PurePosixPath(artifact.vault_path).stem,
                _ROLE_NAMES.get(artifact.kind.value, artifact.kind.value),
                artifact.format.value, artifact.vault_path, source_id, source_name,
            )
            documents[document.identity] = document
        if source_id and self._sources:
            try:
                self._sources.resolve(source_id, capability="read")
                fields = FieldService._load_manifest(root).fields
                for field in fields:
                    prefix = field.relative_root.rstrip("/") + "/"
                    if any(
                        field.relative_root == "." or row.relative_path.startswith(prefix)
                        for row in documents.values()
                    ):
                        contexts.append({
                            "source_id": source_id, "field_id": field.field_id,
                            "title": field.title,
                        })
            except FieldRegistryError as exc:
                diagnostics.append(str(exc))
        return list(documents.values()), contexts, diagnostics

    def _zotero_children(
        self, item_key: str
    ) -> tuple[int | None, list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        try:
            with self._adapter_factory() as adapter:
                parent = adapter.get_item(item_key)
                if not isinstance(parent, dict) or parent.get("key") != item_key:
                    raise ZoteroLocalError("Zotero parent identity is invalid")
                parent_data = parent.get("data")
                if (
                    not isinstance(parent_data, dict)
                    or parent_data.get("itemType") in {"attachment", "note", "annotation"}
                    or parent_data.get("deleted") or parent.get("deleted")
                ):
                    raise PaperRelatedError("Item is not an active Zotero paper")
                library_id = parent.get("library", {}).get("id")
                if type(library_id) is not int or library_id <= 0:
                    library_id = None
                child_reader = getattr(adapter, "get_children_all", None)
                children = (
                    child_reader(item_key) if child_reader is not None
                    else adapter.get_children(item_key)
                )
                if not isinstance(children, list):
                    raise ZoteroLocalError("Zotero children response is invalid")
                for child in children:
                    if not isinstance(child, dict):
                        continue
                    key, data = child.get("key"), child.get("data")
                    if (
                        not isinstance(key, str) or not _ITEM_KEY.fullmatch(key)
                        or not isinstance(data, dict) or data.get("parentItem") != item_key
                        or data.get("itemType") not in {"note", "attachment"}
                        or data.get("deleted") or child.get("deleted")
                    ):
                        continue
                    child_library = child.get("library", {}).get("id")
                    if library_id is not None and child_library != library_id:
                        continue
                    kind = data["itemType"]
                    title = str(data.get("title") or "").strip()
                    if not title and kind == "note":
                        title = unescape(re.sub(r"<[^>]*>", " ", str(data.get("note") or "")))
                        title = " ".join(title.split())[:160]
                    title = title or ("Zotero note" if kind == "note" else "Zotero attachment")
                    actions = []
                    select_action = self._actions.register_related_action(
                        kind=ActionKind.ZOTERO_ITEM, label="Open in Zotero", target=key,
                    )
                    if select_action is not None:
                        actions.append(select_action)
                    available, reason = True, None
                    format_name = "note" if kind == "note" else str(data.get("contentType") or "file")
                    if kind == "attachment" and data.get("contentType") == "application/pdf":
                        format_name = "pdf"
                        try:
                            pdf = PdfRef.from_locator(adapter.resolve_attachment_locator(key))
                        except (ZoteroLocalError, OSError, ValueError):
                            reason = "Local PDF is unavailable; no cloud download was attempted"
                            available = False
                        else:
                            for action_kind, label, target in (
                                (ActionKind.ZOTERO_PDF, "Read in Zotero", pdf.model_dump_json()),
                                (ActionKind.RESOURCE_CMUX, "Read original PDF in cmux (no Zotero annotations)", key),
                            ):
                                action = self._actions.register_related_action(
                                    kind=action_kind, label=label, target=target,
                                    workspace_policy=(
                                        WorkspacePolicy.REQUIRED
                                        if action_kind is ActionKind.RESOURCE_CMUX
                                        else WorkspacePolicy.NONE
                                    ),
                                )
                                if action is not None:
                                    actions.append(action)
                    rows.append({
                        "ref": {"provider_id": "zotero", "entity_type": kind, "entity_id": key},
                        "title": title, "role": f"zotero-{kind}", "format": format_name,
                        "source_name": "Zotero", "available": available,
                        "reason": reason, "actions": actions,
                    })
        except (ZoteroLocalError, OSError, ValueError) as exc:
            return None, rows, [f"Zotero related items are unavailable: {exc}"]
        return library_id, rows, []

    def _source_note_rows(self, item_key: str, library_id: int) -> list[dict[str, Any]]:
        if self._sources is None or self._zotflow is None:
            return []
        rows = []
        for source in self._sources.load_document().sources:
            if not source.enabled:
                continue
            try:
                root = self._sources.resolve(source.source_id, capability="read")
                capability = self._zotflow.availability(
                    library_id, item_key, source_id=source.source_id
                )
                available = bool(capability.available)
                reason = capability.reason
            except (FieldRegistryError, ValueError, RuntimeError):
                continue
            target = json.dumps({
                "library_id": library_id, "item_key": item_key, "source_id": source.source_id,
            })
            action = self._actions.register_related_action(
                kind=ActionKind.ZOTFLOW_SOURCE_NOTE, label="Open ZotFlow source note",
                target=target, available=available, reason=reason,
            )
            rows.append({
                "ref": {
                    "provider_id": f"zotflow:{source.source_id}",
                    "entity_type": "source-note", "entity_id": f"{library_id}:{item_key}",
                },
                "title": "ZotFlow source note", "role": "zotflow-source-note",
                "format": "provider-note", "source_name": root.name,
                "available": available, "reason": reason,
                "actions": [action] if action is not None else [],
            })
        return rows
