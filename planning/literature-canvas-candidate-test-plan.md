# Editable literature Canvas candidate: independent check plan

## Status and scope

2026-10-09: expectations and this plan are prepared before candidate construction.
No check, renderer, CLI, experiment, external app or business operation is executed
by this preparation. Another bounded implementation task will create the candidate.
This is a synthetic design review, not a new runtime default, new CLI, published
template, installed-product acceptance or scientific/human approval.

Independent expected results are in
`tests/fixtures/literature-evolution/CANVAS-EXPECTED.md`. The unchanged input is
`tests/fixtures/literature-evolution/seven-papers.json`. Reuse its seven paper units;
do not reanalyse real papers, modify the input or replace an existing Canvas.

## Input and expected visible result

- Seven declared papers, eight contributions, six structural parent pairs, two
  science relations, eight complete classification statements and ten complete
  tradeoff statements with their evidence and honest source states.
- Native editable JSON Canvas text nodes: a compact top-down main/branch/local/
  pending overview and complete classification/relation cards on the same canvas.
- Parent connectors are explicitly membership only. Type 1/2 eligibility governs
  main/branch; type 3/4 remains local; pending remains visible and unclassified.
  Preserve the reverse comparison in its full card without forcing a crossing
  science-edge drawing or turning it into extends.
- Unique IDs, valid endpoints, no node overlap, horizontal/vertical connector
  segments, no unrelated-node penetration or non-junction crossing, consistent
  alignment, effective font at least 18 px and a spare line for readable clicking.
- No fixed coordinates/colors or finalized layout defaults. No content/evidence
  deletion, flattened image, tiny text, loopback URL or ambiguous cross-Source wiki.

## Later check sequence (not executed here)

1. Record the selected input and pre-existing Canvas byte baselines. Create only
   the explicitly named candidate in a separate destination; label it synthetic
   and unverified. Candidate generation must not alter runtime defaults or input.
2. Parse the candidate as JSON Canvas and inspect native text-node editability,
   IDs, endpoints and any declared routing points. Recover and compare the six
   semantic parent pairs after collapsing only those explicit routing paths.
3. Independently check all seven papers, eight contributions/classifications and
   two relations/ten statements, including basis, source pages and missing-evidence
   states. Check reuse of the mixed paper and preservation of reverse comparison.
4. Check node rectangles and actual routed connector segments for overlap,
   orthogonality, unrelated-node penetration, ambiguous shared segments and
   non-junction crossing. Record observed issues rather than moving nodes during
   evaluation. Do not use the producer's validator as the sole oracle.
5. Present the candidate in the intended editor when that separate operation is
   undertaken. Observe font size, wrapping, spare click space, editable text and
   aligned compact overview. If rendering/font state is unavailable, mark those
   checks pending rather than inferring them from JSON coordinates.
6. Recheck preserved file bytes and report automatic observations separately from
   pending human assessment. Do not click synthetic source links to claim real
   reader or scientific validation.

## Human assessment handoff

The conversation must state the exact candidate path and how to open it, then ask
the user to inspect the vertical overview, branch/local/pending distinctions,
alignment/no crossing, full classification and relation cards, font/readability,
link-click space and native text editing. Report what is still pending explicitly.
Do not request reapproval of already accepted single-paper Canvas or analysis
formats: this is a separate upper-layer candidate.

Visible outputs of the later task are the editable candidate, a concise reading
guide and separate actual check results. This plan does not create those artifacts
or predeclare success. Any failed content or geometry requirement is reported as
not passed, not excused as an aesthetic preference; final visual approval remains
the user's decision.
