# build-literature-tree

Build a **novelty tree** for a research topic. The tree is a variable-depth classification
whose internal nodes are abstract concepts and whose leaves are papers. Two isomorphic tree
types share one structure and renderer, keyed off node kind:

```
technical:  milestone task → pipeline / representation → module (optional) → paper (leaf)
challenge:  challenge → insight → paper (leaf)
```

Each concept records its **novelty anchor** — the first paper that proposed that
task / pipeline / module / insight (classes 1/2/3 and insight seminals). A paper that only
*improves* an existing pipeline (class 4) hangs as an ordinary member, no anchor. Alongside
each tree sits a flat **paper list**: the full collected set (a paper may be listed but not
yet classified, and may appear in more than one tree).

Everything for one topic lives in a folder named for the topic. Index files use a
library-code prefix: `01-Paperlist.md` is the fixed flat ledger, and each tree/view is a
numbered note (`02-…文献树.md`, `03-…`). One tree renders as a single self-contained note —
an inline Mermaid overview, then nested concept sections (task/challenge at `##`,
pipeline/insight at `###`, module at `####`) each with its novelty anchor, an optional
内容简介, and a 论文列表 subpaperlist. Each paper also gets a
companion note under `paper_assets/` whose `# 相关文献树` section links back to its place in
the tree. Rendering is idempotent — content outside the managed markers is preserved. The
normalized document conforms to `contracts/literature-tree.schema.json`.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
