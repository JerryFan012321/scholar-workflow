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
2. **Locate by identifier (exact)**
   - Run `scholar-workflow locate <identifier>` — read-only, deterministic. It
     normalizes the input, queries the Zotero Local API (authority), and returns
     `{match, resource_id, zotero_item_key, conflicts}`:
     - `exact` — already in the library; report the Zotero item key. To name the
       item for the user (display only), read its title from `catalog` or Zotero
       `get_item` by that key; if unavailable, show the identifier as-is.
     - `conflict` — several items carry the same identifier; stop and present the
       keys in `conflicts` for human adjudication. Never auto-merge (NG3).
     - `none` — not in the library.
   - Exit code 3 means the Local API is unreachable — do not treat that as `none`
     (INV12: fail-closed).
   - For an imported item's authoritative current PDF path, follow up with Zotero
     attachment relations (Local API); a not-yet-imported paper only has its
     `paper_inbox` path.
3. **Recall by topic (fuzzy/semantic)**
   - There is no CLI fuzzy matcher. Run `scholar-workflow catalog` (read-only) to get
     the cached projection — one row per item with title + abstract + `zotero_item_key`.
     Read it and judge similarity yourself (INV14: no embeddings, no vector index).
   - If `oldest_sync` is stale (or null), remind the user to run
     `scholar-workflow sync` first — the catalog is a derived mirror, refreshed only
     when the user syncs.
   - A semantic hit is a candidate, not a decision. Confirm identity via `locate`
     on the item's identifier, then resolve its path as in step 2.
4. **Discovery mode**
   - Run `scholar-workflow resolve <identifier>` to normalize + check existence.
   - Web query (Crossref / OpenAlex / Semantic Scholar) requires explicit user
     authorization and is metadata-only — never a PDF source.
   - Return a candidate list with match rationale, arXiv PDF availability, existing status.

## Output
Zotero item key + resolved path (locate), a ranked candidate list from the catalog
with rationale (recall), or a candidate list with rationale (discovery).

## Constraints
- Existence is authoritative from the Zotero Local API; fail-closed on unreachable
- Semantic recall reads the catalog projection only — no embeddings, no vector index
- The resolver has no offline title (`title` is null for identifier inputs); any
  display title is an optional display-layer enrichment, never a decision input
- Web search requires explicit user authorization
- Crossref / OpenAlex may be used to verify metadata, but never to download PDFs
- Discovery produces no file writes
- Never relay paper PDFs from non-arXiv sources

## References

Load on demand.

- `references/resource-location.md` — resolving existing resources to local paths
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — normalization, existence check, semantic recall
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only, metadata-vs-download rules
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — which root holds what
