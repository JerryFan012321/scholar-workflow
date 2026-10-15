# Paper Acquisition and Index Delivery

Use this contract when a request combines paper acquisition with selected knowledge
registration or index maintenance. It describes observable delivery, not a new
manifest, state service or mandatory sequence of research reasoning. An import-only
request does not authorize creating a Field, writing an index or synchronizing Notion.

## Separate completion evidence

| Requested result | Evidence needed before reporting it complete |
|---|---|
| Zotero bibliography | A created/reused item key confirmed through Local API under the shared identity policy |
| PDF | The selected attachment belongs to that item; its declared local file is available. Metadata-only or missing-PDF outcomes keep their reason |
| Selected collection | A read-back of the item's memberships includes the user's chosen collection; preserve other memberships |
| Knowledge paper unit | `paper-registration.md` confirms its owner and selected files; an ordinary Markdown page or ZotFlow Source Note is not owner registration |
| Selected reading index | Read-back of the actual selected file contains the affected papers with their current identities, valid available-material links and honest gaps, in its existing format |

Report only the results the user requested, and distinguish completed, pending,
failed and not-requested parts in ordinary language. A successful Zotero ingest
receipt cannot establish collection membership, a Knowledge owner, index freshness
or a generated Source Note by itself. Missing projected keys mean **not linked**,
not **not in Zotero**. Zotero full-text indexing is separate from bibliography/PDF
availability; a reading URI is not observed reader success or scientific verification.

## Finishing selected material

Reuse confirmed item and attachment identities. After a requested acquisition,
finish the explicitly selected registration/index operations before reporting that
combined task complete. If an index write fails, retain the successful import
outcome and retry only the unfinished operation against fresh file bytes; do not
create another Zotero item or upload another PDF to repair a reading list.

Use the existing index owner and format. Legacy managed-block indexes follow
`skills/sync-projections/references/obsidian-index-format.md`; a current Field ledger
follows `skills/build-literature-tree/references/field-library-format.md` through
that skill, not the legacy nine-column renderer. Preserve the corpus, human text,
selected navigation and unrelated views under that format's update protections.
Resolve links by declared identity/ownership, not similar titles or directory names.
Link existing analyses/Canvases with their actual state; unavailable or unregistered
material stays explicitly missing/pending rather than gaining a placeholder file.

Collection selection, Source initialization, identity conflicts and existing-content
conflicts keep their own approval boundaries in `security-policy.md` and the owning
workflow. ZotFlow owns its Source Notes; link an existing note only after checking
its Zotero identity, and leave absent/unsynchronized notes visible without writing
into that writer's files. Existing Zotero/library data and manifests remain the
authorities described in `storage-policy.md`; this delivery summary owns none of them.
