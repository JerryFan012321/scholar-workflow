---
name: build-literature-tree
description: Organize an Obsidian research topic around existing paper units with a complete paper list, a literature timeline, radial technical routes and a radial challenge/solution tree. Use for 'literature tree', 'novelty tree', 'paper lineage', '文献树', '文献脉络', '技术路线树', '挑战洞见树', '画出发展脉络'.
---

# build-literature-tree

## Result contract

For a new topic library, or an explicitly requested exemplar-style organization, use
the versioned **field-library-v2** contract in `references/field-library-format.md`,
the portable rendering of the user's sole Canonical Knowledge Vault blueprint.
Required elements must be present; absent elements are not added by default.
This is a format contract, not a content quota: actual arguments, depth, figures,
tables, evidence and substantive branch counts follow the selected papers and scope,
never the exemplar's amounts. See the format/content boundary in that reference.
Subsequent output must match its structure, prose roles and appearance, not merely
look similar. Do not mix old live Vaults or test candidates into a second template.
The paper ledger and three different views coexist: **01 complete paper list,
02 literature timeline, 03 center-out technical routes, 04 center-out challenges and
solutions**. Each paper owns a separate leaf in 03/04. Required Markdown explanations,
links, editable Canvas, geometry and honest evidence states are completion conditions,
not suggestions. Match the compact title/leaf content contract, not merely the four
filenames; keep detailed prose and development evidence out of paper cards.
A request for one view changes only that view and its necessary links.

Read the selected format before writing. Use the bundled pure layout helper and
portable styles documented there; the installed skill contains everything required
for geometry, without access to the original exemplars or a code repository.
Paper analysis Markdown, quotations, images and per-paper Canvas still belong to
`analyze-paper`'s current output contract; this Field format never replaces it.

## Operations and scope

- Resolve the user's selected topic/Field, actual existing paper-unit identities and
  declared paths. Reuse existing papers, analyses and notes. New primary owners use
  the established paper-registration interface, not a layout tool.
- When the request also acquires papers or repairs their index after acquisition,
  load `${CLAUDE_PLUGIN_ROOT}/references/paper-delivery.md` for the independent
  import/registration/index completion evidence; keep this Field's selected format.
- Prepare the selected views from the declared corpus and supported relations.
  Unknown classification, missing PDF and incomplete reading stay visible. The
  four novelty classes constrain placement, not how the model must reason.
- The layout helper reads JSON from stdin and emits Canvas to stdout only.
  Inspect its result and link targets before saving within the selected folder.
  It does not register a Source, write notes, open apps or verify scientific support.
- Preserve unrelated files, human prose, accepted layout and user deletions.
  Existing content requires an explicitly scoped update with current-byte checks
  and recovery; do not initialize a template over an existing library.
- Supply an opening/inspection handoff for the resulting notes and Canvas. Report
  format checks, installed-tool checks and pending human assessment separately.

## Compatibility and optional views

- Existing managed Mermaid notes / `project-literature-tree`:
  `references/legacy-concept-tree.md`. Its schema and writer stay unchanged.
- Read-only navigation of existing owned packages:
  `references/field-paper-units.md`; this does not replace the readable ledger.
- Contribution classification and evidence-bearing relation preview:
  `references/evolution-preview.md`; its membership-only Mermaid is not the final 02.
  Reuse its four-class and bounded-evidence semantics.

## Constraints

- A view grants no ownership or write permission. Multiple views/Fields may reference
  one paper; do not copy its reusable analysis or create another primary owner.
- Keep 02/03/04 distinct; a radial map cannot replace the timeline. No fixed number
  of papers, branches, scientific terms, host paths, Vault IDs or attachment keys.
- Plain-language explanations accompany paper entries. No visible machine comments,
  hashes, loopback URLs, unsupported priority/inheritance or cross-task rankings.
- Scope is the selected Field and explicit navigation edits. Zotero bibliography/PDFs
  remain authoritative; styles/configuration changes require a separately explained
  target and preserve unrelated settings.

## References

- `references/field-library-format.md` — required for current Field-library outputs.
- `references/legacy-concept-tree.md` — existing legacy projection only.
- `references/field-paper-units.md` — existing package navigation only.
- `references/evolution-preview.md` — contribution/evolution input only.
- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
