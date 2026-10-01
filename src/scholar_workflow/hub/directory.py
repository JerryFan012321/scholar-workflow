"""Typed, rebuildable root directory for Hub Control Plane v3.

The directory is a projection over authoritative providers.  It intentionally
does not scan the filesystem or ``PATH`` for projects and tools.
"""
from __future__ import annotations

import base64
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, Protocol, Self
from urllib.parse import urlencode

from pydantic import Field, field_validator, model_validator

from scholar_workflow.adapters.zotero_local import (
    ZOTERO_KEY_RE,
    ZoteroLocalAdapter,
    ZoteroLocalError,
)
from scholar_workflow.hub.catalog import CatalogProvider
from scholar_workflow.knowledge.fields import FieldRegistryError, FieldService
from scholar_workflow.knowledge.catalog_models import HubCatalog, HubModel
from scholar_workflow.hub.zotflow import PdfRef
from scholar_workflow.project.layout import is_project_id, validate_project_identity

_PORTABLE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
_LIBRARY_IDS = ("papers", "fields")
_LIBRARY_SPECS = {
    "papers": ("Papers", "paper", "Zotero Local API"),
    "fields": ("Fields", "field", "explicit Obsidian source manifests"),
}
_PUBLIC_PAPER_TYPES = ("Paper", "Report", "Book", "Webpage", "Other")
_PUBLIC_TO_ZOTERO_TYPES = {
    "Paper": (
        "conferencePaper", "journalArticle", "manuscript", "preprint",
        "presentation", "thesis",
    ),
    "Report": ("report", "standard"),
    "Book": ("book", "bookSection", "dictionaryEntry", "encyclopediaArticle"),
    "Webpage": ("blogPost", "forumPost", "webpage"),
    "Other": (
        "artwork", "audioRecording", "bill", "case", "computerProgram", "dataset",
        "email", "film", "hearing", "instantMessage", "interview", "letter",
        "magazineArticle", "map", "newspaperArticle", "patent", "podcast",
        "radioBroadcast", "statute", "tvBroadcast", "videoRecording",
    ),
}
_ZOTERO_BIBLIOGRAPHIC_TYPES = (
    "artwork",
    "audioRecording",
    "bill",
    "blogPost",
    "book",
    "bookSection",
    "case",
    "computerProgram",
    "conferencePaper",
    "dataset",
    "dictionaryEntry",
    "document",
    "email",
    "encyclopediaArticle",
    "film",
    "forumPost",
    "hearing",
    "instantMessage",
    "interview",
    "journalArticle",
    "letter",
    "magazineArticle",
    "manuscript",
    "map",
    "newspaperArticle",
    "patent",
    "podcast",
    "preprint",
    "presentation",
    "radioBroadcast",
    "report",
    "standard",
    "statute",
    "thesis",
    "tvBroadcast",
    "videoRecording",
    "webpage",
)
_ZOTERO_BIBLIOGRAPHIC_QUERY = " || ".join(_ZOTERO_BIBLIOGRAPHIC_TYPES)


class RegistryError(RuntimeError):
    """An explicit host registry could not be validated."""


class UnknownLibraryError(KeyError):
    """A caller requested an unregistered library."""


class TypedEntityRef(HubModel):
    # ``knowledge`` is a typed namespace for knowledge_catalog/context landings;
    # it is deliberately not a fourth LibraryDescriptor/provider.
    library_id: Literal["papers", "projects", "tools", "knowledge"]
    item_type: str = Field(min_length=1, max_length=64)
    item_id: str = Field(min_length=1, max_length=256)

    @field_validator("item_type", "item_id")
    @classmethod
    def _clean_identifier(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("typed reference identifiers must be clean text")
        return value


class EntityRef(HubModel):
    """Provider-scoped v3 identity; URLs and host paths are never identities."""

    provider_id: str = Field(min_length=1, max_length=128)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=256)

    @field_validator("provider_id", "entity_type", "entity_id")
    @classmethod
    def _clean_identifier(cls, value: str) -> str:
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("entity reference identifiers must be clean text")
        return value


class LibraryDescriptor(HubModel):
    library_id: Literal["papers", "fields"]
    label: str
    item_type: str
    authority: str
    available: bool
    total_count: int = Field(ge=0)
    detail: str | None = None


class KnowledgeContextSummary(HubModel):
    topic_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    asset_count: int = Field(ge=0)


class OperationStatus(HubModel):
    bound: bool = False
    project_documents: bool = False
    workspace_actions: bool = False
    task_actions: bool = False
    reason: str | None = "Hub view is not bound to a workspace"


class CapabilityStatus(HubModel):
    available: bool
    reason: str | None = None


class CapabilityMatrix(HubModel):
    vault_writes: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="No writable knowledge source is registered"
        )
    )
    project_document_writes: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="No writable project is registered"
        )
    )
    cmux_launches: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="No cmux destination is selected"
        )
    )
    codex_tasks: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="Codex task worker is not enabled"
        )
    )
    zotflow_annotations: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="ZotFlow capability has not been verified"
        )
    )
    zotero_local_api: CapabilityStatus = Field(
        default_factory=lambda: CapabilityStatus(
            available=False, reason="Zotero Local API has not been probed"
        )
    )


