# Material decisions and phase operations

Load when inventorying selected outputs, returning analytical material or archiving
a phase. The experiment model lives in
[experiment-management](../../../references/experiment-management.md).
These operations use explicit existing roots; they create no project or asset registry.

For pooled inputs, retained result assets or shared copies, first follow
[workspace assets](../../../references/workspace-assets.md). Registration can leave
bytes in place; selecting a phase never selects the entire shared pool for cleanup.
Resolve the selected version/location within scope before preparing a file selection.
The helper below does not resolve asset references or check consumers in other roots.

## Discover outputs and choose by use

Before a new substantial execution, use the actual launcher/configuration and, when
useful, one small smoke execution to discover produced materials. Record uncovered
branches. A smoke test checks outputs, not the scientific conclusion or every future
execution. Reuse its findings until relevant outputs change.

The readable decision contains **material, remaining use, location, size when
known, retention choice and local-return choice**. Input assets, trained models,
selected observations, analysis/display results, recipes and needed diagnostics
can all be retained. Reproducible temporary render/PPT construction files are different
from final images/slides. An unreadable file can be a necessary asset even though it
should not return locally. Unknown purpose is a question, not a deletion reason.

Apply output choices to the actual launcher flags/config and declared temporary paths;
document ineffective/unavailable controls instead of pretending a policy changed the
producer. Prefer generating useful outputs to generating everything then cleaning.
Do not impose universal frame, checkpoint, file-count or age limits.

For exact file checking, the optional standard-library helper reads a small operation
selection. It is not a replacement for scientific records or a mandatory experiment
schema. Write the selection in JSON; each listed path is one regular file below the
explicit root. No folders, globs, absolute paths or symlinks are accepted.

```json
{
  "schema_version": 1,
  "files": [
    {"path": "results/comparison.csv", "kind": "result", "use": "Compare the measured variants", "keep": "retain", "return": true},
    {"path": "models/fitted.bin", "kind": "model", "use": "Repeat evaluation", "keep": "retain", "return": false},
    {"path": ".build/render.tmp", "kind": "temporary", "use": "Recreated by the retained rendering recipe", "keep": "cleanup", "return": false}
  ]
}
```

Kinds are `result`, `recipe`, `record`, `diagnostic`, `input`, `model`, `raw` and
`temporary`; this only distinguishes operation boundaries, not research categories.
Keep choices are `retain`, `cleanup`, `undecided`. Only result/recipe/record/diagnostic
files may be selected for return, with a stated use and `retain`. A human or authorized
agent supplies these classifications; the helper cannot infer scientific value from
an extension. Selection of an unreadable raw/model payload as `result` is a contract
violation, not a loophole. Necessary readable input examples may be explicitly
curated as an analytical result with their source recorded.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/manage-experiments/scripts/materials.py" plan ROOT selection.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/manage-experiments/scripts/materials.py" plan ROOT selection.json --json > material-plan.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/manage-experiments/scripts/materials.py" verify ROOT material-plan.json
```

`plan` measures only listed files, hashes return/cleanup selections and reports
undecided entries. It does not scan the workspace or claim to know total disk usage.
Unselected retained heavy files are stat'ed, not read. `verify` checks the saved
selection, source-root identity and observed file versions; a changed preview fails.
Both commands are read-only. Keep private absolute roots out of published artifacts.
Inspection is not a lock: stop affected writers and recheck immediately before any
native mutation. The helper does not prove future absence of a concurrent change.

## Selected return through SSH

Trigger return when the agreed experiment/measurement task has useful results, or
on a human request. Reuse agreed choices; otherwise recommend a scope and resolve
material uncertainties. Include enough conditions, actual recipe/version references
and explanation to read the selected figures, video, tables or organized data.
Never derive scope from every readable extension or a recursive folder mirror.

The parent initiates native SSH/rsync or an existing project transfer entry. Export
only the selected stable file list. Preserve relative grouping per child/experiment,
write into an operation-specific receiving area, verify the selected bytes, then
replace only the previously owned result files whose current versions match the
expected baseline. Preserve local analysis and notes. A remote deletion is not
automatic permission to delete a local file. No background sync is needed.

Record source experiment/result/recipe identity, selected paths and bytes, excluded
classes, local mapping, received/check time and pending items. On interruption resume
that transfer, not the experiment. Do not advertise partial files as current results;
after verified installation remove that operation's temporary transfer copy. A retry
must not create another lasting complete result tree.

Keep models, raw unreadable data and not-yet-cleaned intermediates remote. A selected
slice or statistic states its scope; do not imply receipt of the complete source.
Large useful results can remain remote with explicitly chosen samples or native HTTP
viewing through SSH. Record availability honestly. Source recovery/backup is separate.

## Repeatable phase archive and cleanup

One workspace-level operation can target an experiment, a child group or the
workspace. It does not add an administrator project or a permanent worker.
Select exact recipe/result pairs under the shared contract's
[archive-point rules](../../../references/experiment-management.md#select-reciperesult-pairs-at-archive-points).
Unselected recipes as well as results can be cleared from intervening phase work;
selection and continuing use determine scope, not a date range or whole directory.

1. Confirm the selected phase and existing authorization. List the chosen recipe
   versions and their individually selected results, including earlier retained
   selections or explicit withdrawals. Check reproducibility scope, future uses, active work and shared
   consumers. Resolve undecided choices; do not impose a fresh human approval when
   the actual task and prior choices already authorize the operation.
2. Save a small phase record **before cleanup**: purpose/outcome, selected recipe
   versions and result links, unresolved limits, retained assets and why, and a
   concrete file cleanup plan. Store hashes/stat observations for cleanup candidates.
   Verify selected results, their producing recipe/code and necessary asset references
   are obtainable for the retained scope. An unresolved retained dependency blocks
   cleanup that could remove its remaining source. Git records light versions;
   no full historical payload/recovery-tree copy is needed.
3. With relevant writers stopped, recheck the plan and remove only the selected,
   unchanged disposable files. Persist per-item progress. A whole directory can be
   removed only when its complete contents and purpose are known, no kept/unlisted
   file exists and the scope is authorized; a `.build` name alone is insufficient.
4. Verify retained material and final state. Keep the small record and changes; a
   later phase appends another record without copying all prior payloads.

A phase record can be a Markdown section plus a small JSON operation log, using
existing project conventions. It contains separate facts for `archive recorded`,
`cleanup pending/partial/complete` and `return pending/partial/complete/not requested`.
Scientific confidence and human assessment are separate. Archive does not certify
the truth of a conclusion, external backup or complete local receipt.

Interrupted cleanup resumes the same logged operation. Reconcile a missing path
as already absent without claiming who deleted it; retry only remaining unchanged
items. A changed/recreated/reused path is excluded and reviewed. Do not delete a new
file merely because an old plan names the same path. Changed retained material or
new consumers requires a new scope. The Skill instructs the responsible agent to
maintain this log; the read-only helper is not an automatic cleanup/recovery engine.

## Close the task visibly

Update the experiment's current results and changelog, then affected child/main
entries through the top PROJECT. Keep the material inventory readable: what stayed,
what returned, what was cleared, what is undecided and what could not be verified.
Report remaining transfer/cleanup/navigation work separately. Core importance and
human visual acceptance remain the person's decisions.
