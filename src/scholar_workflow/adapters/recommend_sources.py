"""Recommendation-source adapters: each emits normalized candidates.

feature-ai-reading skim tier. A candidate is a plain dict with a stable shape so the
funnel can merge/dedup across sources by arxiv_id:
  {arxiv_id, title, authors:[str], source:str, score:float|None,
   abstract_snippet:str|None, url:str}

These make outbound network calls, so — like NotionAdapter — they are only invoked
from bin/recommend-papers.py, never the CLI (INV18). Network paths differ per source:
HF Daily needs the proxy (trust_env=True); S2 needs a direct connection (trust_env=False).
"""
from __future__ import annotations
import httpx

HF_DAILY = "https://huggingface.co/api/daily_papers"
S2_RECOMMEND = "https://api.semanticscholar.org/recommendations/v1/papers"
S2_AUTHOR = "https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
S2_FIELDS = "title,authors,year,abstract,externalIds"


def _snippet(text: str | None, limit: int = 280) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def fetch_hf_daily(limit: int = 50, client: httpx.Client | None = None) -> list[dict]:
    """HuggingFace Daily Papers (community upvotes). Needs the proxy (trust_env=True).
    An injected client (tests) bypasses the default proxy-aware client."""
    owns = client is None
    client = client or httpx.Client(trust_env=True, timeout=30)
    try:
        resp = client.get(HF_DAILY, params={"limit": limit})
        resp.raise_for_status()
        rows = resp.json()
    finally:
        if owns:
            client.close()

    out: list[dict] = []
    for row in rows:
        paper = row.get("paper", {})
        arxiv_id = paper.get("id")
        if not arxiv_id:
            continue
        authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
        out.append({
            "arxiv_id": arxiv_id,
            "title": (paper.get("title") or "").strip(),
            "authors": authors,
            "source": "hf_daily",
            "score": paper.get("upvotes"),
            "abstract_snippet": _snippet(paper.get("summary")),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        })
    return out


def _from_s2(paper: dict, source: str) -> dict | None:
    """Normalize one S2 paper. arXiv-only (dedup key is arxiv_id): rows without an
    ArXiv externalId are dropped, matching the vault's arXiv-only reality (INV10/G3)."""
    arxiv_id = (paper.get("externalIds") or {}).get("ArXiv")
    if not arxiv_id:
        return None
    authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
    return {
        "arxiv_id": arxiv_id,
        "title": (paper.get("title") or "").strip(),
        "authors": authors,
        "source": source,
        "score": None,
        "abstract_snippet": _snippet(paper.get("abstract")),
        "url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def fetch_s2_recommendations(seed_arxiv_ids: list[str], limit: int = 50,
                             client: httpx.Client | None = None) -> list[dict]:
    """Semantic Scholar Recommendations. Zotero-library arXiv ids are the positive
    seeds (G2: library is the profile). Direct connection (trust_env=False, the
    `--noproxy` equivalent). No seeds → no call."""
    if not seed_arxiv_ids:
        return []
    owns = client is None
    client = client or httpx.Client(trust_env=False, timeout=30)
    try:
        resp = client.post(S2_RECOMMEND, params={"fields": S2_FIELDS, "limit": limit},
                           json={"positivePaperIds": [f"ARXIV:{i}" for i in seed_arxiv_ids]})
        resp.raise_for_status()
        papers = resp.json().get("recommendedPapers", [])
    finally:
        if owns:
            client.close()
    return [c for p in papers if (c := _from_s2(p, "s2_recommendations"))]


def fetch_s2_author_papers(author_id: str, limit: int = 50,
                           client: httpx.Client | None = None) -> list[dict]:
    """Latest papers by a registered S2 authorId (watchlist). Direct connection."""
    owns = client is None
    client = client or httpx.Client(trust_env=False, timeout=30)
    try:
        resp = client.get(S2_AUTHOR.format(author_id=author_id),
                          params={"fields": S2_FIELDS, "limit": limit})
        resp.raise_for_status()
        papers = resp.json().get("data", [])
    finally:
        if owns:
            client.close()
    return [c for p in papers if (c := _from_s2(p, "s2_author"))]


def normalize_scholar_inbox(digest: dict, min_score: float = 0.0) -> list[dict]:
    """Normalize a Scholar Inbox digest (already fetched by the vendored client in
    bin/, which owns the session/login). Pure so it stays testable and keeps src/
    network- and MCP-free (INV18). arXiv-only, like the S2 sources."""
    out: list[dict] = []
    for row in digest.get("digest_df", []):
        arxiv_id = row.get("arxiv_id")
        score = row.get("ranking_score", 0) or 0
        if not arxiv_id or score < min_score:
            continue
        authors_str = row.get("shortened_authors", "") or ""
        authors = [a.strip() for a in authors_str.split(",") if a.strip()]
        out.append({
            "arxiv_id": arxiv_id,
            "title": (row.get("title") or "").strip(),
            "authors": authors,
            "source": "scholar_inbox",
            "score": round(score, 3),
            "abstract_snippet": _snippet(row.get("abstract")),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        })
    return out


def merge_candidates(*batches: list[dict]) -> list[dict]:
    """Merge source batches, dedup by arxiv_id. First occurrence wins for scalar
    fields; every contributing source is recorded in `sources`."""
    merged: dict[str, dict] = {}
    for batch in batches:
        for cand in batch:
            key = cand["arxiv_id"]
            if key in merged:
                existing = merged[key]
                if cand["source"] not in existing["sources"]:
                    existing["sources"].append(cand["source"])
            else:
                entry = dict(cand)
                entry["sources"] = [cand["source"]]
                merged[key] = entry
    return list(merged.values())