class DirectoryDiagnostic(HubModel):
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    scope: str | None = None


class DocumentLibraries(HubModel):
    papers: LibraryDescriptor
    fields: LibraryDescriptor


class ProjectDescriptor(HubModel):
    ref: EntityRef
    project_id: str
    display_name: str
    enabled: bool
    capabilities: list[str] = Field(default_factory=list)
    docs_available: bool = False


class ToolDescriptor(HubModel):
    ref: EntityRef
    tool_id: str
    display_name: str
    tool_type: str
    source: str
    enabled: bool
    capabilities: list[str] = Field(default_factory=list)
    recipe_ids: list[str] = Field(default_factory=list)
    healthcheck: str | None = None


class HubDirectory(HubModel):
    """The one canonical v3 root; all compatibility views derive from it."""

    schema_version: int = 3
    libraries: DocumentLibraries
    projects: list[ProjectDescriptor] = Field(default_factory=list)
    tools: list[ToolDescriptor] = Field(default_factory=list)
    capabilities: CapabilityMatrix = Field(default_factory=CapabilityMatrix)
    diagnostics: list[DirectoryDiagnostic] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 3:
            raise ValueError("unsupported HubDirectory schema version")
        return value


class LibraryPage(HubModel):
    library: LibraryDescriptor
    items: list[dict[str, Any]]
    next_cursor: str | None = None


class ProjectRegistration(HubModel):
    project_id: str
    display_name: str = Field(min_length=1, max_length=200)
    root: Path
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)

    @field_validator("project_id")
    @classmethod
    def _project_id(cls, value: str) -> str:
        if not is_project_id(value):
            raise ValueError("project_id must be a canonical UUIDv4")
        return value

    @field_validator("root")
    @classmethod
    def _absolute_root(cls, value: Path) -> Path:
        expanded = value.expanduser()
        if not expanded.is_absolute():
            raise ValueError("project registry roots must be absolute host paths")
        return expanded

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate project capability")
        if any(not _CAPABILITY.fullmatch(value) for value in values):
            raise ValueError("invalid project capability")
        return values


class ProjectRegistryDocument(HubModel):
    schema_version: int = 1
    projects: list[ProjectRegistration] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported project registry schema version")
        return value

    @model_validator(mode="after")
    def _unique_projects(self) -> Self:
        identifiers = [row.project_id for row in self.projects]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate project_id")
        return self


