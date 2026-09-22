# analyze-paper

Create a persistent analysis of one already-ingested paper, or a separate analysis pair for each
paper in a selected batch. Every result has a human-readable Obsidian Markdown note and an editable
JSON Canvas projection.

## Output model

Whole-paper results expose five roles in both artifacts:

1. **Task** — the problem, intended capability, application, and motivation.
2. **Input** — data, representations, assumptions, and prerequisites.
3. **Workflow** — one ordered end-to-end sequence of actual method steps.
4. **Output** — produced results and experiment-backed capabilities.
5. **Boundary** — limitations, applicability limits, source gaps, and inference boundaries.

A focused request declares a subset and plans changes only for those roles. A versioned baseline
sidecar binds the paired revisions. Existing prose, unrequested roles, Canvas layout, and
user-created nodes/edges are preserved; if either artifact differs from its trusted baseline, the
operation returns one paired conflict plus a proposal and performs no silent rebase or overwrite.

Evidence is visible beside each claim. Author statements, analysis inferences, absent reporting,
unverifiable indexed-text gaps, and non-applicable fields remain distinct. Canvas claim nodes link
back to their Markdown evidence blocks; there is no detached Evidence section or node.

The Canvas is a concise view, not a second knowledge database. Generated layouts use readable
heading-sized text nodes, keep the workflow in one visible flow, and contain no more than 40
renderer-owned semantic nodes. User text/file/link/group nodes do not consume that budget or enter
the generated baseline; focused updates retain custom graph items and valid manual layout.

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
identity stays in thin frontmatter, markers, and Vault manifests rather than overwhelming the
human-readable body.
