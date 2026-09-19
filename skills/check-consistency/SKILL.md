---
name: check-consistency
description: Audit Zotero, Obsidian indexes, Notion projections, attachments, and paper_inbox for cross-system drift. Use for 'check consistency', 'audit library', 'find drift', '检查库状态', '审计一致性'. Strictly read-only.
---

# check-consistency

## Steps

1. Resolve the requested scope: all data, a Zotero collection, a Vault directory, or a
   Notion project.
2. Load `references/consistency-invariants.md` and run every applicable check using
   read-only Zotero Local API, filesystem, link-service, and Notion reads.
3. Emit structured JSON containing scope and issues. Each issue includes system,
   category, affected identifier/path, severity (`error|warning|info`), evidence, and
   suggested remedy. Add a Markdown summary only when requested.

## Constraints

- Read-only throughout. Never repair, delete, merge, rewrite, or clear an inbox file.
- Audit only `paper_inbox` for staging orphans; never reverse-scan Zotero `storage/`.
- Zotero identities are resolved by DOI or normalized title+authors. File paths do not
  prove identity.
- A suggested destructive remedy still requires per-item user approval and execution by
  the owning workflow.

## References

- `references/consistency-invariants.md`
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
