# Paper Analysis Output Contract

This file defines the observable result of `analyze-paper`: one detailed Markdown note and
one editable Obsidian JSON Canvas. It does not prescribe how the model reads, reasons,
classifies, or reaches a judgment. The structure below is only the projection of that result.

The two artifacts sit beside each other:

```text
<paper>分析.md
<paper>解析树.canvas
```

The Markdown note is the detailed, evidence-bearing record. The Canvas is a concise visual
projection of the same claims. A Canvas leaf may summarize the note, but it must not add a
claim that the note does not contain.

## Canonical content tree

A whole-paper result contains all five top-level branches and every listed field. Repeat
challenge, contribution, module, comparison, ablation, and limitation subtrees as needed.
A focused result contains only the requested branch or subtree; it does not create empty
siblings.

```text
Paper analysis
├── Abstract
│   ├── Task
│   ├── Technical challenge for previous methods
│   ├── Key insight / motivation
│   │   ├── 一句话洞见 / 动机
│   │   └── 洞见的好处
│   ├── Technical contributions
│   │   └── Contribution N
│   │       ├── 一句话贡献
│   │       └── 贡献的好处
│   └── Experiment headline
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
│   │       ├── Technical reason
│   │       └── Evidence
│   ├── Our pipeline
│   │   ├── 一句话 key innovation / insight / contribution
│   │   └── Contribution N
│   │       ├── 为了解决什么问题
│   │       ├── 具体怎么做
│   │       ├── Advantage / insight
│   │       └── Evidence
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
│       ├── 为什么有效
│       ├── Technical advantage
│       ├── 对应挑战 / 贡献
│       └── Evidence
├── Experiments
│   ├── Comparison experiment N
│   │   ├── 任务 / 数据
│   │   ├── Baseline / metric
│   │   ├── 关键结果
│   │   ├── 支撑的贡献
│   │   └── Evidence
│   └── Ablation study N
│       ├── 模块 / 设计选择
│       ├── 改动
│       ├── 性能影响
│       ├── 可归因结论
│       └── Evidence
└── Limitation
    └── Limitation N
        ├── 局限
        ├── 成因
        ├── 影响范围
        ├── 作者明确陈述 / 分析推断
        └── Evidence
```

## Evidence and availability states

Every claim-bearing field carries a paper-local anchor or an explicit status. Prefer
`§3.2`, `Table 4`, `Figure 6`, `Eq. (7)`, or a PDF page. Use exactly one of these states:

- **作者明确陈述 · `<anchor>`** — the paper states the claim.
- **分析推断 · `<supporting observations>`** — the result is an interpretation; never
  present it as the authors' claim.
- **论文未报告** — the available paper content shows that an applicable item is absent.
- **当前正文通道无法核实 · `<missing material>`** — Zotero indexed text does not expose
  the table, figure, equation, page, or other material required to verify it.
- **不适用 · `<reason>`** — the field does not apply to this paper.

A repository file and line may supplement an implementation claim only when code inspection
was requested. It never replaces a paper anchor for a paper claim.

Every generated claim field uses one visible suffix, in both Markdown and Canvas:

```text
<field>: <value> 〔作者明确陈述 · <anchor>〕
<field>: <value> 〔分析推断 · <supporting observations>〕
<field>: 〔论文未报告〕
<field>: 〔当前正文通道无法核实 · <missing material>〕
<field>: 〔不适用 · <reason>〕
```

The suffix belongs to the field it follows; a subsection-level `Evidence` entry is a compact
field-to-anchor index and does not replace these field-level suffixes. Canvas leaves retain the
same suffix even when their visible wording is shorter.

## Markdown projection

Keep the note natural to read. Use the following headings by default; translate labels only
when the user asks, while retaining the same hierarchy and fields.

