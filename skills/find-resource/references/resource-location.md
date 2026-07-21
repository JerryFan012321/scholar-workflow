# Resource Location

How to resolve an existing resource to a local path (locate mode).

## Papers

1. Resolve the Zotero item key via zotero-mcp: `search_library` by DOI / title+authors,
   confirmed with `get_item_details` (or from a `semantic_search` hit confirmed the same
   way). See `identity-policy.md` for the two-step check.
2. Read the item's attachment relations from `get_item_details` — that path is the
   authority for an imported PDF, queried live (there is no local cache).
3. A paper that has been downloaded but not yet ingested has only its `paper_inbox`
   path; it is not in Zotero yet, so the existence check returns `none`.

## Technical documents

1. Look up the resource in the state mapping by `resource_id`.
2. Read the recorded Vault relative path.

## Output

Return the resolved path and do not copy the file:

- For imported papers, the path from Zotero attachment relations (via zotero-mcp).
- For technical documents, the Vault-relative path — see shared
  `references/storage-policy.md` for which root holds what.

If a resource is not found via zotero-mcp or the state mapping, report it as missing
rather than guessing a path.
