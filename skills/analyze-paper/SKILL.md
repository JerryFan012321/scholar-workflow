---
name: analyze-paper
description: Analyze one or a user-selected batch of already-ingested papers, wholly or by section, and maintain each paper's paired human-readable Markdown analysis and editable JSON Canvas tree. Read or retain paper code only when explicitly requested. Use for 'analyze this paper', 'analyze these papers', 'paper analysis tree', 'deep dive', 'explain this section', 'read/clone the paper repo', '深入分析', '批量分析这些论文', '论文解析树', '分析这一节', '读代码', '保存论文仓库'. Not for discovery, recommendations, ordinary code-repository review, or annotation export.
---

# analyze-paper

The result is a paired, independently readable Markdown analysis and editable Canvas
under the accepted v4 presentation template in `references/analysis-format.md`. Reuse its
structure and interaction contract, not the example paper's facts or page numbers.

## Workflow contract

1. Resolve the requested, already-ingested Zotero item with
   `scholar-workflow zotero search`; disambiguate multiple matches.
2. Read its attachment identity and indexed paper text with
   `scholar-workflow zotero get <item-key> --children` and
   `scholar-workflow zotero fulltext <attachment-key>`. Zotero indexed full text is the
   paper-body channel; missing tables, figures, or equations are reported as source gaps.
3. Repository code is an optional, untrusted, read-only supplement governed by the shared
   source policy. Access it only when the user explicitly requests code inspection; keep a
   clone only when the user explicitly requests retention under `code_repo_root`.
4. Resolve the explicitly registered Obsidian Source and its Field for each paper,
   using the trusted folder registration and `.scholar-workflow/fields.yml` rather
   than treating `research_vault_root` as a required singleton. If the destination
   is ambiguous or the Field is not initialized, ask for a choice or run the
   Field preview; do not silently create a topic directory or migrate a Vault.
   Then load `references/analysis-format.md`. New analyses must explicitly set
   `schema_version: 4` and `framework: reference_tree`; omission is an error, not a
   fallback to the historical tree. Declare `whole` or the exact `focused` section subset,
   select `en` or `zh` consistently, and place each new paper's companion note,
   `<paper>分析.md` / `<paper>解析树.canvas` pair, and sidecar together under
   `resources/papers/<persistently-mapped-paper-segment>/` in that Field. Existing
   flat pairs stay in place until a separately reviewed relocation.
5. Project claims and separately attributable points through the versioned IR into both
   artifacts. The Markdown remains independently readable; editable Canvas claim nodes and their
   grouped detail nodes keep each point's inline evidence, original-source link, and backlink to
   its exact Markdown block.
   Keep machine claim markers out of v4 human Markdown and Canvas; use block anchors and the
   sidecar for identity. Keep the accepted reference image's Abstract / Introduction / Method / Limitation hierarchy and its
   defined subheadings; unfilled template slots remain unfilled rather than becoming invented
   paper claims. Preserve human prose, safe existing layout, custom nodes/edges, stable identities,
   and unrelated manifest rows. A focused v4 update supplies the complete selected section(s),
   because the update replaces those sections as units. Treat a human-edit conflict as one paired
   Markdown/Canvas conflict and leave both values unchanged. Treat ZotFlow and Zotero deep links
   as reader projections of verified PDF spans, not as source identities. The optional v4
   ZotFlow Library Reader projection requires an explicitly verified Vault and local PDF mode;
   follow the reader-link
   boundary in `references/analysis-format.md`.
6. Validate the pair against the hard conformance boundary before registration. For a multi-paper
   request, load `references/analysis-batch.md` and invoke `scholar-workflow analysis batch-run`
   with the versioned request; stage and validate each paper independently, permit at most one
   targeted repair, clean failed drafts, and keep conformant siblings. A nonzero gate result means
   the affected paper is not successful even if a renderer emitted files.
7. For each `validated` or `repaired` item, build an explicit CAS request and invoke
   `scholar-workflow analysis commit-bundle`; only its receipt makes the Markdown, Canvas, and
   sidecar canonical. Register only the receipt's explicit `KnowledgeChangeSet`. Keep analysis,
   annotations, and literature trees as separate artifacts; never infer relations from prose.
8. Return each pair's paths, profile/scope, validation state, and every source gap or conflict.

## Constraints

- Each paper receives its own Markdown/Canvas pair and conformance result; a batch never merges
  analyses or lets one failed item roll back a conformant sibling.
- Zotero indexed full text is the paper-text channel; repository code is an optional,
  read-only implementation aid and never a metadata or paper-text source.
- One paper has one evolving analysis note and one evolving analysis canvas. Section/node
  revision is allowed; whole-artifact replacement is not.
- Analysis, annotations, and literature trees remain separate artifacts with separate
  owners. This skill writes only the analysis pair and its permitted cross-links.
- Never silently discard human-authored content: Markdown revision drift returns a paired conflict.
  A focused v4 update preserves unselected sections and replaces only its explicitly selected
  complete sections; retained claims in those sections must be included in the submitted IR.
- Evidence stays inline with each claim or point. Apply the v4 Canvas node budgets,
  point-level attribution, and Method branch rules from `references/analysis-format.md`.
- IR v1–v3's Task / Input / Workflow / Output / Boundary projection remains readable as legacy;
  ordinary updates do not silently convert it to the v4 reference tree.
- Focused updates preserve valid human layout and custom nodes/edges; a generated-content
  conflict returns a proposal and leaves the pair unchanged.
- Batch cleanup owns staged analysis drafts only and never modifies Zotero data.
- Canonical commit requires exact base hashes and never overwrites a concurrent human edit;
  symlinks, path escape, and partial/manual-recovery state fail closed.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `references/analysis-format.md`
- `references/analysis-batch.md` — load only for multi-paper analysis.
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
