# Knowledge exploration

Load [Vault connections](vault-connections.md) for explicit test/personal runtime
boundaries and **Add Vault/folder**. Read-only host connections are separate from
research edits; connection and inspection never rewrite paper packages.

## Ownership and outputs

The selected folder owns one `.scholar-workflow/exploration.yml` file. It contains
research positioning and explicit references around existing knowledge units.
Paper Markdown, Canvas, sidecars, archived originals and images are read-only to
this capability. The exploration layer does not create another Zotero identity,
Knowledge Source registry or copy of a paper's analysis.

The browser and CLI share this file and its validation rules. A later request
reloads external edits; saves compare the current SHA-256 revision and refuse
stale writes. This is one-file publication, not a transaction over referenced
content. Use the same folder for both entrypoints so they read the same state.
Revision checks do not supply historical version storage or an undo stack.
Each file read also checks the same descriptor's size and stat before and after
reading. A changing or incomplete read refuses rather than presenting conditions
and results assembled from different external edits.

## Atomic paper-unit boundary

A paper unit is the smallest independently organized, navigable and compared
paper object. It is the existing formally identified literature resource and all
its explicitly associated assets, not a newly invented `work` title card. Reuse
the owner allocation and source identity in `paper-registration.md`; the
exploration layer does not allocate a second primary owner or bibliographic item.

This is an organization boundary, not a ban on finer evidence addressing. The
unit owns the resource identity and the declared asset inventory; its files and
internal anchors are addressable parts. Positioning, conditional results,
assessments and inter-unit edges are outer records referring to that identity,
not new paper units. A directory, one PDF, an analysis file or a model name alone
does not establish another paper. Renaming or moving a registered unit must use
the existing identity/location operation, not a fresh title card. A different
resource version is not silently substituted for an evidence-bearing source.

One unit may have many dimension assignments, conditional research records and
topic references while remaining one result and one graph node. Companion notes,
analysis prose, Canvas, annotations, figures, excerpts and supporting code/model/
data references stay assets of that unit, never paper-shaped peer nodes. Claims
and evidence retain precise internal anchors; atomic organization does not make
the underlying evidence unaddressable. Comparisons and relationships reference
units and their evidence, rather than detaching a convenient fragment as a paper.

The UI references existing paper units from an explicitly selected registered
Source/Field. It imports their complete declared asset inventory, not a hand-picked
subset of files. It may edit outer positioning, condition records and assessments;
maintaining the owned paper package remains the responsibility of its existing
operations. Asset counts and repeatable method branches are not fixed quotas.
Missing assets remain diagnosed, not grounds to discard the unit or invent content.

`entity_ref` is required for paper-kind entries and retains the qualified owner
reference. Uniqueness/shape validation alone does not prove current ownership,
inventory completeness, source validity or scientific support: those require the
existing provider/ownership read and their separate evidence. Unresolved ownership
refuses reference creation; a later unavailable source must not be silently
replaced with a guessed same-title file. Names, directories, views and Field
membership are not bibliographic identities. Migration or identity conflict uses
the existing explicit resolution operation, not a new explorer object.
Import refuses a qualified paper identity already occupied by a non-paper kind;
it does not merge the inventories or silently relabel the existing object.
Current owner and local-reader checks do not provide historical versions of the
complete package. The outer manifest is not a content-addressed archive, and
different bibliographic IDs are not automatically merged into a research family.

Other complete resources retain their real `webpage`, `report`, `book` or `other`
kind. Do not relabel a blog as a paper or use these kinds to turn an annotation,
image or extracted paragraph into an independent research unit. Author reports,
independent evaluation and local reproduction remain separate conditional records;
one reproduction result does not overwrite the author's report.

Readable output contains research positioning, all declared assets, conditions
beside results, assessment boundaries and evidence-linked work relations. Keep
machine IDs/revisions in structured interfaces rather than making them reading
requirements. Empty, missing and unverified entries remain explicit.

## Commands

