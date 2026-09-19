# Structured Analysis Note Format

Use this format for the persistent analysis note. It records the causal chain from the
paper's problem through its evidence without mirroring the paper's section order.

## Hub identity

Keep the note human-readable, but register its stable identity in the YAML frontmatter.
Reuse an existing ID; on first creation use one stable ID derived from the paper resource
identity, not from the filename. Human fields such as `title`, `aliases`, and `related`
remain ordinary YAML and may coexist with this allowlisted layer:

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

Do not add an unrecognized `sw_*` field. Renaming the Markdown file does not change
`sw_catalog_id`.

For a whole-paper analysis, populate every applicable top-level section. For a focused
pass, update only the matching subtree and omit empty placeholders. Preserve existing
human content, reuse semantically equivalent headings, and keep all content outside
scholar-workflow managed blocks.

Use the following Chinese headings by default. Translate labels when the user requests
another language, but preserve the hierarchy and fields.

## 0. 结论速览

- **任务与应用：** task, input, output, and intended application.
- **前序方法的核心挑战：** the challenge the paper targets.
- **核心洞见 / 动机：** one-sentence high-level insight.
- **技术贡献：** one row per contribution in this table:

| 贡献 | 解决什么问题 | 核心做法 | 优势 / 洞见 | 证据锚点 |
|---|---|---|---|---|

- **实验结论：** the main empirical result in one or two sentences.

## 1. 问题背景与动机

### 1.1 任务与应用

- **任务：**
- **输入：**
- **输出：**
- **应用：**

### 1.2 前序方法的技术挑战

Repeat one subsection per challenge:

#### 挑战 N：<name>

- **前序方法：**
- **失败表现 / 局限：**
- **技术原因：**
- **证据锚点：** paper section, page, figure, or table.

### 1.3 本文的解法概览

- **一句话创新：**

| 贡献 | 对应挑战 | 怎么做 | 优势 / 洞见 | 证据锚点 |
|---|---|---|---|---|

- **演示 / 应用：** include only when the paper presents them.

## 2. 方法

### 2.1 Pipeline 总览

- **输入 / 输出：**
- **处理流程：** an ordered list of the actual pipeline stages.

Repeat one subsection per pipeline module:

### 2.N <module name>

- **动机：**
- **做法：**
- **为什么有效：**
- **技术优势：**
- **对应挑战 / 贡献：**
- **证据锚点：** paper section, equation, algorithm, figure, or table.

## 3. 实验

### 3.1 实验设置

- **数据集 / 任务：**
- **对比方法：**
- **指标：**

### 3.2 对比实验

| 结论 | 关键结果 | 支撑的贡献 | 证据锚点 |
|---|---|---|---|

### 3.3 消融实验

| 模块 / 设计选择 | 改动 | 性能影响 | 可归因结论 | 证据锚点 |
|---|---|---|---|---|

### 3.4 定性结果与应用

Include only when figures, demos, or applications provide evidence not captured by the
quantitative comparisons.

## 4. 局限

| 局限 | 成因 | 影响范围 | 依据 |
|---|---|---|---|

In `依据`, label each row as either **作者明确陈述** with a paper anchor or **分析推断**
with the observations that support it. Do not present an inference as the paper's claim.

## Evidence anchors

Prefer stable paper-local anchors such as `§3.2`, `Table 4`, `Figure 6`, `Eq. (7)`, or a
PDF page when section numbering is unavailable. A repository file/line may supplement an
implementation claim only when the user requested code inspection; it never replaces the
paper anchor for a paper claim.
