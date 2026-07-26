# Local Link Format

Projections link to files through the local-link service, never via hardcoded
absolute `file://` paths.

## URL shape

```
http://127.0.0.1:23128/open/paper/{attachment-key}
```

`{attachment-key}` is the Zotero **attachment** key (the storage folder name), not the
item key. Get it from zotero-mcp `get_item_details` (the PDF attachment's key).

## Client rules

- Emit only the opaque attachment key in the URL — never an item key, resource ID,
  or absolute path.
- The service resolves the key at open time by globbing
  `{storage_root}/{attachment-key}/*.pdf` (storage_root defaults to `~/Zotero/storage`);
  the projection stores the stable URL, not the resolved path, so switching machines
  or moving the storage folder never invalidates a link already written to the vault.
- If a paper has no PDF attachment yet, omit the PDF link rather than writing a raw path.

The service binds to `127.0.0.1` only. It validates the key against `[A-Z0-9]+` before
touching the filesystem (blocks path traversal), returns 200 + `application/pdf` inline on
a hit, 404 when the folder has no PDF, and 400 on a malformed/invalid key. Full spec lives
with the implementation in `src/scholar_workflow/adapters/local_links.py`.
