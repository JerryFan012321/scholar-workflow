---
name: find-resource
description: Search for papers, verify paper identity, recall related items from the Zotero library, or locate/open an existing resource. Use for 'find papers', 'search literature', 'where is this paper', '找论文', '搜索论文', '这篇论文在哪'. Read-only; not for importing or daily recommendations.
---

# find-resource

## Modes

- **Exact locate** — DOI, title/authors, or a known item.
- **Topic recall** — candidates from the existing Zotero library.
- **Discovery** — candidates from external metadata sources.

## Steps

1. Select the mode from the request.
2. For exact locate, run `scholar-workflow zotero search "<query>" --fulltext`, then
   confirm candidates with `scholar-workflow zotero get <item-key> --children`.
   Apply the identity outcomes from `identity-policy.md`: `exact`, `conflict`, or
   `none`. A conflict is reported with item keys and is never merged here.
3. For topic recall, run the same full-text search and rank the returned candidates.
   Fuzzy relevance never establishes paper identity; confirm exact matches before reuse.
4. For discovery, query paper metadata sources, normalize identifiers, and run the exact
   Zotero existence check before reporting library status.
5. Return:
   - locate: Zotero item key plus attachment key/local-link URL or Vault-relative path;
   - recall/discovery: candidate list with rationale, arXiv-PDF availability, and
     existing/not-found/conflict status.

## Constraints

- Read-only: this skill creates no library item and copies no file.
- Zotero Local API is authoritative for existing metadata and existence. Exit 3 means
  unavailable, not `none`; start/enable Zotero Local API and retry.
- External services provide metadata only. Paper PDFs may come only from arXiv.
- Use DOI, then normalized title+authors, for identity; arXiv id is not the canonical
  library identity.

## References

- `references/resource-location.md`
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
