---
name: export-annotations
description: Export one paper's Zotero annotations (highlights, notes, my comments) into a structured Obsidian markdown note. Strips the Translate plugin's machine translation, keeps only my highlights and comments, reorganized by argument logic. Triggers: 'export annotations', 'extract my highlights', 'turn my annotations into a note', '导出批注', '提取批注', '把论文批注整理成笔记', '整理高亮'. Not for full paper analysis (analyze-paper) or paper discovery (find-resource).
---

# export-annotations

## Triggers
- User wants their Zotero highlights/notes for a specific paper turned into a vault note
- User asks to extract, export, or organize the annotations they made on a paper

## Steps

1. **Resolve the paper.** Run the extractor by title fragment (read-only):
   `python3 ${CLAUDE_PLUGIN_ROOT}/bin/zotero-annotations.py "<title fragment>"`.
   It finds the item, its PDF attachment, and all annotations; strips machine
   translation; prints them in reading order with an inline `(p.N)` tag per entry.

2. **Disambiguate.** If the fragment matches several items, the script lists their
   itemIDs — ask the user which one, then re-run with `--item <id>`. If a title has
   no PDF attachment, report it and stop.

3. **Resolve the vault.** Notes land under `research_vault_root` (plugin userConfig). Ask the
   user for the target subfolder if it is not obvious from context.

4. **Check for an existing note.** Search the target vault for a note on the same
   paper (e.g. an analysis/read-through note). If one exists, do NOT overwrite it —
   create a separate *annotations* note and cross-link both via frontmatter `related`.

5. **Organize by logic, then write.** Reorganize the raw annotations along
   **conceptual / argument logic** (e.g. task framing → representation → architecture
   → results), grouping related entries regardless of source page. Page numbers are
   attached as inline `(p.N)` tags on each entry — never used as section headers or as
   the ordering key. Drop empty entries.
   - Write frontmatter yourself (title, arxiv, `source` = itemID + annotation counts,
     `related`). The script does not emit frontmatter.

6. **Preserve provenance — keep three sources distinct.** The note interleaves three
   kinds of content that must never blur together:
   - **User comments** (annotation `comment`) — reproduce **verbatim** in a callout,
     the backbone of the note. Never paraphrase, condense, supplement, or drop them.
   - **Highlighted text** (annotation `text`) — a plain `>` quote, supporting evidence.
   - **Claude's own additions** (framing, background, cross-section synthesis) — only
     when **explicitly labeled** as a separate `补充（Claude）` callout, so they never
     pass for the user's words or the paper's.
   Additions obey two limits: (a) **information only** — background or connective
   tissue — never *evaluate* the user's comments; (b) **no padding** — if a comment or
   highlight already makes the point, add nothing.

## Constraints
- Read Zotero **read-only** (`mode=ro&immutable=1`); Zotero may hold a lock. Never
  write `zotero.sqlite` (INV8) — the extractor only reads.
- `immutable=1` reads the last committed snapshot; annotations made seconds ago while
  Zotero is open may not appear. If a count looks short, say so.
- Strip the Translate plugin's `🔤…🔤` machine translation; keep only the real
  highlighted original text.
- Never overwrite a human-authored note; the annotations note is separate and
  cross-linked (see storage-policy derived-index / no-overwrite rules).
- One paper per run. No batch export.

## References

Load on demand.

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — vault as note home, no-overwrite of human content
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — read-only boundary, never write zotero.sqlite
