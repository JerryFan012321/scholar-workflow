---
name: check-consistency
description: Audit cross-system consistency across Zotero, papers_root, Obsidian indexes, and Notion projections. Report drift, orphaned files, stale entries, and broken links. Read-only — never auto-fixes. Triggers: 'check consistency', 'audit library', 'find drift', 'check sync status', '检查库状态', '审计一致性', '有没有漂移'.
---

# check-consistency

## Triggers
- User asks to check library state or run periodic maintenance
- Proactively triggered by audit-agent

## Steps

1. Determine scope (full / specific Collection / specific Vault directory / specific Notion project)
2. **Zotero check**: item existence, duplicates, correct Collection assignment
3. **File check**: PDF exists under `papers_root`; SHA-256 matches the attachment record
4. **Obsidian check**: index row Zotero keys resolve; PDF paths are valid
5. **Notion check**: no duplicate Resource IDs; local-link URLs resolve
6. **Hierarchical index check**: parent index descriptions match actual sub-directory contents
7. Compile a drift report: orphaned PDFs, dead keys, stale index rows, broken links, duplicates
8. Output a structured JSON report; optionally a Markdown summary

## Constraints
- Read-only throughout — never fix or delete any discovered issue
- Tag each issue with severity (error / warning / info) and a suggested remedy
- Remedies require user confirmation and run in the corresponding Agent, not in this skill
