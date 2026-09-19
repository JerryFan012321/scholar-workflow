# Resource Location

How to resolve an existing resource to a local path (locate mode).

## Papers

1. Resolve the Zotero item key with `scholar-workflow zotero search` by DOI or
   title+authors, then confirm it with `scholar-workflow zotero get <key> --children`.
   See `identity-policy.md` for the exact check.
2. Read the item's child attachment record from the `get --children` result. Its key is
   the stable input for the local-link service; data is queried live with no local cache.
3. A paper that has been downloaded but not yet ingested has only its `paper_inbox`
   path; it is not in Zotero yet, so the existence check returns `none`.

## Technical documents

1. Look up the resource in the state mapping by `resource_id`.
2. Read the recorded Vault relative path.

## Output

Return the resolved path and do not copy the file:

- For imported papers, the child attachment key and its local-link URL.
- For technical documents, the Vault-relative path — see shared
  `references/storage-policy.md` for which root holds what.

If a resource is not found via the Local API or the state mapping, report it as missing
rather than guessing a path.
