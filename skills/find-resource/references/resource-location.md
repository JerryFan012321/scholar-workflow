# Resource Location

How to resolve an existing resource to a local path (locate mode).

## Papers

1. Resolve the Zotero item key (via DOI / arXiv ID / title match).
2. Read the attachment record to get the linked_file path.
3. The PDF lives under `papers_root`; return its path relative to that root.

## Technical documents

1. Look up the resource in the state mapping by `resource_id`.
2. Read the recorded Vault relative path.

## Output

Return two things, and do not copy the file:

- The local path (relative to `papers_root` or `vault_root` — see shared
  `references/storage-policy.md` for which root holds what).
- A local-link service URL (opaque Resource ID, not a raw file path).

If a resource is not found in either the state mapping or Zotero, report it as
missing rather than guessing a path.
