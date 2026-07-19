---
name: find-resource
description: Search for papers, verify paper identity, build candidate lists, locate existing papers or documents in the local library, open resources in cmux. Triggers: 'find papers', 'search literature', 'where is this paper', 'locate document', '找论文', '搜索论文', '这篇论文在哪', '定位文档'.
---

# find-resource

## Triggers
- User searches for papers, verifies paper identity, or builds a candidate list
- User asks where a paper/document is, or wants to locate or open it in cmux

## Steps

1. Determine request type: **discovery** (search for new resources) or **locate** (find existing ones)
2. **Discovery mode**
   - Normalize input identifiers (DOI / arXiv ID / title)
   - Check the local state store and Zotero for existing copies
   - Query the web only when explicitly authorized (Crossref / OpenAlex / Semantic Scholar)
   - Return candidate list, match rationale, arXiv PDF availability, existing status
3. **Locate mode**
   - Papers: resolve Zotero item/attachment key first, then the relative path under `papers_root`
   - Technical documents: resolve the Vault relative path from the state mapping
   - Return the local path and local-link service URL; do not copy files by default

## Output
Candidate list (discovery) or local path + URL (locate).

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
