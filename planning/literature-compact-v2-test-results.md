# Literature Canvas compact v2: actual results

## Scope

2026-10-09. This is a synthetic layout candidate, not a runtime template change,
installed acceptance, scientific verification or human approval. The independent
expectations were frozen in `literature-compact-v2-test-plan.md` before construction.
Artifacts live in the visualization session's `literature-evolution-compact-v2/`.
No Vault, Zotero, project content, installation, service or version was changed.

## Observed results

An independent evaluator compared the original and new Canvas, preserved files,
raw input and an independently rendered browser preview. It did not modify the
candidate or rely on the producer's browser-observation file as its oracle.

| Check | Actual result |
|---|---|
| Eight overview boxes | Seven changed from 300 × 140 to 294 × 114, each 20.20% less area; pending changed from 300 × 170 to 294 × 142, 18.14% less area |
| Content preservation | All non-geometric fields of 36 nodes and all fields of 10 edges identical; mapping and provenance byte-identical |
| Original preservation | Original directory's 21-file set and every SHA-256 unchanged |
| Structure and geometry | Six semantic parent pairs unchanged; integer anchors, orthogonal arrowless segments; no overlaps, crossings, ambiguous shared segments or unrelated-node penetration |
| Browser readability | Independently observed 32 readable cards at 20 px/28 px line height, no scaling, each with 28 px spare space; no horizontal/vertical overflow or clipping |
| Browser content | All 32 rendered card texts and links match Canvas; network blocked, no links clicked |
| Visible overview | PNG 1160 × 1283, versus prior 1240 × 1590; not an Obsidian screenshot |

The initial 280 px width caused one long title to wrap: its box area decreased
only 5.33%, failing the frozen 15% requirement. This observation and initial Canvas
are retained in `initial-observation.json`. Uniform 294 px boxes resolved that
failure without deleting text or shrinking the font. Expectations did not change.

An independent auxiliary text check initially falsely reported a mismatch because
DOM `textContent` joined paragraphs without separators. Paragraph-wise visible
text comparison passed without any artifact edit. This was an observer correction,
not a product correction or an unreported successful first attempt.

`git diff --check` passed. No Python/runtime code changed, so this narrow artifact
check did not rerun the full suite or claim a new runtime regression result.

## Still pending

Human judgment of compactness and appearance; native Obsidian rendering, editing,
effective card size and click space. Open `overview.png` or `preview.html` to assess
the smaller boxes. Native testing requires opening the separate `.canvas` in an
explicitly selected experimental Vault; no such copy or native opening occurred.
Source links are synthetic examples and must not be used for reader verification.
