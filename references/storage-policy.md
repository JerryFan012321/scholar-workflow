# Storage Policy (shared)

Canonical rule for where every object lives. Applies to all skills and agents.

## Source-of-truth allocation

| Object | Authoritative store | Root |
|---|---|---|
| Paper bibliography, tags, attachment links | Zotero database (read-only via Local API) | Zotero-managed |
| Paper PDFs (post manual import) | Zotero storage | Zotero-managed |
| Downloaded paper PDFs (awaiting manual import) | Inbox | `paper_inbox` |
| Personal knowledge, notes, technical docs | Obsidian Vault | `vault_root` |
| Knowledge outline, projects, tasks | Notion | Notion cloud |
| Plugin runtime state + resource cache | State store | `SCHOLAR_WORKFLOW_HOME` |

## Invariants

1. Downloaded paper PDFs land only in `paper_inbox` awaiting manual Zotero import;
   technical documents live in the Vault even when they are PDFs. Never swap.
2. A paper has at most one identity in the authoritative library (one Zotero item).
3. The Obsidian paper table is a rebuildable derived index, not source of truth.
4. Notion stores no files and never overwrites human-authored fields.
5. The state store holds only mappings, cursors, task state, audit, and the derived
   resource cache — never knowledge content.
6. The resource cache is a read-only mirror of Zotero, refreshed one-way by the
   user-triggered `sync` command. It accelerates existence prefilter and feeds the
   catalog projection; it is never an authority and never written back to Zotero.

## PDF handling

The plugin only downloads PDFs into `paper_inbox`. Once imported, Zotero owns and
relocates the file — the plugin never copies duplicates into multiple directories.
The authoritative current path of an imported PDF comes from Zotero attachment
relations (Local API), not from the cache.
