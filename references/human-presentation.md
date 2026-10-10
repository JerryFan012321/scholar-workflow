# Human-Facing Presentation Contract

This is the shared result contract for material a person reads in Scholar Workflow:
Vault notes, Canvas views, literature trees, annotation notes, reports, Hub views, and
CLI text. It does not prescribe the model's reasoning or force different media into
one layout. Each format-specific contract still owns its headings, fields, graph
geometry, table columns, filenames, and edit behavior.

## Common visible result

- Identify the object and scope, then put the useful conclusion or current state before
  implementation diagnostics. An empty result states why it is empty and what remains
  available.
- Keep one artifact's human labels, structural headings, evidence labels, and status
  wording in its selected language. Identifiers, exact source titles, and verbatim source excerpts may retain
  their original spelling. Do not mix labels merely because machine fields are English.
- Persistent knowledge prose must remain intelligible without opening a sidecar,
  manifest, Hub page, or Canvas. Machine identities, hashes, revision markers, and
  relation records belong in thin metadata or separate machine files, not repeated
  as visible prose. Legacy managed-block delimiters may remain for safe updates but
  are not analysis content or a substitute for a readable body.
- Write as a useful document, not a validation log. Do not expose artifact IDs,
  full hash dumps, internal claim markers or repeated machine status labels in
  ordinary paragraphs, cards or tables. Audit details belong in a linked supplement
  or machine record. Do not strip existing anchors that links depend on: changing
  opaque anchors requires coordinated link migration, not cosmetic hiding.
- Use ordinary, precise language. Explain necessary technical terms on first use;
  do not invent jargon for a simple operation, failure or result. Separate the
  conclusion, supporting observations and limits without repeating a disclaimer
  on every line.
- Primary links need actual relevance: current code/configuration, the authoritative
  plan, experiment conclusions/results and explicitly related paper-unit files.
  Explain each relation. Put inventories, hashes, full logs, snapshots and historical
  checks in a discoverable supplement unless they directly explain the current
  result or failure. Every selected entry, including missing files, stays accounted for.
- Place evidence and a usable source entry beside the statement it supports. Distinguish
  source assertions from analysis inference and unavailable evidence. A page link
  promises a page, not a selected sentence; do not claim finer precision than the
  verified locator provides.
- Derive persistent links from stable source identities, not a loopback port, absolute
  path, or process-local action ID. A visible link or action must work in its current
  reader; if the surface cannot open it, show an explicit supported open action or a
  clear unavailable reason, not link-looking inert text.
- Distinguish complete, partial, failed, conflicted, and unavailable outcomes where
  they apply. Give the affected item, reason, and safe next action; never present a
  rendered draft, pending migration, or recovery snapshot as a validated result.
- Preserve human-authored content on update. When a human edit conflicts with a
  managed projection, show the conflict rather than silently replacing it.

## Compact tree connections

Tree connections must be as short as practicable within the owning format's full
framework, aligned hierarchy, non-crossing/no-occlusion rules, readable text and
click space. Among compliant layouts, prefer shorter actual routed connections
and fewer unnecessary bends or detours. Avoid inflated parent-child gaps and long
empty-space traversals; a permitted shared trunk can serve siblings. Endpoint
distance alone does not measure a route with bends. Compactness never authorizes
missing nodes/links, unreadable shrinking, changed semantics, or violation of the
format's endpoint/arrow rules. Preserve safe accepted human layout during updates;
offer a separately scoped layout change when needed. This is an output requirement,
not a claim that an existing renderer proves a global shortest layout.

## Surface-specific ownership

| Surface | Detailed contract |
|---|---|
| Paper analysis Markdown and Canvas | `skills/analyze-paper/references/analysis-output-template.md` (current required format); `analysis-format.md` in the same directory (v4 compatibility and shared source/update protections) |
| Literature tree and paper ledger | `skills/build-literature-tree/SKILL.md` and `contracts/literature-tree.schema.json`; opt-in contribution/evolution preview uses that skill's `references/evolution-preview.md` and `contracts/literature-evolution.schema.json` |
| Annotation note | `skills/export-annotations/SKILL.md` |
| Reading Report | `skills/recommend-papers/SKILL.md` |
| Consistency audit report | `skills/check-consistency/SKILL.md` |
| Obsidian and Notion projections | `skills/sync-projections/references/obsidian-index-format.md` and `notion-schema.md` |
| Project material overview | `references/project-context.md` |
| Rich internal PROJECT document | `references/project-entry.md` |
| Selected Field paper-unit navigation | `skills/build-literature-tree/references/field-paper-units.md` |
| Experiment review and comparison | `references/experiment-review.md` |
| Legacy Hub view and direct actions | `references/hub-contract.md` |

For a machine-only JSON response, the owning schema controls fields; its companion
human summary, when exposed, follows this contract. A format-specific template may
deliberately use no H1, a fixed table, or its own required Canvas hierarchy without violating
cross-surface consistency. Conformance must check the applicable format and the
shared visible-result rules separately; prose alone does not prove a renderer passes.
