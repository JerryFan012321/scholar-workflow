# recommend-papers

Collect recommendations in one review page. Independent agents and recurring tasks
can submit papers, project homepages and blogs through the same installed CLI.
The page merges duplicate resources, preserves who recommended each one and lets
you filter by domain, resource type and producing task.

## Use the shared entry

```bash
scholar-research recommendations --profile personal schema
scholar-research recommendations --profile personal submit --input recommendations.json
scholar-research recommendations --profile personal open
```

Ask an agent to follow `recommend-papers` and the
[shared intake contract](../../references/recommendation-intake.md). The installed
`schema` output is the submission contract; the
[example](references/submission.example.json) uses synthetic data only.

Each recurring task keeps a stable producer ID. Each execution has a run ID, and
retries reuse their submission IDs and unchanged payloads. You can see results
from all tasks together or select a particular task/domain. A submission receipt
states which entries were accepted, already present, conflicting or invalid.

## What the page shows

- Papers: verified paper information, the complete Chinese abstract translation,
  the original abstract and the available project-homepage link.
- Project pages and blogs: source information, the actual introduction/excerpt and
  its translation when available. A project announcement does not need a paper.
- Attributed raw platform data, such as repository stars, with the actual target,
  source link and observation time. The page does not evaluate popularity or add
  a combined score.
- Domain tags, producing tasks and discovery channels, with separate human review
  and selected/saved/ignored decisions.

The **Reading Report** is the paper component: paper information, abstract and
related project homepage. It does not contain recommendation rationale, scientific
analysis or a reading-coverage report. Operation failures are reported separately.

## Choose resources to ingest

Review the full translated abstract before selecting a paper for ingestion. Keep
its original accessible for checking. Then export the selected-candidate handoff:

```bash
scholar-research recommendations --profile personal handoff
```

The handoff is an input to the normal `find-resource` / `ingest-resource` workflow,
under your actual ingestion request. Exporting it does not write Zotero or the
Vault. Existing identity checks, destinations and source policies still apply.
An abstract content change requires review again; refreshing stars does not.

## Lifecycle and test isolation

```bash
scholar-research recommendations --profile personal list
scholar-research recommendations --profile personal status
scholar-research recommendations --profile personal stop
```

Use `--profile test` for a test pool. For an isolated test location, set
`SCHOLAR_WORKFLOW_HOME` explicitly as well. Test and personal pools are separate;
the page's token and runtime service are local state, not persistent source links.
Do not submit the synthetic example to your personal pool.

## Existing paper sources and configuration

The existing aggregator is still available as a source for candidates:

| Source | Observation |
|---|---|
| Semantic Scholar Recommendations | Papers related to user-supplied or confirmed Zotero arXiv seeds |
| Scholar Inbox | The configured personalized digest, when its session is available |
| S2 author watchlist | New papers from registered researchers |
| Hugging Face Daily Papers | Community paper submissions and votes |

The aggregator returns source metadata and skipped-source diagnostics. It does not
supply the versioned submission envelope automatically, import papers or prove that
a full paper was read. Obtain a complete authoritative abstract before supplying
its translation; a snippet is not a substitute.

Configuration remains in `~/.config/scholar-workflow/recommend.yml`; the optional
project overlay is `~/.config/scholar-workflow/projects/<cwd-name>.yml`. Copy and
adapt [recommend.example.yml](references/recommend.example.yml) when needed.
Project interests/watchlist extend global values; other project keys override.
Scholar Inbox session state stays outside configuration and Git. Missing access
skips that source and remains visible in diagnostics. Existing adapter proxy
routing remains unchanged. Old `notebooklm_classification` settings are ignored;
no NotebookLM package or login is required.

Author-watchlist requests resolve the actual Semantic Scholar `authorId` before
updating the configured watchlist, disambiguating when necessary.

## Platform counts and missing abstracts

Use `submit --refresh-metrics` for recommendations with verified public GitHub/HF
object links; old candidates have `refresh-metrics --candidate-id <id>` and a card
action. Counts show their target and time; failures retain old values. HF likes
are labeled separately from GitHub stars. A missing author abstract can use a
source-backed `summary_zh` with `summary_sources`, explicitly labeled as an agent
summary and reviewed before handoff. Related Blogs use the existing flexible
`links` array. See the [intake contract](../../references/recommendation-intake.md).
