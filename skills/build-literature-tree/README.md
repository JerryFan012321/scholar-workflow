# build-literature-tree

Build a **novelty tree** for a research topic. The tree is a 3-level classification whose
internal nodes are abstract concepts and whose leaves are papers:

```
milestone task (the problem) → pipeline / representation (the method) → paper (leaf)
```

Each concept records its **novelty anchor** — the first paper that proposed that task or
pipeline. Alongside the tree sits a flat **paper list**: the full collected set (a paper
may be listed but not yet classified into the tree).

Everything for one topic lives in a folder named for the topic. Index files use a
library-code prefix: `01-Paperlist.md` is the fixed flat ledger, and each tree/view is a
numbered note (`02-…文献树.md`, `03-…`). One tree renders as a single self-contained note —
an inline Mermaid overview, then nested `##` task / `###` pipeline sections each with its
novelty anchor, an optional 内容简介, and a 论文列表 subpaperlist. Each paper also gets a
companion note under `paper_assets/` whose `# 相关文献树` section links back to its place in
the tree. Rendering is idempotent — content outside the managed markers is preserved. The
normalized document conforms to `contracts/literature-tree.schema.json`.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
