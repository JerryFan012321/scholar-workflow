# Consistency Invariants

The audit checks these invariants against the canonical rules in the shared
`references/storage-policy.md`. Read-only — report violations, never fix.

## Checks by system

| System | Check |
|---|---|
| Zotero | item exists; no duplicates; correct Collection assignment |
| Files | PDF exists under `papers_root`; SHA-256 matches attachment record |
| Obsidian | index-row Zotero keys resolve; PDF relative paths are valid |
| Notion | no duplicate Resource IDs; local-link URLs resolve |
| Hierarchy | parent index descriptions match actual sub-directory contents |

## Drift categories

Orphaned PDFs, dead Zotero keys, stale index rows, broken local links, duplicate
Resource IDs.

## Reporting

Tag each issue `error` / `warning` / `info` with a suggested remedy. Remedies run in
the corresponding Agent after user confirmation, never in this skill.
