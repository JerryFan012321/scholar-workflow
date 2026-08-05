---
name: ingest-resource
description: Import papers or archive technical documents into the local library via zotero-mcp. Handles existence check, PDF download, Zotero create/import, and collection filing. Triggers 'import paper', 'add to Zotero', 'archive document', 'file this PDF', '导入论文', '加入 Zotero', '归档技术文档', '把这篇论文加入'.
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
   - **same-work, different version** — the item's dedup key is `none` (different DOI/title,
     e.g. an arXiv preprint vs an in-library published version of the same work), yet it is
     plainly the same work. This is **not** an NG3 identity conflict, but it is a human call:
     surface both to the user and let them decide (keep both / keep only the published / keep
     only the preprint). Never auto-skip and never auto-merge.
3. Present the plan: which are new (create), present (skip), same-work (adjudicate), or conflicts.

### Phase 2: Acquire metadata (read-only web fetch, no approval)
4. For each `none` item, fetch metadata from an authoritative source: arXiv abs page
   for the preprint, and CVF / DBLP / publisher for the published version. When a
   published version exists, its venue (e.g. "NeurIPS 2024") overrides the arXiv
   "preprint" label — write the venue into `conferenceName` / `proceedingsTitle`.
5. Fill what an authoritative source gives; if a secondary field (volume, pages) is not
   found, leave it empty — never fabricate, and never hammer an unreachable site to
   fill a non-essential field.

### Phase 3: Write into Zotero (additive, no per-action approval)
6. Ask the human for the **organizing direction**, not just a folder name — this is a human
   call, never auto-defaulted. Either ask which collection to file into, or, when organizing
   by an existing literature tree, ask **which tree** to adopt as the structure. When invoked
   from survey-topic the scope is already fixed upstream — inherit it, don't re-ask. (Filing
   itself is safe: in Zotero one item may belong to several collections — a many-to-one
   projection, not a duplicate identity, INV1 — so adding to a collection needs no gate; the
   human call is the direction, not whether to file.)
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
- Existence check precedes every create — `write_item` is pure create, no dedup;
  skipping it duplicates (identity-policy, security-policy)
- A `conflict` is never auto-written — stop that item, surface keys, leave the rest of
  the batch running (identity-policy)
- **Additive-write branch points do not interrupt with questions.** Metadata source
  (arXiv batch vs per-item) and the additive create / import / add-to-collection themselves
  run end to end — a batch of N papers is one authorization, no per-item re-prompt. Note the
  assumptions made in the receipt for later pruning.
- **Stop for a human only in these cases:** (1) the **organizing direction** — which
  collection or which literature tree structure (Step 6), a preference the human owns;
  (2) **same-work different-version** adjudication (Phase 1); (3) **NG3 identity conflict**
  (dedup-key hit or fuzzy match); (4) **destructive / irreversible actions** — delete,
  overwrite-conflict, merge-identity (security-policy). Nothing else gates.
- All writes go through zotero-mcp; never write `zotero.sqlite` (security-policy)
- arXiv is the only PDF source; if none, tag `no_arxiv_pdf`, don't fetch elsewhere (source-policy)
- Downloaded PDFs land only in `paper_inbox`, tech docs only in the Vault; attachments
  stay imported (linkMode 0) for File Syncing (storage-policy)
- Judge record health by title / creators / DOI / attachment — never by `itemType`
  (reads back empty via zotero-mcp) (security-policy)

## References

Load on demand.

- `references/resource-model.md` — kind classification and storage targets
- `references/download-validation.md` — inbox download and PDF validation
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only acquisition, metadata sources
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — dedup keys, two-step existence check
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — storage-root invariants
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — approval boundary, zotero-mcp channel
