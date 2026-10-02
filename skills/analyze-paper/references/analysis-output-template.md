# Required Paper Analysis Output Template

This is the current observable output contract for a paper that has been read and
analyzed. It follows the user's generic reference image supplied on 2026-10-02.
It defines the delivered Markdown and editable Canvas, not a required reading order,
reasoning procedure, or repetition of a previously analyzed paper.

## Required framework

A whole-paper output has these five first-level branches, in this order. Repeated
challenges, contributions and modules follow the paper's actual content; the image's
example counts and ellipses are not facts or fixed counts to copy into an analysis.

```text
Paper
├── Abstract
│   ├── Task
│   ├── Technical challenge for previous methods
│   ├── Key insight / motivation
│   │   ├── One-sentence insight / motivation
│   │   └── Benefit of the insight / motivation
│   ├── Technical contributions
│   │   └── Technical contribution <n>
│   │       ├── One-sentence technical contribution
│   │       └── Benefit of the technical contribution
│   └── Experiment
├── Introduction
│   ├── Task and application
│   ├── Technical challenge for previous methods
│   │   └── Technical challenge <n>
│   │       ├── Previous method
│   │       ├── Failure cases (Limitation)
│   │       └── Technical reason
│   ├── Our pipeline
│   │   ├── One-sentence key innovation / insight / contribution
│   │   └── Contribution <n>
│   │       ├── Problem addressed
│   │       ├── How it is done
│   │       └── Advantage / insight
│   └── Demos / applications
├── Method
│   ├── Overview
│   │   ├── Task / input / output
│   │   └── Method / steps
│   └── Pipeline module <n>
│       ├── Motivation
│       ├── Method
│       ├── Why it works
│       └── Technical advantage
├── Experiments
│   ├── Comparison experiments
│   └── Ablation studies
│       ├── Effects of core contributions / important components
│       └── Effects of design choices in each pipeline module
└── Limitation
```

The Limitation branch contains the limitations and reasoned explanations of why they
arise, not just a list of unsupported weaknesses. The Abstract's singular Experiment
slot is the concise abstract-level account; it does not replace the independent
Experiments branch. A benefit may be left unfilled when the source does not support it
or it is explained in the corresponding contribution. Unfilled slots preserve the
framework without inventing statements or claiming that the paper reports nothing.

Keep insight/motivation distinct from concrete technical contributions. Introduction
challenges distinguish an earlier method, its observed failure/limitation and the
technical reason. Each contribution explains what it does and its advantage, plus
the problem addressed where applicable. Method Overview states the actual task,
inputs, outputs and ordered process; keep the process steps together rather than
scattering them into separate step nodes. Method modules do not add an invented
corresponding-challenge or corresponding-contribution axis.

## Markdown and Canvas projection

- Markdown uses the same five-branch order and the named nested slots, with complete,
  independently readable explanations. The selected English or Chinese presentation
  language governs its framework labels and the Canvas labels consistently.
- Canvas preserves the parent-child relationships in the tree above. Repeated
  challenge/contribution/module instances and their supplied named subslots are
  separate editable nodes. A single grouped details card is not a substitute for
  the reference image's sibling subnodes.
- Each fact-bearing node retains its own concise text, inline evidence, verified
  original-source entry and exact Markdown-block backlink. Evidence is not a separate
  branch. Canvas summaries must not add facts or lose material qualifications.
- Verbatim, original-language short quotations appear next to their own statement
  in Markdown only, with the same source-location link. Canvas retains source links
  and evidence, but does not repeat quotations or add quotation nodes. Quote text
  escaping, attribution and source verification follow `analysis-format.md`.
- Use native editable JSON Canvas text nodes, fine straight square-routed arrowless
  connections, and the reference image's tree-like label treatment. An image, SVG,
  four/five dashboard cards or a flattened text outline is not an editable substitute.
- Preserve compact two-dimensional placement rather than copying the tall screenshot's
  coordinates. Boxes fit their visible content plus roughly one extra line for clicks;
  text, source links and backlinks must not be clipped or obscured. Readability and
  editability remain subject to explicit human assessment in Obsidian.
- Preserve stable identities, safe human layout and unrelated user-created nodes.
  One paper's Markdown, Canvas and sidecar remain together in its mapped paper folder;
  the Zotero PDF stays in Zotero. Existing pairs are not bulk regenerated or migrated
  merely because this output specification changed.

Scope, evidence states, reader verification, paired conflict/CAS protection and source
ownership retain the boundaries in `analysis-format.md` and the shared policies.
A focused result declares its selected branches; it must not silently remove sibling
branches or be presented as a complete whole-paper result.

## Compatibility and completion boundary

The existing IR v4 machine schema and renderer implement the older four-branch tree
and one grouped details node per claim. `analysis-format.md` describes that versioned
compatibility interface. They do **not** yet implement this five-branch template.
Do not label a four-branch v4 render as a conformant new-format result, put Experiments
under Method/Limitation to evade the schema, or bypass paired validation to save it.
When the available tool cannot represent this template, report that implementation
limitation and return a noncanonical proposal rather than a validated success.

A versioned implementation must adapt schema, model, Markdown/Canvas renderers,
conformance and baseline/update compatibility together. Count actual independently
rendered nodes; do not use the old grouped-node accounting to conceal expanded nodes.
If a geometry or node budget conflicts with required content, report the conflict
instead of merging away named slots, dropping content or silently relaxing a limit.
An explicit format conversion preserves prior source/claim content and follows the
ordinary paired review and conflict protections; it is not an automatic refresh.

Completion for this template requires independent checks of all five branches, the
required subslots and parent-child edges, point-local evidence/links/backlinks, editable
nodes and readable geometry. Passing quotation tests or an older layout fixture does
not establish new-template conformity. Scientific source fidelity and installed-product
human assessment remain separate from structural conformance.
