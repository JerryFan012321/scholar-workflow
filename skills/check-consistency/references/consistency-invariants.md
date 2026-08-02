# Consistency Invariants

The audit checks these invariants against the canonical rules in the shared
`references/storage-policy.md`. Read-only — report violations, never fix.

## Checks by system

| System | Check |
|---|---|
| Zotero | item exists; no duplicates; correct Collection assignment |
| Attachments | file resolves on disk; linked files (linkMode 2) store a **relative** path (`attachments:…`), not absolute |
| Files | attachment file exists at its resolved path; not a size-0 ghost |
| Obsidian | index-row Zotero item keys resolve; PDF link-service URLs resolve (attachment key globs a real PDF under storage_root); content outside managed markers untouched |
| Notion | no duplicate Resource IDs; local-link URLs resolve |
| Hierarchy | parent index descriptions match actual sub-directory contents |

## Drift categories

Orphaned PDFs, dead Zotero keys, stale index rows, broken local links, duplicate
Resource IDs, plus two cross-machine attachment risks:

- **Absolute-path linked file** — a linkMode-2 attachment whose `get_item_details` path
  is absolute (`/Users/…`, `C:\…`) instead of relative. It resolves on its origin
  machine but breaks on every other synced machine. Report as cross-machine drift.
- **Ghost attachment** — an attachment record with no file at its resolved path (size 0).
  Remedy: re-import the source file, or delete the record (deletion needs approval).

## Reporting

Tag each issue `error` / `warning` / `info` with a suggested remedy. Remedies run in
the corresponding Agent after user confirmation, never in this skill.
