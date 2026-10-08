# Five-branch Analysis v5 Interface

The human output template is owned by `analysis-output-template.md`. This reference
defines its explicit machine interface, not a reading or reasoning procedure.
Evidence states, source/quote verification, reader identity and paired storage
protection retain `analysis-format.md` and the shared source/storage policies.

## Identity and scope

- New analyses use this explicit v5 interface. Check installed runtime support;
  a specification or source checkout is not proof that the installed tool supports it.
- `schema_version: 5`, `profile.framework: reference_tree_v5`, explicit `language: en|zh`.
- Optional document-level `capacity: expanded` explicitly selects 96 independent
  records and 192 managed nodes. Omission retains the standard 40/96 limits.
  This option is v5-only; ordinary updates cannot change the selected capacity.
  Verify installed support before supplying it; older installations reject it.
- `profile.markdown_quotes: true`. Supported author claims/inferences include a
  short original-language excerpt and a verified source span; only Markdown renders
  the excerpt. Structural projection cannot prove that the source contains it.
- New presentation explicitly selects `profile.markdown_folded_quotes: true` in
  supporting runtimes. It uniformly folds all supplied excerpts without changing
  original text, exact emphasis, reader links or Canvas. The full display/adoption
  contract is in `analysis-format.md`; old omitted/false inputs remain compatible.
- `whole` roles normalize to Abstract, Introduction, Method, Experiments, Limitation.
  A branch can have no supported facts; preserve its structure without inventing them.
- `focused` names the selected branches and supplies their complete replacement.
  Ordinary updates cannot convert v4 to v5, change its framework or silently switch
  reader. Unselected branches and human content retain paired conflict protection.
- Schema: `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`; baseline:
  `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-baseline.schema.json`.

## Outline paths and independent points

Each claim has a stable `claim_id`, role and unique `outline_path`. `<slug>` is a
lowercase alphanumeric/hyphen identifier, not an absolute path or a display title.
Each supplied point has its own stable `point_id`, text, evidence and block anchor.
Repeated challenges/contributions/modules have separate claims and parents.
Point text and Canvas summaries are prose, not additional framework headings or
machine claim comments. Literal non-heading hash-prefixed text remains prose.

| Claim outline path | Permitted point IDs |
|---|---|
| `abstract/task` | none |
| `abstract/previous_methods/<slug>` | `challenge-<positive integer>` |
| `abstract/insight` | `motivation`, `advantage` |
| `abstract/contributions/<slug>` | `summary`, `advantage` |
| `abstract/experiment` | none |
| `abstract/experiment/<slug>` | `finding-<positive integer>` |
| `introduction/task_application` | none |
| `introduction/previous_methods/<slug>` | `previous-method`, `limitation`, `technical-reason` |
| `introduction/our_pipeline/insight` | none |
| `introduction/our_pipeline/contributions/<slug>` | `purpose`, `how`, `advantage` |
| `introduction/demos_application` | none |
| `method/overview` | `task-io`, `steps` |
| `method/modules/<slug>` | `motivation`, `method`, `why-it-works`, `technical-advantage` |
| `experiments/comparison/<slug>` | `finding-<positive integer>` |
| `experiments/ablation/<slug>` | `components`, `design-choices` |
| `limitation/explanation` | none |
| `limitation/explanation/<slug>` | `reason-<positive integer>` |

Counts follow the paper, not the example's number of instances. Missing fixed
subslots render as empty labels, never fabricated availability records. All process
steps stay together in `method/overview`'s `steps` point; Method modules do not add
corresponding-challenge/contribution axes. Different modules never share a point node.

## Structural containers are not facts

Use `container: true` only for a grouping claim with no parent statement. It requires
`body: ""`, no Canvas summary, `evidence.kind: not_applicable`, a structural explanation,
no evidence anchor and no source spans. Its canonical template label is rendered;
its arbitrary `title` or detail is not shown as an unsupported fact. It has no claim
block anchor or own source entry. Its points remain independently attributable records.
Non-container claims require a nonblank body and their own evidence/backlink.

