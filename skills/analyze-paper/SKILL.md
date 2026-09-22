---
name: analyze-paper
description: Analyze one or a user-selected batch of already-ingested papers, wholly or by section, and maintain each paper's paired human-readable Markdown analysis and editable JSON Canvas tree. Read or retain paper code only when explicitly requested. Use for 'analyze this paper', 'analyze these papers', 'paper analysis tree', 'deep dive', 'explain this section', 'read/clone the paper repo', '深入分析', '批量分析这些论文', '论文解析树', '分析这一节', '读代码', '保存论文仓库'. Not for discovery, recommendations, ordinary code-repository review, or annotation export.
---

# analyze-paper

This skill constrains the analysis result and its external interfaces, not the model's
reading order, reasoning framework, or internal method. The canonical artifacts are the
structured projection of the paper-specific judgment.

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
4. Resolve each paper's topic folder under `research_vault_root`, then load
   `references/analysis-format.md`. Declare `whole` or the exact `focused` role subset and maintain
   one `<paper>分析.md` / `<paper>解析树.canvas` pair per paper.
5. Project claims through the versioned analysis IR into both artifacts. The Markdown remains
   independently readable; the Canvas keeps the same claims, inline evidence states, and links
   each claim back to its Markdown block. Preserve human prose, safe existing layout, custom
   nodes/edges, stable identities, and unrelated manifest rows. Treat a human-edit conflict as
   one paired Markdown/Canvas conflict and leave both values unchanged.
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
- Preserve all human-authored content and all managed blocks.
- Evidence stays inline with its claim. The Canvas uses no more than 40 renderer-owned semantic
  nodes (user-created nodes do not consume that budget), readable generated geometry, and an
  ordered end-to-end Workflow rather than invented
  challenge/contribution pipeline nodes.
- Baselines own only renderer-emitted node/edge IDs and generated content/endpoint revisions.
  Focused updates preserve valid human layout and custom nodes/edges; generated-content conflicts
  return a proposal and leave the pair unchanged.
- Batch cleanup owns staged analysis drafts only and never modifies or rolls back Zotero data.
- Canonical commit requires exact base hashes and never overwrites a concurrent human edit;
  symlinks, path escape, and partial/manual-recovery state fail closed.

## References

- `references/analysis-format.md`
- `references/analysis-batch.md` — load only for multi-paper analysis.
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
