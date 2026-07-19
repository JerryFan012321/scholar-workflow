---
name: ingest-resource
description: Import papers or archive technical documents into the local library. Handles planning (dry-run) and execution (requires approved plan). Triggers: 'import paper', 'add to Zotero', 'archive document', 'file this PDF', '导入论文', '加入 Zotero', '归档技术文档', '把这篇论文加入'.
---

# ingest-resource

## Triggers
- User provides a paper list or candidates to add to the system
- User asks to archive a technical document, web snapshot, draw.io, or other non-paper material
- User approves an import plan (holds a `plan_id`)

## Steps

### Phase 1: Plan (always dry-run)
1. Classify resource `kind` (paper / technical_document / snapshot / drawio / image)
2. Normalize DOI, arXiv ID, title, authors, year
3. Check the input batch, state store, target directories, and Zotero (dedup)
4. Papers: recommend a Zotero Collection and Obsidian index location
5. Technical documents: recommend a Vault category directory
6. Generate a structured `action-plan.json` showing create / update / skip / conflict / download targets
7. Wait for user approval; return the `plan_id`

### Phase 2: Execute (requires a valid plan_id)
8. Validate `plan_id`, input digest, config version, and approval status
9. Papers: download the PDF from arXiv to a temp dir; verify %PDF magic / size / SHA-256
10. Papers: call `ZoteroWriteAdapter` to upsert the item and linked_file
11. Technical documents: download or copy into the Vault category; write source/time/hash metadata
12. Return receipt: Zotero key, PDF path, Vault path

## Constraints
- Phase 1 never writes to external systems
- Phase 2 must not run without a valid `plan_id`
- Any change to plan content invalidates the prior approval
- Paper PDFs go only to `papers_root`; technical documents only to the Vault — never swap
- If arXiv has no PDF, record metadata and candidate status; do not fetch from other sources
- If the Bridge health check fails, stop — never fall back to Local API or another bypass
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
