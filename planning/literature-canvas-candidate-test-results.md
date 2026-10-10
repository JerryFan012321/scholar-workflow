# Editable literature Canvas candidate: actual results

## Scope and current state

2026-10-09. This is a synthetic design candidate, not a released template,
installed-product acceptance, scientific verification or human approval. The
independent plan is `literature-canvas-candidate-test-plan.md`; the handwritten
inventory is `tests/fixtures/literature-evolution/CANVAS-EXPECTED.md`.

The editable candidate and browser previews are complete. Independent content and
side-anchor geometry checks passed; native editor rendering, effective font size,
editing, source navigation and human assessment remain pending. Synthetic source
links must not be used for reader tests.

## Candidate and independent observations

Artifacts live in the separate visualization session's
`literature-evolution-candidate/` directory, not in a Vault or runtime package:

- `literature-evolution.canvas`: native text nodes and arrowless edges;
- `preview.html`, `overview.png`, `relations.png` and separate detail SVGs;
- `GUIDE.md`: reading/editing instructions and pending checks;
- `source-provenance.json`: unchanged synthetic input and full source locators;
- `candidate-map.json`: node-location aid, not the scientific oracle;
- `baseline.json`: the selected fixture and seven pre-existing preview files.

An independent evaluator used the raw fixture and handwritten inventory, not the
producer's checker or results, to observe:

| Check | Actual result | Boundary |
|---|---|---|
| Paper reuse and classification | Seven ledger entries, eight contributions and eight complete classification statements retained | Same paper reused for two contributions; no new owner or real priority claim |
| Scientific relations | Two complete relations and ten full tradeoff statements retained, including reverse comparison | Scientific relations are not inferred from parent membership |
| Evidence and states | Sixteen source occurrences, ten unique page URIs; statement text, basis, section, page and unverified state match the fixture | Declared locators only; no link probing or scientific verification |
| Full provenance | Structured synthetic input equals the original fixture | All hashes, qualified identities, library IDs and attachment keys remain available outside readable cards |
| Native structure | Thirty-six text nodes, including four explicitly nonsemantic junctions; IDs globally unique and endpoints valid | JSON editability is not observed native editor behavior |
| Membership | Ten axis-aligned segments recover exactly six semantic parent pairs | Pending has no parent; only 1/2 occupy main/major branch |
| Geometry | Zero overlapping node interiors, unrelated-node penetration, non-junction crossing or ambiguous shared segment | Exact integer side anchors, no tolerance waiver; not an Obsidian rendering observation |
| Preservation | Original fixture, independent expectations and eight selected baseline files unchanged; five audited candidate files unchanged during evaluation | No old paper Canvas was selected, read or modified; absence in this destination is not a machine-wide assertion |

The independently observed Canvas SHA-256 is
`8059c4c0d61a70fb92973f61154415aeec6d553a944852c13ca4326f8cf68585`.

## Browser layout: failures and correction

The first browser observation was not a layout pass. Two relation cards were 116 px
short of their measured content, and five other cards left only 24 px instead of
the preview's 28 px line. Browser `errors: []` means no JavaScript page errors,
not sufficient card space. That observation is retained in
`initial-browser-observation.json`.

The intermediate `corrected-browser-observation.json` also did not pass: three
cards still overflowed and four others lacked a spare line, with a worst deficit
of 78 px. Preview HTML/SVG namespace handling and text layout were corrected
before final sizing. Neither intermediate render is recorded as successful.

The bounded correction resized cards from measured content and moved repeated
library/attachment identifiers into provenance. It retained every statement,
evidence basis, page link and full locator. Final `browser-observation.json`
records 32 readable cards at 20 px, no horizontal overflow, at least 28 px spare
space and no page errors. `overview.png` is 1240 × 1590; `relations.png` is
1380 × 1801. These are local browser renders, not Obsidian screenshots. No external
requests or synthetic-link clicks were used. The root agent visually inspected
both screenshots without treating that inspection as human approval.

The preview and tiny routing nodes still require native editor observation.
The conversation must ask the user to assess compactness, alignment, branch/local/
pending readability and the full relation cards; native editing, effective font
size and click space remain a separate later check. No runtime carrier/default was
selected from these automatic observations.

## Current development-tree regression

The full unit/contract regression was explained before execution. It used existing
isolated test fixtures and temporary test state; it did not run a real paper
analysis, experiment recipe, library migration or installed integration acceptance.

```text
rtk proxy uv run --offline --with pytest python -m pytest tests/unit tests/contract -q --tb=short
2417 passed, 11 warnings in 105.20s
```

The warnings include existing SWIG/PyMuPDF deprecations and Python's warning about
forking a multithreaded process. Passing these tests does not establish that those
warnings are harmless in all production environments.

Ruff passed for all 24 changed or untracked Python files in the current worktree.
`git diff --check` passed. A separate wider `ruff check src/scholar_workflow ...`
exited 1 with 52 diagnostics across 34 source files. A byte-diff check against
`HEAD` for all 34 files exited 0 with no differences: those diagnostics are
inherited in unchanged files, not introduced by this slice. They remain unresolved
technical debt; the full source lint result is not reported as passing. No bulk
formatting or unrelated repair was performed.

## Boundaries retained

- Existing single-paper Markdown/Canvas requirements and approvals remain intact.
- The seven-paper input remains the source of synthetic facts; the candidate is a
  view, not another ownership or scientific-relation store.
- No new Canvas CLI/default, package version, commit, publication or installation.
- No formal Vault, Zotero, real project, service or main-branch operation.
- Content preservation, orthogonal geometry, editor rendering and human judgment
  are separate checks. G17 remains incomplete.
