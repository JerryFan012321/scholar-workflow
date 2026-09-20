---
name: analyze-paper
description: Analyze one already-ingested paper, wholly or by section, and maintain its paired Obsidian Markdown analysis and editable JSON Canvas tree. Read or retain the paper's code only when the user explicitly asks. Use for 'analyze this paper', 'paper analysis tree', 'deep dive', 'explain this section', 'read/clone the paper repo', '深入分析', '论文解析树', '分析这一节', '读代码', '保存论文仓库'. Not for discovery, recommendations, ordinary code-repository review, or annotation export.
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
4. Resolve the paper's topic folder under `research_vault_root`, then load
   `references/analysis-format.md` and maintain one paired result per paper:
   `<paper>分析.md` and `<paper>解析树.canvas`.
5. Project the same claims into both artifacts. A whole-paper request fills the complete
   canonical tree; a focused request changes only the requested subtree. Create missing
   artifacts and otherwise preserve human prose, Canvas layout, custom nodes/edges, stable
   identities, heading/field-level edit baselines, and unrelated manifest rows. A human-edit conflict
   is preserved and reported, never silently overwritten; the same canonical path is updated in
   Markdown and Canvas only as one paired unit.
6. Register and link the pair exactly as specified by the format contract. Keep analysis,
   annotations, and literature trees as separate artifacts. Add links to the pair outside
   managed blocks in the paper's `paper_assets/<year>-<first-author>-<title>.md` hub.
7. Return the two paths, the analyzed scope, and every source gap that limits verification.

## Constraints

- Each paper receives its own Markdown/Canvas pair; a multi-paper request never merges
  analyses into one pair.
- Zotero indexed full text is the paper-text channel; repository code is an optional,
  read-only implementation aid and never a metadata or paper-text source.
- One paper has one evolving analysis note and one evolving analysis canvas. Section/node
  revision is allowed; whole-artifact replacement is not.
- Analysis, annotations, and literature trees remain separate artifacts with separate
  owners. This skill writes only the analysis pair and its permitted cross-links.
- Preserve all human-authored content and all managed blocks.

## References

- `references/analysis-format.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
