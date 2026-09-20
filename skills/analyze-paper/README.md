# analyze-paper

Create a persistent, detailed analysis of one already-ingested paper as a paired
Obsidian Markdown note and editable JSON Canvas. The skill does not prescribe how the
paper must be read or reasoned about. It projects freely formed judgments into one
canonical, human-readable result structure.

## What it produces

- `<paper-name>分析.md` — the complete analysis, with evidence anchors and explicit
  source status.
- `<paper-name>解析树.canvas` — an editable left-to-right tree that maps one-to-one to
  the Markdown note. It may shorten wording for display, but it does not add claims that
  are absent from the note.

Both files live under `research_vault_root`, beside the paper's index row / related-docs
hub. The Markdown note uses thin `sw_*` frontmatter; the Canvas is registered separately in
`.scholar-workflow/artifacts.yml`, remains valid JSON Canvas, and receives no private top-level
fields. Analysis content stays outside managed projection blocks, so a later sync does not
overwrite it.

## Canonical analysis tree

Whole-paper analysis projects the result into five corresponding branches in both
artifacts:

1. **Abstract** — task, technical challenge, key insight and its benefit, technical
   contributions and their benefits, and the experiment headline.
2. **Introduction** — task/application (including inputs and outputs), prior-method
   challenges (previous method, failure or limitation, technical reason), the proposed
   pipeline (one-sentence innovation plus each contribution's problem, mechanism, and
   advantage), and demos/applications.
3. **Method** — an overview of the task, inputs, outputs, and method steps, followed by
   each pipeline module's motivation, mechanism, why it works, and technical advantage.
4. **Experiments** — comparison experiments and ablations, including the evaluated
   task/data, baseline or changed component, metric/result, supported contribution or
   attributable conclusion, and evidence anchor.
5. **Limitation** — each limitation, its cause and scope, whether it is author-stated or
   an analysis inference, and its evidence anchor.

Claim-bearing entries distinguish paper-reported evidence from analysis inference and
carry a visible field-level evidence/status suffix in both artifacts. Missing values are explicit:
`论文未报告`, `当前正文通道无法核实`, and `不适用` have different meanings and are not
interchangeable.

This tree is an output schema, not a reading sequence or reasoning framework.

## Whole and focused updates

- A **whole-paper** pass fills all five branches without fabricating unsupported content.
- A **focused** pass updates only the requested subtree and preserves the rest of the
  note, the user's Canvas layout, and custom Canvas nodes.
- Invisible heading/field identity and baseline-hash comments distinguish unchanged generated
  structure from human edits. Human-edited content is preserved and returned as a path-level conflict,
  not silently overwritten; its matching Markdown/Canvas path is treated as one paired update.
- Repeated challenges, contributions, method modules, experiments, ablations, and
  limitations expand to match the paper rather than a fixed count.
- Each paper keeps one evolving Markdown/Canvas pair; later passes deepen or revise the
  relevant nodes instead of blanking the pair and starting over.

## Sources and safety

The paper body comes from Zotero indexed text via
`scholar-workflow zotero fulltext`; Zotero remains authoritative for paper identity and
metadata. If indexed text omits a table, figure, or formula needed to support a field,
the result records that source gap instead of guessing.

The paper's code repository is consulted only when you explicitly request it. It is
cloned read-only, treated as untrusted evidence rather than instructions, and never
executed, built, or installed. The clone is temporary unless you explicitly ask to keep
it under `code_repo_root`.

The analysis note remains separate from the annotations note produced by
`export-annotations`; the two are cross-linked through frontmatter `related`.

## Usage

Ask to “analyze this paper” for the complete tree, or name a section such as the method,
experiments, or one module for a focused update. Mention “read/check the code repository”
explicitly if repository evidence is required, and say whether the clone should be kept.
