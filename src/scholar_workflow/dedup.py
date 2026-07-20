"""Existence check: does this resource already live in the authoritative library?

Two-tier by design (see AGENT.md / GOALS INV1):
  - EXACT match (DOI / arXiv base id) is authoritative and guards INV1 (one paper ->
    one Zotero item). The authority is the Zotero Local API, queried live; a stale
    local cache is never trusted to *deny* existence.
  - FUZZY / semantic recall is NOT decided here. The host LLM reads the catalog
    projection and judges; a fuzzy hit on the write path becomes a conflict for
    human adjudication (NG3), never an automatic merge.

Fail-closed: if Zotero is unreachable we raise DependencyError (exit code 3) rather
than returning NONE — "can't reach Zotero" must never be misread as "new paper",
which would create a duplicate.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from scholar_workflow.models import Resource


class DependencyError(RuntimeError):
    """A required dependency (Zotero Local API) is unavailable. Maps to exit code 3."""


class Match(Enum):
    EXACT = "exact"
    CONFLICT = "conflict"
    NONE = "none"


@dataclass
class ExistenceResult:
    match: Match
    resource_id: str | None = None
    zotero_item_key: str | None = None
    conflicts: list[str] = field(default_factory=list)


def _search(zotero, resource: Resource) -> list[tuple[str, str]]:
    """Return (identifier, item_key) pairs for each identifier that hits Zotero."""
    hits: list[tuple[str, str]] = []
    ids = resource.identifiers
    try:
        if ids.arxiv:
            for it in zotero.search_by_arxiv(ids.arxiv):
                hits.append(("arxiv", it["key"]))
                break
        if ids.doi:
            for it in zotero.search_by_doi(ids.doi):
                hits.append(("doi", it["key"]))
                break
    except DependencyError:
        raise
    except Exception as exc:  # network / connection failure -> fail closed
        raise DependencyError(f"Zotero Local API unavailable: {exc}") from exc
    return hits


def check_existence(resource: Resource, zotero, state=None) -> ExistenceResult:
    """Resolve whether `resource` already exists. Zotero Local API is authoritative.

    `state` (local cache) is an optional fast prefilter and is never used to deny
    existence. `zotero` must expose search_by_arxiv / search_by_doi.
    """
    hits = _search(zotero, resource)
    if not hits:
        return ExistenceResult(Match.NONE)

    item_keys = {key for _id, key in hits}
    if len(item_keys) > 1:
        # Identifiers on one input point to different Zotero items -> human decides (NG3).
        return ExistenceResult(Match.CONFLICT, resource_id=resource.resource_id,
                               conflicts=sorted(item_keys))

    key = item_keys.pop()
    return ExistenceResult(Match.EXACT, resource_id=resource.resource_id,
                           zotero_item_key=key)


def decide_operation(result: ExistenceResult) -> tuple[str, list[str]]:
    """Map an existence result to a plan operation + conflict list (deterministic).

    NONE -> create. EXACT -> skip (already in the authoritative library). CONFLICT ->
    conflict for human adjudication (NG3): never an automatic merge or skip.
    """
    if result.match is Match.EXACT:
        return "skip", []
    if result.match is Match.CONFLICT:
        return "conflict", result.conflicts
    return "create", []
