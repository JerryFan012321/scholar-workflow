# Editable Paper Analysis Canvas

Each whole-paper analysis has one editable Obsidian JSON Canvas beside its detailed note:

```text
<paper>分析.md
<paper>解析树.canvas
```

The Markdown note holds detailed reasoning and evidence. The Canvas holds the concise,
paper-specific analysis tree below. Claims must agree across both artifacts; Canvas leaves
may summarize but may not introduce a claim absent from the note. The Canvas root links to
the Markdown note, and the note lists the Canvas in frontmatter `related`.

## Required tree

For a whole-paper analysis, create every top-level branch and every listed field. Repeat
challenge, contribution, and pipeline-module subtrees as needed. A leaf contains the actual
paper-specific answer, not only its field label. When a genuinely applicable field is not
reported by the paper, write `论文未报告` rather than fabricating content.

```text
论文解析树
├── Abstract
│   ├── Task
│   ├── Technical challenge for previous methods
│   ├── Key insight / motivation
│   │   ├── 一句话 insight / motivation
│   │   └── insight 的好处
│   ├── Technical contributions
│   │   └── Contribution N
│   │       ├── 一句话 contribution
│   │       └── contribution 的好处
│   └── Experiment
├── Introduction
│   ├── Task and application
│   │   ├── 具体任务
│   │   ├── 输入
│   │   ├── 输出
│   │   └── 应用
│   ├── Technical challenges for previous methods
│   │   └── Technical challenge N
│   │       ├── Previous method
│   │       ├── Failure cases / limitation
│   │       └── Technical reason
│   ├── Our pipeline
│   │   ├── 一句话 key innovation / insight / contribution
│   │   └── Contribution N
│   │       ├── 为了解决什么问题
│   │       ├── 具体怎么做
│   │       └── Advantage / insight
│   └── Demos / applications
├── Method
│   ├── Overview
│   │   ├── 具体任务
│   │   ├── 输入
│   │   ├── 输出
│   │   └── 方法步骤
│   └── Pipeline module N
│       ├── Motivation
│       ├── 做法
│       ├── 为什么能 work
│       └── Technical advantage
├── Experiments
│   ├── Comparison experiments
│   └── Ablation studies
│       ├── Core contributions / important components 对性能的影响
│       └── 各 pipeline module / design choice 对性能的影响
└── Limitation
    ├── 局限
    ├── 为什么会有该局限
    ├── 影响范围
    └── 作者明确陈述 / 分析推断 + 证据锚点
```

`Abstract` is a concise synopsis derived from the full read; do not copy the paper abstract
verbatim. `Introduction`, `Method`, and `Experiments` contain the expanded structure. The
same challenge or contribution may appear in both synopsis and expanded form, but their
claims must remain consistent.

## JSON Canvas contract

- JSON Canvas 1.0 object: `{"nodes": [...], "edges": [...]}`.
- Use editable `text` nodes. Each node has a unique 16-character lowercase hexadecimal
  `id`, integer `x`, `y`, `width`, `height`, and Markdown `text`.
- Each edge has its own unique 16-character hexadecimal `id`, valid `fromNode` and
  `toNode`, `fromSide: "right"`, `toSide: "left"`, and `toEnd: "arrow"`.
- Lay out the tree left-to-right with 50–100 px gaps and no overlaps. Use the figure's
  branch colors consistently: Abstract `"1"`, Introduction `"2"`, Method `"3"`,
  Experiments `"4"`, Limitation `"5"`.
- The root node includes a wikilink to `[[<paper>分析]]`.
- Put evidence anchors in the relevant leaf text, using the same anchors as the Markdown
  note.

After every create or edit, parse the JSON, confirm all node/edge IDs are globally unique,
and confirm every edge endpoint exists.

## Hub registration

JSON Canvas 1.0 has no YAML frontmatter and its top-level object remains only the standard
`nodes`/`edges` payload. Register the Canvas separately in the Vault-side
`.scholar-workflow/artifacts.yml`; never add Hub-only keys to the Canvas JSON and never
infer identity from its filename.

Preserve every unrelated manifest row. Create or update exactly one row with stable IDs
matching the paired Markdown note:

```yaml
schema_version: 1
artifacts:
  - artifact_id: analysis:<stable-paper-resource-id>:canvas
    kind: analysis-canvas
    format: canvas
    vault_path: <topic-relative-path>/<paper>解析树.canvas
    resource_id: <existing-hub-resource-id>
    topic_id: <existing-hub-topic-id>
    parent_id: analysis:<stable-paper-resource-id>
```

If the Canvas is renamed or moved, update only `vault_path`; its `artifact_id` stays fixed.
The referenced file must already exist, stay inside the Vault, and not traverse a symlink.

## Editable-update rule

An existing Canvas is human-editable state, not a disposable render. Read it before an
update. Preserve node IDs, positions, dimensions, colors, and user-added nodes/edges.
Change the text of an existing generated node only when the underlying analysis changes;
add or remove generated subtrees only when the paper analysis requires it. A focused pass
updates only its matching subtree. If the first run is focused rather than whole-paper,
create only the root and covered branch, then expand the same Canvas on later passes.