Claims/points use faithful concise summaries when their body exceeds 180 characters.
Their visible title, summary and inline source labels remain bounded by the checked
schema. Concision cannot remove a material qualification or add unsupported facts.

## Observable rendering and conformance

- Every record has its own text node, inline evidence and exact Markdown-block
  backlink. A grouped `/details` replacement does not meet this template.
- Labels follow the declared language. Labels occupy their own first line; statement,
  evidence and links remain independently readable. Quotes immediately follow their
  corresponding Markdown statement; no private comments or detached Evidence section.
- All five main branches share a trunk. Same-depth nodes align on the left;
  subtrees occupy non-overlapping vertical bands. Both edge ends have no arrow,
  `fromSide: right`, `toSide: left`, `styleAttributes.pathfindingMethod: square`.
- Apply the alignment, crossing and visible-node occlusion rules in
  `analysis-output-template.md` to the actual candidate, including preserved manual
  layout and extra graph items that interact with managed content. Absence of
  rectangle overlaps alone is not enough.
- Text boxes fit measured visible text plus approximately one click line. The current
  standard capacity preserves limits of 40 actual independent records, 96 total managed nodes;
  explicitly selected expanded capacity allows 96 records and 192 managed nodes. Both retain
  420 px maximum node height and 2:1 maximum overall aspect ratio. Container labels
  do not count as facts but do count toward total nodes. Failure reports the actual
  conflict; it never hides records, merges slots, shrinks fonts or silently raises limits.
- For an expanded tree that is too tall, aligned layer gutters may increase uniformly
  from 64 px to at most 344 px, using only the width needed for the 2:1 limit.
  Box dimensions and vertical bands remain content-driven and unchanged. If bounded
  spacing is insufficient, conformance still fails; spacing is not visual acceptance.
- A renderer may return a noncanonical candidate for review. Baseline creation,
  batch success and canonical writes require a passing conformance report. A file
  existing is not proof of success. Source fidelity and human visual assessment are
  separate, explicitly reported checks.

## Unique Canvas source targets

From 0.41.2, optional `profile.canvas_unique_sources: true` renders an identical
source link only once within each claim/point node, retaining its first occurrence.
All source spans, identities, hashes and independent Markdown excerpts/links remain
in the IR and body. Different rendered page or native annotation targets stay
distinct; this is not evidence deduplication or precise text-selection support.

Omission or `false` preserves the earlier projection and baseline serialization.
Existing pairs adopt the option only through an explicit `whole` paired format
update; a `focused` update must retain it. Adoption preserves node identities,
geometry, styles, edges and unrelated human content. It does not reanalyze a paper
or change its reader, framework or capacity. Verify installed support before use.

## Exact companion-note routes

From 0.41.3, optional `profile.canvas_note_path` is the paired Markdown's explicit Vault-relative
`.md` path. The renderer uses it for every claim, point and image-card block backlink,
with the existing visible alias unchanged. Its filename must equal `note_stem + ".md"`;
absolute paths, URLs, traversal, link syntax and control characters are rejected.
It is a display route, never object identity or authority to write another folder.

For a new pair, resolve its actual companion position in the containing registered
Obsidian Vault rather than trusting an ambiguous filename. Canonical commit compares
the route with the authorized Source and requested Markdown before writing. A missing
or mismatched containing-Vault registration refuses this explicit-route commit.
Check installed support before supplying this field.

Omission retains legacy link rendering and baseline serialization. An existing pair
adopts or rebinds the route only through an explicit `whole` paired format update;
focused updates retain it. Markdown, evidence, node identities, geometry and edges
remain unchanged. A review copy uses its own explicit companion location and is not
a canonical write. When copied to another position, the saved route may still point
to the original: reproduction reports the required rebinding without rewriting files.
Verify actual clicks reach the paired file **and** block; filename matching, static
link resolution or a conformant graph alone is not reader acceptance.

## Selected Canvas source images

An optional `canvas_image` on a factual claim or point supplements that same record
with one editable image card. Only `experimental_table` under experiment comparison /
ablation and `process_diagram` under Method Overview / an actual module are allowed.
No paragraph, quotation or generic screenshot kind exists. Do not encode untyped
image embeds in Canvas summaries or labels; Markdown paragraph crops can remain in
the full body with a plain Canvas summary.

