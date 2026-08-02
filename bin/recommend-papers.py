#!/usr/bin/env python3
"""Fetch + merge recommendation candidates from the enabled sources (skill mechanical layer).

feature-ai-reading skim tier, step ①: gathers candidates from the four feeds (per
recommend.yml `sources` toggles), merges/dedups by arxiv_id, prints the all-options
list as JSON for the host LLM to refine (step ②) and skim via NotebookLM (step ③).

NOT wired into the CLI — the CLI never makes outbound network calls (INV18). Reuses the
recommend_sources adapters. Emits only metadata (cheap); NotebookLM skimming of the
refined shortlist is orchestrated separately by the SKILL via notebooklm-py.

Optional stdin JSON supplies context the CLI can't (it never touches MCP): the host LLM
gathers it via zotero-mcp / config and pipes it in:
  {"seed_arxiv_ids": ["2501.00001", ...]}   # Zotero-library seeds for S2 recommendations
Network paths differ per source: HF Daily needs the proxy; S2 goes direct (trust_env
handled in the adapters); Scholar Inbox uses the vendored client's own session.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from scholar_workflow.config import load_recommend_config
from scholar_workflow.adapters.recommend_sources import (
    fetch_hf_daily, fetch_s2_recommendations, fetch_s2_author_papers,
    normalize_scholar_inbox, merge_candidates,
)

# Vendored Scholar Inbox client lives beside this skill's scripts/, off the package path.
_SI_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "recommend-papers" / "scripts"


def _fetch_scholar_inbox(min_score: float) -> list[dict]:
    """Fetch + normalize the Scholar Inbox digest via the vendored client, which owns
    the ~7-day session cookie (login is a separate step). No session → source skipped."""
    if str(_SI_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SI_SCRIPTS))
    from scholar_inbox import ScholarInboxClient  # vendored, MIT (see THIRD_PARTY_LICENSES)
    client = ScholarInboxClient(config_dir=None)
    client._config = __import__("scholar_inbox").Config()  # default project-local dir
    digest = client.get_digest()
    return normalize_scholar_inbox(digest or {}, min_score=min_score)


def main() -> None:
    cfg = load_recommend_config()
    stdin_ctx: dict = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            stdin_ctx = json.loads(raw)
    seed_arxiv_ids = stdin_ctx.get("seed_arxiv_ids", [])

    batches: list[list[dict]] = []
    skipped: list[str] = []
    limit = max(cfg.daily_limit * 3, 30)

    if cfg.sources.get("hf_daily", False):
        try:
            batches.append(fetch_hf_daily(limit=limit))
        except Exception as exc:  # a single source failing must not sink the run
            skipped.append(f"hf_daily: {exc}")

    if cfg.sources.get("s2_recommendations", False):
        if seed_arxiv_ids:
            try:
                batches.append(fetch_s2_recommendations(seed_arxiv_ids, limit=limit))
            except Exception as exc:
                skipped.append(f"s2_recommendations: {exc}")
        else:
            skipped.append("s2_recommendations: no seed_arxiv_ids on stdin (pipe Zotero seeds)")

    if cfg.sources.get("s2_author", False):
        for author_id in cfg.watchlist:
            try:
                batches.append(fetch_s2_author_papers(author_id, limit=limit))
            except Exception as exc:
                skipped.append(f"s2_author[{author_id}]: {exc}")
        if not cfg.watchlist:
            skipped.append("s2_author: empty watchlist (register authorIds first)")

    if cfg.sources.get("scholar_inbox", False):
        try:
            batches.append(_fetch_scholar_inbox(cfg.min_score))
        except Exception as exc:
            skipped.append(f"scholar_inbox: {exc}")

    candidates = merge_candidates(*batches)
    json.dump({"candidates": candidates, "count": len(candidates), "skipped": skipped},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
