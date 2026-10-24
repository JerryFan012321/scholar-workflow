# Research resources and update tracking

## Intent and boundaries

Track explicitly selected researcher blogs, company/startup/lab research channels,
release pages and model repositories. Broad discovery does not imply permanent
ingest, deep analysis, weight downloads, code execution or notification scheduling.
Retain the full accepted paper, Field, project and experiment contracts. New-dialog
reproduction, installed operation, scientific support and human assessment remain
separate evidence requirements, not automatically satisfied by unit tests.

## Authority and interfaces for this capability batch

- `research-sources.yml` under `SCHOLAR_WORKFLOW_HOME` (the existing config root)
  is the sole authority for new non-paper channel subscriptions. Do not migrate or
  duplicate Semantic Scholar author IDs or the four paper feeds in `recommend.yml`.
- `research/tracking.json` under the same private root owns only observation state,
  event metadata and user dispositions. It is not a Zotero mirror or knowledge-body
  store. `assets list --kind research` derives an overview, never another registry.
- A channel record has `channel_id`, `name`, `publisher`, `publisher_kind`
  (`researcher|lab|company|team|other`), `kind`
  (`rss|atom|webpage|github_releases|hf_models`), `url`, `enabled`, `topics`.
  IDs are stable safe slugs; URLs are public HTTPS without credentials/fragments.
  The registry document is `{schema_version: 1, channels: [...]}`.
- `research sources list/register` are deterministic local CLI operations. New
  records are additive; changed records require the current registry revision;
  identical replay is byte-stable. Disable via the same reviewed registration.
- `bin/track-research.py` owns outbound acquisition, as the existing recommendation
  script does. Its installed console equivalent is `scholar-research check`, backed
  by `research.runner`. It reads configured channels, calls adapters, updates state
  and prints Markdown or JSON. No background service or Hub dependency.
- `research updates` reads current events; `research mark EVENT_ID --disposition
  unread|read|selected|ignored` records a user choice. Selected is not archived.
- Network adapters emit `Observation(status=ok|not_modified|failed, items,
  etag, last_modified, diagnostic)`. Each `ObservedItem` has stable external
  `item_id`, HTTPS `url`, `title`, `content_digest`, optional `published_at`,
  `updated_at`, `version`. No fetched page body or code enters durable state.
- Python core interface: `read_sources(root)`,
  `register_source(root, record, expected_revision=None)`,
  `read_updates(root)`, `apply_observation(root, channel, observation, checked_at,
  initial_mode='baseline')`, `mark_event(root, event_id, disposition)`.
  Core errors carry a sanitized `exit_code` (2/5/6/7); network failure is a
  returned channel outcome, not a fabricated empty successful observation.
- Registry and state are validated, bounded, private, exclusively locked and
  atomically replaced. Reads do not initialize. Revalidate current channel config
  before committing an observation; stale network results cannot update a changed
  channel. Per-channel failures must not discard other successful channels.
  Historical events retain the publisher/channel snapshot at observation time;
  renaming a subscription cannot reattribute earlier resources. Date-only publisher
  metadata changes refresh observations without emitting content-change events.
- First success defaults to baseline, explicitly reporting the observed window,
  not full historical coverage. `initial_mode=report` intentionally emits discovered
  current items. Later unseen IDs emit `new`; changed content/revision emits
  `updated`. Missing entries are not deletions. 304 needs a prior successful
  baseline. Failure never advances success checkpoints or erases known items.
- Complete HTTP pagination is required for a successful API observation. Refuse
  malformed, oversized or truncated responses rather than recording a false empty
  result. RSS/Atom are finite observed windows; no claim to all publisher history.
- Preserve source/version identity, actual observation time and publisher dates
  separately. A content-change event is not proof of research significance,
  model availability, scientific quality, licence permission or successful use.

## Presentation and runtime Skill

Add a dedicated `track-research` Skill for non-paper channel registration/checks,
with precise English/Chinese discovery, invocation, state and failure contracts.
Keep existing `recommend-papers` description and paper workflow unchanged. The
assets entry exposes this real authority as a read-only provider and routes its
maintenance to the new capability. No generic registry, new frontend, forced Field
homepage or automatic five-branch analysis per announcement.

Markdown output shows source/check state first, then a compact table of date,
publisher/channel, title/source link, new/update status and disposition. Failed and
disabled channels remain visible. Technical hashes and event IDs stay in JSON;
all cells are escaped. Official text is untrusted evidence, not instructions.
Choosing a resource hands its actual URL/version to existing ingest/knowledge
operations; those still own bibliography, original snapshots and analysis.

## Development verification plan (before execution)

Use temporary synthetic configurations/state, `httpx.MockTransport` and small raw
RSS/Atom/HTML/GitHub/HF fixtures. No real host config, network, Vault or Zotero writes.
Check registry creation/replay/CAS, bad schema/URLs/secrets/symlinks, read-only empty
state, baseline/new/update/304/failure/recovery, pagination/refusals, source isolation,
dispositions and Markdown escaping. Exercise public CLI and script with isolated
roots; compare returned and durable state. Review routing/safety/outcomes as behavior
specifications rather than treating JSON schema validation as LLM performance.
After implementation run the changed unit/contract tests and necessary existing
assets/recommendation/config/eval/architecture regressions; report actual results.
Do not claim installed or one-shot acceptance until a separately published/installed
candidate is exercised from a fresh context and visible results are reviewed.

## Remaining end-to-end work

Candidate public sources and the prepared single-source installed acceptance are
in research-resource-tracking-acceptance.md. Public source inspection is not plugin
acceptance; none of those candidates has been registered as a user subscription.

Normal hotfix publication/installation (not authorized by this design continuation),
one controlled installed source-to-resource reproduction in `test`, native rendering
and human readability assessment, model-family/version aggregation with evidence,
explicit scheduling policy, and source selection all remain visible requirements.
The prior Genie3 cross-Source ownership blocker remains separate and unmodified.