class ToolDefinition(HubModel):
    tool_id: str
    display_name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=200)
    tool_type: Literal["scholar-workflow", "codex", "cmux", "zotero", "obsidian", "external"]
    capabilities: list[str] = Field(default_factory=list)
    recipe_ids: list[str] = Field(default_factory=list)
    healthcheck: str | None = None
    enabled: bool = True

    @field_validator("tool_id")
    @classmethod
    def _tool_id(cls, value: str) -> str:
        if not _PORTABLE_ID.fullmatch(value):
            raise ValueError("tool_id must be a portable stable identifier")
        return value

    @field_validator("capabilities", "recipe_ids")
    @classmethod
    def _unique_clean_lists(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate tool capability or recipe")
        if any(not _CAPABILITY.fullmatch(value) for value in values):
            raise ValueError("invalid tool capability or recipe")
        return values

    @field_validator("healthcheck")
    @classmethod
    def _healthcheck_id(cls, value: str | None) -> str | None:
        if value is not None and not _CAPABILITY.fullmatch(value):
            raise ValueError("healthcheck must be a registered identifier, not a command")
        return value


class ToolRegistryDocument(HubModel):
    schema_version: int = 1
    tools: list[ToolDefinition] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported tool registry schema version")
        return value

    @model_validator(mode="after")
    def _unique_tools(self) -> Self:
        identifiers = [row.tool_id for row in self.tools]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate tool_id")
        return self


class _ExplicitJSONRegistry:
    document_type: type[HubModel]
    collection_field: str

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> list[Any]:
        if not self.path.exists():
            return []
        if self.path.is_symlink() or not self.path.is_file():
            raise RegistryError(f"Invalid explicit registry: {self.path.name}")
        try:
            document = self.document_type.model_validate_json(
                self.path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise RegistryError(f"Invalid explicit registry: {self.path.name}") from exc
        return list(getattr(document, self.collection_field))

    def save(self, rows: list[Any]) -> None:
        """Atomically save caller-supplied registrations; never discover entries."""
        document = self.document_type.model_validate(
            {"schema_version": 1, self.collection_field: rows}
        )
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if parent.is_symlink() or not parent.is_dir() or self.path.is_symlink():
            raise RegistryError(f"Invalid explicit registry path: {self.path.name}")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=parent
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(document.model_dump_json(indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600, follow_symlinks=False)
        finally:
            temporary.unlink(missing_ok=True)


class ProjectRegistry(_ExplicitJSONRegistry):
    document_type = ProjectRegistryDocument
    collection_field = "projects"

    def resolve(self, project_id: str, *, capability: str | None = None) -> ProjectRegistration:
        for project in self.load():
            if project.project_id != project_id:
                continue
            if not project.enabled:
                raise RegistryError("Project is disabled")
            if capability is not None and capability not in project.capabilities:
                raise RegistryError(f"Project does not allow capability: {capability}")
            try:
                root = project.root.resolve(strict=True)
            except OSError as exc:
                raise RegistryError("Registered project root is unavailable") from exc
            if not root.is_dir():
                raise RegistryError("Registered project root is unavailable")
            manifest_path = root / "project-layout.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise RegistryError("Registered project has no trusted project-layout.json")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_id = validate_project_identity(manifest)
            except (OSError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
                raise RegistryError("Registered project layout identity is invalid") from exc
            if manifest_id != project.project_id:
                raise RegistryError("Project registry identity does not match project-layout.json")
            return project.model_copy(update={"root": root})
        raise RegistryError("Unknown project_id")


class ToolRegistry(_ExplicitJSONRegistry):
    document_type = ToolRegistryDocument
    collection_field = "tools"


class LibraryProviderUnavailable(RuntimeError):
    """A typed library's authoritative provider is currently unavailable."""


class _ProviderPage(HubModel):
    items: list[dict[str, Any]]
    total_count: int = Field(ge=0)
    has_more: bool
    consumed_count: int = Field(ge=0)


class _LibraryProvider(Protocol):
    def status(self) -> tuple[int, str | None]: ...

    def page(
        self,
        *,
        offset: int,
        limit: int,
        query: str,
        sort: str,
        direction: str,
        item_type: str | None,
    ) -> _ProviderPage: ...

    def resolve(self, item_id: str) -> dict[str, Any] | None: ...


def _typed_landing_path(reference: dict[str, str]) -> str:
    """Legacy one-cycle compatibility route; v3 never emits it in normal items."""
    return "/hub/item?" + urlencode(
        {
            "library_id": reference["library_id"],
            "item_type": reference["item_type"],
            "item_id": reference["item_id"],
        }
    )


class _PaperProvider:
    """Compatibility provider for injected/catalog-only callers and tests."""

    def __init__(self, catalog_provider: CatalogProvider) -> None:
        self._catalog_provider = catalog_provider

    def _items(self) -> list[dict[str, Any]]:
        catalog = self._catalog_provider.load()
        rows = []
        for resource in catalog.resources:
            if str(resource.kind) != "paper":
                continue
            item_id = resource.zotero.item_key or resource.resource_id
            reference = EntityRef(
                provider_id="zotero" if resource.zotero.item_key else "knowledge-catalog",
                entity_type="paper",
                entity_id=item_id,
            ).model_dump(mode="json")
            rows.append(
                {
                    "ref": reference,
                    "title": resource.title,
                    "resource_id": resource.resource_id,
                    "kind": str(resource.kind),
                    "authors": list(resource.authors),
                    "year": resource.year,
                    "venue": resource.venue,
                    "importance": resource.importance,
                    "identifiers": resource.identifiers.model_dump(mode="json"),
                    "topic_ids": list(resource.topic_ids),
                    "zotero_item_key": resource.zotero.item_key,
                    "attachment_key": resource.zotero.attachment_key,
                    "paper_type": "Paper",
                    "pdf_ref": None,
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["entity_id"])

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self._items()
                if row["ref"]["entity_id"] == item_id
                or row.get("resource_id") == item_id
            ),
            None,
        )

    def resolve_attachment(self, item_id: str) -> dict[str, Any] | None:
        for paper in self._items():
            if paper.get("attachment_key") != item_id:
                continue
            reference = EntityRef(
                provider_id="zotero",
                entity_type="attachment",
                entity_id=item_id,
            ).model_dump(mode="json")
            return {
                "ref": reference,
                "title": f"PDF · {paper.get('title') or paper['resource_id']}",
                "parent_ref": paper["ref"],
                "attachment_key": item_id,
                "pdf_path": f"/api/v3/pdfs/zotero/{item_id}/content",
                "pdf_ref": paper.get("pdf_ref"),
            }
        return None

    def status(self) -> tuple[int, str | None]:
        count = len(self._items())
        detail = "No papers are available from the catalog provider" if count == 0 else None
        return count, detail

    def page(
        self,
        *,
        offset: int,
        limit: int,
        query: str,
        sort: str,
        direction: str,
        item_type: str | None,
    ) -> _ProviderPage:
        return _registry_page(
            self._items(), offset=offset, limit=limit, query=query, sort=sort,
            direction=direction, item_type=item_type,
        )


class ZoteroPaperLibraryProvider:
    """Page Zotero directly, without materializing the complete paper library."""

    def __init__(
        self,
        adapter_factory: Callable[[], ZoteroLocalAdapter] = ZoteroLocalAdapter,
    ) -> None:
        self._adapter_factory = adapter_factory

    def status(self) -> tuple[int, str | None]:
        page = self._read_page(
            offset=0, limit=1, query="", sort="title", direction="asc", item_type=None
        )
        detail = "No papers are available from Zotero" if page.total_count == 0 else None
        return page.total_count, detail

    def page(self, *, offset: int, limit: int, query: str, sort: str, direction: str,
             item_type: str | None) -> _ProviderPage:
        return self._read_page(
            offset=offset, limit=limit, query=query, sort=sort,
            direction=direction, item_type=item_type,
        )

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        try:
            with self._adapter_factory() as adapter:
                item = _zotero_paper_item(adapter.get_item(item_id))
                if item is None:
                    return None
                attachment_key = _pdf_attachment_key(adapter.get_children(item_id))
                pdf_ref = None
                pdf_detail = None
                if attachment_key:
                    try:
                        locator = adapter.resolve_attachment_locator(attachment_key)
                        pdf_ref = PdfRef.from_locator(locator).model_dump(mode="json")
                    except ZoteroLocalError as exc:
                        pdf_detail = str(exc)
        except (ZoteroLocalError, OSError, ValueError) as exc:
            raise LibraryProviderUnavailable("Zotero Local API is unavailable") from exc
        item["attachment_key"] = attachment_key
        item["pdf_ref"] = pdf_ref
        item["pdf_detail"] = pdf_detail
        item["pdf_path"] = (
            f"/api/v3/pdfs/zotero/{attachment_key}/content" if pdf_ref else None
        )
        return item

    def resolve_attachment(self, item_id: str) -> dict[str, Any] | None:
        try:
            with self._adapter_factory() as adapter:
                payload = adapter.get_item(item_id)
        except (ZoteroLocalError, OSError, ValueError) as exc:
            raise LibraryProviderUnavailable("Zotero Local API is unavailable") from exc
        data = payload.get("data")
        key = payload.get("key")
        if (
            key != item_id
            or not isinstance(data, dict)
            or data.get("itemType") != "attachment"
        ):
            return None
        content_type = str(data.get("contentType") or "").casefold()
        filename = str(data.get("filename") or "")
        if content_type != "application/pdf" and not filename.casefold().endswith(".pdf"):
            return None
        try:
            with self._adapter_factory() as adapter:
                locator = adapter.resolve_attachment_locator(item_id)
        except (ZoteroLocalError, OSError, ValueError) as exc:
            raise LibraryProviderUnavailable("Zotero PDF is unavailable") from exc
        reference = EntityRef(
            provider_id="zotero",
            entity_type="attachment",
            entity_id=item_id,
        ).model_dump(mode="json")
        parent_key = data.get("parentItem")
        parent_ref = None
        if isinstance(parent_key, str) and ZOTERO_KEY_RE.fullmatch(parent_key):
            parent_ref = EntityRef(
                provider_id="zotero",
                entity_type="paper",
                entity_id=parent_key,
            ).model_dump(mode="json")
        return {
            "ref": reference,
            "title": data.get("title") or filename or f"PDF {item_id}",
            "parent_ref": parent_ref,
            "attachment_key": item_id,
            "pdf_path": f"/api/v3/pdfs/zotero/{item_id}/content",
            "pdf_ref": PdfRef.from_locator(locator).model_dump(mode="json"),
        }

    def _read_page(self, *, offset: int, limit: int, query: str, sort: str,
                   direction: str, item_type: str | None) -> _ProviderPage:
        try:
            with self._adapter_factory() as adapter:
                zotero_page = adapter.list_items_page(
                    start=offset,
                    limit=limit,
                    query=query or None,
                    sort={"id": "dateAdded", "title": "title", "year": "date"}[sort],
                    direction=direction,
                    item_type=(
                        " || ".join(_PUBLIC_TO_ZOTERO_TYPES[item_type])
                        if item_type in _PUBLIC_TO_ZOTERO_TYPES
                        else item_type
                        if item_type in _ZOTERO_BIBLIOGRAPHIC_TYPES
                        else _ZOTERO_BIBLIOGRAPHIC_QUERY
                    ),
                )
                visible_items = []
                for row in zotero_page.items:
                    item = _zotero_paper_item(row)
                    if item is None:
                        continue
                    attachment_key = _pdf_attachment_key(
                        adapter.get_children(item["zotero_item_key"])
                    )
                    item["attachment_key"] = attachment_key
                    item["pdf_ref"] = None
                    item["pdf_detail"] = None
                    if attachment_key:
                        try:
                            locator = adapter.resolve_attachment_locator(attachment_key)
                            item["pdf_ref"] = PdfRef.from_locator(locator).model_dump(
                                mode="json"
                            )
                            item["pdf_path"] = (
                                f"/api/v3/pdfs/zotero/{attachment_key}/content"
                            )
                        except ZoteroLocalError as exc:
                            item["pdf_path"] = None
                            item["pdf_detail"] = str(exc)
                    visible_items.append(item)
        except (ZoteroLocalError, OSError) as exc:
            raise LibraryProviderUnavailable("Zotero Local API is unavailable") from exc
        if zotero_page.total is None:
            total = offset + len(zotero_page.items)
            has_more = len(zotero_page.items) == limit
        else:
            total = zotero_page.total
            has_more = offset + len(zotero_page.items) < total
        return _ProviderPage(
            items=visible_items,
            total_count=total,
            has_more=has_more,
            consumed_count=len(zotero_page.items),
        )


class _ProjectProvider:
    def __init__(self, registry: ProjectRegistry) -> None:
        self._registry = registry

    def _items(self) -> list[dict[str, Any]]:
        rows = []
        for project in self._registry.load():
            docs_available = False
            if project.enabled:
                resolved_project = self._registry.resolve(project.project_id)
                try:
                    root = resolved_project.root
                    docs = root / "docs"
                    docs_available = docs.is_dir() and not docs.is_symlink()
                except OSError:
                    pass
            rows.append(
                {
                    "ref": EntityRef(
                        provider_id="project-registry",
                        entity_type="project",
                        entity_id=project.project_id,
                    ).model_dump(mode="json"),
                    "project_id": project.project_id,
                    "display_name": project.display_name,
                    "enabled": project.enabled,
                    "capabilities": list(project.capabilities),
                    "docs_available": docs_available,
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["entity_id"])

    def status(self) -> tuple[int, str | None]:
        count = len(self._items())
        return count, "No projects are registered" if count == 0 else None

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self._items() if row["ref"]["entity_id"] == item_id),
            None,
        )

    def page(self, *, offset: int, limit: int, query: str, sort: str, direction: str,
             item_type: str | None) -> _ProviderPage:
        return _registry_page(
            self._items(), offset=offset, limit=limit, query=query, sort=sort,
            direction=direction, item_type=item_type,
        )


class _ToolProvider:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def _items(self) -> list[dict[str, Any]]:
        rows = []
        for tool in self._registry.load():
            rows.append(
                {
                    "ref": EntityRef(
                        provider_id="tool-registry",
                        entity_type="tool",
                        entity_id=tool.tool_id,
                    ).model_dump(mode="json"),
                    "tool_id": tool.tool_id,
                    "display_name": tool.display_name,
                    "tool_type": tool.tool_type,
                    "source": tool.source,
                    "enabled": tool.enabled,
                    "capabilities": list(tool.capabilities),
                    "recipe_ids": list(tool.recipe_ids),
                    "healthcheck": tool.healthcheck,
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["entity_id"])

    def status(self) -> tuple[int, str | None]:
        count = len(self._items())
        return count, "No tools are registered" if count == 0 else None

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self._items() if row["ref"]["entity_id"] == item_id),
            None,
        )

    def page(self, *, offset: int, limit: int, query: str, sort: str, direction: str,
             item_type: str | None) -> _ProviderPage:
        return _registry_page(
            self._items(), offset=offset, limit=limit, query=query, sort=sort,
            direction=direction, item_type=item_type,
        )


class _FieldProvider:
    def __init__(self, service: FieldService | None) -> None:
        self._service = service

    def _items(self) -> list[dict[str, Any]]:
        if self._service is None:
            return []
        rows = []
        for field in self._service.list_fields():
            field_id = field.get("field_id")
            source_id = field.get("source_id")
            if not isinstance(field_id, str) or not isinstance(source_id, str):
                continue
            rows.append(
                {
                    **field,
                    "ref": EntityRef(
                        provider_id=source_id,
                        entity_type="field",
                        entity_id=field_id,
                    ).model_dump(mode="json"),
                }
            )
        return sorted(
            rows,
            key=lambda row: (
                not bool(row.get("available")),
                str(row.get("title") or row.get("field_id") or "").casefold(),
            ),
        )

    def status(self) -> tuple[int, str | None]:
        rows = self._items()
        count = sum(bool(row.get("field_id")) for row in rows)
        detail = None
        if self._service is None:
            detail = "No Obsidian source registry is configured"
        elif count == 0:
            detail = "No Fields are registered; choose a Vault or folder to preview"
        return count, detail

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (
                row
                for row in self._items()
                if row.get("ref", {}).get("entity_id") == item_id
            ),
            None,
        )

    def page(
        self,
        *,
        offset: int,
        limit: int,
        query: str,
        sort: str,
        direction: str,
        item_type: str | None,
    ) -> _ProviderPage:
        return _registry_page(
            self._items(),
            offset=offset,
            limit=limit,
            query=query,
            sort=sort,
            direction=direction,
            item_type=item_type,
        )


