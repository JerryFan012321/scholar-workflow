# build-literature-tree

Build a readable topic library around existing paper units. The **field-library-v2**
profile keeps four coexisting entries: a complete paper list, a horizontal literature
timeline, a center-out technical-route map and a center-out problem/solution map.
The three maps are editable JSON Canvas; paired notes explain methods, conditions,
limitations and source support in ordinary language. Each radial leaf is one paper.
Timeline titles are short-name/year links; radial paper cards contain one method
sentence and navigation. Detailed evidence stays in paired prose, common reading
status in the list, and development/test records outside the human topic folder.

The user's Canonical Knowledge Vault is the sole blueprint. Required elements cannot
be omitted, absent elements are not added by default, and later outputs must match
its structure and appearance. One domain overview and `resources/<paper>/Paper.md`
with existing analysis/Canvas form the navigation; no extra topic homepage or taxonomy.
This fixes presentation, not scientific content or volume: arguments, depth, images,
tables, evidence and branch counts follow the actual papers, never the sample's counts.

The installed skill bundles its precise output contract, scoped CSS styles and a
stdlib-only deterministic layout/check helper. Neither a source checkout nor the
original exemplar Vault is needed. The helper reads prepared JSON on stdin and emits
Canvas on stdout; it never writes files, infers ownership or verifies scientific facts.
See [the format and native setup](references/field-library-format.md) for input fields,
slots, links, Advanced Canvas prerequisites, safe updates and manual assessment.

Existing paper owners/paths and user edits are preserved. Missing PDFs and incomplete
reading remain visible; no paper count or scientific classification is copied from a
sample. Paper analysis, folded quotations and per-paper Canvas remain governed by
`analyze-paper`, not this topic layout.

Existing Mermaid concept projections remain available through the unchanged
`project-literature-tree` interface; see [legacy compatibility](references/legacy-concept-tree.md).
Read-only package lists and contribution/evolution previews are separate optional modes.
See [SKILL.md](SKILL.md) for scope and reference routing.
