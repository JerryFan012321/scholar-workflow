---
name: ingest-resource
description: Add papers to Zotero through the Local API or archive technical documents in the Vault. Use for 'import paper', 'add to Zotero', 'archive this document', '导入论文', '加入 Zotero', '归档技术文档'. Not for read-only search or recommendation.
---

# ingest-resource

## Steps

1. Classify each input with `references/resource-model.md`.
2. For a paper, normalize its identity and run
   `scholar-workflow zotero search`, then
   `scholar-workflow zotero get <item-key> --children` when confirmation is needed:
   - `exact`: reuse and skip creation;
   - `none`: continue;
   - multiple exact matches: stop that item and report the keys;
   - same work with a different publication identity/version: ask whether to keep one
     or both. Never auto-skip or merge.
3. Fetch new-item metadata from an authoritative source. Prefer published venue metadata
   over an arXiv preprint label; leave unavailable secondary fields empty.
4. Resolve the organizing direction: target Zotero collection or existing literature
   tree. Reuse an upstream confirmed direction; otherwise ask once before writing.
5. Download the arXiv PDF to `paper_inbox` and apply
   `references/download-validation.md`.
6. Send one JSON payload per item to `scholar-workflow zotero ingest`:
   `{"metadata": {...}, "collection_keys": [...], "pdf_path": "..."}`.
   Run `scholar-workflow zotero authorize` first when write authorization is absent;
   choose **Always Allow** for the multi-phase PDF import.
7. For a non-paper technical document, write it to the Vault target defined by
   `resource-model.md` and record source, time, and hash.
8. Report item key, attachment key, final storage path, collection, and projection status.

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
- Paper PDFs come only from arXiv and remain imported attachments (linkMode 0). A paper
  without an arXiv PDF is tagged `no_arxiv_pdf`; do not fetch elsewhere.
- Exit 3 means Local API unavailable, never not-found. Stop that item and retry after
  Zotero Local API is available.
- Keep other batch items running when one item conflicts or fails.

## References

- `references/resource-model.md`
- `references/download-validation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