def _registry_page(
    items: list[dict[str, Any]],
    *,
    offset: int,
    limit: int,
    query: str,
    sort: str,
    direction: str,
    item_type: str | None,
) -> _ProviderPage:
    if query:
        items = [
            row
            for row in items
            if query in json.dumps(row, ensure_ascii=False).casefold()
        ]
    if item_type:
        items = [
            row for row in items
            if item_type in {
                row["ref"].get("entity_type", row["ref"].get("item_type")),
                row.get("tool_type"),
                row.get("zotero_item_type"),
                row.get("paper_type"),
            }
        ]
    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        if sort == "id":
            return 0, str(
                row["ref"].get("entity_id", row["ref"].get("item_id", ""))
            ).casefold()
        value = row.get(sort)
        if sort == "title" and value is None:
            value = row.get("display_name")
        if value is None:
            return 1, ""
        if sort == "year" and isinstance(value, int):
            return 0, f"{value:09d}"
        return 0, str(value).casefold()

    items.sort(
        key=sort_key,
        reverse=direction == "desc",
    )
    if sort != "id":
        items.sort(
            key=lambda row: (
                row.get(sort) is None
                and not (sort == "title" and row.get("display_name") is not None)
            )
        )
    page = items[offset:offset + limit]
    return _ProviderPage(
        items=page,
        total_count=len(items),
        has_more=offset + len(page) < len(items),
        consumed_count=len(page),
    )


