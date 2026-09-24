# Stable PDF Link Format

Persistent projections link to a Zotero attachment identity, never to a Hub port,
absolute `file://` path, storage-directory guess, or process-local action ID.

## Human-readable URI

```text
zotero://open-pdf/library/items/{attachment-key}
```

`{attachment-key}` is the Zotero **attachment** key, not the parent item key or a
storage-folder name. Resolve it from the parent/child relationship returned by Zotero
Local API. If a paper has no PDF attachment, omit the PDF action rather than inventing
a path or URL.

ZotFlow-managed notes may use its own registered action protocol:

```text
obsidian://zotflow?type=open-attachment&...
```

Only ZotFlow writes those links. Scholar-generated general Markdown uses the Zotero URI.

## Machine identity

Machine relations store a `PdfRef`, not either display URI:

```text
PdfRef {
  provider: "zotero",
  library_id,
  attachment_key,
  content_hash
}
```

Hub resolves that reference to a direct, pre-registered action at runtime. Its dynamic
loopback origin and opaque action ID are temporary and must never be persisted.

## Legacy links

Legacy fixed-port `/open/paper/<attachment-key>` URLs are read-only migration input.
Do not emit it in a new or rebuilt projection. Rewrite existing occurrences only inside
an approved per-Field migration transaction; do not perform a cross-Vault bulk replace.
