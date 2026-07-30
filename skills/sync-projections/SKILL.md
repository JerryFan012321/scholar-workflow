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

Two shapes, same rules. A **single table** (one topic → one file) uses
`scholar-workflow project-obsidian`. A **hierarchical index** (mirror a whole Zotero
collection subtree) uses `scholar-workflow project-tree`. In both, the host LLM gathers
data via zotero-mcp and hands JSON to the CLI; the CLI owns rendering + all path
computation and never queries zotero-mcp itself (INV18).

1. Rebuild from Zotero via zotero-mcp (queried live) — never treat the existing Obsidian
   files as source of truth, and never read a local cache (there is none; INV13). For a
   tree: `get_collections(recursive=true)` for structure, then `get_collection_items`
   per collection; read each paper's `prio:★/★★/★★★` tag for the Importance column.
2. Build the payload and call the CLI:
   - single table → `{index, heading, entries[]}` → `project-obsidian`
   - subtree → `{root, tree:{name, collection_key, papers[], children[]}}` → `project-tree`
3. **Always `--dry-run` first** (project-tree). It prints every file it would write
   (path + heading + body) and touches nothing — review the plan, then re-run without
   the flag to apply. Applying is additive: new files + managed-block rewrites only.
4. Each paper row is 10 columns: Title, Authors (`; `-joined), Year, Venue (keep it —
   with Year it lets a later step look up the BibTeX citation), Importance (from
   `prio:★★★`, empty when untagged), Zotero (`zotero://select/items/@<item-key>`), PDF
   (link-service URL by attachment key — see `references/link-format.md`), arXiv, DOI,
   Synced (ISO date from the input, not `now()` — keeps re-projection idempotent).
5. PDF links only resolve while the loopback link service is running
   (`scholar-workflow serve-links`). If a PDF URL returns connection-refused, the service
   is down — start it; it is not a data error.

### Notion management projection (two-DB model)
6. Upsert the **paper** into the Papers DB by stable Resource ID → capture its page_id;
   then upsert each **related document** into the Related Docs DB by Doc ID, setting its
   `Paper` relation to that page_id (see `references/notion-schema.md`). Never create by title
7. Write only machine-managed fields; never overwrite human content. A related doc projects
   a one-paragraph Summary + a Vault backlink only — the full note body stays in Obsidian
8. Point links at a stable web entry (arXiv/DOI `Web Source`) or the Vault; never hardcode
   absolute file:// paths, and leave the host-only loopback Local URL empty for Notion
9. Upload no files — no note body is projected, only Summary + backlink

## Hierarchical layout (project-tree)
- The tree mirrors the Zotero collection tree. A **hub** node (has child collections)
  renders to `<parent>/<name>/index.md` and holds a MOC wikilink list to its children; a
  **leaf** node renders to `<parent>/<name>.md` and holds the paper table. The nested
  `index.md` for hubs is deliberate — it stops a folder and its own note from showing as
  same-named siblings in the Obsidian file tree.
- Leaf headings get a `相关论文` suffix (e.g. `# text2cad相关论文`); hub headings stay the
  bare collection name.
- The heading is written **only when the file is first created**; re-running updates the
  managed block but not the `# heading` line. If a collection is renamed or the heading
  rule changes, fix the `# heading` of existing files by hand.

## Constraints
- The Obsidian paper table is a derived index; the rebuild source is Zotero via
  zotero-mcp, queried live — never a local mirror
- Rebuilding the managed block is an additive write; overwriting human content outside
  it is never done
- The vault index directory is a plain `paper/` subtree (no numeric prefix); PDFs live
  under `papers_root` and are reached only via link-service URLs, never copied into the vault
- The Notion `Sync Revision` field drives incremental updates to avoid needless overwrites
- The two subtasks may run in parallel but report status independently

## References

Load on demand.

- `references/obsidian-index-format.md` — managed block, 10-column table, folder-mirror/MOC hierarchy
- `references/notion-schema.md` — machine vs human fields, upsert rules
- `references/link-format.md` — local-link service URL format
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — derived-index invariant
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — loopback links, no file upload
