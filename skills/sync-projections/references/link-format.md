# Local Link Format

Projections link to files through the local-link service, never via hardcoded
absolute `file://` paths.

## URL shape

```
http://127.0.0.1:23128/open/paper/{zotero-item-key}
http://127.0.0.1:23128/open/document/{resource-id}
```

## Client rules

- Emit only opaque identifiers (Zotero key or Resource ID) in the URL.
- The service resolves the identifier to a file under `papers_root` or `vault_root`
  at open time; the projection stores the stable URL, not the resolved path.
- If a resource has no stable identifier yet, omit the link rather than writing a
  raw path.

The service binds to `127.0.0.1` only and refuses arbitrary file paths; its full
spec lives with the service implementation in `src/scholar_workflow/adapters/`.
