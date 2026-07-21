---
name: ingest-resource
description: Import papers or archive technical documents into the local library via zotero-mcp. Handles existence check, PDF download, Zotero create/import, and collection filing. Triggers: 'import paper', 'add to Zotero', 'archive document', 'file this PDF', '导入论文', '加入 Zotero', '归档技术文档', '把这篇论文加入'.
---

# ingest-resource

## Triggers
- User provides a paper list or candidates to add to the system
- User asks to archive a technical document, web snapshot, draw.io, or other non-paper material

## What a paper needs

A paper in the library needs exactly two things: **its PDF** and **its metadata**
(venue, year, DOI, authors). The PDF comes from arXiv; the metadata comes from an
authoritative web source — never parsed out of the PDF.

## Steps

### Phase 1: Existence check (read-only, via zotero-mcp)
1. Normalize each input's identifier (DOI primary, title+authors secondary; arXiv id is
   a download-source label, not an identity — `identity-policy.md`).
2. Two-step existence check per item (host LLM, since the CLI cannot reach zotero-mcp):
   `search_library` recall → `get_item_details` field-level confirm. Outcomes:
   - **exact** — already present; do not re-create. Report the item key.
   - **conflict** — several items share the identity; stop that item, surface keys for
     human adjudication (NG3). Do not affect other items in the batch.
   - **none** — safe to create.
3. Present the plan: which are new (create), present (skip), or conflicts.

### Phase 2: Acquire metadata (read-only web fetch, no approval)
4. For each `none` item, fetch metadata from an authoritative source: arXiv abs page
   for the preprint, and CVF / DBLP / publisher for the published version. When a
   published version exists, its venue (e.g. "NeurIPS 2024") overrides the arXiv
   "preprint" label — write the venue into `conferenceName` / `proceedingsTitle`.
5. Fill what an authoritative source gives; if a secondary field (volume, pages) is not
   found, leave it empty — never fabricate, and never hammer an unreachable site to
   fill a non-essential field.

### Phase 3: Write into Zotero (additive, no per-action approval)
6. Ask which collection the paper belongs to — the target collection is an input to the
   write. The user may answer "leave in library root".
7. Download the arXiv PDF into `paper_inbox` (%PDF magic / size verified).
8. Create the item and attach the PDF via zotero-mcp:
   - `write_item action=create` with the metadata, then `write_item action=import` to
     attach the inbox PDF under the new item; or attach to an existing item when
     repairing.
   - `add_items_to_collection` to file it into the chosen collection.
9. Technical documents: copy into the Vault category; write source/time/hash metadata.
10. Report the receipt: Zotero item key, attachment key, PDF path in Zotero storage,
    collection, Obsidian/Notion projection status.

## Constraints
- `write_item` is pure create with no dedup — the Phase 1 existence check MUST precede
  every create, or duplicates result
- `itemType` reads back empty through zotero-mcp for every item and cannot be set via
  `write_metadata`; this is a read-layer artifact, not corruption — never judge a
  record dirty by it, and judge health by title/creators/DOI/attachment-on-disk instead
- All Zotero writes go through zotero-mcp controlled tools; never write `zotero.sqlite`
- Additive writes (create/import/collection/metadata/download) proceed under the user's
  standing instruction; only delete/overwrite-conflict/merge need approval
- Ingesting a paper is ONE authorized action: existence check → download → create →
  import → add-to-collection runs end to end with no mid-process approval gate
- Attachments must stay imported (linkMode 0, in Zotero storage) so Zotero File Syncing
  carries them across machines; do not convert them to linked files
- Downloaded PDFs land only in `paper_inbox`; technical documents only in the Vault
- If arXiv has no PDF, tag `no_arxiv_pdf`; do not fetch from other sources
- A `conflict` is never written automatically — surface it for the user
- On identity conflict, stop that item without affecting other safe items in the batch

## References

Load on demand.

- `references/resource-model.md` — kind classification and storage targets
- `references/download-validation.md` — inbox download and PDF validation
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only acquisition, metadata sources
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — dedup keys, two-step existence check
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — storage-root invariants
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — approval boundary, zotero-mcp channel
