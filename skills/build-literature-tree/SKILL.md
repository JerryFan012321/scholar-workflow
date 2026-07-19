---
name: build-literature-tree
description: Generate evidence-based literature lineage graphs, timelines, and method evolution trees for a research topic. Triggers: 'literature tree', 'paper lineage', 'research evolution', 'follow-up papers', '文献脉络', '论文发展树', '画出发展脉络', 'NeRF 到 3DGS'.
---

# build-literature-tree

## Triggers
- User asks for a topic's paper timeline, development lineage, follow-up relationships, or contribution map

## Steps

1. Determine the paper set from a Zotero Collection, a paper index, or a user list
2. Read the hierarchical index; fetch abstracts or introductions on demand (not full text)
3. Generate candidate citation edges (`cites`) and method-relation edges
4. For each non-citation relation, extract evidence: source location in the paper, abstract basis, confidence
5. Classify relation types: `cites` / `follow-up` / `method-extension` / `representation-shift` / `benchmark-successor` / `contradicts`
6. Flag milestone candidates; submit low-confidence edges and milestone judgments for user review
7. After review, save the normalized `literature-graph.json`
8. Render Mermaid / draw.io / HTML visualizations; PNG is a render artifact, not the source of truth
9. Optional: emit a concise Notion outline projection

## Constraints
- Every non-`cites` edge must carry `evidence` (source, location, summary), `confidence`, and `review_status`
- A citation only proves "cites"; it cannot alone prove method inheritance or a breakthrough
- Never auto-flag "milestone" or "breakthrough" without evidence
- Graph data requires user approval before it is written
- Output conforms to `contracts/literature-graph.schema.json`

## References

Load on demand.

- `references/edge-evidence.md` — relation types, evidence and confidence rules
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — approval before writing graph data
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — where the graph JSON lives
