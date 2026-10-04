# Paper Analysis v4 Compatibility Contract

The current required result framework is in `analysis-output-template.md`: five first-level
branches and individually expanded reference-image subslots. This document records the existing
IR v4 interface, its older four-branch/grouped-details projection, and evidence/link/update
boundaries retained across the format change. Its old topology does not override the current
required template or constitute new-format support. New analyses use the explicit v5
interface in `analysis-v5-format.md`; retain v4 only for existing-format compatibility.

Within that compatibility scope, this contract governs identity, hierarchy, evidence,
cross-artifact links and layout, not a reading order or internal reasoning method. IR v1–v3's
Task / Input / Workflow / Output / Boundary format remains readable as a legacy projection;
an ordinary update must not silently convert a legacy pair to v4.

## Historical v4 presentation template and its boundary

The previously reviewed v4 reference-tree presentation records its historical appearance and
interaction contract, not any example paper's claims, source verdicts or migration status. It
does not establish acceptance of the later five-branch template. Keep these compatibility
properties together:

| Output | Accepted template behavior |
|---|---|
| Paper folder | One Field-local folder owns the companion note, analysis Markdown, editable Canvas, and sidecar; Zotero retains the PDF. |
| Markdown | Independently readable prose under the four reference-image branches, with no `sw-analysis-claim` comments or detached Evidence section. Each supported claim/point carries its evidence, source link, and an adjacent verbatim short excerpt. |
| Canvas | The same branch/content hierarchy as Markdown, editable text nodes, straight square-routed arrowless connections, compact two-dimensional layout, and roughly one extra line of clickable space per text box. No long single-axis pipeline. |
| Navigation | Each claim/point can open its verified original-source location and link back from Canvas to the exact Markdown block. The chosen reader route is a projection of stable source identity, not the identity itself. |

Keep the reference image's framework and named slots; leave unsupported slots empty. Each
paper needs its own claim/point attribution and reader-capability check, followed by paired
Markdown/Canvas/sidecar validation. Reusing the template does not require repeating the
same example paper's visual acceptance or performing a real-Vault bulk operation.

## Artifact pair and profile

Each new paper has one `resources/papers/<stable-paper-segment>/` folder inside its
registered Field. Its human-readable paper companion note, evolving `<paper>分析.md` /
`<paper>解析树.canvas` pair, and analysis sidecar share that folder; the PDF remains in Zotero.
The segment is allocated and persistently mapped to the resource identity, never inferred as
identity from a title. Existing flat `paper_assets/` and analysis pairs remain readable in place;
moving them requires a separately reviewed relocation transaction, not an ordinary update.
Markdown is the complete, independently readable analysis. The editable Canvas is a concise
projection of the same claims, not a second source of knowledge. Analysis, annotations,
literature trees, and the source PDF have separate owners.

An existing IR v4 document declares `framework: reference_tree` and `language: en` or `zh`.
The selected language applies to framework labels, claim/point prose, evidence descriptions,
source-link labels, and Canvas backlink aliases. An English tree is English throughout; a
Chinese tree is Chinese throughout. Verbatim source excerpts retain the source's original language;
their captions follow the analysis language. Structural conformance checks the generated language labels,
while factual and prose-language quality still need semantic review.

- `whole` renders all four sections: **Abstract, Introduction, Method, Limitation**. A section
  may have no factual claim when the source or reference image leaves it unfilled.
- `focused` declares a non-empty subset of those sections. The current update boundary is a
  **complete selected section**: include all retained claims in each selected section, not only
  one changed contribution. Unselected sections remain unchanged. A claim-level change within a
  section is prepared as a complete replacement for that section; otherwise it could drop its
  sibling claims.

These sections are output organization, not a mandated analysis or reading sequence. The visible
framework follows the supplied reference image:

```text
Paper
├── Abstract
│   ├── Task
│   ├── Technical challenge for previous methods
│   ├── Key insight / motivation
│   ├── Technical contributions
│   └── Experiment
├── Introduction
│   ├── Task and application
│   ├── Technical challenge for previous methods
│   └── Our pipeline
│       ├── Key innovation / insight
│       └── Technical contributions
├── Method
│   ├── Overview
│   └── Pipeline modules
└── Limitation
    └── Reasoned limitations
```

Framework headings may remain visible without a factual claim underneath. In particular, an
unfilled Experiment, Method, or Limitation slot in the reference image is not evidence that a paper reports a
result there. Do not create a claim merely to fill a structural label. Real contributions,
challenges, and modules may repeat to match the paper; the named framework branches stay fixed.
The Method branch contains the actual process, without invented corresponding-challenge or
corresponding-contribution pipeline nodes.

The machine contract is `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`. Every v4 claim
has a stable `claim_id`, one of the four `role` values, a title, complete `body`, evidence, and an
`outline_path` in this template:

