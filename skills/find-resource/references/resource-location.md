# Resource Location

How to resolve an existing resource to a local path (locate mode).

## Papers

1. Resolve the Zotero item key with `scholar-workflow locate <identifier>` (exact,
   read-only), or from a catalog semantic hit confirmed by `locate`.
2. Read the item's attachment relations via the Zotero Local API — that path is the
   authority for an imported PDF. The cache never holds the authoritative location.
3. A paper that has been downloaded but not yet imported has only its `paper_inbox`
   path; it is not in Zotero yet, so `locate` returns `none`.

## Technical documents

1. Look up the resource in the state mapping by `resource_id`.
2. Read the recorded Vault relative path.

## Output

Return the resolved path and do not copy the file:

- For imported papers, the path from Zotero attachment relations (Local API).
- For technical documents, the Vault-relative path — see shared
  `references/storage-policy.md` for which root holds what.

If a resource is not found via the Local API or the state mapping, report it as
missing rather than guessing a path.