def _zotero_paper_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    key = payload.get("key")
    data = payload.get("data")
    if not isinstance(key, str) or not ZOTERO_KEY_RE.fullmatch(key) or not isinstance(data, dict):
        return None
    zotero_item_type = data.get("itemType")
    if zotero_item_type not in _ZOTERO_BIBLIOGRAPHIC_TYPES:
        return None
    creators = data.get("creators")
    authors = []
    if isinstance(creators, list):
        for creator in creators:
            if not isinstance(creator, dict):
                continue
            name = creator.get("name")
            if not isinstance(name, str):
                parts = [creator.get("firstName"), creator.get("lastName")]
                name = " ".join(part for part in parts if isinstance(part, str) and part)
            if name:
                authors.append(name)
    raw_date = data.get("date")
    year_match = re.search(
        r"\b(1[5-9]\d{2}|20\d{2}|21\d{2})\b",
        str(raw_date or ""),
    )
    title = data.get("title")
    doi = data.get("DOI")
    url = data.get("url")
    reference = EntityRef(
        provider_id="zotero",
        entity_type="paper",
        entity_id=key,
    ).model_dump(mode="json")
    return {
        "ref": reference,
        "title": title if isinstance(title, str) and title else None,
        "resource_id": f"zotero:{key}",
        "kind": "paper",
        "paper_type": _public_paper_type(str(zotero_item_type)),
        "zotero_item_type": zotero_item_type,
        "authors": authors,
        "year": int(year_match.group(1)) if year_match else None,
        "venue": data.get("publicationTitle") or data.get("conferenceName"),
        "importance": None,
        "identifiers": {
            "doi": doi if isinstance(doi, str) and doi else None,
            "arxiv": None,
            "isbn": data.get("ISBN") if isinstance(data.get("ISBN"), str) else None,
            "url": url if isinstance(url, str) and url else None,
        },
        "topic_ids": [],
        "zotero_item_key": key,
        "attachment_key": None,
        "pdf_path": None,
    }


