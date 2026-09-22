# Paper Analysis v2 Output Contract

This contract governs the observable output of `analyze-paper`. It constrains artifact
identity, roles, evidence placement, cross-artifact links, and readable layout. It does not
prescribe how a model reads a paper or forms its judgment.

## Artifact pair

Each paper has one evolving pair under its knowledge-space folder:

```text
<paper>分析.md
<paper>解析树.canvas
```

The Markdown note is the complete, independently readable analysis. The Canvas is a concise,
editable projection of the same claims; it is never the only human-readable version and may not
introduce claims absent from the note.

Analysis, annotations, literature trees, and the source PDF remain separate artifacts.

## Profiles and observable roles

Every run declares an analysis profile:

- `whole` covers all five roles: **Task, Input, Workflow, Output, Boundary**.
- `focused` names a non-empty subset and emits only that subset. Existing roles outside the
  requested subset remain unchanged.

The roles are an output interface, not a reading sequence:

| Role | Observable content |
|---|---|
| Task | The problem, intended capability, application, and paper-specific motivation |
| Input | Data, observations, representations, assumptions, and prerequisites |
| Workflow | One ordered end-to-end flow containing the method's actual steps |
| Output | Produced representation/result and experiment-backed capabilities |
| Boundary | Limitations, applicability limits, source gaps, and inferential boundaries |

Workflow nodes describe actual method steps. Do not add `对应挑战`, `对应贡献`,
`corresponding challenge`, or `corresponding contribution` nodes when they are not steps in the
paper's flow. Discuss motivation or advantages inside the relevant step when needed.

The versioned machine contract is
`${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`. A claim has a stable `claim_id`, one
role, a human-facing title and body, one evidence state, and an `order` only for Workflow steps.
Whole-paper IR must cover every role. Focused IR must cover exactly its declared role subset.

## Inline evidence

Every claim carries exactly one visible evidence or availability suffix in both artifacts:

```text
〔作者明确陈述 · <paper-local anchor>〕
〔分析推断 · <supporting observations>〕
〔论文未报告〕
〔当前正文通道无法核实 · <missing material>〕
〔不适用 · <reason>〕
```

Use paper-local anchors such as `§3.2`, `Table 4`, `Figure 6`, `Eq. (7)`, or a PDF page. A
repository file/line may supplement an implementation claim only when code inspection was
requested; it never replaces the paper anchor for a paper claim.

Evidence remains in the same Markdown block and Canvas node as its claim. Do not create a
standalone Evidence section, Evidence table, or Evidence node. `论文未报告` means the available
paper content supports absence; `当前正文通道无法核实` means the indexed-text channel omitted
material needed for verification.

## Markdown projection

Keep machine metadata thin and keep the body natural to read:

```markdown
---
sw_schema: 2
sw_kind: paper-analysis
sw_catalog_id: "analysis:<stable-paper-resource-id>"
sw_analysis_profile: whole
---

# <论文标题>：论文分析

> 分析范围：全文（任务、输入、分步流程、输出、边界）

## 任务

### <claim title>
<human-readable explanation> 〔作者明确陈述 · §1〕 ^claim-<claim-id>
<!-- sw-analysis-claim id="<claim-id>" role="task" -->

## 输入

...

## 分步流程

1. **<step title>。** <explanation> 〔作者明确陈述 · §3.1〕 ^claim-<claim-id>
<!-- sw-analysis-claim id="<claim-id>" role="workflow" -->

## 输出

...

## 边界

...
```

For a focused result, replace the scope line with the declared subset and omit unrequested role
headings from a newly created projection. When updating an existing pair, preserve all
unrequested roles and surrounding human prose.

The `sw-analysis-claim` comment is identity metadata. It must not contain analysis prose. A
missing or malformed marker makes the corresponding existing block human-owned. Preserve such
content and report the conflict rather than adopting or overwriting it silently. If a maintained
baseline or revision receipt says either side was human-edited, preserve the Markdown/Canvas
pair for that claim and report one paired conflict.

## Canvas projection

Use standard JSON Canvas 1.0 with the exact top-level shape:

```json
{"nodes": [], "edges": []}
```

The visible graph uses this hierarchy:

```text
Paper analysis
├── Task
├── Input
├── Workflow: step 1 → step 2 → ...
├── Output
└── Boundary
```

Rules:

- Use editable text nodes and directed edges. Generated IDs are stable for an artifact and
  canonical role/claim path; preserve existing IDs on update.
- The renderer-owned subgraph contains at most 40 semantic nodes, including root and role nodes.
  User-created text, file, link, and group nodes do not consume that budget and are not adopted
  merely because they share the Canvas.
- Generated text nodes are at least 360 px wide and 140 px high. Use Markdown headings in node
  text, consistent branch colors, generous spacing, and non-overlapping positions.
- Workflow steps form one visible ordered flow instead of repeating disconnected module trees.
- Each claim node contains its claim and evidence suffix together, plus
  `[[<paper>分析#^claim-<claim-id>|正文]]`. This is the evidence backlink to the detailed note.
- A generated claim node carries the matching `sw-analysis-claim` marker. Nodes without a valid
  generated marker and non-generated edges are user-owned and remain unchanged.
- After any update, parse the JSON, verify unique node/edge IDs and every endpoint across the whole
  Canvas, then verify claim coverage/backlinks and readable geometry only for the renderer-owned
  subgraph. A dangling user edge is invalid, but a user node is not rejected for its type, size, or
  overlap with the generated layout.

Canvas JSON receives no private top-level keys. Register it in the Vault-side
`.scholar-workflow/artifacts.yml`, preserving unrelated rows:

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
only `vault_path`; stable artifact identity does not depend on the filename or loopback URL.

## Conformance boundary

Hard conformance validates schema version, profile coverage, stable IDs, inline evidence,
Markdown claim content and anchors, Canvas claim content/backlinking/geometry/edges, the ordered
Workflow flow, and the 40-node limit. It does not score prose style, argument count, analysis
framework, or wording.

Every newly rendered pair receives a baseline sidecar that binds the source IR, full Markdown
revision, claim hashes, and only the exact node/edge IDs emitted by the renderer. Its Canvas hash
covers generated node content and generated edge endpoints, not user nodes, user edges, styling, or
layout. A focused update is first planned as a zero-write operation: it preserves custom graph
items and valid human layout, while a generated-content/endpoint edit, unsafe graph, missing or
corrupt baseline, or Markdown revision conflict produces one paired conflict and a proposed result.
It never silently rebases or overwrites either artifact.

The checked-in runtime contracts are:

- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`
- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-baseline.schema.json`
- `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-conformance-report.schema.json`

For a user-selected multi-paper run, also load `references/analysis-batch.md` before staging any
artifact.
