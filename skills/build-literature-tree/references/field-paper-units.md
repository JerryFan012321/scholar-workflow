# Existing Field Paper-Unit Navigation

Use this optional read-only view to navigate existing paper packages in one
explicitly selected registered Field. It is separate from the fixed bibliographic
`01-Paperlist.md` and the technical/challenge/evolution tree formats. It does not
replace those outputs, analyse papers, select a saved filename or create owners.

## Invocation and inputs

```sh
scholar-workflow knowledge list --paper-units \
  --source-id SOURCE_UUID --field-id FIELD_UUID --language en
scholar-workflow knowledge list --paper-units \
  --source-id SOURCE_UUID --field-id FIELD_UUID --format json
```

Both selectors are mandatory. Use ordinary `knowledge list --format json` to
inspect registered identities first. Do not select the first Field by default.
`--resolve-references` is a separate list mode and cannot be combined with
`--paper-units`. The default list and existing schemas/writers remain unchanged.
This feature is available from 0.43.0. Native navigation acceptance is separate
from installation and read-only contract checks.

The view derives from registered Field/provider declarations. Local papers come
from the selected Field's declared primary owners; contextual selections come
only from its explicit qualified references. A reference to a declared analysis
or Canvas resolves through its owner. Repeated references merge into one paper
unit while retaining every selection purpose. Equal display titles do not merge
different identities, and neighboring files do not establish a relation.

## Human result

Show the selected Field and read-only scope, followed by a compact table with:

| Column | Required content |
|---|---|
| Paper | Existing local paper-unit title; not a claim of fresh Zotero bibliography |
| Owning Field | Actual primary placement, not the referencing Field |
| Purpose in this Field | Local ownership and every declared contextual purpose |
| Material | Declared primary information note and current availability |
| Analysis | Every declared analysis Markdown entry or undeclared state |
| Canvas | Every declared editable Canvas entry or undeclared state |
| Notes | Declared reading/annotation notes with their titles and states |
| Status | Observed ownership/file limitations, distinct from source/GUI acceptance |

Retain other declared attachments in readable supplemental entries rather than
dropping them to fit the table. Missing files remain listed as missing. No declared
analysis means undeclared, not missing, failed or complete. Keep unresolved and
non-paper selections with their full purpose and explanation in a diagnostic
section; never invent a paper owner to fill the table. An empty, fully available
inventory explicitly says no paper units are selected. Unavailable authority is
not an empty library.

Human output uses one selected label language, escaped titles/purposes and honest
status wording. Qualified identities and technical diagnostics remain in JSON,
not repeated visible IDs, hashes or absolute host paths. If an existing supporting
title equals its object identity, show a readable role instead; retain custom
titles and the original JSON declaration. This view emits to stdout
only. Saving it later requires an explicit target and preserves human content;
do not overwrite the fixed ledger or paper companions as a side effect.

## Opening and completion boundary

For an available, uniquely owned Markdown/Canvas file with a unique containing
Obsidian reader mapping, the view may expose an encoded `obsidian://open` URI.
The URI includes the real reader Vault ID and path relative to that Vault, even
when the registered Source is a subdirectory or another Source owns the file.
No title-based or ambiguous cross-Vault wikilink is fabricated. Missing, unsafe,
conflicted, unsupported or unmapped files retain an unavailable reason instead
of a link. A URI is an open-request candidate, not observed reader behavior.

For an explicit revalidated native open, reuse:

```sh
scholar-workflow knowledge open OWNER_SOURCE_UUID 'source-relative/note.md'
```

Use the returned machine identity/path, not a title-derived path. The reader
only routes the window; registration and file checks still bound access.
Generating the list does not open any app, execute code, read paper bodies,
download PDFs or write a registry, lock, manifest, managed block or note.
Zotero remains the authority for bibliography/PDFs/formal annotations; this local
package view does not invent a PDF locator or refresh that bibliography.

Completion of this read-only view proves only the observed inventory/diagnostics
and formatting. Source support, installed behavior, link-click convenience and
native visual/editing assessment require their own evidence.