def _public_paper_type(zotero_item_type: str) -> str:
    for public_type, item_types in _PUBLIC_TO_ZOTERO_TYPES.items():
        if zotero_item_type in item_types:
            return public_type
    return "Other"


def _pdf_attachment_key(children: list[dict[str, Any]]) -> str | None:
    candidates = []
    for child in children:
        key = child.get("key")
        data = child.get("data")
        if not isinstance(key, str) or not ZOTERO_KEY_RE.fullmatch(key):
            continue
        if not isinstance(data, dict) or data.get("itemType") != "attachment":
            continue
        content_type = str(data.get("contentType") or "").casefold()
        filename = str(data.get("filename") or "").casefold()
        if content_type == "application/pdf" or filename.endswith(".pdf"):
            candidates.append(key)
    return min(candidates) if candidates else None


class HubDirectoryService:
    """Build the canonical root and page typed libraries on the server."""

    def __init__(
        self,
        catalog_provider: CatalogProvider,
        project_registry: ProjectRegistry,
        tool_registry: ToolRegistry,
        *,
        paper_provider: _LibraryProvider | None = None,
        field_service: FieldService | None = None,
        capability_status: Callable[[], CapabilityMatrix] | None = None,
        operation_status: Callable[[], OperationStatus] | None = None,
    ) -> None:
        self.catalog_provider = catalog_provider
        self.project_registry = project_registry
        self.tool_registry = tool_registry
        self.field_service = field_service
        self._capability_status = capability_status or CapabilityMatrix
        self._operation_status = operation_status or OperationStatus
        self._providers: dict[str, _LibraryProvider] = {
            "papers": paper_provider or _PaperProvider(catalog_provider),
            "fields": _FieldProvider(field_service),
        }
        self._project_provider = _ProjectProvider(project_registry)
        self._tool_provider = _ToolProvider(tool_registry)

    def load(self) -> HubDirectory:
        descriptors, diagnostics = self._descriptors()
        try:
            projects = [ProjectDescriptor.model_validate(row) for row in self._project_provider._items()]
        except (RegistryError, OSError, ValueError):
            projects = []
            diagnostics.append(
                DirectoryDiagnostic(
                    level="error",
                    code="projects_provider_invalid",
                    message="The explicit project registry is invalid",
                    scope="projects",
                )
            )
        try:
            tools = [ToolDescriptor.model_validate(row) for row in self._tool_provider._items()]
        except (RegistryError, OSError, ValueError):
            tools = []
            diagnostics.append(
                DirectoryDiagnostic(
                    level="error",
                    code="tools_provider_invalid",
                    message="The explicit tool registry is invalid",
                    scope="tools",
                )
            )
        return HubDirectory(
            libraries=DocumentLibraries(
                papers=descriptors["papers"],
                fields=descriptors["fields"],
            ),
            projects=projects,
            tools=tools,
            capabilities=self._capability_status(),
            diagnostics=diagnostics,
        )

    def list_items(
        self,
        library_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        query: str | None = None,
        sort: str = "title",
        direction: str = "asc",
        item_type: str | None = None,
    ) -> LibraryPage:
        if library_id not in _LIBRARY_IDS:
            raise UnknownLibraryError(library_id)
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        normalized_query = (query or "").strip().casefold()
        if len(normalized_query) > 200:
            raise ValueError("query is too long")
        if sort not in {"id", "title", "year"}:
            raise ValueError("sort must be id, title, or year")
        if direction not in {"asc", "desc"}:
            raise ValueError("direction must be asc or desc")
        if item_type is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", item_type):
            raise ValueError("invalid type filter")
        if library_id == "papers" and item_type not in {None, *_PUBLIC_PAPER_TYPES}:
            raise ValueError(
                "paper type filter must be Paper, Report, Book, Webpage, or Other"
            )
        if library_id == "fields" and item_type not in {None, "field"}:
            raise ValueError("Fields only expose the field type")
        offset = _decode_cursor(
            cursor, library_id, normalized_query, sort, direction, item_type
        )
        provider_page = self._providers[library_id].page(
            offset=offset,
            limit=limit,
            query=normalized_query,
            sort=sort,
            direction=direction,
            item_type=item_type,
        )
        label, descriptor_item_type, authority = _LIBRARY_SPECS[library_id]
        descriptor = LibraryDescriptor(
            library_id=library_id,
            label=label,
            item_type=descriptor_item_type,
            authority=authority,
            available=True,
            total_count=provider_page.total_count,
            detail=(
                f"No {library_id} are available"
                if provider_page.total_count == 0
                else None
            ),
        )
        next_offset = offset + provider_page.consumed_count
        next_cursor = (
            _encode_cursor(
                library_id, normalized_query, sort, direction, item_type, next_offset
            )
            if provider_page.has_more
            else None
        )
        descriptor = descriptor.model_copy(update={"total_count": provider_page.total_count})
        return LibraryPage(
            library=descriptor,
            items=provider_page.items,
            next_cursor=next_cursor,
        )

    def resolve_entity(self, reference: EntityRef) -> dict[str, Any] | None:
        if reference.provider_id == "zotero":
            provider = self._providers["papers"]
            if reference.entity_type == "paper":
                return provider.resolve(reference.entity_id)
            if reference.entity_type == "attachment":
                resolver = getattr(provider, "resolve_attachment", None)
                return resolver(reference.entity_id) if resolver is not None else None
            return None
        if reference.provider_id == "project-registry" and reference.entity_type == "project":
            return self._project_provider.resolve(reference.entity_id)
        if reference.provider_id == "tool-registry" and reference.entity_type == "tool":
            return self._tool_provider.resolve(reference.entity_id)
        if reference.entity_type == "field":
            return self._providers["fields"].resolve(reference.entity_id)
        return None

    def resolve_item(self, reference: TypedEntityRef) -> dict[str, Any] | None:
        """Resolve the one-cycle v2 typed identity compatibility surface."""
        if reference.library_id == "knowledge":
            catalog = self.catalog_provider.load()
            if reference.item_type == "artifact":
                artifact = next(
                    (
                        row
                        for row in catalog.artifacts
                        if row.artifact_id == reference.item_id
                    ),
                    None,
                )
                if artifact is None:
                    return None
                payload = artifact.model_dump(mode="json")
                payload["ref"] = reference.model_dump(mode="json")
                payload["title"] = artifact.artifact_id
                return payload
            if reference.item_type == "topic":
                topic = next(
                    (row for row in catalog.topics if row.topic_id == reference.item_id),
                    None,
                )
                if topic is None:
                    return None
                payload = topic.model_dump(mode="json")
                payload["ref"] = reference.model_dump(mode="json")
                payload["title"] = topic.name
                return payload
            return None
        if reference.library_id == "papers":
            provider = self._providers["papers"]
            if reference.item_type == "paper":
                return provider.resolve(reference.item_id)
            if reference.item_type == "attachment":
                resolver = getattr(provider, "resolve_attachment", None)
                return resolver(reference.item_id) if resolver is not None else None
            return None
        provider = (
            self._project_provider
            if reference.library_id == "projects"
            else self._tool_provider
        )
        expected_type = "project" if reference.library_id == "projects" else "tool"
        if reference.item_type != expected_type:
            return None
        return provider.resolve(reference.item_id)

    def compatibility_catalog(self) -> HubCatalog:
        """Derive the v1 response from v3 providers, never another fact root."""
        return self.catalog_provider.load()

    def compatibility_directory_v2(self) -> dict[str, Any]:
        """Return a read-only v2-shaped projection of the canonical v3 root."""
        root = self.load()
        catalog = self.catalog_provider.load()
        paper = root.libraries.papers.model_dump(mode="json")
        project_count = len(root.projects)
        tool_count = len(root.tools)
        libraries = [
            paper,
            {
                "library_id": "projects",
                "label": "Projects",
                "item_type": "project",
                "authority": "explicit host project registry",
                "available": not any(
                    row.code == "projects_provider_invalid" for row in root.diagnostics
                ),
                "total_count": project_count,
                "detail": "No projects are registered" if project_count == 0 else None,
            },
            {
                "library_id": "tools",
                "label": "Tools",
                "item_type": "tool",
                "authority": "explicit tool registry",
                "available": not any(
                    row.code == "tools_provider_invalid" for row in root.diagnostics
                ),
                "total_count": tool_count,
                "detail": "No tools are registered" if tool_count == 0 else None,
            },
        ]
        return {
            "schema_version": 2,
            "libraries": libraries,
            "knowledge_catalog": catalog.model_dump(mode="json"),
            "knowledge_contexts": {
                "topic_count": len(catalog.topics),
                "artifact_count": len(catalog.artifacts),
                "asset_count": len(catalog.assets),
            },
            "operations": self._operation_status().model_dump(mode="json"),
            "diagnostics": [row.model_dump(mode="json") for row in root.diagnostics],
        }

    def list_compat_items(self, library_id: str, **kwargs: Any) -> dict[str, Any]:
        """Derive v2 paging, including former project/tool pseudo-libraries."""
        if library_id in _LIBRARY_IDS:
            page = self.list_items(library_id, **kwargs)
            payload = page.model_dump(mode="json")
            payload["items"] = [self._legacy_item(row, library_id) for row in payload["items"]]
            return payload
        provider = {
            "projects": self._project_provider,
            "tools": self._tool_provider,
        }.get(library_id)
        if provider is None:
            raise UnknownLibraryError(library_id)
        cursor = kwargs.pop("cursor", None)
        limit = kwargs.pop("limit", 50)
        query = (kwargs.pop("query", None) or "").strip().casefold()
        sort = kwargs.pop("sort", "title")
        direction = kwargs.pop("direction", "asc")
        item_type = kwargs.pop("item_type", None)
        if kwargs:
            raise ValueError("unsupported compatibility paging option")
        offset = _decode_cursor(cursor, library_id, query, sort, direction, item_type)
        provider_page = provider.page(
            offset=offset,
            limit=limit,
            query=query,
            sort=sort,
            direction=direction,
            item_type=item_type,
        )
        next_offset = offset + provider_page.consumed_count
        return {
            "library": {
                "library_id": library_id,
                "label": "Projects" if library_id == "projects" else "Tools",
                "item_type": "project" if library_id == "projects" else "tool",
                "authority": (
                    "explicit host project registry"
                    if library_id == "projects"
                    else "explicit tool registry"
                ),
                "available": True,
                "total_count": provider_page.total_count,
                "detail": None,
            },
            "items": [self._legacy_item(row, library_id) for row in provider_page.items],
            "next_cursor": (
                _encode_cursor(library_id, query, sort, direction, item_type, next_offset)
                if provider_page.has_more
                else None
            ),
        }

    @staticmethod
    def _legacy_item(row: dict[str, Any], library_id: str) -> dict[str, Any]:
        payload = dict(row)
        reference = row.get("ref", {})
        entity_type = str(reference.get("entity_type") or "item")
        entity_id = str(reference.get("entity_id") or "")
        legacy_ref = {
            "library_id": library_id,
            "item_type": entity_type,
            "item_id": entity_id,
        }
        payload["ref"] = legacy_ref
        payload["landing_path"] = _typed_landing_path(legacy_ref)
        return payload

    def _descriptors(self) -> tuple[dict[str, LibraryDescriptor], list[DirectoryDiagnostic]]:
        descriptors = {}
        diagnostics = []
        for library_id in _LIBRARY_IDS:
            label, item_type, authority = _LIBRARY_SPECS[library_id]
            try:
                count, detail = self._providers[library_id].status()
                available = True
            except LibraryProviderUnavailable:
                count = 0
                available = False
                detail = f"The {library_id} authoritative provider is unavailable"
                diagnostics.append(
                    DirectoryDiagnostic(
                        level="warning",
                        code=f"{library_id}_provider_unavailable",
                        message=detail,
                        scope=library_id,
                    )
                )
            except (RegistryError, FieldRegistryError):
                count = 0
                available = False
                detail = f"The {library_id} provider registry is invalid"
                diagnostics.append(
                    DirectoryDiagnostic(
                        level="error",
                        code=f"{library_id}_provider_invalid",
                        message=detail,
                        scope=library_id,
                    )
                )
            descriptors[library_id] = LibraryDescriptor(
                library_id=library_id,
                label=label,
                item_type=item_type,
                authority=authority,
                available=available,
                total_count=count,
                detail=detail,
            )
        return descriptors, diagnostics


