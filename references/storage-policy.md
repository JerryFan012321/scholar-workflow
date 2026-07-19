# Storage Policy (shared)

Canonical rule for where every object lives. Applies to all skills and agents.

## Source-of-truth allocation

| Object | Authoritative store | Root |
|---|---|---|
| Paper bibliography, tags, attachment links | Zotero database | Zotero-managed |
| Paper PDFs | Zotero linked_file | `papers_root` |
| Personal knowledge, notes, technical docs | Obsidian Vault | `vault_root` |
| Knowledge outline, projects, tasks | Notion | Notion cloud |
| Plugin runtime state | State store | `SCHOLAR_WORKFLOW_HOME` |

## Invariants

1. Paper PDFs live only under `papers_root`; technical documents live in the Vault
   even when they are PDFs. Never swap.
2. A paper has at most one Zotero parent item and one primary PDF attachment.
3. The Obsidian paper table is a rebuildable derived index, not source of truth.
4. Notion stores no files and never overwrites human-authored fields.
5. The state store holds only mappings, cursors, task state, and audit — never
   knowledge content.

## PDF migration

PDF relocation happens via config change plus the Zotero attachment relation —
never by copying duplicates into multiple directories.
