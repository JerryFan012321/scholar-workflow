---
name: check-consistency
description: Audit Zotero, Obsidian indexes, Notion projections, attachments, and paper_inbox for cross-system drift. Use for 'check consistency', 'audit library', 'find drift', '检查库状态', '审计一致性'. Strictly read-only.
---

# check-consistency

## Result contract

The supported scope is all data, a Zotero collection, a Vault directory, or a Notion
project. Return structured JSON identifying the applied scope and every applicable
issue. Each issue includes system, category, affected identifier/path, severity
(`error|warning|info`), evidence, and suggested remedy. Add a Markdown summary only
when requested. Load `references/consistency-invariants.md` for the checks and use
read-only Zotero Local API, filesystem, and Notion reads.

## Constraints

- Read-only throughout. Never repair, delete, merge, rewrite, or clear an inbox file.
- Audit only `paper_inbox` for staging orphans; never reverse-scan Zotero `storage/`.
- Zotero identities are resolved by DOI or normalized title+authors. File paths do not
  prove identity.
- A suggested destructive remedy still requires per-item user approval and execution by
  the owning workflow.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `references/consistency-invariants.md`
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
