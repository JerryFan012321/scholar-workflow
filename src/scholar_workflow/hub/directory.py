"""Typed, rebuildable root directory for Hub Control Plane v2.

The directory is a projection over authoritative providers.  It intentionally
does not scan the filesystem or ``PATH`` for projects and tools.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid
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
from scholar_workflow.hub.models import HubCatalog, HubModel

_PORTABLE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,127}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9._:-]{0,63}$")
_LIBRARY_IDS = ("papers", "projects", "tools")
_LIBRARY_SPECS = {
    "papers": ("Papers", "paper", "Zotero Local API"),
    "projects": ("Projects", "project", "explicit host project registry"),
    "tools": ("Tools", "tool", "explicit tool registry"),
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


class LibraryDescriptor(HubModel):
    library_id: Literal["papers", "projects", "tools"]
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


class DirectoryDiagnostic(HubModel):
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    library_id: Literal["papers", "projects", "tools"] | None = None


class HubDirectory(HubModel):
    """The one canonical Hub root; ``knowledge_catalog`` is a subprojection."""

    schema_version: int = 2
    libraries: list[LibraryDescriptor]
    knowledge_catalog: HubCatalog
    knowledge_contexts: KnowledgeContextSummary
    operations: OperationStatus = Field(default_factory=OperationStatus)
    diagnostics: list[DirectoryDiagnostic] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 2:
            raise ValueError("unsupported HubDirectory schema version")
        return value

    @model_validator(mode="after")
    def _fixed_libraries(self) -> Self:
        identifiers = tuple(row.library_id for row in self.libraries)
        if identifiers != _LIBRARY_IDS:
            raise ValueError("HubDirectory must expose papers, projects, and tools in order")
        return self


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
        try:
            parsed = uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("project_id must be a canonical UUIDv4") from exc
        if parsed.version != 4 or str(parsed) != value:
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)


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
                raw_manifest_id = manifest.get("project_id")
                if not isinstance(raw_manifest_id, str):
                    raise TypeError("project_id must be a canonical string")
                manifest_id = uuid.UUID(raw_manifest_id)
            except (OSError, TypeError, ValueError, AttributeError, json.JSONDecodeError) as exc:
                raise RegistryError("Registered project layout identity is invalid") from exc
            if (
                manifest.get("schema_version") != 2
                or manifest_id.version != 4
                or raw_manifest_id != str(manifest_id)
                or str(manifest_id) != project.project_id
            ):
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
            reference = TypedEntityRef(
                library_id="papers",
                item_type="paper",
                item_id=resource.resource_id,
            ).model_dump(mode="json")
            rows.append(
                {
                    "ref": reference,
                    "landing_path": _typed_landing_path(reference),
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
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["item_id"])

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self._items() if row["ref"]["item_id"] == item_id),
            None,
        )

    def resolve_attachment(self, item_id: str) -> dict[str, Any] | None:
        for paper in self._items():
            if paper.get("attachment_key") != item_id:
                continue
            reference = TypedEntityRef(
                library_id="papers",
                item_type="attachment",
                item_id=item_id,
            ).model_dump(mode="json")
            return {
                "ref": reference,
                "landing_path": _typed_landing_path(reference),
                "title": f"PDF · {paper.get('title') or paper['resource_id']}",
                "parent_ref": paper["ref"],
                "attachment_key": item_id,
                "pdf_path": f"/open/paper/{item_id}",
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
        except (ZoteroLocalError, OSError, ValueError) as exc:
            raise LibraryProviderUnavailable("Zotero Local API is unavailable") from exc
        item["attachment_key"] = attachment_key
        item["pdf_path"] = f"/open/paper/{attachment_key}" if attachment_key else None
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
        reference = TypedEntityRef(
            library_id="papers",
            item_type="attachment",
            item_id=item_id,
        ).model_dump(mode="json")
        parent_key = data.get("parentItem")
        parent_ref = None
        if isinstance(parent_key, str) and ZOTERO_KEY_RE.fullmatch(parent_key):
            parent_ref = TypedEntityRef(
                library_id="papers",
                item_type="paper",
                item_id=parent_key,
            ).model_dump(mode="json")
        return {
            "ref": reference,
            "landing_path": _typed_landing_path(reference),
            "title": data.get("title") or filename or f"PDF {item_id}",
            "parent_ref": parent_ref,
            "attachment_key": item_id,
            "pdf_path": f"/open/paper/{item_id}",
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
                    item_type=item_type or _ZOTERO_BIBLIOGRAPHIC_QUERY,
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
                    item["pdf_path"] = (
                        f"/open/paper/{attachment_key}" if attachment_key else None
                    )
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
                    "ref": TypedEntityRef(
                        library_id="projects",
                        item_type="project",
                        item_id=project.project_id,
                    ).model_dump(mode="json"),
                    "display_name": project.display_name,
                    "enabled": project.enabled,
                    "capabilities": list(project.capabilities),
                    "docs_available": docs_available,
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["item_id"])

    def status(self) -> tuple[int, str | None]:
        count = len(self._items())
        return count, "No projects are registered" if count == 0 else None

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self._items() if row["ref"]["item_id"] == item_id),
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
                    "ref": TypedEntityRef(
                        library_id="tools",
                        item_type="tool",
                        item_id=tool.tool_id,
                    ).model_dump(mode="json"),
                    "display_name": tool.display_name,
                    "tool_type": tool.tool_type,
                    "source": tool.source,
                    "enabled": tool.enabled,
                    "capabilities": list(tool.capabilities),
                    "recipe_ids": list(tool.recipe_ids),
                    "healthcheck": tool.healthcheck,
                }
            )
        return sorted(rows, key=lambda row: row["ref"]["item_id"])

    def status(self) -> tuple[int, str | None]:
        count = len(self._items())
        return count, "No tools are registered" if count == 0 else None

    def resolve(self, item_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self._items() if row["ref"]["item_id"] == item_id),
            None,
        )

    def page(self, *, offset: int, limit: int, query: str, sort: str, direction: str,
             item_type: str | None) -> _ProviderPage:
        return _registry_page(
            self._items(), offset=offset, limit=limit, query=query, sort=sort,
            direction=direction, item_type=item_type,
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
            if item_type in {row["ref"]["item_type"], row.get("tool_type"), row.get("zotero_item_type")}
        ]
    def sort_key(row: dict[str, Any]) -> tuple[int, str]:
        if sort == "id":
            return 0, str(row["ref"]["item_id"]).casefold()
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
    reference = TypedEntityRef(
        library_id="papers",
        item_type="paper",
        item_id=key,
    ).model_dump(mode="json")
    return {
        "ref": reference,
        "landing_path": _typed_landing_path(reference),
        "title": title if isinstance(title, str) and title else None,
        "resource_id": f"zotero:{key}",
        "kind": "paper",
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
        operation_status: Callable[[], OperationStatus] | None = None,
    ) -> None:
        self.catalog_provider = catalog_provider
        self.project_registry = project_registry
        self.tool_registry = tool_registry
        self._operation_status = operation_status or OperationStatus
        self._providers: dict[str, _LibraryProvider] = {
            "papers": paper_provider or _PaperProvider(catalog_provider),
            "projects": _ProjectProvider(project_registry),
            "tools": _ToolProvider(tool_registry),
        }

    def load(self) -> HubDirectory:
        catalog = self.catalog_provider.load()
        descriptors, diagnostics = self._descriptors()
        return HubDirectory(
            libraries=descriptors,
            knowledge_catalog=catalog,
            knowledge_contexts=KnowledgeContextSummary(
                topic_count=len(catalog.topics),
                artifact_count=len(catalog.artifacts),
                asset_count=len(catalog.assets),
            ),
            operations=self._operation_status(),
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
        if library_id not in self._providers:
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
        if (
            library_id == "papers"
            and item_type is not None
            and item_type not in _ZOTERO_BIBLIOGRAPHIC_TYPES
        ):
            raise ValueError("paper type filter must be a bibliographic Zotero item type")
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

    def resolve_item(self, reference: TypedEntityRef) -> dict[str, Any] | None:
        """Resolve one typed identity without materializing a live provider's full library."""
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
                payload["landing_path"] = _typed_landing_path(payload["ref"])
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
                payload["landing_path"] = _typed_landing_path(payload["ref"])
                payload["title"] = topic.name
                return payload
            return None
        provider = self._providers[reference.library_id]
        if reference.library_id == "papers":
            if reference.item_type == "paper":
                return provider.resolve(reference.item_id)
            if reference.item_type == "attachment":
                resolver = getattr(provider, "resolve_attachment", None)
                return resolver(reference.item_id) if resolver is not None else None
            return None
        expected_type = "project" if reference.library_id == "projects" else "tool"
        if reference.item_type != expected_type:
            return None
        return provider.resolve(reference.item_id)

    def compatibility_catalog(self) -> HubCatalog:
        """Derive the v1 response from the one v2 root, never another store."""
        return self.load().knowledge_catalog

    def _descriptors(self) -> tuple[list[LibraryDescriptor], list[DirectoryDiagnostic]]:
        descriptors = []
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
                        library_id=library_id,
                    )
                )
            except RegistryError:
                count = 0
                available = False
                detail = f"The {library_id} provider registry is invalid"
                diagnostics.append(
                    DirectoryDiagnostic(
                        level="error",
                        code=f"{library_id}_provider_invalid",
                        message=detail,
                        library_id=library_id,
                    )
                )
            descriptors.append(
                LibraryDescriptor(
                    library_id=library_id,
                    label=label,
                    item_type=item_type,
                    authority=authority,
                    available=available,
                    total_count=count,
                    detail=detail,
                )
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
