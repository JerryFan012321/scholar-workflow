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
  wording in its selected language. Identifiers and exact source titles may retain
  their original spelling. Do not mix labels merely because machine fields are English.
- Persistent knowledge prose must remain intelligible without opening a sidecar,
  manifest, Hub page, or Canvas. Machine identities, hashes, revision markers, and
  relation records belong in thin metadata or separate machine files, not repeated
  as visible prose. Legacy managed-block delimiters may remain for safe updates but
  are not analysis content or a substitute for a readable body.
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

## Surface-specific ownership

| Surface | Detailed contract |
|---|---|
| Paper analysis Markdown and Canvas | `skills/analyze-paper/references/analysis-format.md` |
| Literature tree and paper ledger | `skills/build-literature-tree/SKILL.md` and `contracts/literature-tree.schema.json` |
| Annotation note | `skills/export-annotations/SKILL.md` |
| Reading Report | `skills/recommend-papers/SKILL.md` |
| Obsidian and Notion projections | `skills/sync-projections/references/obsidian-index-format.md` and `notion-schema.md` |
| Project material overview | `references/project-context.md` |
| Legacy Hub view and direct actions | `references/hub-contract.md` |

For a machine-only JSON response, the owning schema controls fields; its companion
human summary, when exposed, follows this contract. A format-specific template may
deliberately use no H1, a fixed table, or a four-branch Canvas without violating
cross-surface consistency. Conformance must check the applicable format and the
shared visible-result rules separately; prose alone does not prove a renderer passes.