| Outline path | Optional claim-local point IDs |
|---|---|
| `abstract/task` | none |
| `abstract/previous_methods/<slug>` | `challenge-1` … `challenge-3` |
| `abstract/insight` | `motivation`, `advantage` |
| `abstract/contributions/<slug>` | `summary`, `advantage` |
| `abstract/experiment` | none |
| `abstract/experiment/<slug>` | `finding-1` … `finding-4` |
| `introduction/task_application` | none |
| `introduction/previous_methods/<slug>` | `previous-method`, `limitation`, `technical-reason` |
| `introduction/our_pipeline/insight` | none |
| `introduction/our_pipeline/contributions/<slug>` | `purpose`, `how`, `advantage` |
| `method/overview` | none |
| `method/modules/<slug>` | `motivation`, `method`, `why-it-works`, `technical-advantage` |
| `limitation/explanation` | none |
| `limitation/explanation/<slug>` | `reason-1` … `reason-4` |

`<slug>` is a stable lowercase Latin/digit/hyphen identifier for one repeated method, challenge,
contribution, experiment, limitation, or module. Repeated experiment and limitation claims stay
under the existing reference-image branches; they are not new framework categories. Their bounded
finding/reason points preserve individually attributed statements without turning either branch
into one oversized Canvas card. Only supplied point IDs in the corresponding row are valid; absent
points stay absent rather than being fabricated. Each point has a stable claim-local `point_id`,
complete single-paragraph `text`, and its own evidence. A point longer than 180 characters needs
a faithful `canvas_summary` of at most 180 characters. A v4 claim body longer than 180 characters
requires a faithful `canvas_summary` of at most 180 characters; its title must stay within 120
characters. Evidence anchors/details and source-link counts are similarly bounded for Canvas
readability. Neither summary may add a fact or discard a material qualification. The body
plus points are the complete Markdown explanation.
The `schema_version` is mandatory: existing v4 pairs retain `4` with `framework: reference_tree`;
new analyses use `5` with `framework: reference_tree_v5`, and legacy v1–v3 remain explicit.
Claim bodies may contain explanatory paragraphs but cannot inject
new framework headings or renderer markers.

## Evidence and verifiable source locations

Each claim and each supplied point keeps its evidence or availability suffix beside its text in
both artifacts. The labels follow the document language; for example:

```text
〔Author-stated · §3.2〕       〔作者明确陈述 · §3.2〕
〔Analysis inference · …〕     〔分析推断 · …〕
〔Not reported in the paper〕  〔论文未报告〕
```

The Canvas abbreviates these labels to `〔Author〕`, `〔Inference〕`, `〔N/A〕`, etc., plus live
`PDF p.N` or source-block links. The full evidence anchor/reason stays inline in the Markdown
block reached through each Canvas backlink; this keeps the tree legible without detaching evidence.

The other states are `unverifiable` (当前正文通道无法核实; current indexed-text channel lacks needed
material) and `not_applicable` (不适用; reason supplied). `not_reported` means supported absence, not merely a missing
figure or table in Zotero's text index. There is no detached Evidence section, table, or node.

For every v4 `author_stated` or `analysis_inference` claim/point, evidence includes at least
one `source_span`. A Zotero PDF span records library identity/type, current attachment key,
content hash, **zero-based physical** `page_index`, optional display-only `page_label`, and an
optional real annotation key. A registered Vault Markdown span records Source/artifact identity,
Source-relative note path, and explicit block ID. The span is the source locator; its rendered
reader link is not a new object identity. A repository file/line can supplement an implementation
claim only after requested code inspection and cannot replace a paper-local anchor.

Immediately after the suffix, render an original-source link in the same Markdown block and
Canvas claim or grouped point-detail node. The document's optional `reader` selects only the
link projection; it does not change the source span. With the default Zotero-native reader,
`page_index=3` links to physical PDF page 4:

```text
[Source · PDF page 4](zotero://open-pdf/library/items/<attachment-key>?page=4)
[[<relative-note-path>#^<block-id>|Source · paragraph]]
```

A verified annotation key may append `&annotation=<key>`; a page-only link does not select an
exact sentence. Keep a section, figure/table identifier, or short quotation to aid manual
location. PDF page labels, including Roman numerals, are not URI page numbers. For other formats,
use a verified format-specific locator or link the document and state that precise positioning is
manual. Persistent analysis content does not store fixed Hub ports or absolute source paths.

The structural gate cannot prove that the cited page, quote, block, or annotation actually belongs
to the current source. Before canonical use, resolve the Zotero attachment through Local API,
compare its current bytes with the recorded hash, verify annotation membership, and resolve a
Vault block against its registered document. Stale locators require re-verification.

### Markdown-only verbatim excerpts

