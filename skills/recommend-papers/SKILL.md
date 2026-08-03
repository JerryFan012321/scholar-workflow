---
name: recommend-papers
description: Daily paper recommendation feed — aggregates multiple sources, skims a user-picked shortlist to produce a cheap ephemeral Reading Report, and registers watchlist authors. Picked papers flow into find-resource / ingest-resource. Triggers 'recommend papers', 'daily papers', 'what should I read', 'paper feed', 'skim recommendations', 'watchlist', '推荐论文', '今日论文', '每日论文', '有什么新论文', '略读推荐', '关注这个作者', '登记研究者'. Not full paper analysis (analyze-paper) or targeted lookup (find-resource).
---

# recommend-papers

## Triggers
- User wants a daily/periodic feed of new papers worth reading
- User asks what to read, or to skim recommendations to decide what to ingest
- User wants to register a researcher/lab to watch (watchlist sub-mode)

## Steps (skim funnel)

1. **Gather Zotero seeds (for S2 recommendations).** S2 recommendations use the
   user's own library as positive seeds (G2: library is the taste profile). Collect
   the arXiv ids of recent/representative library items via zotero-mcp, and pass them
   on stdin — the mechanical layer never touches MCP itself (INV18).

2. **Fetch + merge all enabled sources.** Run the aggregator:
   `echo '{"seed_arxiv_ids": [...]}' | python3 ${CLAUDE_PLUGIN_ROOT}/bin/recommend-papers.py`.
   It reads `recommend.yml` toggles, calls each enabled source, merges/dedups by
   arXiv id, and prints `{candidates, count, skipped}` — **metadata only, no skim**
   (title/authors/source/score/abstract snippet). A source that errors lands in
   `skipped`; the run still completes on the rest.

3. **Refine to a shortlist (step ②).** Filter the all-options list against the user's
   `interests` (and per-project keywords), let the user pick, or filter by source.
   Interest matching, ranking, and picking are your own judgment — not encoded here.

4. **Skim ONLY the shortlist via NotebookLM (step ③).** For each shortlisted paper,
   add its arXiv URL to a NotebookLM notebook (`notebooklm-py`) and ask source-grounded
   questions (core contribution, method, results). ≈500 tokens/question vs ≈50K to read
   the PDF — that economy is the whole point, so never skim the full pool, only the
   shortlist. Reuse a same-topic notebook if one already exists; else create one.

5. **Emit the Reading Report (step ④), then hand off.** Produce a short markdown list
   (title + one-line grounded description + why-relevant) for the user to decide from.
   The report is **ephemeral — never written to the vault or Zotero** (INV23). Papers
   the user wants flow into `find-resource` / `ingest-resource` (two-step dedup there).

## Watchlist registration (sub-mode)
- User gives a researcher name (+ affiliation / notable paper). Resolve to a stable S2
  `authorId` (disambiguate common names — e.g. "He Wang" has thousands of matches).
  Store the id in the `watchlist` of `recommend.yml` (global) or the project overlay.
- This is a mode of this skill, not a separate skill. authorId ledgers are personal
  registered data: gitignored, template-only (env-records style).

## Config (two layers, YAML)
- Global `~/.config/scholar-workflow/recommend.yml` — interests, source toggles,
  daily_limit, min_score, notebooklm_classification, global watchlist.
- Project `~/.config/scholar-workflow/projects/<cwd-name>.yml` — auto-loaded by cwd
  name; interests/watchlist are additive (extend), other keys override.
- Template: `references/recommend.example.yml`. Not credentials — session cookies /
  tokens live in env vars / the vendored client's session store, never in these files.

## Constraints
- **Skim output is ephemeral (INV23).** The Reading Report is a decision aid; it does
  not enter the vault or Zotero. Only ingestion (via find/ingest) mutates the library.
- **NotebookLM skims the shortlist only**, never the full candidate pool — the token
  economy is the reason the tier exists.
- **arXiv-only candidates.** Merge/dedup key is arXiv id; sources without an arXiv id
  for a paper drop it (matches the vault's arXiv-only reality, INV10 / source-policy).
- **Network paths differ per source** and are fixed in the adapters: HF Daily needs the
  proxy; S2 goes direct; Scholar Inbox uses its vendored session. Don't override them.
- **External deps, login state.** `notebooklm-py` and Scholar Inbox both store real
  login state — prefer a throwaway Google account for NotebookLM. If NotebookLM is
  unreachable, fall back to metadata-only recommendations or `get_content`; if Scholar
  Inbox has no session, that source is skipped and the run degrades to three sources.
- **Never auto-ingest.** Picked papers go through the normal find/ingest pipeline so
  the two-step dedup gate runs; this skill never writes to Zotero directly.

## References
Load on demand.
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only PDF source, authoritative metadata
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — credential handling, no tokens in config/git
- `references/recommend.example.yml` — config template (global + project layers)
- `scripts/THIRD_PARTY_LICENSES` — vendored Scholar Inbox client attribution (MIT, Jiahao Shao)
