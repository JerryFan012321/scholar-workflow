# analyze-paper

Create a persistent analysis of one already-ingested paper, or a separate analysis pair for each
paper in a selected batch. Every result has a human-readable Obsidian Markdown note and an editable
JSON Canvas projection.

For new papers, the companion note, analysis Markdown, Canvas, and sidecar live together in
`<Field>/resources/papers/<stable-paper-segment>/`; the Zotero PDF remains outside the Vault.
The segment is persisted with the resource mapping. Existing flat files remain readable and are
not moved by an ordinary analysis update.

## Output model

The current required format is the reference image's five-section tree in both artifacts:

1. **Abstract** — Task; technical challenge for previous methods; key insight/motivation;
   technical contributions; Experiment.
2. **Introduction** — Task and application; previous-method challenges; Our pipeline with
   key innovation/insight and technical contributions; Demos/applications.
3. **Method** — Overview with task/input/output and steps kept together, followed by the
   paper's actual pipeline modules and their named subslots.
4. **Experiments** — Comparison experiments and Ablation studies; the latter distinguishes
   effects of core contributions/components from each module's design choices.
5. **Limitation** — limitations with their reasons.

Canvas expands the reference image's challenge/contribution/module subslots as separate
editable nodes. The full current result contract is `references/analysis-output-template.md`.
New analyses use the explicit v5 interface in `references/analysis-v5-format.md`, with
`schema_version: 5` and `framework: reference_tree_v5`. Check the installed runtime's
support before producing a pair. The older v4 four-section/grouped-details interface remains
for existing-format compatibility only; it cannot substitute for a new five-section result.
Structural conformance does not establish scientific source fidelity or visual acceptance
in Obsidian. Unsupported output is reported as a limitation, not a v4 success.

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
New analyses also include short verbatim source excerpts immediately below the supported
statement in Markdown, each with its own page/block link. Original wording and language are
retained. Ordinary prose quotes include a complete source sentence and enough adjacent context
to understand its subject, conditions and qualifications, not isolated keywords or figure labels;
paraphrases and translations are not presented as exact quotes. The bounded quote capacity
accommodates necessary context without imposing that capacity as a target length. Unverifiable wording
is a source gap. Canvas does not repeat the quotations and retains the required editable tree.
Older analyses remain unchanged; converting their format requires an explicit whole-analysis
update, not a silent refresh. The detailed contract is `references/analysis-format.md`.
On request, native PDF region screenshots can accompany Markdown claims; this does not
implicitly add them to Canvas. Canvas image supplements follow the experimental-table /
key-process-diagram restriction in `references/analysis-output-template.md`, without
replacing the editable tree. The optional v5 `canvas_image` interface is available from
0.41.0; its fields and conflict behavior are in `references/analysis-v5-format.md`.
Check the actual installed version before adding images; structural checks do not
prove native display or human readability.
Paper-local images and their crop replay input have explicit asset ownership;
0.40.1 reproduction includes that manifest and its hash-checked files, not just the
analysis trio. See the same format contract and shared reproduction contract.
The v4/v5 `reader` projection can select an explicitly verified ZotFlow Library Reader in a registered
Vault, opening a local Zotero attachment at its physical page inside Obsidian in both artifacts.
The default remains Zotero-native. The structured source span remains authoritative; a page
link never claims exact text selection or annotation synchronization.

A registered Source may be a Vault subfolder. `knowledge reader SOURCE_ID`
resolves the containing Obsidian Vault for the reader without granting parent
folder access. `knowledge open SOURCE_ID 'relative/note.md'` (or `.canvas`)
opens an existing document in its native editor without Hub; see the shared
[registration/open contract](../../references/knowledge-registration.md).

For a requested portable exemplar, use `knowledge canvas-plan` and `knowledge register-canvas`
after paired commit/provider apply to declare the existing Canvas in the Source's artifact manifest.
The [Canvas declaration contract](../../references/canvas-registration.md) covers digest-bound
review, unchanged prose/graph, conflicts and conditional recovery. This is not full provider
restoration on another host or scientific/human approval.

From 0.39.0, ownership replay provides `knowledge reproduction-plan` and
`restore-plan/restore` for a copied, explicitly attached Source. It preserves all content,
refuses existing providers, and records reader/source handoffs separately; see the shared
[reproduction contract](../../references/knowledge-reproduction.md). Verify these commands
are present in the installed version; tests are not external-tool or human acceptance.

The historical v4 Canvas is a concise view, not a second knowledge database. It uses one root, four branches,
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

For v5, each independently attributable point has its own editable node rather than a
grouped detail line. Same-depth alignment and non-crossing/non-occlusion are hard requirements;
the default budget remains 40 records/96 managed nodes. An explicit document-level
`capacity: expanded` selects 96 records/192 managed nodes in supporting installations.
It does not relax geometry, evidence or readability, and ordinary updates cannot change it.
See `references/analysis-output-template.md` for the complete geometry contract. Existing v4
pairs retain their own versioned projection and are not silently converted.

The legacy joint-placement, provider-bootstrap and Field legacy-cutover interfaces still
accept v4 only. New v5 analysis support does not enable those migration routes or authorize
Field initialization, relocation or a silent v5-to-v4 downgrade.

## Batch conformance

For an existing v4/v5 pair, prepare an `AnalysisCommitRequest` containing its exact
three-file base hashes, then run `scholar-workflow analysis stage-update --request
update.json --vault-root /registered/source`. This stages a layout-preserving update
without changing the originals. Save the returned `commit_request` as JSON and use it
with `analysis commit-bundle`; apply only the receipt's explicit change set.
Human-content, stale-base or geometry conflicts stop the update. A regenerated
whole-tree batch cannot be committed if it would discard the existing graph.
See `references/analysis-batch.md` for the request and handoff contract.
These update entries require installed runtime 0.38.1 or later. When an editor has
only added supported empty-frontmatter Canvas metadata, use the explicit
`analysis acknowledge-canvas-metadata` entry first and save its returned `next_request`
for staging. It records the proven new hash through provider CAS without rewriting
the Vault files; it does not adopt text/layout edits or commit an analysis revision.
From 0.38.2, an explicit `--registered-canvas-hash` also permits proven re-encoding
of that unchanged metadata-bearing graph; the provider and exact encoding proof
must both agree. See the same reference before using it.

The replay package can inspect its explicitly selected knowledge folder with
`scholar-workflow knowledge preview /absolute/folder --language en` without Hub.
This is a zero-write navigation/ownership preview, not Source registration or paper acceptance.

Check an existing displayed pair with `scholar-workflow analysis check-bundle
/absolute/paper-folder --markdown 'Paper Analysis.md' --canvas 'Paper Tree.canvas'
--sidecar 'analysis.baseline.json' --require-ir 5 --language en`. The public checker
reads only these files and checks actual conformance, geometry, backlinks and baseline
consistency; it neither regenerates nor registers them. JSON reports preserve file hashes
and original findings. Source fidelity, live readers and human assessment remain separate.

Requested reproducible exemplars include a non-secret versioned input and replay
note alongside the pair, using the installed public batch/commit interfaces.
`references/reproduction.md` distinguishes staged files, navigable review copies
and canonical receipts, and records source and human-visual checks separately.
For a missing paper owner, the explicit `knowledge paper-plan/register-paper`
interface creates only a new companion folder, inventory and navigation through
a digest-bound recoverable transaction; see the shared paper-registration contract.
It does not adopt existing review copies or substitute for the paired commit receipt.

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