New analyses explicitly set `profile.markdown_quotes: true`. Each `author_stated` or
`analysis_inference` claim and point supplies at least one short, contiguous, verbatim excerpt in
its supporting `source_span.quote` (1–400 characters). PDF and registered Markdown spans both
support this field. The excerpt follows that statement in the human Markdown, with the same
span's page/annotation or block link; it is not a separate Evidence section or a bibliography.
For an inference, quote the source observation it rests on, not an invented author conclusion.

Keep the original spelling, punctuation, qualifications, and language. A translation or
paraphrase remains analysis prose, not the exact quote. Use the shortest sufficient passage within
applicable quotation limits; do not silently splice passages or insert an ellipsis into `quote`.
Multiple excerpts use separate spans and source links. If the accessible source channel cannot
verify the wording or its precise location, report an explicit source gap rather than guessing a
quotation or recording a supported success. Availability-only statements need no invented quote.

The renderer escapes Markdown/HTML syntax to show source text literally. Conformance checks
presence, attribution, link, and agreement with the supplied IR; it cannot prove verbatim fidelity
to the source, which still requires source review. Canvas receives **no quote text or quote nodes**;
its concise claims, inline evidence, source links, backlinks, geometry, and node budgets are unchanged.

Previously saved IRs omit this profile field (or set it to `false`) and keep their existing output,
baseline and update behavior, even if they contain an unused `quote`. This is compatibility, not the
new-analysis default. A focused update retains its baseline's setting; adopting the new format on
an existing pair needs an explicitly requested whole-analysis format update with current source
verification and the usual paired CAS/conflict protections. Never bulk refresh older papers or
hand-edit just the Markdown to add quotations.

### Obsidian-internal ZotFlow reader link

The source span stays `library_id + attachment_key + content_hash + page_index` regardless of the
reader. In a manually authored or experimental Obsidian note, a ZotFlow Library Reader link may
open a verified local attachment when that Vault has an enabled, audited ZotFlow version in local
Zotero-storage mode and the link has been checked there. A successful route in one Vault does not
prove it works in another Vault or plugin version.

For the tested ZotFlow 1.6.6 route, a zero-based `page_index` of 3 uses:

```text
obsidian://zotflow?vault=<verified-16-hex-vault-id>&type=open-attachment&libraryID=<numeric-library-id>&key=<attachment-key>&navigation=%7B%22pageIndex%22%3A3%7D
```

Resolve the registered Vault's host-local Obsidian ID, encode the JSON navigation, and re-check the observed
`navigation` parameter after a plugin upgrade. A real annotation deep link needs a verified
annotation key; page navigation is not text selection or proof of bidirectional sync.

When the authorized Source is a Vault subdirectory, resolve the unique containing
host-registered Vault for the reader ID, while keeping all file operations inside
the selected Source. `knowledge reader/open` exposes that distinction; see the
shared `knowledge-registration.md` contract. Parent reader identity grants no
additional content permissions. The same resolution is enforced at v4/v5 commit.

For IR v4, `reader: {kind: zotflow_library, vault_id: <verified-16-hex-vault-id>}` selects the versioned ZotFlow
Library Reader projection in both Markdown and Canvas; omitting `reader` (or setting
`zotero_native`) retains the native Zotero route. The ZotFlow option is used only after that
Vault's plugin version and desktop local-storage mode have been positively verified, and the
attachment bytes exist locally. An annotation key in a source span does not make this page link
an annotation selection. Never hand-edit one member of a managed Markdown/Canvas/sidecar bundle
to change its reader. A legacy `vault_name` may be previewed but cannot be committed as a new v4
bundle; a new host must re-resolve its own Vault ID. Zotero-native fallback opens a separate application.

## Human-readable Markdown and editable Canvas

The Markdown keeps machine metadata thin and follows the same framework. For English output:

```markdown
---
sw_schema: 2
sw_kind: paper-analysis
sw_catalog_id: "analysis:<stable-paper-resource-id>"
sw_analysis_profile: whole
sw_analysis_framework: reference_tree
sw_analysis_language: en
---

# <paper title>: Paper Analysis

> Scope: Whole paper

## Abstract

### Task

#### <claim title>
<complete explanation> 〔Author-stated · §1〕 [Source · PDF page 4](zotero://open-pdf/library/items/<attachment-key>?page=4) ^claim-<claim-id>

> **Original excerpt** · [Source · PDF page 4](zotero://open-pdf/library/items/<attachment-key>?page=4)
>
> <short verbatim excerpt, in the original source language>

### Technical challenge for previous methods

...

## Introduction
...

## Method
...

## Limitation
...
```

