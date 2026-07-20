---
name: ingest-resource
description: Import papers or archive technical documents into the local library. Handles planning (dry-run) and execution (requires approved plan). Triggers: 'import paper', 'add to Zotero', 'archive document', 'file this PDF', '导入论文', '加入 Zotero', '归档技术文档', '把这篇论文加入'.
---

# ingest-resource

## Triggers
- User provides a paper list or candidates to add to the system
- User asks to archive a technical document, web snapshot, draw.io, or other non-paper material

## Steps

### Phase 1: Plan (dry-run, never writes)
1. Run `scholar-workflow plan <inputs...>` — it resolves each input, dedups against
   the state store, and emits a structured plan (one action per resource:
   create / skip / conflict, with arXiv download targets for papers).
2. Read that JSON and present it to the user in a human-readable form: how many are
   new (create), already present (skip), or fuzzy-matched conflicts needing a decision.
3. For papers, note the recommended Zotero Collection and Obsidian index location;
   for technical documents, the Vault category directory.
4. Wait for the user to approve in-conversation. Approval is a dialogue act — there
   is no plan file and no `plan_id` to hand back.

### Phase 2: Execute (only after in-conversation approval)
5. Run `scholar-workflow apply <inputs...>` — it re-resolves, re-dedups, and writes.
   Papers: download the PDF from arXiv (temp dir, %PDF magic / size / SHA-256 verified),
   then upsert the Zotero item + linked_file via `ZoteroWriteAdapter`.
6. Technical documents: copy into the Vault category; write source/time/hash metadata.
7. Report the receipt: Zotero key, PDF path, Vault path.

## Constraints
- Phase 1 never writes to external systems
- Never run `apply` until the user has approved the plan in-conversation
- Paper PDFs go only to `papers_root`; technical documents only to the Vault — never swap
- If arXiv has no PDF, record metadata and candidate status; do not fetch from other sources
- If the Bridge health check fails, stop — never fall back to Local API or another bypass
- A `conflict` action is never written automatically — surface it for the user to adjudicate
- On identity conflict, stop that item without affecting other safe items in the batch

## References

Load on demand.

- `references/resource-model.md` — kind classification and storage targets
- `references/download-validation.md` — temp-dir download and PDF validation
- `references/zotero-fields.md` — Zotero field mapping and attachment shape
- `references/bridge-contract.md` — the write client contract
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only acquisition
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — dedup keys, version handling
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — storage-root invariants
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — approval gate, permission boundary
