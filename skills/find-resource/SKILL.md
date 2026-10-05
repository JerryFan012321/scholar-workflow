---
name: find-resource
description: Search for papers, verify paper identity, recall related items from the Zotero library, or locate/open an existing resource. Use for 'find papers', 'search literature', 'where is this paper', '找论文', '搜索论文', '这篇论文在哪'. Read-only; not for importing or daily recommendations.
---

# find-resource

## Results

- **Exact locate:** confirmed Zotero item key, attachment key and runtime direct action or
  stable attachment-key URI,
  or registered Vault-relative path; report `none` or conflicting item keys explicitly.
- **Topic recall:** candidates from the existing Zotero library with observable title,
  abstract or indexed-text match signals and the stated basis of any ordering.
- **Discovery:** external metadata candidates with normalized identifiers, arXiv-PDF
  availability and `existing | not-found | conflict` Zotero status.
- **Requested open:** use the chosen native reader or cmux destination without copying
  the source. Report launch acceptance separately from an observed reader display.

## Source and identity boundary

Use `scholar-workflow zotero search "<query>" --fulltext` for existing-library recall;
confirm identity and child attachment with `scholar-workflow zotero get <item-key> --children`.
External discovery sources supply metadata only. Apply the exact existence outcomes in
`identity-policy.md` before claiming an item is present or absent. Fuzzy relevance is a
candidate signal, never identity proof.

## Constraints

- Read-only: this skill creates no library item and copies no file.
- Zotero Local API is authoritative for existing metadata and existence. Exit 3 means
  unavailable, not `none`; do not report absence from an unavailable provider.
- Follow the shared source and identity policies for external metadata and exact matches.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `references/resource-location.md` — locate a resource or open it in a requested native reader/cmux location.
- `${CLAUDE_PLUGIN_ROOT}/references/identity-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
