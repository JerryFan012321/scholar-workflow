---
name: sync-projections
description: Rebuild Obsidian paper indexes or push the one-way Notion management projection from live Zotero data. Use for 'update index', 'rebuild paper table', 'sync Notion', '重建索引', '更新论文表', '同步 Notion'.
---

# sync-projections

## Obsidian

1. Choose one output:
   - one topic table: `scholar-workflow project-obsidian`;
   - a Zotero collection subtree: `scholar-workflow project-tree`.
2. Read live structure and papers with
   `scholar-workflow zotero collections` and
   `scholar-workflow zotero collection-items <key>`. Existing Obsidian files and
   local caches are never the data source.
3. Build the payload defined by `references/obsidian-index-format.md`:
   - topic: `{index, heading, entries[]}`;
   - subtree: `{root, tree:{name, collection_key, papers[], children[]}}`.
4. For `project-tree`, run `--dry-run`, review every target path, then apply.
   Renderers may create files and replace managed blocks only.
5. PDF cells use the attachment-key URL from `references/link-format.md`. Start
   `scholar-workflow serve-links` when a valid URL is connection-refused.

## Notion

1. Build
   `{papers:[{resource_id,fields}],related_docs:[{doc_id,paper_resource_id,fields}]}`
   according to `references/notion-schema.md`.
2. Pipe it to
   `SCHOLAR_WORKFLOW_NOTION_TOKEN=… ${CLAUDE_PLUGIN_ROOT}/bin/notion-project.py`.
   The script upserts papers by `Resource ID`, then related documents by `Doc ID`,
   wires relations, and returns page-id maps.
3. Build the topic page from those page IDs. Each paper entry links to its Papers page,
   Web Source, and Local URL; related material links to its Related Docs page.
4. Report Obsidian and Notion results independently.

## Constraints

- Projection is one-way: Zotero/Obsidian → Notion. Never write Notion edits back.
- Modify only Obsidian managed blocks and Notion machine-managed fields. Preserve all
  human content.
- Project no files or full note bodies to Notion: only fields, one-paragraph Summary,
  and Vault backlink.
- `notion-project.py` is the only Notion API caller. The token comes only from
  `SCHOLAR_WORKFLOW_NOTION_TOKEN`.
- The Vault index uses the plain `paper/` subtree. PDFs stay in Zotero storage.
- Skip unchanged Notion records by `Sync Revision`.

## References

- `references/obsidian-index-format.md`
- `references/notion-schema.md`
- `references/link-format.md`
- `${CLAUDE_PLUGIN_ROOT}/bin/notion-project.py`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
