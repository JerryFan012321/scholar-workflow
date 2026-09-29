# analyze-paper

Create a persistent analysis of one already-ingested paper, or a separate analysis pair for each
paper in a selected batch. Every result has a human-readable Obsidian Markdown note and an editable
JSON Canvas projection.

For new papers, the companion note, analysis Markdown, Canvas, and sidecar live together in
`<Field>/resources/papers/<stable-paper-segment>/`; the Zotero PDF remains outside the Vault.
The segment is persisted with the resource mapping. Existing flat files remain readable and are
not moved by an ordinary analysis update.

## Output model

New IR v4 analyses use the reference image's four-section tree in both artifacts:

1. **Abstract** — Task; technical challenge for previous methods; key insight/motivation;
   technical contributions; Experiment.
2. **Introduction** — Task and application; previous-method challenges; Our pipeline with
   key innovation/insight and technical contributions.
3. **Method** — Overview and the paper's actual pipeline modules.
4. **Limitation** — limitations with their reasons.

These are visible output branches, not a prescribed reading or reasoning order. Repeated
challenges, contributions, and modules use stable outline paths; an unfilled template branch
remains structural and never becomes a fabricated paper claim. The chosen `en` or `zh` language
applies consistently to tree labels, analysis prose, evidence, links, and backlinks. Existing IR
v1–v3 five-role analyses remain readable and require an explicit migration to adopt v4.

A focused v4 request declares a section subset and submits **all retained claims in every
selected section**. The update replaces those complete sections, leaving unselected sections
unchanged. A versioned baseline sidecar binds the paired revisions. Existing human prose,
Canvas layout, and user-created nodes/edges are preserved; if either artifact differs from its
trusted baseline, the operation returns one paired conflict plus a proposal and performs no
silent rebase or overwrite.

Evidence is visible beside each claim. Author statements, analysis inferences, absent reporting,
unverifiable indexed-text gaps, and non-applicable fields remain distinct. Canvas claim nodes link
back to their Markdown evidence blocks; there is no detached Evidence section or node.
For a claim with separately attributable statements, v4 keeps stable evidence-bearing points in
the Markdown claim block and projects them as separate lines within one editable Canvas detail
text node for that claim. Every claim and
point has inline evidence, original-source links when source-backed, and an exact backlink to the
corresponding Markdown block. V4 author-stated claims/points and inferences require a source span.
Zotero PDF spans link to a physical page or an existing annotation; registered Vault Markdown
spans link to a block. Both links appear inline in Markdown and Canvas alongside the Canvas-to-note
backlink. Page links are not exact text selections, and source identity/revision must be verified
separately from structural conformance.
The v4 `reader` projection can select an explicitly verified ZotFlow Library Reader in a named
Vault, opening a local Zotero attachment at its physical page inside Obsidian in both artifacts.
The default remains Zotero-native. The structured source span remains authoritative; a page
link never claims exact text selection or annotation synchronization.

The Canvas is a concise view, not a second knowledge database. It uses one root, four branches,
gray framework labels, and fine parent-child lines instead of card panels. The v4 budget is at
most 40 generated claim/detail Canvas nodes and 96 total generated Canvas nodes including framework labels. User
text/file/link/group nodes do not consume that budget or enter the generated baseline. The
renderer emits square-routing hints for optional Advanced Canvas; the `.canvas` remains editable
without it, though line appearance may differ. Manual edits to generated *text* are not automatic
two-way Markdown synchronization: the next managed update reports a conflict; safe layout/style
edits and custom graph items remain preserved.
Generated text boxes estimate CJK wrapping and reserve one extra visible line so their source
and Markdown-backlink labels remain clickable. V4 human-facing text has no machine claim comments;
claim identity is carried by block anchors, deterministic Canvas IDs, and the sidecar.

## Batch conformance

Each paper in a batch is staged and checked independently. A hard contract validates profile
coverage, IDs, inline evidence, backlinks, Canvas integrity, readable geometry, and node count
without grading prose style or the model's reasoning method. A failing item receives at most one
targeted repair. If it still fails, its staged drafts are removed after diagnostics are recorded;
successful siblings remain available. Zotero items, PDFs, and canonical knowledge artifacts are
never part of this rollback.

A conformant stage becomes canonical only through the three-file CAS commit. Markdown, Canvas,
and the analysis sidecar share a journal and receipt; stale base hashes or symlinks fail closed,
and conditional rollback never overwrites a concurrent human edit. The resulting deterministic
change set contains only explicitly supplied relations and projections, not links inferred from
free-form prose.

A separate read-only maintenance audit accepts only manifest-resolved knowledge objects and
analysis pairs. It reports orphan/duplicate objects, template residue, raw legacy 23128 links,
pair conformance, and catalog drift without scanning arbitrary directories or repairing files;
installing a weekly schedule remains an explicit operational choice.

## Sources and safety

Paper identity and metadata come from Zotero, and paper text comes from Zotero indexed full text.
Missing figures, tables, or equations become explicit source gaps. Code repositories are read only
when requested and are never executed, built, or installed.

The Markdown/Canvas pair remains separate from annotations and literature-tree artifacts. Machine
identity stays in thin frontmatter, the sidecar, and Vault manifests rather than overwhelming
the human-readable body. Legacy v1–v3 marker-bearing analyses are read without silent rewriting.