The image object declares `asset_id`, paper-relative `image_path` under `attachments/`
(PNG only), bare SHA-256, `pixel_width`, `pixel_height`, a single-line `caption`, and
`source` (a Zotero PDF span without `quote`). Its attachment identity, hash and page
must match a supported source span of its own record. The label identifies the
source figure/table; matching metadata alone does not prove crop fidelity.

The renderer adds a child text card with a note-relative image embed, caption,
verified-source projection and exact record-block backlink; it does not replace
any framework node or render quotations in Canvas. Without the explicit Markdown
projection below it retains the historical Markdown output. Image dimensions
contribute to the card's measured size; all existing geometry gates remain.

Canonical commit requires the image's ID, owner, paper-local path, media type, size
and hash in `.scholar-workflow/assets.yml`; it checks the actual PNG bytes/dimensions
before writing and before issuing a receipt. Image drift triggers paired recovery,
not an overwrite of the external image. Read-only package inspection checks the
explicit images as well as the analysis trio. Reproduction refuses an image missing
from its owned inventory and carries the declared images and manifest.

Keep the source-region replay input as an explicitly owned supporting asset under
the shared reproduction/source-image contract. Selecting `experimental_table` or
`process_diagram` is a claim about the crop, not an automatic visual classification
or proof that labels, units and qualifiers survive. Native display and human review
are separate. This optional interface is available from 0.41.0; check the actual
installed version before use, since 0.40.2 rejects it. Existing safe layouts remain protected; an update
that cannot fit its image returns a conflict proposal, not a silent relayout.

## Markdown source-image projection

New v5 analyses with selected key process figures or experimental tables explicitly
set `profile.markdown_source_images: true` in a runtime supporting this field. Each
selected `canvas_image` also renders beside its own Markdown claim/point, after the
statement and original excerpt, with a relative embed, its caption and verified
source-page link. Do not encode a duplicate image into the scientific text. This
option changes no Canvas text, nodes, geometry, links or ownership.

If the same image is already embedded in that point's text or its owning claim's
body, reuse it and render only the caption/source line. Direct Markdown embeds and
Obsidian `![[attachments/...]]` embeds are recognized, including `./` and URL-encoded
relative targets. A filename mention, ordinary link, escaped example, code sample
or hidden HTML comment is not a displayed image. A sibling point or detached gallery
does not substitute for the selected record. Conformance requires the projected
image and caption/link in their expected positions; omission, modification or
relocation fails instead of becoming a successful batch item.

Omission or `false` retains legacy rendering and baseline serialization. A focused
update retains its baseline setting. An existing pair adopts this feature only
through an explicitly requested whole paired format update; once enabled, an
ordinary update cannot remove it. The asset inventory, PNG/hash/dimension checks,
source verification, CAS and human assessment boundaries remain unchanged. Paragraph
crops remain Markdown-only supplements governed by `analysis-format.md`; selecting
this option does not put them in Canvas or initiate screenshot generation.
Check actual installed support: earlier installations reject this profile field.

## Reader, ownership and old artifacts

Verified ZotFlow projections require the registered Vault ID and local PDF mode.
Their Obsidian Library Reader links are projections of stable source spans, not PDF
identities or proof of annotation synchronization. Unverified reader configuration
cannot become a new canonical pair; do not hand-edit one file's links.

New Markdown, Canvas and sidecar stay together in the mapped Field paper folder.
Canonical writes keep source registration, provider owner, full snapshot CAS, safe
relative paths, symlink protection and journal/conditional recovery checks. Old v4
bytes and identities are not silently re-trusted, moved or regenerated. User-created
nodes/edges and safe style/layout remain distinct from managed content; conflicts
return a proposal without overwriting either artifact.

The legacy joint-placement, provider-bootstrap and Field legacy-cutover interfaces
accept v4 only. This v5 analysis interface does not authorize those migration routes
to accept v5, initialize a Field, or relocate existing content. An ordinary paired
analysis commit is not a migration or bootstrap transaction.