```sh
# Open in cmux when running there; otherwise use the normal browser.
scholar-workflow knowledge explore --root /path/to/selected/folder
# Keep the service in this terminal without opening a window.
scholar-workflow knowledge explore --root /path/to/selected/folder --no-open
# Read current packages from an explicit registered Source/Field without saving.
scholar-workflow knowledge explore --root /path/to/containing/vault --source-id SOURCE --field-id FIELD

# Explicit first creation; an omitted spec uses four editable empty dimensions.
scholar-workflow knowledge exploration-init --root /path/to/selected/folder --spec model.yml
# Preview existing registered paper-unit references; no paper is rewritten.
scholar-workflow knowledge exploration-import --root /path/to/selected/folder --source-id SOURCE --field-id FIELD
# Apply that reference selection against the displayed revision ('absent' for first creation).
scholar-workflow knowledge exploration-import --root /path/to/selected/folder --source-id SOURCE --field-id FIELD --apply --expected-revision REV
# Save a complete replacement model against its actual current revision.
scholar-workflow knowledge exploration-apply --root /path/to/selected/folder --spec model.yml --expected-revision sha256:CURRENT_HASH
# Read-only query and Markdown export.
scholar-workflow knowledge exploration-query --root /path/to/selected/folder --selection query.yml
scholar-workflow knowledge exploration-export --root /path/to/selected/folder
```

`init` refuses an existing manifest. The `init`/`apply` JSON result includes the
current `revision` and `data`; the browser also loads them from `/api/state`.
Generic `init`/`apply` cannot introduce a paper identity or add, remove or replace
its assets. Use `exploration-import` to reference actual registered units and
refresh their declared inventory; use the existing owner operations to maintain
the package itself. Existing outer attributes, records and assessments remain
editable. A schema-valid spec is not evidence of a formally owned paper unit.
Query without `--selection` returns the default selection. A missing manifest is
an empty in-memory model, not implicit file creation. Export prints only to
stdout: put an explicitly requested independent navigation document in the
chosen folder so relative asset links retain their meaning. Do not redirect or
insert the export into an existing paper unit.

`explore` defaults to port 0 (OS-selected), prints a session URL and stops on
Ctrl-C. A token in that URL authorizes only this local explorer session and
expires with the process. Share neither the token nor the full session URL.
`--port` selects an explicit local port when needed; no fixed port is required.
Browser requests do not accept a root path, command or model configuration.

Supplying both Source/Field selectors opens a live, read-only projection of that
Field's owned paper packages. It writes no exploration manifest or owned asset.
The provider reports local declaration readability separately from global owner
uniqueness. An otherwise checked local package may remain readable when only
other Sources' declarations are unavailable; its global `incomplete` status stays
visible. Known conflicts, unsafe/local changed declarations and unsafe files are
not bypassed. Unresolved cross-Source references remain diagnostics, not guessed
nodes. This projection cannot save, prepare new references, edit records or grant
PDF-reader approval; normal import/ownership and local-only reader gates remain
unchanged. Local Markdown, figures and Canvas navigation use the same declared
files, never an analysis copy. Repeated reads recheck the live provider.

The local adapter provides `GET /api/state`, `POST /api/query`, `POST /api/save`,
`GET /api/assets/{work_id}`, declared-file content at
`GET /api/asset/{work_id}/{asset_id}` and `POST /api/open` with only
`work_id`/`asset_id`. Queries may include a complete `_draft` model for validated
in-memory preview; this does not save it. Saving submits `data` and its last
loaded revision as `expected_revision`. A conflict returns HTTP 409 with no overwrite.

Markdown uses `GET /api/preview/{work_id}/{asset_id}`: `text` and its
`document_revision` come from the same bounded file read. Each supported inline
link retains its label and whole-text UTF-16 `start`/`end` offsets. Web entries
carry their HTTP(S) URI; native entries carry only an opaque session `link_id`.
Prepare a native link through `GET /api/reading-link/{link_id}`, then submit
`POST /api/open-link` with only `link_id`. These IDs address internal assets or
source locations; they are not new works, persisted knowledge or owner identities.

The same response includes `images`, with whole-text UTF-16 positions, labels
and either a session `media_id` or an unavailable reason. Retrieve a valid image
through authenticated `GET /api/preview-media/{media_id}`; this does not accept
a path or remote URL. Media actions remain internal to the paper unit.

