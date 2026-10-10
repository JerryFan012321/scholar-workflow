# Field paper-unit assets: independent expectations

Prepared before production implementation and test execution. These expectations
extend the existing `EXPECTED.md` inventory; they do not define another owner,
registry, knowledge schema, tool dispatcher, analysis, or content validator.

## Explicit selected inventory

The synthetic Source A / Field A still selects exactly local Alpha, sparse Beta,
and referenced external Gamma in Source B / Field B. Alpha and Gamma retain the
same display title and their original primary ownership. Existing primary,
analysis Markdown, Canvas, purposes, and encoded native reader candidates remain.

Each fixture provider explicitly declares its paper's analysis Markdown, Canvas,
and optional sidecar artifacts. Asset input uses the existing `HubAsset` fields:
`asset_id`, `owner_artifact_ids`, `vault_path`, `display_name`, `media_type`, `size`,
`sha256`, and `role`. No new asset identity or relation format is introduced.

Source A's portable `.scholar-workflow/assets.yml` declares for Alpha:

| Asset | Explicit owner | Role |
| --- | --- | --- |
| Figure image | Alpha analysis | embed |
| Measurement data | Alpha analysis | data |
| Appendix binary | Alpha Canvas | supplement |
| Source-region text | Alpha analysis | source |
| Shared image | Alpha analysis and Canvas | embed |
| Sidecar-associated data | Alpha provider sidecar | data |
| Legacy attachment | Alpha analysis, at Source-level `attachments/` | supplement |

Source B's manifest declares a same-named figure and external data for Gamma.
They remain Gamma supplements and use Source B's root and declarations. The view
must not inspect the same relative path in Source A for an external asset. Every
asset attached to any provider-declared artifact of the selected paper remains
in that paper's existing `files` list. The shared image occurs once per paper,
even when two artifacts and repeated Field references select it. Assets are
supplements and never become paper owners, primary documents, or Field entries.

A manifest-declared asset owned only by another Field's paper is excluded. An
undeclared neighboring file, equal display title, directory proximity, and a
Markdown embed are never relationship authority. A source must not borrow an
artifact ID from another Source merely because its text matches.

Existing `snapshot.catalog.assets` declarations remain usable. The resulting
supplements include catalog-only and portable-only declarations. A consistent
asset declared in both inputs appears once, including its multi-owner relation.
Owner-list order is not part of that relation: the same owner set in a different
order is still a consistent declaration. A file explicitly shared by artifacts
of two selected papers appears once under each paper without acquiring a new
primary owner. The same asset ID in two Sources is qualified by its owning Source
and cannot cause a cross-Source merge.

Conflicting declarations are not resolved by taking the first row, preferring
the catalog, or preferring the portable manifest. Conflicting IDs, paths, or owner
relations are excluded from executable navigation and reported as an incomplete
asset declaration. In this supplemental file-list format, neither conflicting
choice is emitted as the selected file; independently unambiguous assets remain.

## Availability and safe opening

- Images, data, source text, and binary supplements remain visible with their
  declared display name and relative path. Under the existing native capability
  contract they have `file_state=available`, `open_state=unsupported_type`, and
  no URI. That supported inventory result may be complete; it does not claim
  that the asset was opened or its contents verified.
- Missing assets retain their identity, declared name, and path with
  `file_state=missing`, `open_state=file_unavailable`, and no URI. The result is
  partial. One missing asset must not remove another valid supplement.
- Symlink leaves, symlink parents, directories, and special files are unsafe
  assets. They remain accounted for without following targets, reading bodies,
  blocking on a FIFO, or exposing a URI. The result is partial.
- A file replaced during inspection is reported as changed and unavailable,
  even when the replacement has the same bytes. No stale open candidate survives.
- An explicitly related Markdown supplement may reuse the existing safe native
  Markdown action. It remains an asset supplement, uses its owning Source's
  containing Vault and encoded path, and requires all ordinary ownership, safe
  metadata, reader, and completion checks. A changed or conflicted declaration
  or changed file disables that candidate; its suffix alone grants no authority.

## Declaration diagnostics

`assets.yml` is optional. A stable absent file means no additional portable
assets, preserves any catalog assets, and leaves existing complete fixtures
complete. A valid empty manifest has the same additive meaning.

A present malformed, unsupported-schema, invalid-entry, duplicate, oversized,
non-regular, symlinked, or unreadable manifest is an observed declaration
problem, not an empty successful asset inventory. Return a partial result and
an asset-specific diagnostic qualified by its Source. Keep paper units and
usable provider document navigation; never invent omitted asset identities or
relationships from nearby bytes. When valid asset entries can be independently
retained, retain them with the diagnostic rather than silently dropping them.

Manifest replacement or modification during inspection is diagnosed even if
the manifest's final bytes equal the first read. A manifest that appears after
being observed absent is also changed. Any previously observed asset relations
from a changed declaration remain explicitly incomplete and have no URI; the
query must not claim a complete inventory from mixed revisions.

## Human and command result

The opt-in CLI JSON envelope remains schema 1 with exactly the original selected
paper units and supplemental `files` entries. Human output in either selected
language accounts for each supplement by readable filename and honest available,
unsupported, missing, or unsafe wording. It does not expose IDs, hashes, absolute
host paths, fake Markdown links, or GUI/content-acceptance claims. The existing
analysis/Canvas native candidates remain readable and correctly encoded.

The ordinary Field list retains its existing envelope and does not acquire asset
or provider bodies. The paper-unit query emits stdout only and performs no
network request, subprocess, GUI dispatch, lock, registration, file write, asset
body/image read, or byte hashing. Declared size/hash values are metadata, not
integrity or scientific-support evidence. Synthetic byte preservation and exact
declaration/body I/O guards verify this boundary; real Vaults, Zotero, installs,
releases, services, and native visual acceptance are outside these tests.
