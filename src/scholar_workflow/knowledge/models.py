"""Strict identities and ownership contracts for human-readable knowledge.

These models do not import analysis, HTTP, workspace, or task execution code.
"""
from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scholar_workflow.models import ResourceKind


ATOMIC_RESOURCE_KINDS = (
    ResourceKind.PAPER,
    ResourceKind.TECHNICAL_DOCUMENT,
    ResourceKind.BLOG_POST,
)


class CoreDocumentKind(StrEnum):
    """Human-authored documents that organize a knowledge context."""

    CHARTER = "charter"
    SURVEY = "survey"
    CATALOG = "catalog"


class SupportingDocumentKind(StrEnum):
    """Documents that must remain attached to an atomic resource or context."""

    ANALYSIS = "analysis"
    ANALYSIS_CANVAS = "analysis_canvas"
    ANNOTATIONS = "annotations"
    READING_NOTE = "reading_note"
    ATTACHMENT = "attachment"


def _validate_vault_path(value: str, *, suffix: str | None = None) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
        or value != path.as_posix()
        or (suffix is not None and not value.endswith(suffix))
    ):
        expected = f" ending in {suffix}" if suffix else ""
        raise ValueError(f"path must be a safe Vault-relative POSIX path{expected}")
    return value


class KnowledgeAtomicResource(BaseModel):
    """A paper, technical document, or blog with its own human-readable note."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1, max_length=256)
    kind: Literal[
        ResourceKind.PAPER,
        ResourceKind.TECHNICAL_DOCUMENT,
        ResourceKind.BLOG_POST,
    ]
    title: str = Field(min_length=1, max_length=1000)
    markdown_path: str

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeAtomicResource:
        self.markdown_path = _validate_vault_path(self.markdown_path, suffix=".md")
        return self


class KnowledgeCoreDocument(BaseModel):
    """A charter, synthesis, or directory document anchoring a context."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    kind: CoreDocumentKind
    title: str = Field(min_length=1, max_length=1000)
    markdown_path: str

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeCoreDocument:
        self.markdown_path = _validate_vault_path(self.markdown_path, suffix=".md")
        return self


class KnowledgeSupportingDocument(BaseModel):
    """A subordinate artifact that cannot be represented as an atomic resource."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    kind: SupportingDocumentKind
    title: str = Field(min_length=1, max_length=1000)
    vault_path: str
    owner_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeSupportingDocument:
        if self.kind is SupportingDocumentKind.ANALYSIS_CANVAS:
            expected_suffix = ".canvas"
        elif self.kind in {
            SupportingDocumentKind.ANALYSIS,
            SupportingDocumentKind.ANNOTATIONS,
            SupportingDocumentKind.READING_NOTE,
        }:
            expected_suffix = ".md"
        else:
            expected_suffix = None
        self.vault_path = _validate_vault_path(self.vault_path, suffix=expected_suffix)
        return self


class KnowledgeManifest(BaseModel):
    """Explicit Knowledge System inventory; it never discovers objects from prose."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    atomic_resources: list[KnowledgeAtomicResource] = Field(default_factory=list)
    core_documents: list[KnowledgeCoreDocument] = Field(default_factory=list)
    supporting_documents: list[KnowledgeSupportingDocument] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> KnowledgeManifest:
        primary_ids = {
            resource.resource_id for resource in self.atomic_resources
        } | {document.document_id for document in self.core_documents}
        all_ids = [resource.resource_id for resource in self.atomic_resources]
        all_ids.extend(document.document_id for document in self.core_documents)
        all_ids.extend(document.document_id for document in self.supporting_documents)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("knowledge object IDs must be globally unique")

        paths = [resource.markdown_path for resource in self.atomic_resources]
        paths.extend(document.markdown_path for document in self.core_documents)
        paths.extend(document.vault_path for document in self.supporting_documents)
        if len(paths) != len(set(paths)):
            raise ValueError("knowledge object paths must be globally unique")

        orphaned = sorted(
            document.document_id
            for document in self.supporting_documents
            if document.owner_id not in primary_ids
        )
        if orphaned:
            raise ValueError(f"supporting documents require an atomic/context owner: {orphaned}")
        return self


class KnowledgeRelation(BaseModel):
    """One explicitly supplied relation; no relation is inferred from note text."""

    model_config = ConfigDict(extra="forbid")

    from_id: str = Field(min_length=1, max_length=256)
    relation: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    to_id: str = Field(min_length=1, max_length=256)


class KnowledgeProjection(BaseModel):
    """One explicitly supplied projection identity, never an executable URL."""

    model_config = ConfigDict(extra="forbid")

    projection_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    target_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def reject_urls(self) -> KnowledgeProjection:
        if "://" in self.projection_id or "://" in self.target_id:
            raise ValueError("projection identities cannot be URLs")
        return self