Whole-unit selection uses authenticated `GET /api/unit-fields`,
`POST /api/unit-options` with only `source_id`/`field_id`, and
`POST /api/unit-reference` with `data`, those selectors, and selected qualified
`unit_refs` (`source_id`/`object_id`). The last operation returns proposed `data`
without saving. It rereads the actual registered inventory and references every
declared file of each selected unit, not a browser-provided file subset. Unknown,
duplicate or conflicting selections refuse. Browser selection never accepts a
root path and never registers a new Source or paper.

Saving a new paper or changed paper inventory also requires the complete proposal
confirmed by that session's real unit-reference operation. Direct save requests
cannot substitute an invented owner, a selected-file fragment or extra assets.
Session receipts only authorize the proposed reference; they are not a second
ownership registry or knowledge source. Reopening an unsaved draft requires
reselecting its new units. Draft previews enforce the same confirmed-unit boundary;
schema-valid but unconfirmed paper fragments cannot appear as preview nodes.

Paper editors preserve kind and owner reference; the owned asset list is read-only
there. Outer editing forms validate a candidate copy through the shared query
core before adopting it. On incompatibility, retain the original draft, filter,
form and input rather than publishing invalid state or closing the form.
The shared save core also rejects retargeting/rekeying an existing paper, changing
its kind or dropping/replacing an existing asset location. This protection is not
only a disabled UI control. Removing an entire outer unit reference does not
delete any original asset. A real ownership/location reconciliation remains a
separate explicit operation; this editor does not migrate the unit.

New records prefer an explicitly chosen or currently selected unit. Without one,
only the unique match of the completed current query may be suggested; a pending
query or ambiguous result requires an explicit choice, never the first library
entry. A new relationship may suggest that start, but its other endpoint requires
selection. Editing an existing record/relation preserves its declared endpoints.
When a selected unit is removed from the outer manifest, clear its old detail
panel and actions without deleting the source. A successful query clears its own
previous query error, not unrelated save-conflict or external-change warnings.

Invalid input exits 2; stale revisions or an existing initialization exit 5.
Report native opening separately: a successful URL open is not evidence that
Obsidian, ZotFlow or a PDF reader displayed the requested asset.

## File schema

`schema_version` is integer `1`; the only top-level lists are `dimensions`,
`works`, `records`, `edges` and `views`. Unknown fields are rejected. IDs are
stable strings containing letters/digits plus `.`, `_`, `:`, `-`; human labels
can be changed without reallocating identity.

| List | Fields |
|---|---|
| `dimensions` | `id`, `label`, `kind`, `multiple`, `scope`, `values`, `sortable`; optional `unit`, `description` |
| `works` | `id`, `title`, `kind`, `attributes`, `assets`; optional `year`, `summary`, `entity_ref`, `asset_diagnostics` |
| `records` | `id`, `work_id`, `dimensions`, `conditions`, `result`, `evidence`, `assessment`, `origin` |
| `edges` | `id`, `from_id`, `to_id`, `kind`, `label`, `evidence`, `explanation` |
| `views` | `id`, `title`, `query` |

Dimension `kind` is `enum`, `reference`, `text`, `number` or `date`. `scope` is
`work` or `record`; multiplicity determines scalar versus list values. Dates use
`YYYY-MM-DD`; numbers must be finite. Enum/reference `values` contain `id`,
`label` and optional `parent_id`; parent references must exist and be acyclic.
Reference values resolve to declared options or work IDs. The parent hierarchy
is retained but does not implicitly expand a filter to all descendants.
Only reference dimensions resolve a work ID to its title during readable export;
a text value equal to a work ID remains the original text.

Initial `foundation`, `paradigm`, `problem` and `task` definitions are editable
record-scoped, multiple enum dimensions. They are not the only permitted
dimensions. A measured value belongs to a condition-specific record when its
meaning depends on task, data, hardware or budget. Defining a dimension does not
invent values for works or past records.

