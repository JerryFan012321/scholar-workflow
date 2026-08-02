# recommend-papers

A daily paper-recommendation feed. It aggregates four complementary sources, merges
them by arXiv id, and skims a shortlist you pick through NotebookLM to produce a cheap
**Reading Report** — a decision aid, not a vault artifact. Papers you like flow into the
normal `find-resource` / `ingest-resource` pipeline.

## The four sources

| Source | Signal | Auth |
|---|---|---|
| Semantic Scholar Recommendations | your Zotero library as positive seeds | none |
| Scholar Inbox | trained personalized digest (up/down votes over time) | session cookie (~7 days) |
| S2 author watchlist | new papers from researchers/labs you registered | none |
| HuggingFace Daily Papers | community upvote heat | none |

Each source contributes a normalized candidate (`arxiv_id`, title, authors, source,
score, abstract snippet, url). Candidates are deduped by arXiv id; every contributing
source is recorded so you can see overlap.

## How the funnel works

1. **All options** — the aggregator prints every candidate as *metadata only* (cheap,
   no skim).
2. **Refine** — filter against your interests / project keywords, or pick by hand, to
   get a shortlist.
3. **Skim** — only the shortlist goes through NotebookLM (~500 tokens/question vs ~50K
   to read a PDF).
4. **Report** — a short markdown list you decide from. Ephemeral; ingest the keepers.

## Setup

1. Copy the config template:
   ```bash
   cp references/recommend.example.yml ~/.config/scholar-workflow/recommend.yml
   ```
   Edit `interests`, `sources` toggles, `daily_limit`, and `watchlist`.
   Optional per-project overlay: `~/.config/scholar-workflow/projects/<cwd-name>.yml`
   (interests/watchlist are additive; other keys override).

2. Install NotebookLM automation (for the skim tier):
   ```bash
   pipx install "notebooklm-py[browser]"
   notebooklm login
   ```
   This stores a real Google login — a throwaway account is recommended.

3. Scholar Inbox (optional fourth source) needs a session cookie. The vendored client
   drives a browser login via `playwright-cli`; the cookie is stored under
   `~/.config/scholar-workflow/scholar-inbox/session.json` (chmod 600) and lasts ~7
   days. Without it, that source is skipped and the run uses the other three.

## Watchlist

Give a researcher's name (plus affiliation or a notable paper) and the skill resolves a
stable Semantic Scholar `authorId`, then stores it in `watchlist`. This avoids the
common-name problem (e.g. many authors share "He Wang"). The ledger is personal data —
gitignored, template-only.

## Troubleshooting

- **A source shows under `skipped`** — that source failed or is unconfigured (no seeds,
  empty watchlist, no Scholar Inbox session). The run still completes on the rest.
- **HF Daily times out** — it goes through your system HTTP proxy (`httpx` `trust_env`,
  i.e. `HTTP_PROXY`/`HTTPS_PROXY`), while S2 connects directly. These paths are fixed in
  the adapters; if HF Daily can't reach the network, check your proxy env vars.
- **NotebookLM unreachable** — fall back to metadata-only recommendations, or read via
  `analyze-paper` / `get_content` (slower, more tokens).

## Attribution

The Scholar Inbox client under `scripts/scholar_inbox/` is adapted from
[sjh-skills](https://github.com/jiahao-shao1/sjh-skills) (MIT License, Copyright (c)
2026 Jiahao Shao). See `scripts/THIRD_PARTY_LICENSES`.
