# Experiment Review Result Contract

Applies to read-only reviews of selected project experiments, including comparisons
embedded or linked from a private PROJECT.md. Run/Attempt/Artifact records retain
their existing authority. README.md remains the external presentation document;
reviewing or saving a report does not authorize publishing internal project facts.
Record lifecycle rules remain in `skills/init-project/references/experiment-records.md`.

## Required human result

Use one presentation language. The following sections are required; translate their
labels consistently. Tables may split when width harms readability, without losing
the required information. Put the conclusion, a useful evidence-linked visual and
the main results before detailed comparison conditions and verification records.

1. **Summary and scope:** selected project, Runs, result Attempts, requested metrics
   and comparison goal; the useful conclusion first, plus complete/partial status.
   Label synthetic, unexecuted or unverified inputs explicitly.
2. **Run results:** one row per selected Run/result selection showing the source
   Attempt, metric and unit, artifact/source link, evidence availability/integrity,
   and comparable/not-established status. Retain missing and conflicted rows.
   If more than one result per Run is requested, label them separately rather than
   collapsing them into an unspecified Run score.
3. **Comparison conditions:** for every selected Run, dataset identity/version/split
   and manifest, metric definition/unit/direction/evaluation protocol, configuration
   differences, seed, environment, recorded source revision and captured Target.
   Link to the actual declarations. Mark absent conditions as not recorded and
   distinguish declared equality from independently verified execution.
4. **Attempt history:** all Attempts in the requested history, with Run, Attempt,
   recorded status/exit outcome and failure/retry/replay meaning. Link records and
   available logs/notes. A successful exit is not proof of a valid scientific result.
5. **Differences and limits:** changes supported by the selected evidence,
   incomparable or unknown conditions, analyst interpretation, and any unavailable
   files or reader checks. State unresolved items and safe next actions without
   silently performing them.

Source links are relative to the report's actual location. A conversation-only
review may use host-supported absolute local links; a saved portable report uses
relative links, not workstation-specific paths. Link recipes, resolved configs,
reports and metric files beside their uses. Full hashes and machine identity dumps
do not belong in the main prose; concise integrity states identify what was checked.

## Visuals and plain language

For available numeric or visual evidence, include a meaningful comparison plot,
result image or source table beside the conclusion. Prefer selected existing
figures; any new chart must be directly reproducible from the cited selected data.
Label axes, units, series, conditions and synthetic/unexecuted scope. Keep scales
comparable, missing values missing and unsupported uncertainty absent. Do not
invent values, add decoration in place of results or run experiments to fill a page.
If no useful visual is supported, state what is unavailable and why; do not pretend
the illustrated requirement has been met.

Figures do not replace source-linked values, comparison conditions or limitations.
Explain what the reader can and cannot conclude in ordinary language. Use experiment
and execution attempt in human prose; introduce Run and Attempt only when their
exact record meaning matters. Artifact IDs, byte counts, hashes and validation
vocabulary belong in supplementary records, not repeated result cells. Preserve
usable source and failure-log links.

## Metric evidence and comparison semantics

- The current archive has no universal metrics payload schema. Read the explicitly
  selected metric from its actual format and declaration; do not infer a unit,
  evaluation protocol or metric meaning from a filename, title or another Run.
- A local evidence-backed metric requires the selected ArtifactRecord's role
  `metrics`, matching `source_attempt_id`, and actual file size/SHA-256 match.
  The recipe, Attempt and artifact must agree on Run/result identity. Conflicting,
  changed, missing or unparseable evidence remains visible and does not support
  a verified score. A manifest-only remote locator is not local evidence.
- Use the Attempt's frozen Target snapshot for execution placement, not the current
  profile. Distinguish recorded source/environment facts from actual verification;
  reading hashes is not atomic snapshot capture or proof that an execution occurred.
- Configuration or source changes may be the deliberate comparison variable.
  Describe them rather than requiring identical configurations. A comparable numeric
  delta requires established metric meaning/unit/protocol and relevant evaluation
  data conditions. If these are absent or incompatible, show available values side
  by side with the uncertainty and withhold a verified delta/ranking.
- Missing values are not zero. Retries and replays of one Run are not independent
  Run replications. Do not turn them into scientific sample counts, uncertainty or
  significance claims. If such claims are requested, identify the independent
  evidence needed instead of fabricating it.
- Preserve units in differences. For a fraction metric, a difference of 0.05 is
  five percentage points, not a five-percent relative increase. Numeric comparison
  is descriptive unless the inputs separately support a stronger conclusion.

## Storage and completion

The report is a derived human view, not a new authority or synchronized result store.
Default delivery is the conversation; an explicitly saved report may be linked from
PROJECT.md without changing Run recipes, human notes or raw artifacts. Keep existing
documents unchanged unless their update was explicitly requested. A report can be
structurally complete while its comparison is partial; label both honestly. Automated
fact checks do not certify reader navigation or visual usability.