Work `kind` is `paper`, `webpage`, `report`, `book` or `other`. `attributes` holds
only work-scoped assignments. Each asset has a globally unique `id`, readable
`label`, `kind` and `uri`. Registration is explicit: filenames and title matches
do not prove that a file belongs to this work.

An `entity_ref`, required for papers, retains `source_id` and `object_id` from an existing
Knowledge owner. `exploration-import` reads the existing registered Field's public
paper-unit inventory and the host's declared Source roots. It reuses these identities
and preserves human work labels/attributes/records, adding only missing explicit
asset references. Existing conflicting URIs refuse instead of silently replacing
them. Local root-relative preview requires an actual registered-root mapping;
cross-root references retain their public native URI. Unresolved ownership or missing
locators are reported rather than inferred or omitted. It does not register a Source,
copy a paper or repair a formal library. The default import is a zero-write preview.
For an exploration root inside a registered Source, map the declared Source-relative
asset into that root before deciding whether it is external. Do not require the
Source and exploration roots to be identical or follow a target symlink to make
it appear local.

The same qualified provider resource supplies explicitly registered original-page,
DOI and arXiv links. The import reads only known Zotero parent items and their
paginated children through the Local API; it does not scan the library, read PDF
content, download cloud attachments or request write authorization. Native item,
PDF, note and child-attachment links require confirmed parent/library identities.
Without Zotero, registered files and web links remain usable and
`asset_diagnostics` retains the missing verification in the interface/export.
Refreshing references updates these provider diagnostics, not human research
judgments. Code/model/data pages still require explicit links; their ownership is
not inferred from prose, title similarity or a guessed repository URL.

A record represents one actual joint setup, with record-scoped assignments in
`dimensions`, string-key/string-value `conditions`, readable `result` and
`assessment`, and evidence asset IDs. `origin` is `author`, `independent`,
`local` or `analysis`. Recording an experiment citation does not run or copy it.
No evidence entry means evidence was not supplied, not that a claim is verified.

Edge endpoints are work IDs; evidence contains at least one existing asset ID.
`extends`, `borrows`, `fuses` and `context` use an explicit `from_id → to_id`
direction described by their label/explanation; `competes` is symmetric. The
direction follows the declared meaning, never publication dates alone. A valid
edge shape checks references, not scientific support. Preserve unknown or
contested relationships as such rather than silently asserting a lineage.

## Query and comparison

```yaml
filters:
  foundation: {mode: any, values: [base-a]}
  task: {mode: all, values: [task-a, task-b]}
sort_by: year
descending: false
include_context: true
```

Optional `text` matches work titles/summaries. Filters combine across dimensions;
within one dimension, `any` means at least one selected value and `all` means all
selected values. Work-scoped constraints match the corresponding work, while
all record-scoped constraints must match one and the same record. A work with
B1/T1 and B2/T2 records does not match B1/T2.

The result contains `works`, matched `records`, `edges` and
`context_work_ids`. With context enabled, immediate connected works can appear
as context; they are not query matches. Saved views retain query definitions,
not another authoritative result list. A visual card move changes layout only;
semantic classification changes require editing assignments or relationships.

`title`, `year` or an explicitly sortable single-value text/number/date dimension
can order results. Missing values stay last, not zero. Enum/reference values
have no implied ranking; multiple-value dimensions cannot be sorted without a
separate comparison. Conflicting sort values across a work's matched records
require a narrower query. Ordering is not a declaration of scientific superiority.

Keep comparison conditions and results together. State shared conditions,
the differences being compared and known unaligned/unknown conditions. Preserve
author claims separately from local reproduction or analysis; incomplete
conditions can be read side by side without claiming a fair ranking. This
capability stores these declarations; it does not automatically certify a
benchmark protocol or compute a universal quality score.

## Asset navigation and opening

Assets may use root-relative files or `https`, `http`, `obsidian`, `zotero` URIs.
Local paths reject absolute paths, `..`, backslash aliases and symlink traversal.
Keep every declared asset in the returned list; missing/unreadable/unsafe local
files carry diagnostics. External links are not remotely checked, so display
them as unverified rather than implying availability from an HTTP-looking URI.