An attributable point remains in its claim's Markdown block with its own evidence, source link,
and `^point-<claim-id-length>-<claim-id>-<point-id>` anchor. A Canvas claim node links to
`#^claim-<claim-id>`; a claim's points share **one editable detail text node**, with one line per
point linking to its own exact Markdown point anchor. Each line retains that point's inline
evidence and original-source link. The length prefix keeps point IDs unambiguous when IDs contain
hyphens. No `sw-analysis-claim` HTML comments or opaque Scholar-specific marker tags appear in v4
human Markdown or Canvas node text. Native Obsidian `^claim-…` / `^point-…` block IDs still appear
in Markdown source to support exact backlinks; the IR and sidecar own claim identity and Canvas
node mapping. V1–v3 legacy files retain their historical
marker contract and are not silently rewritten. A point's original excerpt is a blockquote
indented under that list item, not another point or a Canvas node. In Chinese output the caption
is `原文摘录`; an English original excerpt remains English.

The renderer emits standard JSON Canvas 1.0 with `{"nodes": [], "edges": []}` at the top level.
Opening it in Advanced Canvas may add its narrow `metadata` envelope (`version` and
`frontmatter`); validation and focused updates accept and preserve that envelope without treating
it as Scholar identity or allowing arbitrary top-level fields. The root and four section branches lead through the gray reference-framework
labels to claim and grouped point-detail text nodes. No panel-card layout, independent Evidence area, or giant
vertical pipeline is the intended projection. Generated node/edge IDs are stable for their
artifact and outline paths. The v4 limit is **40 generated claim/detail Canvas nodes** and **96 total
renderer-owned Canvas nodes** including root, section, framework labels, and grouped details. User-created graph items
do not consume that budget. A generated node taller than 420 px or a whole generated tree with aspect
ratio above 2:1 fails instead of producing a long unreadable strip. Generated nodes must not
overlap; text boxes reserve roughly one visible line beyond the measured text, including CJK
wrapping, so source and backlink labels remain clickable. Spacing needs visual
inspection in Obsidian.

The renderer uses fine, square-routed, arrowless parent-child edges. An installed Advanced Canvas
may display the square routing and borderless label styling; it is optional, and ordinary Canvas
remains editable when those presentation attributes are unavailable. The source of truth remains
the standard `nodes`/`edges` graph, not a screenshot or an SVG. Editing a generated Canvas node's
text is possible in Obsidian, but it is **not automatic two-way synchronization** into Markdown:
subsequent managed updates report a paired conflict rather than silently overwriting that edit.
Safe manual geometry/color changes and custom nodes/edges remain preserved.

Register the Canvas in the Vault-side `.scholar-workflow/artifacts.yml`, preserving unrelated
rows. Do not inject private top-level Canvas identity fields or infer identity from the filename:

```yaml
schema_version: 1
artifacts:
  - artifact_id: analysis:<stable-paper-resource-id>:canvas
    kind: analysis-canvas
    format: canvas
    vault_path: <field-relative-path>/resources/papers/<stable-paper-segment>/<paper>解析树.canvas
    resource_id: <existing-hub-resource-id>
    topic_id: <existing-hub-topic-id>
    parent_id: analysis:<stable-paper-resource-id>
```

The file must already exist inside the Vault without traversing a symlink. A move changes
`vault_path`, not stable artifact identity.

## Conformance and update boundary

Hard conformance checks version/framework/profile coverage, valid outline paths and point slots,
stable identities, inline evidence and source links, Markdown claim/point anchors and opted-in
verbatim-excerpt placement/content, Canvas
framework labels/claim/grouped-point content/backlinks, graph endpoints, non-overlapping generated
geometry, square routing, and both node budgets. It does not grade scientific correctness or
prose language automatically. Each batch item is staged and checked independently; failure may
receive at most one targeted repair, then only that item's staged drafts are cleaned.

A newly rendered pair receives a baseline sidecar binding the IR, full Markdown revision,
claim hashes, and exact renderer-owned node/edge IDs. Its Canvas hash covers generated content
and edge endpoints, not user nodes, user edges, styling, or layout. A focused update is zero-write
until its proposed complete selected section(s) pass validation against the baseline. A generated
content/endpoint edit, unsafe graph, missing/corrupt baseline, or Markdown revision conflict
returns one paired conflict and a proposal. It never silently rebases or overwrites either
artifact. Moving from v1–v3 to v4 requires an explicit reviewed migration, not a focused update.

Canonical commit requires exact base hashes and commits the Markdown, Canvas, and sidecar as one
recoverable bundle. Structural conformance is necessary but does not replace source-location
verification or human review of scientific claims.

The legacy joint-placement, provider-bootstrap and Field legacy-cutover interfaces remain
v4-only; new v5 analysis rendering and paired commits do not make those migration interfaces
v5-capable. Their version gate does not authorize downgrading a new analysis to v4.

The checked-in runtime schemas are:

- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`
- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-baseline.schema.json`
- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-conformance-report.schema.json`

For a user-selected multi-paper run, also load `references/analysis-batch.md` before staging.
