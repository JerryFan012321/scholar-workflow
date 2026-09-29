---
name: ingest-resource
description: Add papers to Zotero through the Local API or archive technical documents in the Vault. Use for 'import paper', 'add to Zotero', 'archive this document', '导入论文', '加入 Zotero', '归档技术文档'. Not for read-only search or recommendation.
---

# ingest-resource

## Result and write boundary

Each item reports its kind, result (`reused | created | conflict | failed`),
Zotero item/attachment keys and collection when applicable, final storage target,
projection status when applicable, and any missing-PDF or failed validation reason.
A failed or conflicting item
does not invalidate successful siblings. `references/resource-model.md` defines which
kinds may enter Zotero and where non-paper resources belong.

The external write dependencies are:

- Before paper creation, run `scholar-workflow zotero search` and confirm candidates with
  `scholar-workflow zotero get <item-key> --children` when needed. Reuse an exact match;
  continue on `none`; report multiple exact keys or a same-work publication/version
  conflict without auto-merging.
- The organizing target is a selected Zotero collection or existing literature tree.
  Reuse an already confirmed choice; otherwise ask before writing.
- A new paper PDF enters `paper_inbox` from arXiv and passes
  `references/download-validation.md` before import. Send one
  `{"metadata": {...}, "collection_keys": [...], "pdf_path": "..."}` payload per item
  to `scholar-workflow zotero ingest`. When write authorization is missing, run
  `scholar-workflow zotero authorize` first and choose **Always Allow** for the
  multi-phase import.
- A non-paper technical document goes to the registered Vault target in
  `resource-model.md`, with its source, time, and hash recorded.

## Write gates

The user's ingest request authorizes additive download, create, import, metadata fill, and
collection membership for the batch. Pause only for:

- an unspecified organizing direction;
- same-work/different-version adjudication;
- an identity conflict;
- delete, overwrite-conflict, or merge-identity.

## Constraints

- Every create has a skill-level existence preview; `zotero ingest` repeats the exact
  check immediately before writing.
- All Zotero writes use the Local API CLI. Never write `zotero.sqlite`.
- Follow the shared source and storage policies for arXiv-only PDF acquisition,
  imported attachments, and the `no_arxiv_pdf` state.
- Exit 3 means Local API unavailable, never not-found. Stop that item and retry after
  Zotero Local API is available.
- Keep other batch items running when one item conflicts or fails.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `references/resource-model.md`
- `references/download-validation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
