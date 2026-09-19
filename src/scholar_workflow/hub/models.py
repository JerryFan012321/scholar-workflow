"""Canonical models shared by every Scholar Workflow Hub projection.

``HubCatalog`` is a rebuildable snapshot of identities and relationships.  It
does not own paper metadata, note bodies, files, URLs to launch, or commands to
execute.  Zotero remains authoritative for bibliography; the Vault remains
authoritative for human-readable notes.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scholar_workflow.models import Identifiers, ResourceKind


_ZOTERO_KEY = re.compile(r"^[23456789ABCDEFGHIJKLMNPQRSTUVWXYZ]{8}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+\-]*/[a-z0-9][a-z0-9!#$&^_.+\-]*$"
)


class HubModel(BaseModel):
    """Strict base so a contract change cannot be hidden in an extra field."""

    model_config = ConfigDict(extra="forbid")


class ArtifactKind(StrEnum):
    COLLECTION_INDEX = "collection-index"
    PAPER_LIST = "paper-list"
    PAPER_HUB = "paper-hub"
    LITERATURE_TREE = "literature-tree"
    PAPER_ANALYSIS = "paper-analysis"
    ANALYSIS_CANVAS = "analysis-canvas"
    ANNOTATION_NOTE = "annotation-note"
    READING_NOTE = "reading-note"
    DIRECTION_NOTE = "direction-note"
    TECHNICAL_DOCUMENT = "technical-document"


class ArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    CANVAS = "canvas"
    FILE = "file"


class TreeKind(StrEnum):
    TECHNICAL = "technical"
    CHALLENGE = "challenge"


class AssetRole(StrEnum):
    """How a Vault asset is presented beside its owning document."""

    EMBED = "embed"
    SUPPLEMENT = "supplement"
    DATA = "data"
    SOURCE = "source"


class ZoteroLink(HubModel):
    item_key: str | None = None
    attachment_key: str | None = None
    collection_keys: list[str] = Field(default_factory=list)

    @field_validator("item_key", "attachment_key")
    @classmethod
    def _valid_optional_key(cls, value: str | None) -> str | None:
        if value is not None and not _ZOTERO_KEY.fullmatch(value):
            raise ValueError("invalid Zotero key")
        return value

    @field_validator("collection_keys")
    @classmethod
    def _valid_collection_keys(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate Zotero collection key")
        if any(not _ZOTERO_KEY.fullmatch(value) for value in values):
            raise ValueError("invalid Zotero collection key")
        return values


class ProjectionLinks(HubModel):
    """Stable remote projection IDs only; never URLs or executable actions."""

    notion_page_id: str | None = None


class HubResource(HubModel):
    resource_id: str = Field(min_length=1)
    kind: ResourceKind
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    importance: str | None = None
    identifiers: Identifiers = Field(default_factory=Identifiers)
    zotero: ZoteroLink = Field(default_factory=ZoteroLink)
    projections: ProjectionLinks = Field(default_factory=ProjectionLinks)
    topic_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_refs(self) -> Self:
        _ensure_unique(self.topic_ids, "topic ID on resource")
        _ensure_unique(self.artifact_ids, "artifact ID on resource")
        return self


class HubTopic(HubModel):
    topic_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    parent_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_refs(self) -> Self:
        _ensure_unique(self.resource_ids, "resource ID on topic")
        _ensure_unique(self.artifact_ids, "artifact ID on topic")
        return self


class HubArtifact(HubModel):
    artifact_id: str = Field(min_length=1)
    kind: ArtifactKind
    format: ArtifactFormat
    vault_path: str
    resource_id: str | None = None
    topic_id: str | None = None
    parent_id: str | None = None
    tree_kind: TreeKind | None = None
    revision: str | None = None

    @field_validator("vault_path")
    @classmethod
    def _vault_relative_posix_path(cls, value: str) -> str:
        return _validate_vault_relative_path(value)


class HubAsset(HubModel):
    """A Vault-owned supporting file explicitly attached to Hub artifacts.

    Paper PDFs are deliberately absent: their opaque attachment keys live under
    ``HubResource.zotero`` and Zotero remains authoritative for their bytes.
    """

    asset_id: str = Field(min_length=1)
    owner_artifact_ids: list[str] = Field(min_length=1)
    vault_path: str
    display_name: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size: int = Field(ge=0)
    sha256: str
    role: AssetRole

    @field_validator("owner_artifact_ids")
    @classmethod
    def _unique_owners(cls, values: list[str]) -> list[str]:
        _ensure_unique(values, "owner artifact ID on asset")
        return values

    @field_validator("vault_path")
    @classmethod
    def _vault_relative_posix_path(cls, value: str) -> str:
        return _validate_vault_relative_path(value)

    @field_validator("display_name")
    @classmethod
    def _single_visible_name(cls, value: str) -> str:
        if (
            value in {"", ".", ".."}
            or value.startswith(".")
            or value.endswith((" ", "."))
            or any(char in value for char in '<>:"/\\|?*')
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError("display_name must be one visible cross-platform filename")
        return value

    @field_validator("media_type")
    @classmethod
    def _valid_media_type(cls, value: str) -> str:
        normalized = value.lower()
        if not _MEDIA_TYPE.fullmatch(normalized):
            raise ValueError("invalid media_type")
        return normalized

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("sha256 must use the sha256:<hex> form")
        return value


class SourceStatus(HubModel):
    source: str = Field(min_length=1)
    available: bool
    detail: str | None = None


class CatalogDiagnostic(HubModel):
    level: str
    code: str
    message: str
    entity_id: str | None = None


def _validate_vault_relative_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError("vault_path must be a non-empty POSIX path")
    path = PurePosixPath(value)
    raw_parts = value.split("/")
    if path.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("vault_path must stay relative to the Vault")
    return path.as_posix()


def _ensure_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


class HubCatalog(HubModel):
    schema_version: int = 1
    revision: str = ""
    generated_at: datetime
    sources: list[SourceStatus] = Field(default_factory=list)
    resources: list[HubResource] = Field(default_factory=list)
    topics: list[HubTopic] = Field(default_factory=list)
    artifacts: list[HubArtifact] = Field(default_factory=list)
    assets: list[HubAsset] = Field(default_factory=list)
    diagnostics: list[CatalogDiagnostic] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _supported_schema(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported HubCatalog schema version")
        return value

    @model_validator(mode="after")
    def _validate_graph_and_revision(self) -> Self:
        resources = _index_unique(self.resources, "resource_id")
        topics = _index_unique(self.topics, "topic_id")
        artifacts = _index_unique(self.artifacts, "artifact_id")
        _index_unique(self.assets, "asset_id")

        asset_paths: dict[str, str] = {}
        for asset in self.assets:
            current = asset_paths.get(asset.vault_path)
            if current is not None:
                raise ValueError(
                    f"duplicate asset vault_path: {asset.vault_path} "
                    f"({current}, {asset.asset_id})"
                )
            asset_paths[asset.vault_path] = asset.asset_id
            _require_known(
                asset.owner_artifact_ids,
                artifacts,
                "artifact",
                asset.asset_id,
            )

        for topic in self.topics:
            if topic.parent_id is not None and topic.parent_id not in topics:
                raise ValueError(f"topic {topic.topic_id} references unknown parent topic")
            _require_known(topic.resource_ids, resources, "resource", topic.topic_id)
            _require_known(topic.artifact_ids, artifacts, "artifact", topic.topic_id)
        for resource in self.resources:
            _require_known(resource.topic_ids, topics, "topic", resource.resource_id)
            _require_known(resource.artifact_ids, artifacts, "artifact", resource.resource_id)
        known_parents = set(resources) | set(topics) | set(artifacts)
        for artifact in self.artifacts:
            if artifact.resource_id is not None and artifact.resource_id not in resources:
                raise ValueError(f"artifact {artifact.artifact_id} references unknown resource")
            if artifact.topic_id is not None and artifact.topic_id not in topics:
                raise ValueError(f"artifact {artifact.artifact_id} references unknown topic")
            if artifact.parent_id is not None and artifact.parent_id not in known_parents:
                raise ValueError(f"artifact {artifact.artifact_id} references unknown parent")

        computed = self.compute_revision()
        if self.revision and self.revision != computed:
            raise ValueError("HubCatalog revision does not match its contents")
        self.revision = computed
        return self

    def compute_revision(self) -> str:
        """Hash semantic catalog content, excluding generation time and list ordering."""
        payload = self.model_dump(mode="json", exclude={"generated_at", "revision"})
        payload["sources"] = sorted(payload["sources"], key=lambda row: row["source"])
        payload["resources"] = sorted(payload["resources"], key=lambda row: row["resource_id"])
        payload["topics"] = sorted(payload["topics"], key=lambda row: row["topic_id"])
        payload["artifacts"] = sorted(payload["artifacts"], key=lambda row: row["artifact_id"])
        payload["assets"] = sorted(payload["assets"], key=lambda row: row["asset_id"])
        payload["diagnostics"] = sorted(
            payload["diagnostics"],
            key=lambda row: (row["level"], row["code"], row.get("entity_id") or ""),
        )
        for row in payload["resources"]:
            row["topic_ids"] = sorted(row["topic_ids"])
            row["artifact_ids"] = sorted(row["artifact_ids"])
            row["zotero"]["collection_keys"] = sorted(row["zotero"]["collection_keys"])
        for row in payload["topics"]:
            row["resource_ids"] = sorted(row["resource_ids"])
            row["artifact_ids"] = sorted(row["artifact_ids"])
        for row in payload["assets"]:
            row["owner_artifact_ids"] = sorted(row["owner_artifact_ids"])
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _index_unique(rows: list[HubModel], field: str) -> dict[str, HubModel]:
    result: dict[str, HubModel] = {}
    for row in rows:
        value = str(getattr(row, field))
        if value in result:
            raise ValueError(f"duplicate {field}: {value}")
        result[value] = row
    return result


def _require_known(
    refs: list[str], known: dict[str, HubModel], kind: str, owner: str
) -> None:
    for ref in refs:
        if ref not in known:
            raise ValueError(f"{owner} references unknown {kind}: {ref}")
