---
name: build-literature-tree
description: Build a novelty tree for a research topic — a 3-level classification (milestone task → pipeline/representation → paper) plus a flat paper list, rendered as Obsidian notes with an inline Mermaid overview. Triggers: 'literature tree', 'novelty tree', 'paper lineage', 'research evolution', 'follow-up papers', '文献脉络', '文献树', '论文发展树', '里程碑任务', '研究方向发展树', '画出发展脉络', 'NeRF 到 3DGS'.
---

# build-literature-tree

## Triggers
- User asks to organize a research direction's papers into a development tree, milestone/task map, or novelty structure

## Model

Per 彭思达's literature-tree method, the tree is a 3-level classification whose internal
nodes are **abstract concepts** and whose leaves are **papers**:

```
milestone task (the problem) → pipeline / representation (the method) → paper (leaf)
```

Each concept records its **novelty anchor** — the first paper that proposed that task or
pipeline (1类/2类/3类 novelty). Alongside the tree sits a flat **paper list**: the full
collected set. A paper may be in the list but not yet classified into the tree.

## Grill — lock scope before building

Both the domain boundary and the granularity are scalable: the same topic renders as a
~10-node skeleton or a 200-node full spectrum. The tree cannot converge until these dials
are locked. Before Step 1, run a short dialogue to fix four gates coarse-to-fine; Gate 0
sets the defaults for the rest.

- **Gate 0 · Purpose** — what is the tree for?
  - onboarding → wide, shallow, anchors only
  - find a gap → deep, recent, weight the unsolved
  - related work → medium, weight representative works + lineage
  - baselines / SOTA → narrow, weight reproducible + current best
- **Gate 1 · Boundary** — one milestone task (narrow) / one pipeline family (medium) /
  a whole problem domain (wide). If the domain word is polysemous (e.g. "world model"
  splits along orthogonal function vs. domain axes), pick the cut-axis first, then cut
  the boundary.
- **Gate 2 · Resolution** — skeleton (anchors + 1-2 main pipelines, ~10 nodes) / trunk
  (3-5 representative papers per pipeline) / full spectrum.
- **Gate 3 · Time window** — founding classics / a specific era (e.g. deep-learning era,
  2018+) / frontier only. The novelty anchor is window-relative: "first to propose" means
  first within the chosen window.

Anchor ownership: a founding paper may fit several layers. Rule — an anchor belongs to the
highest layer that can explain it (a word-origin paper anchors the topic root, not a branch).

Lock the gates, sketch the coarsest skeleton first, then add detail layer-by-layer on the
user's feedback until they signal enough.

## Steps

1. Collect the paper set for the direction (a Zotero collection via zotero-mcp, a paper index, or a user list). This is the flat paper list.
2. Read the papers; extract the direction's milestone **tasks** (the important problems). For each, mark the first paper that proposed it (novelty anchor).
   - **When the set is large**, prefer batch-reading via NotebookLM (`notebooklm-py`, the same skim engine as recommend-papers) instead of pulling every full body — add the papers' arXiv URLs to a notebook and ask source-grounded questions (each paper's core contribution, which task it solves, who first proposed pipeline X). ≈500 tokens/question vs ≈50K to read a PDF. Reuse a same-topic notebook if recommend-papers already built one; else create a temporary one. Classification and first-proposer judgment stay yours — NotebookLM is only the read substrate. If it is unreachable, fall back to zotero-mcp `get_content` or shrink the batch.
3. Group papers under their tasks; extract each task's representative **pipelines / representations**, and mark the first paper proposing each.
4. Subdivide papers by pipeline. Papers not yet placed stay in the paper list with `classified: false`.
5. Assemble the `literature-tree.schema.json` document and render it: pipe `{"root": "<vault dir>", "doc": {...}}` to `scholar-workflow project-literature-tree` (use `--dry-run` to preview file paths first).

## Constraints
- Tree topology is exactly `task → pipeline → paper`: internal nodes are concepts, papers are leaves referenced by `resource_id`.
- Each concept records its novelty anchor = the first paper that proposed that task/pipeline (a verifiable priority fact, not a value judgment — see GOALS NG7).
- Always carry the flat paper list alongside the tree; a paper may be listed but unclassified.
- Render target this round: Obsidian managed block + inline Mermaid only. No PNG / draw.io / HTML / Notion.
- Paper metadata comes from Zotero / authoritative web sources, never parsed from the PDF body (GOALS G3/INV10).
- Output conforms to `contracts/literature-tree.schema.json`.

## References

Load on demand.

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — where the tree JSON and vault notes live
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — additive managed-block writes are the normal path; only destructive actions gate
