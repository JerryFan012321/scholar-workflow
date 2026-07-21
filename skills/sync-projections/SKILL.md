---
name: sync-projections
description: Rebuild Obsidian paper index tables and sync Notion management projections after ingestion or on demand. Triggers: 'update index', 'rebuild paper table', 'sync Notion', 'update knowledge index', '更新论文表', '同步 Notion', '重建索引'.
---

# sync-projections

## Triggers
- After a paper import completes (handoff from library-agent)
- User asks to rebuild a topic paper table or sync Notion structure
- Collection changes, PDF migration, or a periodic-maintenance request

## Steps

### Obsidian index update
1. Rebuild the target index table from Zotero via zotero-mcp (queried live) — do not
   treat the existing Obsidian table as source of truth, and do not read from a local
   cache (there is none; INV13).
2. Locate the managed block in the target file (`<!-- scholar-workflow:start/end -->`)
3. Update only the rows inside the managed block; preserve all human content outside it
4. For large directories, update the parent description and sub-indexes before leaf tables
5. The table must include: title, authors, year, venue, Zotero item key, PDF relative path, arXiv, DOI, synced time

### Notion management projection
6. Upsert by stable Resource ID — never blindly create pages by title
7. Write only machine-managed fields (see `references/notion-schema.md`); never overwrite human content
8. Point links at the local-link service or a stable web entry; never hardcode absolute file:// paths
9. Upload no files

## Constraints
- The Obsidian paper table is a derived index; the rebuild source is Zotero via
  zotero-mcp, queried live — never a local mirror
- Rebuilding the managed block is an additive write; overwriting human content outside
  it is never done
- The Notion `Sync Revision` field drives incremental updates to avoid needless overwrites
- The two subtasks may run in parallel but report status independently

## References

Load on demand.

- `references/obsidian-index-format.md` — managed block, table columns, hierarchy
- `references/notion-schema.md` — machine vs human fields, upsert rules
- `references/link-format.md` — local-link service URL format
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — derived-index invariant
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — loopback links, no file upload
