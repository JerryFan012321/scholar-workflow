---
name: check-consistency
description: Audit cross-system consistency across Zotero, Obsidian indexes, and Notion projections. Report drift, orphaned files, stale entries, and broken links. Read-only — never auto-fixes. Triggers: 'check consistency', 'audit library', 'find drift', 'check sync status', '检查库状态', '审计一致性', '有没有漂移'.
---

# check-consistency

## Triggers
- User asks to check library state or run periodic maintenance
- Proactively triggered by audit-agent

## Steps

1. Determine scope (full / specific Collection / specific Vault directory / specific Notion project)
2. **Zotero check** (via zotero-mcp, read-only): item existence, duplicate identities,
   correct Collection assignment
3. **File check**: the attachment path from `get_item_details` resolves to a real file
   on disk (a ghost attachment — DB record with no file, size 0 — is drift to report)
4. **Linked-file portability check**: for linkMode-2 attachments, the `get_item_details`
   path must be relative (`attachments:…`), not absolute (`/Users/…`, `C:\…`). An
   absolute path locks the file to one machine — cross-machine drift to report.
5. **Obsidian check**: index-row Zotero keys resolve via zotero-mcp; PDF paths are valid
6. **Notion check**: no duplicate Resource IDs; local-link URLs resolve
7. **Hierarchical index check**: parent index descriptions match actual sub-directory contents
8. Compile a drift report: orphaned PDFs, ghost attachments, absolute-path linked files, dead keys, stale index rows, broken links, duplicate identities
9. Output a structured JSON report; optionally a Markdown summary

## Constraints
- Read-only throughout — never fix or delete any discovered issue
- Tag each issue with severity (error / warning / info) and a suggested remedy
- Remedies require the corresponding Agent; deletion/merge remedies need user approval

## References

Load on demand.

- `references/consistency-invariants.md` — per-system checks and drift categories
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — canonical invariants being audited
