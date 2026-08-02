# build-literature-tree

Build a **novelty tree** for a research topic, following 彭思达's literature-tree method.
The tree is a 3-level classification whose internal nodes are abstract concepts and whose
leaves are papers:

```
milestone task (the problem) → pipeline / representation (the method) → paper (leaf)
```

Each concept records its **novelty anchor** — the first paper that proposed that task or
pipeline. Alongside the tree sits a flat **paper list**: the full collected set (a paper
may be listed but not yet classified into the tree).

The result renders to Obsidian managed-block notes: the topic root note carries an inline
Mermaid overview and the flat paper list; each concept note carries its novelty anchor plus
a MOC wikilink list or a paper table. Rendering is idempotent — content outside the managed
markers is preserved. The normalized document conforms to `contracts/literature-tree.schema.json`.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
