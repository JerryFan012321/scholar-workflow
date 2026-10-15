# sync-projections

Maintain the derived projections of the library after ingestion or on demand.

- **Obsidian index** — rebuild paper index tables from Zotero and the state
  mapping, writing only inside the managed block and preserving all human content
  outside it.
- **Notion projection** — upsert by stable Resource ID, writing only
  machine-managed fields. Never uploads files or overwrites human content.

The Obsidian table is a rebuildable derived index, not source of truth. The two
subtasks may run in parallel. PDF cells persist Zotero attachment URIs; Hub ports and
runtime action IDs are never written into the Vault or Notion.

Missing Zotero/PDF keys are shown as `Not linked`, not silent empty cells or a claim
that the paper was never imported. A current Field's five-column ledger keeps its
own format through `build-literature-tree`; do not replace it with this legacy table.
Post-ingest repairs follow the shared [paper delivery contract](../../references/paper-delivery.md)
and never repeat acquisition merely because the index is stale.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