```markdown
# <论文标题>：结构化解析

## Abstract｜结论速览

### Task
- **任务与应用：** <value> 〔<evidence-or-availability-state>〕

### Technical challenge for previous methods
- **核心挑战：** <value> 〔<evidence-or-availability-state>〕

### Key insight / motivation
- **一句话洞见 / 动机：** <value> 〔<evidence-or-availability-state>〕
- **洞见的好处：** <value> 〔<evidence-or-availability-state>〕

### Technical contributions
#### Contribution N：<名称>
- **一句话贡献：** <value> 〔<evidence-or-availability-state>〕
- **贡献的好处：** <value> 〔<evidence-or-availability-state>〕

### Experiment headline
- **主要实验结论：** <value> 〔<evidence-or-availability-state>〕

## Introduction｜问题背景与解法

### Task and application
- **具体任务：** <value> 〔<evidence-or-availability-state>〕
- **输入：** <value> 〔<evidence-or-availability-state>〕
- **输出：** <value> 〔<evidence-or-availability-state>〕
- **应用：** <value> 〔<evidence-or-availability-state>〕

### Technical challenges for previous methods
#### Technical challenge N：<名称>
- **Previous method：** <value> 〔<evidence-or-availability-state>〕
- **Failure cases / limitation：** <value> 〔<evidence-or-availability-state>〕
- **Technical reason：** <value> 〔<evidence-or-availability-state>〕
- **Evidence：** <field → state/anchor map>

### Our pipeline
- **一句话 key innovation / insight / contribution：** <value> 〔<evidence-or-availability-state>〕

#### Contribution N：<名称>
- **为了解决什么问题：** <value> 〔<evidence-or-availability-state>〕
- **具体怎么做：** <value> 〔<evidence-or-availability-state>〕
- **Advantage / insight：** <value> 〔<evidence-or-availability-state>〕
- **Evidence：** <field → state/anchor map>

### Demos / applications
- **演示或应用：** <value> 〔<evidence-or-availability-state>〕

## Method｜方法

### Overview
- **具体任务：** <value> 〔<evidence-or-availability-state>〕
- **输入：** <value> 〔<evidence-or-availability-state>〕
- **输出：** <value> 〔<evidence-or-availability-state>〕
- **方法步骤：**
  1. <step> 〔<evidence-or-availability-state>〕

### Pipeline module N：<名称>
- **Motivation：** <value> 〔<evidence-or-availability-state>〕
- **做法：** <value> 〔<evidence-or-availability-state>〕
- **为什么有效：** <value> 〔<evidence-or-availability-state>〕
- **Technical advantage：** <value> 〔<evidence-or-availability-state>〕
- **对应挑战 / 贡献：** <value> 〔<evidence-or-availability-state>〕
- **Evidence：** <field → state/anchor map>

## Experiments｜实验

### Comparison experiment N：<名称>
- **任务 / 数据：** <value> 〔<evidence-or-availability-state>〕
- **Baseline / metric：** <value> 〔<evidence-or-availability-state>〕
- **关键结果：** <value> 〔<evidence-or-availability-state>〕
- **支撑的贡献：** <value> 〔<evidence-or-availability-state>〕
- **Evidence：** <field → state/anchor map>

### Ablation study N：<名称>
- **模块 / 设计选择：** <value> 〔<evidence-or-availability-state>〕
- **改动：** <value> 〔<evidence-or-availability-state>〕
- **性能影响：** <value> 〔<evidence-or-availability-state>〕
- **可归因结论：** <value> 〔<evidence-or-availability-state>〕
- **Evidence：** <field → state/anchor map>

## Limitation｜局限

### Limitation N：<名称>
- **局限：** <value> 〔<evidence-or-availability-state>〕
- **成因：** <value> 〔<evidence-or-availability-state>〕
- **影响范围：** <value> 〔<evidence-or-availability-state>〕
- **归属：** 作者明确陈述 / 分析推断
- **Evidence：** <field → state/anchor map>
```

For a whole-paper result, do not silently omit a canonical field: use an availability state
when no verified value can be supplied. For a focused result, omit branches outside the
requested scope. Human-authored prose may appear around this structure and is preserved on
later updates.

### Generated-field identity and human-edit conflicts

Every generated Markdown heading (root, fixed structural, or repeated), every generated Markdown
field, and every generated Canvas node ends with an invisible Markdown comment:

```markdown
<!-- sw-analysis-field path="introduction/challenges/challenge-01/technical-reason" base_sha256="<64 lowercase hex>" -->
```

In Markdown, put the comment on the line immediately after the heading or field it identifies.
In Canvas, append it on a new line inside that node's `text`. The canonical path is stable for
the life of the field. A repeated subtree receives its path segment on first creation and keeps
it even when display order changes. The marker path is the same canonical field path used to
derive the generated Canvas node ID.

`base_sha256` uses the exact source fragment immediately preceding its marker: for Markdown, the
identified heading/field line plus its continuation lines; for Canvas, the node `text` before the
final marker line. Remove the marker, then compute exactly:

