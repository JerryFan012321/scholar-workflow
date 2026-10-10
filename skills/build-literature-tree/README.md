# build-literature-tree

## Existing paper-unit navigation — development only

For a selected registered Field, `knowledge list --paper-units --source-id SOURCE_UUID
--field-id FIELD_UUID --language en` groups its local papers and explicit contextual
references into existing paper packages. It retains all purposes and declared
information/analysis/Canvas/note entries, including missing or conflicted states.
Safe reader-mapped Markdown/Canvas entries have direct Obsidian links; no app opens
while listing. This is not a bibliography refresh or a replacement for the fixed
`01-Paperlist.md`. It writes nothing and is **not in installed 0.42.0**. See
[the navigation contract](references/field-paper-units.md). Installed/native and
human readability acceptance remain separate.

## Contribution/evolution preview — development only

The unreleased development tree also provides `literature-preview --input evolution.json
--format md|json`. It validates explicit contribution-level novelty types and placement,
then shows a compact vertical membership overview and complete evidence-linked technical
tradeoffs. It reuses paper identities without copying notes. It reads no configuration,
registry or original content and writes nothing. This is **not in installed 0.42.0**;
real scientific support, the final editable figure and human appearance acceptance remain
separate. See [the preview contract](references/evolution-preview.md).

## Existing concept-classification view

Build a **novelty tree** for a research topic. The tree is a variable-depth classification
whose internal nodes are abstract concepts and whose leaves are papers. Two isomorphic tree
types share one structure and renderer, keyed off node kind:

```
technical:  milestone task → pipeline / representation → module (optional) → paper (leaf)
challenge:  challenge → insight → paper (leaf)
```

Each concept records its **novelty anchor** — the earliest supported introducing paper
within the tree's declared corpus for that task / pipeline / module / insight (classes
1/2/3 and insight seminals). It is left unresolved when priority is not established; the
tree does not turn a bounded corpus into a global first-paper claim. A paper that only
*improves* an existing pipeline (class 4) hangs as an ordinary member, no anchor. Alongside
each tree sits a flat **paper list**: the full collected set (a paper may be listed but not
yet classified, and may appear in more than one tree).

Everything for one topic lives in a folder named for the topic. Index files use a
library-code prefix: `01-Paperlist.md` is the fixed flat ledger, and each tree/view is a
numbered note (`02-…文献树.md`, `03-…`). One tree renders as a single self-contained note —
an inline Mermaid overview, then nested concept sections (task/challenge at `##`,
pipeline/insight at `###`, module at `####`) each with its novelty anchor, an optional
内容简介, and a 论文列表 subpaperlist. Each paper also gets a
companion note under `resources/papers/<stable-paper-segment>/论文信息.md` whose
`# 相关文献树` section links back to its place in the tree. Its analysis, Canvas, sidecar,
and other Scholar-owned notes share that folder; the PDF stays in Zotero. The folder
segment is recorded against the stable paper identity rather than inferred from the
filename. Existing `paper_assets/*.md` notes remain at their declared paths until an
explicit reviewed migration. Rendering is idempotent — content outside the managed
markers is preserved. The normalized document conforms to
`contracts/literature-tree.schema.json`.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
