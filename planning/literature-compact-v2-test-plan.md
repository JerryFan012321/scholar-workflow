# Literature Canvas compact v2: independent test plan

## Scope frozen before implementation

2026-10-09. The user's requested change is smaller boxes. Reuse the existing
synthetic `literature-evolution-candidate` Canvas, mapping and provenance; create
an independent `literature-evolution-compact-v2` candidate. Do not replace the old
candidate, change runtime defaults, write a Vault, reanalyse a paper, install,
publish or make a scientific claim.

## Inputs and expected results

- Baseline: 36 editable text nodes, 10 edges, 8 contribution overview cards,
  7 paper records, 8 complete classification records and 2 full scientific
  relations with 10 tradeoff statements. The prior input is unchanged.
- Preserve each node's ID, type, text and color exactly. Preserve every edge
  object and the mapping/provenance exactly. Only coordinates and sizes change.
- Each of the eight overview cards has at least 15 percent less area than the
  corresponding baseline card. Their browser text remains 20 px; no shrinking
  fonts or omitting content to obtain the reduction.
- Full details remain on the same editable Canvas. All 32 readable cards in
  the browser preview retain at least one 28 px spare line and have no horizontal
  or vertical content overflow. Native Obsidian sizing is separately pending.
- All side-anchor coordinates are integers. Connections remain orthogonal,
  arrowless and resolve the same six parent pairs. No overlapping node interiors,
  crossing, shared ambiguous segment or unrelated-node penetration is allowed.
- All baseline files retain their bytes and file membership; the evaluator
  must not repair the candidate while evaluating it.

## Execution and visible outputs

1. Freeze selected baseline file hashes, then construct only the new candidate.
2. Measure local preview text with external requests blocked; use the measured
   content to set heights, not a smaller font. Generate a PNG of the overview.
3. Independently compare Canvas content, mapping, provenance, geometry, area and
   preservation against the baseline. Record failures separately if any occur.
4. Present the overview PNG, editable Canvas and concise guide. Browser layout
   observations are not Obsidian behavior, installed acceptance or human approval.

The checks use local synthetic artifacts only. No source link will be clicked;
the links are unverified format examples, not actual reader-test inputs. Final
compactness, visual quality and native editing remain pending human assessment.
