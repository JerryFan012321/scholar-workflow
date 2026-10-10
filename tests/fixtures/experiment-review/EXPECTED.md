# Experiment review: independent expectations

Prepared before the review skill and its evaluation. These are handwritten facts,
not a generated report or a production-validator oracle. The reviewer receives only
`project/` and the runtime skill/result contract, not this file or the test plan.
No experiment has been executed: every record and observation is synthetic.

## Selected records and exact facts

| Run | Attempt | Recorded status | Selected score | Meaning |
|---|---|---|---|---|
| `20261009-1000-baseline` | `wrong-cwd` | failed, exit 2 | absent | Preserve the recorded path failure; absence is not zero. |
| `20261009-1000-baseline` | `primary` | succeeded, exit 0 | 0.80 | Explicitly selected baseline result. |
| `20261009-1000-baseline` | `replay` | succeeded, exit 0 | 0.80 | Same Run replay, byte-identical metrics; not a second independent Run. |
| `20261009-1100-variant` | `primary` | succeeded, exit 0 | 0.85 | Explicitly selected variant result. |

- Exactly two selected Runs and four Attempts are in scope. Do not discover more
  projects, choose the latest or highest-scoring Attempt, or execute either recipe.
- Both Runs declare the same synthetic dataset, version, fixed test split and
  dataset manifest; both metrics declare `synthetic-eval-v1`, unit `fraction`, range
  `[0, 1]`, and `higher_is_better: true` for `accuracy`.
- The visible configuration choice differs: `baseline` versus `variant`.
  The seed and environment are equal. Source commit is a synthetic placeholder,
  not a verified Git revision or evidence of actual execution.
- The selected recorded difference is `0.85 - 0.80 = 0.05 fraction`, equivalently
  **5 percentage points**. Do not call it a 5 percent relative increase.
- This difference is descriptive for the declared synthetic comparison. No
  independent repeated Runs, significance test, uncertainty estimate, causal claim
  or scientific generalization is established by this input.
- Every local metrics artifact has role `metrics`, its declared source Attempt,
  and size/SHA-256 matching its bytes. The baseline promoted artifact belongs to
  `primary`, not `replay`; backup remains `not-verified`.
- Target profiles are captured inside each Attempt. Read the frozen snapshot,
  not a later mutable global profile, as the execution-placement declaration.
- Human notes and failed records remain unchanged. A review creates no second
  authoritative recipe, metric store, plan, registry or experiment index.

## Required human result

One independently readable Markdown review should show the selected scope and
synthetic/unexecuted status, comparison conditions and configuration difference,
the two Run-level results with unit/direction and the descriptive delta, and a
separate account of all four Attempt statuses. Include useful relative links to
the actual Run recipes, configurations, reports, metrics and relevant failure or
human notes. Explain which source Attempt supplies each result.

Missing evidence and limits must remain visible. Use a consistent presentation
language, readable tables and prose; do not flood the review with machine hashes.
The exact title, heading wording, column order and optional graph are not frozen
by this fixture. Report usability and appearance remain pending human assessment.
The raw project files must be byte-for-byte unchanged after the review.

## Isolated negative cases

Each case uses a separate temporary copy of `project/`; do not edit the fixture.
If a metrics file is deliberately changed, refresh its enclosing file-identity
records for semantic cases so a stale hash does not obscure the intended question.

1. Remove the variant's metric unit or evaluation protocol: retain the recorded
   numeric values, but label the missing condition unknown and do not assert a
   verified comparable delta or ranking. Unknown does not inherit the other Run's
   metadata.
2. Remove the variant's `accuracy` value: show missing, never `0`; do not compute
   a numeric delta or silently substitute another Attempt/metric.
3. Mark the selected variant metrics artifact `manifest-only` with a remote
   locator and no local-copy fields: report local evidence unavailable and do not
   download the remote object, infer its value from the URI or substitute a local
   artifact. Preserve the selection and its diagnostic.
4. Make the selected local metrics hash or source Attempt association inconsistent:
   show the conflict and withhold an evidence-backed result for that artifact;
   do not repair records, pick the best/last Attempt or hide the failure.

## Evaluation boundary

Preparation does not run pytest, CLI validation, Git, an experiment, a reader app,
network access or publication/installation. The later isolated reviewer may read
these bounded raw files and return Markdown; that is skill evaluation, not real
business execution or installed-product acceptance. The evaluator compares its
result against these independently written expectations and reports actual outcomes
separately. No result is marked passed in advance.
