# Required Paper Analysis Output Template

This is the current observable output contract for a paper that has been read and
analyzed. It follows the user's generic paper-analysis reference image.
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
- Markdown also shows verified source-region images beside the analysis they support:
  include selected key process figures and result tables in the corresponding Method
  and Experiments text, not only in Canvas. Relevant paragraph crops may supplement
  the body. Keep readable figure/table captions, necessary labels/conditions, original
  quotations and exact source-page links; an image does not replace that prose or
  evidence. Reuse already owned, verified assets rather than taking duplicate crops.
  Use the v5 Markdown source-image projection in `analysis-v5-format.md` when the
  installed runtime supports it. Body-only paragraph crops retain the shared image
  contract in `analysis-format.md`. Neither route authorizes a single-file patch.
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
- Alignment and non-crossing are hard requirements: generated nodes at the same
  hierarchy depth share a left edge; siblings follow consistent spacing and each
  subtree occupies its own vertical band. Connections never cross unrelated branches
  or pass through a node. A shared trunk among siblings is allowed, not a crossing.
  Every visible human graph item, including preserved text, file, link and group nodes,
  must leave managed content and its links unobscured. Extra edges that touch or cross
  managed content obey the same crossing and occlusion checks; being user-created
  does not bypass them. Independent safe human graph items remain preserved.
  Fixed endpoint sides are required for a provable route; automatically floating
  endpoints or otherwise unprovable paths do not qualify as non-crossing. Report
  the conflict without deleting or rewriting human graph items.
- Preserve compact two-dimensional placement rather than copying the tall screenshot's
  coordinates. Boxes fit their visible content plus roughly one extra line for clicks;
  text, source links and backlinks must not be clipped or obscured. Readability and
  editability remain subject to explicit human assessment in Obsidian.
- Preserve stable identities, safe human layout and unrelated user-created nodes.
  One paper's Markdown, Canvas and sidecar remain together in its mapped paper folder;
  the Zotero PDF stays in Zotero. Existing pairs are not bulk regenerated or migrated
  merely because this output specification changed.
- An Analysis/back-to-body link must open this pair's exact Markdown file and block,
  not another same-named note. The v5 explicit companion-route interface is defined
  in `analysis-v5-format.md`; a moved review copy needs its own verified route.

Scope, evidence states, reader verification, paired conflict/CAS protection and source
ownership retain the boundaries in `analysis-format.md` and the shared policies.
A focused result declares its selected branches; it must not silently remove sibling
branches or be presented as a complete whole-paper result.

## Selected Canvas images

Canvas image supplements are limited to **experimental data tables** and **key
pipeline / process diagrams**. Paragraph crops and verbatim excerpts belong in
Markdown, not Canvas. This restriction concerns image supplements; it does not
replace any required editable framework or claim/point node.

- Place a data table beside its corresponding comparison or ablation content under
  Experiments; place a key process diagram beside Method Overview or its actual module.
  Keep each image associated with that content, not a detached evidence gallery.
- Preserve the source table's caption, column/row labels, units and necessary conditions;
  preserve a process diagram's labels, legend and meaningful connections. A crop must
  not hide a qualification or imply that an agent-redrawn diagram is an original figure.
- Keep a readable figure/table identifier, verified source-page entry and exact
  Markdown-block backlink beside each image. Use explicitly owned paper-local assets
  with their hashes and replay inputs, following the existing source/image contract in
  `analysis-format.md` and the shared knowledge reproduction contract.
- Images supplement the editable text tree; they never flatten it into a bitmap or
  replace named subslots, evidence links or material qualifications. Apply the same
  alignment, crossing, occlusion and readable-size requirements to the actual graph,
  including images and their captions. Preserve a safe accepted layout when updating.

Do not bulk add images to existing pairs. Use a verified installed paired interface
that can represent and validate the selected supplements; an unsupported generator
must report the limitation rather than hand-edit one managed file or claim completion.

## Compatibility and completion boundary

The IR v4 machine schema and renderer implement the older four-branch tree
and one grouped details node per claim. `analysis-format.md` describes that versioned
compatibility interface. They do **not** implement this five-branch template.
New analyses use the explicit v5 interface in `analysis-v5-format.md`. Check installed
runtime support rather than inferring capability from the specification or a source checkout.
Do not label a four-branch v4 render as a conformant new-format result, put Experiments
under Method/Limitation to evade the schema, or bypass paired validation to save it.
When the available tool cannot represent this template, report that implementation
limitation and return a noncanonical proposal rather than a validated success.

Count actual independently rendered nodes; do not use the old grouped-node accounting
to conceal expanded nodes.
If a geometry or node budget conflicts with required content, report the conflict
instead of merging away named slots, dropping content or silently relaxing a limit.
An explicit format conversion preserves prior source/claim content and follows the
ordinary paired review and conflict protections; it is not an automatic refresh.

Completion for this template requires independent checks of all five branches, the
required subslots and parent-child edges, point-local evidence/links/backlinks, editable
nodes and readable geometry. Passing quotation tests or an older layout fixture does
not establish new-template conformity. Scientific source fidelity and installed-product
human assessment remain separate from structural conformance.
