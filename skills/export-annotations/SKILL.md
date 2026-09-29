---
name: export-annotations
description: Export one paper's Zotero highlights and comments to a separate Obsidian annotations note. Use for 'export annotations', 'extract my highlights', '整理批注', '导出批注', '整理高亮'. Not for paper analysis or discovery.
---

# export-annotations

## Source and destination boundary

Read annotations with `scholar-workflow zotero annotations "<title fragment>" --json`;
disambiguate multiple matches with `--item <item-key> --json`. Report a missing PDF
attachment rather than inventing content. The destination is a registered Knowledge
Source/Field; legacy `research_vault_root` is only a migration candidate, not an
implicit destination.

## Output contract

- Create one separate annotations note without overwriting analysis or human-authored
  notes; use frontmatter `related` to link them.
- Frontmatter contains title, arXiv ID when available, source item ID, annotation
  counts, and related links. Entries have descriptive headings, inline `(p.N)`
  provenance, and source order within a group when it matters.
- User comments are verbatim callouts; highlighted source text is block quoted;
  model-added context uses a separate `补充（模型）` callout. Omit empty entries and
  stripped machine translations.

## Constraints

- The extractor reads Zotero annotations only through the loopback Local API and emits a
  read-only `AnnotationIR` projection. It never opens a SQLite database and never requests
  a Zotero Web API key. A just-created annotation may be absent until Zotero commits it.
- Strip `🔤…🔤` Translate-plugin output.
- Never paraphrase or drop user comments. Model additions must not be presented as the
  user's words or the paper's text.
- One paper per run.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
