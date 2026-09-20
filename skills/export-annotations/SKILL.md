---
name: export-annotations
description: Export one paper's Zotero highlights and comments to a separate Obsidian annotations note. Use for 'export annotations', 'extract my highlights', '整理批注', '导出批注', '整理高亮'. Not for paper analysis or discovery.
---

# export-annotations

## Steps

1. Run the read-only extractor:
   `python3 ${CLAUDE_PLUGIN_ROOT}/bin/zotero-annotations.py "<title fragment>"`.
2. If several items match, ask for the item and rerun with `--item <id>`. If there is
   no PDF attachment, report it and stop.
3. Resolve a destination under `research_vault_root`; ask for the topic subfolder only
   when it is not inferable.
4. Create a separate annotations note. Never overwrite an analysis or human-authored
   note; cross-link related notes through frontmatter `related`.
5. Write frontmatter with title, arXiv id, source item ID, annotation counts, and related
   links. Group entries under descriptive headings suited to the material or requested
   view; retain inline `(p.N)` provenance and preserve source order within a group when it
   matters.
6. Preserve source types exactly:
   - user comments: verbatim callouts;
   - highlighted paper text: block quotes;
   - model-added context: a separate `补充（模型）` callout.
   Omit empty entries and stripped machine translations.

## Constraints

- The extractor reads Zotero with `mode=ro&immutable=1` and never writes
  `zotero.sqlite`. A just-created annotation may be absent until Zotero commits it.
- Strip `🔤…🔤` Translate-plugin output.
- Never paraphrase or drop user comments. Model additions must not be presented as the
  user's words or the paper's text.
- One paper per run.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
