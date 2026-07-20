"""Existence check: does this resource already live in our library?

Two-tier by design (see AGENT.md / GOALS INV1):
  - EXACT match (DOI / arXiv base id / resource_id equality) is deterministic and
    guards INV1 (one paper -> at most one Zotero item). Never delegated to an LLM.
  - FUZZY only returns a candidate shortlist; the judgment call is made upstream
    (an LLM in find/ingest), and a fuzzy hit on the write path becomes a conflict
    for human adjudication (NG3), never an automatic merge.

The write path re-confirms an exact hit against live Zotero before upserting (the
local cache may be stale); that confirmation lives in the apply flow, not here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from scholar_workflow.identity import normalize_title
from scholar_workflow.models import Resource


class Match(Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NONE = "none"


@dataclass
class ExistenceResult:
    match: Match
    resource_id: str | None = None
    zotero_item_key: str | None = None
    candidates: list[dict] = field(default_factory=list)


def check_existence(resource: Resource, state) -> ExistenceResult:
    """Resolve whether `resource` already exists. Exact is authoritative; fuzzy recalls."""
    ids = resource.identifiers
    hit = state.find_exact(resource_id=resource.resource_id,
                           doi=ids.doi, arxiv=ids.arxiv)
    if hit:
        return ExistenceResult(Match.EXACT, resource_id=hit["resource_id"],
                               zotero_item_key=hit.get("zotero_item_key"))

    title_norm = normalize_title(resource.title)
    candidates = state.find_candidates(title_norm, year=resource.year)
    if candidates:
        return ExistenceResult(Match.FUZZY, candidates=candidates)

    return ExistenceResult(Match.NONE)


def decide_operation(result: ExistenceResult) -> tuple[str, list[str]]:
    """Map an existence result to a plan operation + conflict list (deterministic).

    NONE  -> create. EXACT -> skip (already in library; offline resolver carries no
    fresh metadata to justify an update). FUZZY -> conflict for human adjudication
    (NG3): a fuzzy hit is never an automatic merge or skip.
    """
    if result.match is Match.EXACT:
        return "skip", []
    if result.match is Match.FUZZY:
        return "conflict", [c["resource_id"] for c in result.candidates]
    return "create", []
