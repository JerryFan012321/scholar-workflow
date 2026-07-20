"""Input resolution: raw user input -> normalized Resource objects.

Offline classification/normalization only. Title/authors/year come from the Zotero
Local API downstream (the authoritative metadata source), so this module stays a
pure, network-free, unit-testable normalizer.
"""
from __future__ import annotations
import csv
import re
from pathlib import Path
from scholar_workflow.identity import normalize_arxiv, normalize_doi, make_resource_id
from scholar_workflow.models import Resource, Identifiers, ResourceKind

DOI_RE = re.compile(r"^(doi:|https?://doi\.org/)?(10\.\d{4,9}/\S+)$", re.I)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(abs|pdf)/(\d{4}\.\d{4,5})(v\d+)?", re.I)
URL_RE = re.compile(r"^https?://", re.I)


def classify_input(raw: str) -> str:
    """Return one of: arxiv | doi | url | title."""
    raw = raw.strip()
    if normalize_arxiv(raw) or ARXIV_URL_RE.search(raw):
        return "arxiv"
    if DOI_RE.match(raw):
        return "doi"
    if URL_RE.match(raw):
        return "url"
    return "title"


def _extract_arxiv_id(raw: str) -> str | None:
    """Pull a base arXiv id from a bare id or an arxiv.org URL."""
    if base := normalize_arxiv(raw):
        return base
    if m := ARXIV_URL_RE.search(raw):
        return m.group(2)
    return None


def resolve_one(raw: str) -> Resource:
    """Resolve a single raw input into a Resource (offline; no network)."""
    kind = classify_input(raw)
    identifiers = Identifiers()
    # For identifier inputs we have no real title offline; leave it None so no host
    # can mistake a placeholder for a title. url/title inputs keep the user's text.
    title: str | None = raw.strip()

    if kind == "arxiv":
        arxiv_id = _extract_arxiv_id(raw)
        identifiers.arxiv = arxiv_id
        identifiers.url = f"https://arxiv.org/abs/{arxiv_id}"
        title = None
        rid = make_resource_id("paper", {"arxiv": arxiv_id})
    elif kind == "doi":
        doi = normalize_doi(DOI_RE.match(raw.strip()).group(2))
        identifiers.doi = doi
        title = None
        rid = make_resource_id("paper", {"doi": doi})
    elif kind == "url":
        identifiers.url = raw.strip()
        rid = make_resource_id("paper", {"title": title, "first_author": "", "year": ""})
    else:  # title
        rid = make_resource_id("paper", {"title": title, "first_author": "", "year": ""})

    return Resource(resource_id=rid, kind=ResourceKind.PAPER, title=title,
                    identifiers=identifiers)


def resolve_many(raws: list[str]) -> list[Resource]:
    """Resolve a batch, collapsing inputs that share a resource_id (dedup by identity)."""
    seen: dict[str, Resource] = {}
    for raw in raws:
        if not raw.strip():
            continue
        res = resolve_one(raw)
        seen.setdefault(res.resource_id, res)  # first wins; identical ids collapse
    return list(seen.values())


def resolve_csv(path: Path) -> list[Resource]:
    """Resolve a CSV whose first column holds an identifier (DOI/arXiv/title)."""
    raws: list[str] = []
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if row and row[0].strip():
                raws.append(row[0].strip())
    return resolve_many(raws)
