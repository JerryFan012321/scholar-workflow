---
name: recommend-papers
description: Produce an ephemeral daily paper feed from configured sources, skim only a selected shortlist, or maintain an author watchlist. Use for 'recommend papers', 'daily papers', 'what should I read', 'watch this author', '推荐论文', '今日论文', '关注这个作者'. Not for targeted lookup or full paper analysis.
---

# recommend-papers

## Feed

1. Collect representative arXiv IDs from the Zotero library with
   `scholar-workflow zotero search`; use them as Semantic Scholar positive seeds.
2. Run the configured source aggregator:
   `echo '{"seed_arxiv_ids":[...]}' | python3 ${CLAUDE_PLUGIN_ROOT}/bin/recommend-papers.py`.
   It returns `{candidates,count,skipped}`; source failures remain in `skipped` and do
   not discard successful sources.
3. Select a shortlist from the metadata result. Do not skim the whole candidate pool.
4. Skim only the shortlist with NotebookLM using arXiv URLs. Reuse a same-topic notebook
   when available. If NotebookLM is unavailable, use Zotero indexed full text for a
   smaller shortlist or return metadata-only recommendations.
5. Return an ephemeral Markdown Reading Report: title, one-line grounded description,
   why relevant, source, and arXiv link. Never write the report to Zotero or the Vault.
6. Send user-selected papers to `find-resource` / `ingest-resource`; this skill never
   ingests directly.

## Watchlist

Resolve a named researcher to a stable Semantic Scholar `authorId`, disambiguating when
necessary, then add it to the global or project `watchlist` in `recommend.yml`.

## Configuration

- global: `~/.config/scholar-workflow/recommend.yml`;
- project overlay: `~/.config/scholar-workflow/projects/<cwd-name>.yml`;
- schema/example: `references/recommend.example.yml`.

Project interests and watchlist extend global values; other project keys override them.
Credentials and session state never belong in these YAML files.

## Constraints

- Candidates require an arXiv ID and deduplicate by base arXiv ID.
- Use the network behavior implemented by each adapter; do not override per-source proxy
  routing.
- Missing Scholar Inbox login skips that source. NotebookLM and Scholar Inbox login
  state must remain outside config and Git; prefer a separate NotebookLM account.
- Never auto-ingest. The normal identity and source gates run after user selection.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
- `references/recommend.example.yml`
- `scripts/THIRD_PARTY_LICENSES`
