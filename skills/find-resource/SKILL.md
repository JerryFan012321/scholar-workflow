---
name: find-resource
description: Search for papers, verify paper identity, build candidate lists, locate existing papers or documents in the local library, open resources in cmux. Triggers: 'find papers', 'search literature', 'where is this paper', 'locate document', '找论文', '搜索论文', '这篇论文在哪', '定位文档'.
---

# find-resource

## Triggers
- User searches for papers, verifies paper identity, or builds a candidate list
- User asks where a paper/document is, or wants to locate or open it in cmux

## Steps

1. Determine request type: **locate** (is it already in our library?) or
   **discovery** (search for new resources).
2. **Locate mode**
   - Run `scholar-workflow locate <identifier>` — read-only. It normalizes the input
     and returns `{match, resource_id, zotero_item_key, candidates}`:
     - `exact` — the resource is already in the library (report the Zotero key / path)
     - `fuzzy` — the CLI surfaces candidates only; judge whether any is truly the same
       paper and present the reasoning. A fuzzy result is never treated as a decision.
     - `none` — not found locally
   - Report the local path / local-link URL; do not copy files by default.
3. **Discovery mode**
   - Run `scholar-workflow resolve <identifier>` to normalize + check local existence.
   - Web query (Crossref / OpenAlex / Semantic Scholar) requires explicit user
     authorization and is metadata-only — never a PDF source.
   - Return a candidate list with match rationale, arXiv PDF availability, existing status.

## Output
Local path + URL (locate) or a candidate list with rationale (discovery).

## Constraints
- Web search requires explicit user authorization
- Crossref / OpenAlex may be used to verify metadata, but never to download PDFs
- Discovery produces no file writes
- Never relay paper PDFs from non-arXiv sources

## References

Load on demand.

- `references/resource-location.md` — resolving existing resources to local paths
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md` — normalization, dedup keys, metadata priority
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only, metadata-vs-download rules
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — which root holds what
