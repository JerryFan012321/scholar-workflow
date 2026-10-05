---
name: analyze-paper
description: Analyze one or a user-selected batch of already-ingested papers, wholly or by section, and maintain each paper's paired human-readable Markdown analysis and editable JSON Canvas tree. Read or retain paper code only when explicitly requested. Use for 'analyze this paper', 'analyze these papers', 'paper analysis tree', 'deep dive', 'explain this section', 'read/clone the paper repo', '深入分析', '批量分析这些论文', '论文解析树', '分析这一节', '读代码', '保存论文仓库'. Not for discovery, recommendations, ordinary code-repository review, or annotation export.
---

# analyze-paper

The result is a paired, independently readable Markdown analysis and editable Canvas.
The current required output framework is `references/analysis-output-template.md`;
`references/analysis-format.md` owns the existing v4 compatibility interface and shared
evidence/update boundaries. Reuse the output structure, not an example paper's facts.
The explicit v5 interface is `references/analysis-v5-format.md`. Use it only when the
installed runtime supports v5; the older four-branch v4 renderer does not satisfy the
new template. Report an unsupported-version limitation rather than substituting v4.

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
   If this already-ingested paper has no owner yet, use the explicit new-folder
   registration in `${CLAUDE_PLUGIN_ROOT}/references/paper-registration.md` before
   paired commit. Existing folders require their own reviewed adoption/migration;
   never initialize a provider with a fabricated owner.
   Then load `references/analysis-output-template.md` and the versioned interface in
   `references/analysis-v5-format.md` for a new five-branch analysis, or
   `references/analysis-format.md` for an existing v4 pair. Declare the supported version/framework explicitly;
   the existing v4 interface is for compatibility, not proof of new-template support.
   Declare `whole` or the exact `focused` section subset,
   select `en` or `zh` consistently, and place each new paper's companion note,
   `<paper>分析.md` / `<paper>解析树.canvas` pair, and sidecar together under
   `resources/papers/<persistently-mapped-paper-segment>/` in that Field. Existing
   flat pairs stay in place until a separately reviewed relocation.
5. Project claims and separately attributable points through the versioned IR into both
   artifacts. The Markdown remains independently readable; the required Canvas expands the
   reference image's named subslots into separate editable nodes, each keeping its inline
   evidence, original-source link and exact Markdown-block backlink.
   The Markdown-only verbatim-excerpt contract is in `references/analysis-format.md`;
   Canvas keeps a concise projection without quotations.
   Keep machine claim markers out of v4 human Markdown and Canvas; use block anchors and the
   sidecar for identity. Keep the current reference image's five-branch hierarchy and its
   defined subheadings; unfilled template slots remain unfilled rather than becoming invented
   paper claims. Preserve human prose, safe existing layout, custom nodes/edges, stable identities,
   and unrelated manifest rows. A focused v4 update supplies the complete selected section(s),
   because the update replaces those sections as units. Treat a human-edit conflict as one paired
   Markdown/Canvas conflict and leave both values unchanged. Treat ZotFlow and Zotero deep links
   as reader projections of verified PDF spans, not as source identities. The optional v4
   ZotFlow Library Reader projection requires an explicitly verified Vault and local PDF mode;
   follow the reader-link
   boundary in `references/analysis-format.md`.
6. For an existing v4/v5 pair, load `references/analysis-batch.md` and use
   `scholar-workflow analysis stage-update` with the exact three-file base hashes.
   It preserves the existing graph and returns a complete merged commit request;
   ordinary `batch-run` regeneration is not an existing-pair update.
   The same reference owns the explicit metadata-only acknowledgement for an editor save;
   it never replaces a content commit or adopts text/layout drift.
   Validate the pair against the hard conformance boundary before registration. For a multi-paper
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

When the user requests a reproducible exemplar or replayable analysis package,
load `references/reproduction.md`. Keep the versioned input and reader/source
checks alongside the displayed pair; a staged or copied review candidate is not
a canonical commit. Replay uses the installed public CLI, not a private renderer.

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
- Evidence stays inline with each claim or point. Apply the required topology from
  `references/analysis-output-template.md` and the selected version's validation boundaries;
  retain v4 node accounting only for the v4 compatibility projection.
- IR v1–v3's Task / Input / Workflow / Output / Boundary projection remains readable as legacy;
  ordinary updates do not silently convert it to the v4 reference tree.
- Focused updates preserve valid human layout and custom nodes/edges; a generated-content
  conflict returns a proposal and leaves the pair unchanged.
- Batch cleanup owns staged analysis drafts only and never modifies Zotero data.
- Canonical commit requires exact base hashes and never overwrites a concurrent human edit;
  symlinks, path escape, and partial/manual-recovery state fail closed.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `references/analysis-output-template.md` — current required Markdown/Canvas framework.
- `references/analysis-v5-format.md` — explicit five-branch machine/result interface.
- `references/analysis-format.md`
- `references/reproduction.md` — only for a requested exemplar or replayable package.
- `references/analysis-batch.md` — load for multi-paper analysis or an existing-pair update.
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