def _encode_cursor(
    library_id: str,
    query: str,
    sort: str,
    direction: str,
    item_type: str | None,
    offset: int,
) -> str:
    raw = json.dumps(
        {
            "v": 1, "library": library_id, "query": query, "sort": sort,
            "direction": direction, "type": item_type, "offset": offset,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None,
    library_id: str,
    query: str,
    sort: str,
    direction: str,
    item_type: str | None,
) -> int:
    if cursor is None:
        return 0
    if not cursor or len(cursor) > 512:
        raise ValueError("invalid cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if set(payload) != {"v", "library", "query", "sort", "direction", "type", "offset"}:
            raise ValueError
        if (
            payload["v"] != 1 or payload["library"] != library_id
            or payload["query"] != query or payload["sort"] != sort
            or payload["direction"] != direction or payload["type"] != item_type
        ):
            raise ValueError
        offset = payload["offset"]
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError
        return offset
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid cursor") from exc


__all__ = [
    "DirectoryDiagnostic",
    "HubDirectory",
    "HubDirectoryService",
    "LibraryDescriptor",
    "LibraryPage",
    "OperationStatus",
    "ProjectRegistration",
    "ProjectRegistry",
    "RegistryError",
    "ToolDefinition",
    "ToolRegistry",
    "TypedEntityRef",
    "UnknownLibraryError",
]