```python
normalized = "\n".join(line.rstrip(" \t") for line in visible_fragment.splitlines())
base_sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

Do not add a terminal newline and do not apply Unicode normalization. These comments are
field-identity metadata, not the managed projection blocks used by `sync-projections`; they do not
make surrounding prose machine-owned.

Update behavior is fail-safe:

- An unmarked heading/field/node, content whose marker was removed, and a malformed marker are
  human-owned and remain unchanged. Legacy unmarked analysis content is not adopted
  automatically; add markers only after the user explicitly approves that field-level adoption.
- When the current visible-value hash equals `base_sha256`, the generated field may be changed
  within the requested scope; the new value receives a new baseline hash.
- When the hashes differ, the field is human-edited. Preserve it verbatim and report its canonical
  path plus the proposed value as a conflict. Replace it only after the user explicitly accepts
  that field-level change.
- The Markdown heading or field and Canvas node with the same canonical path form one cross-artifact update
  unit. If either side is missing, malformed, human-owned, or baseline-conflicted, change neither
  side; preserve both current values and report one paired conflict with the proposed value. A new
  path is created on both sides together. Prepare and validate both file revisions before writing;
  if an external write still fails after one file changes, report the resulting mismatch
  immediately rather than continuing other updates.
- Remove a generated repeated subtree only when all its generated fields still match their
  baselines and it contains no unmarked/user-created content or custom edge. Otherwise preserve
  it and report the conflict.
- A Canvas node without a generated field marker is user-created. A Canvas edge is generated
  only when its ID matches the deterministic canonical-path edge ID below; all other edges are
  user-created. If a generated edge's endpoints or direction fields differ from the canonical
  values, treat it as human-edited, preserve it, and report the conflict.

### Markdown Hub identity

Reuse existing stable IDs. On first creation, derive the catalog identity from the paper
resource identity, never from the filename. Keep analysis prose outside managed blocks and
use only the allowlisted `sw_*` fields:

```yaml
---
sw_schema: 1
sw_kind: paper-analysis
sw_catalog_id: analysis:<stable-paper-resource-id>
sw_resource_id: <existing-hub-resource-id>
sw_topic_id: <existing-hub-topic-id>
related:
  - "[[<paper>解析树.canvas]]"
---
```

Renaming the Markdown file does not change `sw_catalog_id`. Cross-link a separate annotations
note in `related` when one exists; do not merge annotation content into the analysis note.

## Canvas projection

Use a JSON Canvas 1.0 document with the exact top-level shape
`{"nodes": [...], "edges": [...]}`. Represent the canonical tree with editable `text` nodes
and directed parent-to-child edges. The root is `论文解析树\n[[<paper>分析]]`.

- Each node has a unique 16-character lowercase hexadecimal `id`, integer `x`, `y`,
  `width`, `height`, and Markdown `text`.
- Each edge has its own unique 16-character lowercase hexadecimal `id`, valid `fromNode`
  and `toNode`, `fromSide: "right"`, `toSide: "left"`, and `toEnd: "arrow"`.
- Lay out branches left-to-right with 50–100 px gaps and no overlap. Use branch colors
  consistently: Abstract `"1"`, Introduction `"2"`, Method `"3"`, Experiments `"4"`,
  Limitation `"5"`.
- A leaf contains its label, concise paper-specific value, and evidence/availability state;
  a node containing only a field label is incomplete.
- Every generated node carries the `sw-analysis-field` marker and baseline hash described above;
  the visible text excludes that marker when comparing claims with Markdown.
- A new generated node ID is the first 16 lowercase hexadecimal characters of
  `SHA-256("<analysis-artifact-id>\n<canonical-field-path>")`; a generated edge uses
  `SHA-256("edge\n<from-path>\n<to-path>")` the same way. Existing IDs always win. On the
  improbable collision between two valid generated paths, append `#2`, `#3`, ... to the second
  hashed path until unique and then preserve that ID. If the canonical ID is occupied by an
  unmarked, malformed, or differently marked user-owned node, report a field conflict and create
  no duplicate; the `#2` fallback is not an ownership bypass. A repeatable subtree's path segment
  is assigned on first creation and retained as its identity; never renumber surviving siblings
  merely because display ordering changed.
- Parse the JSON after every change, verify global node/edge ID uniqueness, and verify that
  every edge endpoint exists.

### Canvas Hub identity

Canvas JSON receives no frontmatter or Hub-only keys. Register it in the Vault-side
`.scholar-workflow/artifacts.yml`, preserving every unrelated row:

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

The file must already exist inside the Vault and must not traverse a symlink. A move changes
only `vault_path`; `artifact_id` remains stable.

## Update and preservation contract

- Read both existing artifacts before an update.
- Whole-paper updates may update all canonical branches; focused updates modify only their
  matching Markdown section and Canvas subtree.
- Apply the generated-field baseline rules before changing or deleting content. Preserve
  unrelated human prose, human-edited fields, existing semantic headings, node IDs, positions,
  dimensions, colors, and user-created nodes/edges.
- Add or remove generated repeated subtrees only when the analysis result changes. Never
  regenerate an existing Canvas wholesale.
- Keep Markdown and Canvas claims synchronized. If one side cannot be updated safely, report
  the paired canonical-path conflict and leave both sides unchanged instead of silently diverging.
- Keep the analysis pair, annotations note, and literature-tree notes separate. This skill
  does not modify literature-tree placement.
