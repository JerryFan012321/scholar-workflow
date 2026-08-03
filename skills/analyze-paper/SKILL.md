---
name: analyze-paper
description: Analyze one already-ingested paper in depth and write the analysis as a companion Obsidian note. Supports whole-paper or focused/partial analysis. Triggers 'analyze this paper', 'detailed analysis', 'read through this paper', 'explain this section', 'deep dive', 'analyze the method', '详细分析', '深入分析', '通读这篇论文', '解读这篇', '分析这一节', '局部分析'. Not paper discovery (find-resource), recommendation skim (recommend-papers), or annotation export (export-annotations).
---

# analyze-paper

## Triggers
- User wants an in-depth read-through or a focused analysis of one ingested paper
- User asks to explain/analyze a specific section, method, or result of a paper

## Steps

1. **Resolve the paper.** Identify the Zotero item (by title fragment / arxiv id via
   zotero-mcp). If several match, ask which one. The paper must already be in the
   library — this skill analyzes ingested papers, it does not discover or ingest.

2. **Read the body via get_content.** Use zotero-mcp `get_content` to pull the paper's
   text. **Never parse the PDF body yourself** (INV10 / INV24): metadata stays from
   authoritative sources; get_content is the one text channel here.

3. **Resolve the analysis note.** One paper → one analysis note (e.g.
   `<paper-name>分析.md`) under `research_vault_root`, in the same folder as the paper's index
   row / related-docs hub. Ask for the subfolder if not obvious.

4. **Write or append.**
   - **Whole-paper analysis** → write the note body (your synthesis — how you read it
     is your own ability, not encoded here).
   - **Focused / partial analysis** → append a *new section* to the existing analysis
     note (e.g. `## 方法分析`, `## 实验解读`), never overwriting prior sections.
   - All content goes in the **human area, outside any managed block** — INV4 protects
     it from re-projection. Do not wrap analysis in scholar-workflow managed markers.

5. **Cross-link, keep sources distinct.** In frontmatter `related`, link the analysis
   note to the paper's **annotations note** (export-annotations product) and vice
   versa. The two are separate artifacts: annotations = the user's highlights/comments;
   analysis = Claude's read-through. Never merge them into one note.

6. **Hang on the related-docs hub (INV20).** Add a link to this analysis note as an
   out-of-managed-block entry on the paper's `<paper-name>论文相关资料.md` hub, so it
   aggregates alongside annotations / direction notes. Do not duplicate metadata there.

## Constraints
- **Source is get_content, not the PDF (INV24 / INV10).** Body text comes through
  zotero-mcp only; the PDF is never parsed for text, and metadata never comes from it.
- **Analysis lives outside managed blocks (INV4).** It is human-area content; a later
  projection/sync must never overwrite it. Only the derived index/hub uses managed
  blocks, and this skill only *appends an entry* there, it does not own that block.
- **Analysis note ≠ annotations note.** Distinct files, cross-linked via `related`.
  Never fold the user's annotations into the analysis or vice versa.
- **Focused analyses append, never replace.** Each partial pass is an additive section
  on the same note, preserving earlier sections.
- **One paper per run.** No batch analysis.

## References
Load on demand.
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — vault as note home, no-overwrite of human content, derived-index rules
- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — authoritative metadata, no PDF-body parsing
