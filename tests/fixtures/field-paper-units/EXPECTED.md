# Field paper-unit navigation: independent expectations

Prepared before implementation. This is a read-only navigation view of existing
paper packages, not a new bibliography, owner registry, analysis or migration.

## Selected corpus

Select Source A / Field A explicitly. Its provider declares local paper Alpha,
its analysis and Canvas, and a local sparse paper Beta. Its Field also references
Alpha's analysis for one purpose and an external Source B paper Gamma plus Gamma's
Canvas for two different purposes. Gamma belongs to Field B. Alpha and Gamma may
have the same display title; they must remain two paper units. Another local
Field and an undeclared similarly named file must not enter this view.

The result has exactly Alpha, Beta and Gamma, each once. Alpha retains local and
reference selection and its purpose. Gamma retains both external purposes and
its original owner/Field; no copied paper package appears. The files come only
from explicit primary/supporting/artifact ownership, not filename proximity.

## States and boundaries

- Missing declared Canvas stays visible as missing, with no open URI.
- A paper with no declared analysis says undeclared, not missing or completed.
- References to missing objects or non-paper core documents remain visible
  diagnostics. They must not silently vanish or become invented paper owners.
- A duplicate owner in another Source produces conflict and disables document
  links; a Source qualification must not hide that conflict.
- Disabled, unsafe, corrupt, unavailable or changing authority is not an empty
  library. Unknown Source/Field and unreadable selected provider refuse safely.
- Read-only registered Sources work; write capability is not a prerequisite.
- Subdirectory Sources use the containing reader Vault's full relative path in
  their URI. Cross-Source files use their own reader, not the caller's Vault.
- Without a unique reader mapping, retain the file and a reader-unavailable
  reason; do not fabricate a cross-Vault wikilink or a fake clickable URL.
- Paths, filenames and titles containing Markdown/URL delimiters cannot inject
  another link or table row. Missing/unsafe/symlinked/unsupported files have no URI.
- A native open URI is a read-only dispatch candidate, not observed GUI success;
  no app, CLI subprocess, network request, PDF download, lock or file write occurs.
- Every input file and registry/provider declaration remains byte-identical.

## Observable interface

Existing `knowledge list` defaults and schema stay unchanged. Opt-in
`knowledge list --paper-units --source-id SOURCE --field-id FIELD` emits this one
Field only. Both selectors are mandatory; selectors without the opt-in mode and
combining it with `--resolve-references` are input errors, not implicit scans.
Machine mode retains qualified identities and observed diagnostics; human mode
shows a compact paper table, file entries/status and full selection purposes,
without repeated IDs/hashes/absolute host paths or fake success claims.
Existing analysis declarations can use their artifact identity as a title. For
that exact machine-title case, human links use a readable role or filename while
JSON keeps the declared title and identity; custom human titles stay unchanged.

The fixed old `01-Paperlist.md` contract/writer is unchanged. This mode emits to
stdout only, never chooses a saved filename or overwrites a managed block.
