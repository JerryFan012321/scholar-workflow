"""Core data models (Pydantic v2)."""
from __future__ import annotations
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone


class ResourceKind(StrEnum):
    PAPER = "paper"
    TECHNICAL_DOCUMENT = "technical_document"
    SNAPSHOT = "snapshot"
    DRAWIO = "drawio"
    IMAGE = "image"
    DATASET = "dataset"


class TaskState(StrEnum):
    """States the CLI download flow actually writes. The pre-zotero-mcp pipeline
    states (classify/dedup/sync/index/project + approval/conflict) are gone — those
    stages now live in the skill layer, not the CLI."""
    APPROVED = "approved"        # job created, about to download
    DOWNLOADED = "downloaded"    # PDF landed in the inbox, awaiting manual Zotero import
    NO_ARXIV_PDF = "no_arxiv_pdf"
    DOWNLOAD_FAILED = "download_failed"


class Identifiers(BaseModel):
    doi: str | None = None
    arxiv: str | None = None
    isbn: str | None = None
    url: str | None = None


class ZoteroRefs(BaseModel):
    item_key: str | None = None
    attachment_key: str | None = None
    collection_keys: list[str] = Field(default_factory=list)


class FileInfo(BaseModel):
    root: str  # "papers_root" | "vault_root"
    relative_path: str | None = None
    sha256: str | None = None
    source: str | None = None  # "arxiv" | "user" | "web"


class Projections(BaseModel):
    obsidian_index: str | None = None
    notion_page_id: str | None = None
    local_url: str | None = None


class Resource(BaseModel):
    resource_id: str
    kind: ResourceKind
    title: str | None = None  # None when the offline resolver has no real title; fill from Zotero downstream
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    identifiers: Identifiers = Field(default_factory=Identifiers)
    zotero: ZoteroRefs = Field(default_factory=ZoteroRefs)
    file: FileInfo | None = None
    projections: Projections = Field(default_factory=Projections)


class ActionItem(BaseModel):
    resource_id: str
    operation: str  # create | update | skip | conflict
    download_url: str | None = None
    zotero_collection_key: str | None = None
    obsidian_index: str | None = None
    vault_path: str | None = None
    notion_projection: bool = False
    conflicts: list[str] = Field(default_factory=list)
    skip_reason: str | None = None


class ActionPlan(BaseModel):
    """A deterministic "what to download / project" list. Not a signed, expiring,
    tamper-checked plan — the CLI generates and consumes it in one call, and approval
    of destructive actions lives in the skill layer (host LLM via zotero-mcp)."""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actions: list[ActionItem] = Field(default_factory=list)
