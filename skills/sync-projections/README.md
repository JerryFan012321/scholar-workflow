# sync-projections

Maintain the derived projections of the library after ingestion or on demand.

- **Obsidian index** — rebuild paper index tables from Zotero and the state
  mapping, writing only inside the managed block and preserving all human content
  outside it.
- **Notion projection** — upsert by stable Resource ID, writing only
  machine-managed fields. Never uploads files or overwrites human content.

The Obsidian table is a rebuildable derived index, not source of truth. The two
subtasks may run in parallel.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
