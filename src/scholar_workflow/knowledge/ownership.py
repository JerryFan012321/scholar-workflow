"""Read-only ownership results; declarations remain the only authority.

The Knowledge core has no dependency on analysis, projects, services, or readers.
An orchestration layer supplies validated placements from registered Sources.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict


class KnowledgeOwnerLocation(BaseModel):
    """One declared object and its primary owner, relative to a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    field_id: str
    field_title: str
    object_id: str
    owner_id: str
    relative_path: str
    owner_path: str
    file_state: Literal["available", "missing", "unsafe", "not_checked"] = "not_checked"


class KnowledgeOwnershipIssue(BaseModel):
    """An incomplete declaration check; technical messages never contain bodies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str | None
    code: str


class KnowledgeOwnershipResolution(BaseModel):
    """Ownership, path availability, and reader verification are independent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    object_id: str
    status: Literal["resolved", "not_found", "conflict", "incomplete"]
    locations: list[KnowledgeOwnerLocation]
    owner_candidates: list[KnowledgeOwnerLocation]
    issues: list[KnowledgeOwnershipIssue]
    reader_state: Literal["unverified"] = "unverified"


def resolve_declared_ownership(
    object_id: str,
    placements: Sequence[KnowledgeOwnerLocation],
    issues: Sequence[KnowledgeOwnershipIssue] = (),
) -> KnowledgeOwnershipResolution:
    """Never choose a first match or equate a reader URI with ownership.

    A unique analysis is still conflicted when its primary resource has two
    declarations. Unreadable Sources prevent a claim of complete uniqueness.
    """
    locations = sorted(
        (row for row in placements if row.object_id == object_id),
        key=lambda row: (row.source_id, row.relative_path),
    )
    owner_ids = {row.owner_id for row in locations}
    owners = sorted(
        (row for row in placements if row.object_id in owner_ids
         and row.object_id == row.owner_id),
        key=lambda row: (row.source_id, row.relative_path),
    )
    if len(locations) > 1 or len(owners) > 1:
        status = "conflict"
    elif issues or (locations and not owners):
        status = "incomplete"
    elif not locations:
        status = "not_found"
    else:
        status = "resolved"
    return KnowledgeOwnershipResolution(
        object_id=object_id, status=status, locations=locations,
        owner_candidates=owners, issues=list(issues),
    )
