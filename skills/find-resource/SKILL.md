---
name: find-resource
description: Search for papers, verify paper identity, build candidate lists, locate existing papers or documents in the local library, open resources in cmux. Triggers: 'find papers', 'search literature', 'where is this paper', 'locate document', '找论文', '搜索论文', '这篇论文在哪', '定位文档'.
---

# find-resource

## Triggers
- User searches for papers, verifies paper identity, or builds a candidate list
- User asks where a paper/document is, or wants to locate or open it in cmux

## Steps

1. Determine request type: **locate by identifier** (exact), **recall by topic**
   (fuzzy/semantic), or **discovery** (search for new resources).

2. **Locate by identifier (exact)** — via zotero-mcp, read-only:
   - `search_library` by DOI, then by title+authors (arXiv id is a download-source
     label, not an identity — see `identity-policy.md`).
   - Confirm each hit with `get_item_details`, comparing DOI / title / authors:
     - **exact** — already in the library; report the Zotero item key and title.
     - **conflict** — several items share the same identity; stop and present the keys
       for human adjudication. Never auto-merge (NG3).
     - **none** — not in the library.
   - For an imported item's authoritative current PDF path, read its attachment
     relations from `get_item_details`; a not-yet-ingested paper only has its
     `paper_inbox` path.

3. **Recall by topic (fuzzy/semantic)** — via zotero-mcp:
   - `semantic_search` (and/or `search_library` full-text) by topic. Read titles and
     abstracts from the results and judge similarity yourself (INV14: this project
     builds no embeddings or vector index of its own — recall is delegated to
     zotero-mcp).
   - A semantic hit is a candidate, not a decision. Confirm identity with the two-step
     check in step 2 before treating it as the same paper.

4. **Discovery mode**:
   - Normalize the identifier, then run the existence check (step 2) to see whether it
     is already in the library.
   - Web query (arXiv, Crossref, OpenAlex, Semantic Scholar, CVF, DBLP) is read-only
     and needs no approval; it is metadata-only — never a PDF source.
   - Return a candidate list with match rationale, arXiv PDF availability, existing
     status.

## Output
Zotero item key + resolved path (locate), a ranked candidate list with rationale
(recall), or a candidate list with rationale (discovery).

## Constraints
- Existence and metadata are authoritative from zotero-mcp, queried live — never cached
- The CLI cannot reach zotero-mcp; all Zotero queries run in the host LLM here
- Semantic recall is delegated to zotero-mcp `semantic_search`; no local embeddings
- Web fetch for metadata/identity is read-only — no approval needed
- Crossref / OpenAlex / CVF / DBLP may verify metadata, never download PDFs
- Discovery produces no writes
- Never relay paper PDFs from non-arXiv sources

## References

Load on demand.

- `references/resource-location.md` — resolving existing resources to local paths
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — normalization, existence check, semantic recall
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only, metadata-vs-download rules
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — which root holds what
