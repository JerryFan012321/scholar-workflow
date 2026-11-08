---
name: recommend-papers
description: Recommend research papers, project homepages and blogs, submit them to the shared recommendation page, or maintain an author watchlist. Use for 'recommend papers', 'daily papers', 'recommend research blogs', 'what should I read', 'watch this author', '推荐论文', '今日论文', '推荐研究项目', '推荐博客', '关注这个作者'. Not for targeted lookup, channel monitoring or full paper analysis.
---

# recommend-papers

## Shared recommendation entry

Before producing, submitting or reviewing recommendations, follow the
[recommendation intake contract](../../references/recommendation-intake.md).
It defines the shared entry for papers, project homepages and blogs, the Reading
Report, tags, raw platform data, retry receipts and human selection handoff.

Every recommending agent uses the same installed entry for the user's chosen pool:

```text
scholar-research recommendations --profile personal schema
scholar-research recommendations --profile personal submit --input recommendations.json --refresh-metrics
scholar-research recommendations --profile personal open
```

Use a stable producer ID for a recurring task, a separate run ID per execution and
the same submission ID and payload on retries. Follow the receipt, not a guessed
success. Do not write the pool database directly. Schedules remain owned by the
calling host; this skill does not create an agent scheduler.

Use `--profile test` for an explicitly selected test pool. Never send test examples
to the personal pool or alter installed runtime files to make acceptance pass.

For declared GitHub/Hugging Face objects, collect raw platform counts through that
explicit refresh entry; retain unknown/failure states rather than dropping the
heat area or inventing zero. Include related verified Blog links among the flexible
attachments. When no original abstract exists, follow the intake contract's
sourced-summary branch and label the result explicitly; never fabricate an abstract.

## Existing source aggregation

- Use user-supplied arXiv IDs or the confirmed results of
  `scholar-workflow zotero search "<requested-or-configured-topic>" --fulltext` as
  Semantic Scholar positive seeds.
- The configured aggregator remains available:
  `echo '{"seed_arxiv_ids":[...]}' | python3 ${CLAUDE_PLUGIN_ROOT}/bin/recommend-papers.py`.
  Its `{candidates,count,skipped}` output is source input, not the versioned
  submission envelope. Preserve source failures and map selected candidates through
  the intake contract. Fetch the complete authoritative abstract and translate it;
  a truncated snippet cannot stand in for the abstract.
- Retrieve full text only for a user-selected reading request, through native host
  tools and the shared source policy. An abstract does not establish full-text
  reading; do not import a paper merely to obtain a reader.

## Watchlist

Resolve a named researcher to a stable Semantic Scholar `authorId`, disambiguating when
necessary, then add it to the global or project `watchlist` in `recommend.yml`.

## Configuration

- global: `~/.config/scholar-workflow/recommend.yml`;
- project overlay: `~/.config/scholar-workflow/projects/<cwd-name>.yml`;
- schema/example: `references/recommend.example.yml`.

Project interests and watchlist extend global values; other project keys override them.
Credentials and session state never belong in these YAML files.
Legacy `notebooklm_classification` values remain readable but are ignored; no
NotebookLM package, account, login or fallback is used.

## Constraints

- The legacy paper aggregator requires arXiv IDs; the shared intake also accepts
  project homepages and blogs under their own typed identities.
- Use the network behavior implemented by each adapter; do not override per-source proxy
  routing.
- Missing Scholar Inbox login skips that source. Its session state must remain
  outside config and Git.
- Never auto-ingest. The normal identity and source gates run after user selection.

## References

- [Recommendation intake](../../references/recommendation-intake.md) — required for
  submissions, the recommendation page and Reading Report/handoff output.
- [Synthetic submission example](references/submission.example.json) — adapt only
  with verified real metadata; the example is not a real recommendation.
- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
- `references/recommend.example.yml`
- `scripts/THIRD_PARTY_LICENSES`
