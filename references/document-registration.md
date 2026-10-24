# Selected official webpage ownership and source snapshot

Use for a user-selected official webpage/blog with a real Zotero `webpage` or
`blogPost` bibliographic item and no paper PDF. This branch registers the authorized
original text as a Knowledge resource; it is not paper ingestion, a PDF substitute,
an analysis, or permission to archive unrelated pages. Source acquisition and reuse
follow `source-policy.md`; source/field lookup follows `asset-management.md` and
`knowledge-registration.md`.

## Inputs and observable result

The inputs are the selected writable Source/Field, exact Zotero item key, persistent
folder segment, presentation language, a UTF-8 Markdown source snapshot, original
URL and ISO retrieval time. Confirm the item and ordered creators through the Local
API. Zotero owns the bibliography; the selected Source owns the snapshot. A matching
title, standalone HTML download or manually invented provider does not establish
registered ownership.

Prepare the snapshot from the chosen first-party source, with readable source title,
attribution and source URL, and explicit block anchors for the original passages
that analysis will reference. Preserve source language, conditions, figures/media
entries and known extraction gaps. Keep translations, analysis and inferred method
details out of the original passages. Record actual retrieval time separately from
publication/last-modified dates; do not label a current page a historical original.
Archiving or possessing bytes does not grant an open license or redistribution right.

Successful registration creates Field-local `resources/<segment>/Source.md`, its
explicit resource declaration and navigation/provider records. The portable
resource declaration binds `markdown_path` and `markdown_sha256` to the complete
snapshot bytes. The provider catalog retains the original URL in `identifiers.url`;
the approved plan and private journal retain `retrieved_at`, not a new portable
manifest field. These are source-capture declarations: the CLI does not fetch the
remote page or prove that the submitted text faithfully represents it. Keep the
actual first-party source comparison distinct from registration success.
The returned atomic `resource_id` is also the `artifact_id` used by `vault_markdown`
source spans referring to this document; the analysis and Canvas have their own supporting-artifact IDs.
Do not invent a second source artifact ID, PDF attachment key or page number.
Keep machine hashes/revisions in metadata and receipts rather than the source prose.

## Installed plan and registration

Check that the normally installed CLI provides both commands and inspect their help.
In a supporting runtime:

```sh
scholar-workflow knowledge document-plan \
  --source-id SOURCE_UUID --field-id FIELD_UUID --item-key WEBPAGE_KEY \
  --segment stable-source-segment --language en \
  --markdown SNAPSHOT.md --source-url https://official.example/article/ \
  --retrieved-at 2026-01-01T12:00:00Z
```

The URL, time and paths above are placeholders for the chosen source, not reusable
source facts. The zero-write plan binds the submitted snapshot bytes, live Zotero
identity and the actual Source/Field/provider/manifest revisions to its confirmation
digest. Review the new folder, snapshot, declared identity and navigation. Keep
saved plans outside the selected Source so recording a plan does not change its
reviewed file set. Use `--format json` for the separate machine record.

Repeat the same arguments with `knowledge register-document` and
`--approved-digest HEX_DIGEST`. Confirm the exact plan; `--yes` skips only the
prompt after that digest has been reviewed. A stale digest or changed input requires
a new plan, not acceptance of different bytes. Source initialization remains the
separate knowledge-registration operation; a missing historical provider is unknown,
not an empty inventory to fabricate.

An existing folder, resource or conflicting identity is not adopted, overwritten or
renamed automatically. Cross-Source duplicate ownership, wrong item type, changed
source URL/content, unavailable roots, traversal and symlinks stop registration.
This entry does not refresh an old snapshot, migrate an analysis or move a source.
Report the exact conflict and retain current content.

## Recovery and analysis handoff

The operation coordinates Source.md, declarations and provider state through CAS and
a persistent recovery journal. It is a recoverable logical transaction, not one
filesystem-wide atomic write. After interruption, repeat the exact approved request;
continue only when every member is still its recorded before or after value. A
concurrent edit, root rebind or changed source/input refuses continuation. Retain
the journal for explicit recovery; never delete it, rewrite an owner or overwrite
human content to force success. A recovery snapshot is not a verified backup.

Read back the registration receipt and current owner before analysis. Use its
resource ID, Source-relative `Source.md` path, block IDs and bound content hash.
Each source-backed v5 record uses `vault_markdown` spans resolving to those exact
blocks. Zotero's webpage URL remains a bibliography/source URL, not a fabricated
`zotero://open-pdf` route. The v5 source and quotation interface is owned by
`skills/analyze-paper/references/analysis-v5-format.md`.

The analysis Markdown, editable Canvas and sidecar stay beside Source.md in the
same resource folder. Use ordinary installed batch staging, conformance,
`analysis commit-bundle` and explicit provider apply with current revisions.
Registration is not an analysis commit receipt. Preserve all five output branches;
undisclosed technical or experimental content stays absent rather than being filled
from a predecessor, related paper or third-party explanation. The analysis identifies
its actual webpage scope instead of claiming a complete technical-paper analysis.

For copyright/permission-limited excerpt display, follow only the versioned
quotation-omission interface in `skills/analyze-paper/references/analysis-v5-format.md`.
Source verification and the shared source policy remain separate requirements.

Webpage figures/media retain their actual source, ownership and reuse limits. The
existing PDF-backed `canvas_image` field is not a webpage-media interface: do not
invent a PDF span to fit it. Report unsupported image projection; the editable
text tree and its source-block links remain required. Original-text registration,
analysis conformance, semantic support, native links and human readability are
separate results, and only actual receipts/checks may be reported as completed.