Include explicitly known original pages/PDF entries, information/analysis notes,
Canvas, annotation/reading/source notes, code/model/data pages and related
experiment reports. No category requires an invented placeholder or copy.
Root-external local resources use their existing supported native URI; do not
expand the selected root to arbitrary files or embed absolute file paths.

The browser resolves local file content through a declared asset ID. Native URI
links open their registered application; a Canvas opens in its native application
rather than presenting its raw JSON as a graph preview.
External websites open in a browser. Underlying tool availability and permissions
remain independent. Native PDF annotation authority and local-only ZotFlow
requirements retain their existing contracts.

An external URI being declared is not proof that its reader is ready. For Zotero
PDF and ZotFlow reading actions, loading the saved unit's asset list rechecks its
current provider owner, parent/attachment/library identities, Local API locator
and actual local PDF digest. The session remembers that check without changing
the knowledge manifest. Opening requires that snapshot and repeats verification;
changed identity, Source registration or PDF bytes refuse until the list is
refreshed. Native launch preserves the registered page/annotation URI.
ZotFlow also requires the selected Source's exact containing Vault and the shared
adapter's live local-storage/compatibility proof. No secret configuration or cloud
PDF fallback is used; see `security-policy.md` for that authority boundary.
Unavailable actions retain their declared link and show a separate readable
reason; unrelated assets, comparisons and editing remain usable. A successful
request still proves only launch submission, not native display or human acceptance.
Opening a native asset from a comparison/evidence row prepares that unit's asset
list before submitting its ID. The reader gate still checks again at launch;
users do not need to visit the unit's detail panel to establish a hidden precondition.

The same reader boundary applies to original-source links inside Markdown, not
only asset-card buttons. Render native links as controlled inline actions, never
raw application-protocol anchors. Bind each action to the exact declared source,
document digest, literal link and target identity; reread before preparation and
launch. Changed files, declarations, ambiguous ownership or expired/cross-session
IDs refuse. Browser requests cannot supply a URI, path or attachment key.

Keep the original page/annotation locator unchanged. ZotFlow links emitted by
the analysis renderer use encoded `navigation={"pageIndex":n}` with a zero-based
physical page index; do not replace it with a different page parameter. Only
that bounded navigation shape is supported. Local heading/block links require
an exact declared asset match and preserve the anchor in the Obsidian open path;
neither a basename nor a similar title proves ownership. Unknown/unsupported
links retain their visible labels and diagnostics. Code/image pseudo-links are
not launch actions. Previewing does not launch or bulk-probe readers, rewrite
the paper body, or validate the scientific claim behind a link.

Readable previews preserve supported paper-body presentation: headings and
paragraphs, direct-evidence emphasis, lists/tables, and default-collapsed Obsidian
quote callouts. A callout title keeps its exact source action visible; expanding
reveals the complete supplied quotation. Paper images and captions remain at
their source position outside the quotation. Frontmatter and block identity
markers do not become reading prose. This is a safe preview, not a full Obsidian
plugin engine; unsupported syntax remains readable and the original can still
be opened in its native application. Never execute embedded HTML or scripts.
Non-Markdown text attachments, including code and configuration, remain literal
code previews; Markdown rules must not hide or reformat their contents.

Inline images require an exact declared raster asset, resolved relative to the
document or its explicit Source location. No same-name guess, remote auto-load,
SVG/HTML rendering or root expansion is allowed. Inline media currently requires
an asset inside the selected preview root; an external native image entry is not
permission to read an arbitrary filesystem location. Session media IDs bind the
source revision, literal embed, declaration and actual image digest; reread them
before serving bounded bytes. Changed, missing or unsupported images keep a
caption and a diagnosis rather than disappearing or becoming a new paper.

## Current scope

This version supplies an outer file-backed model, local edit/query interface and
readable Markdown export. Existing paper package formats are unchanged. It does
not yet supply automatic website-body snapshots, a tracking-to-ingestion bridge,
continuous file watching, automatic Obsidian document insertion or a research
agent scheduler. Those require their own implementation and evidence.

Development checks, normal product installation, actual local/native opening and
human evaluation are different results. Keep unresolved stages visible instead
of presenting a syntactically valid model as accepted scientific knowledge.
