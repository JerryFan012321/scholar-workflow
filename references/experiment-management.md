# Experiment Management

Use for new experiment organization or an explicitly selected adaptation. Existing
Run/Attempt bundles remain readable under their
[legacy contract](../skills/init-project/references/experiment-records.md); do not
rename their identities, rewrite them or reinterpret their lifecycle. The native
legacy commands are not an implementation of this new experiment model.

## Objects and ownership

| Object | Required meaning |
|---|---|
| Main project | Local research management, unique plan, knowledge, agent context, cross-experiment analysis and selected returned results |
| Remote workspace | Deployment/resource directory containing execution children and shared resource entries; not another research parent or privileged agent |
| Child project | An experiment group and its working context, still a project; primary is its research role |
| Experiment | A question or validation purpose with materially distinct conclusions; may contain several recipes, variants, seeds and result groups |
| Recipe | A lightweight reproducible specification: obtainable code revisions, experiment scripts, effective configuration/overrides, versioned asset references, environment definition and invocation; no asset payloads |
| Result group | Independently interpretable observations tied to the actual recipe/version and conditions that produced them |
| Changelog | Meaningful corrections, supplementary measurements, comparisons and their effects on results, rather than another directory of output copies |
| Execution record | Minimal observed facts: recipe/result references, start/end, execution location, outcome and necessary diagnostics; neither a new experiment nor a scientific verdict |
| Phase archive | A retained selection of exact recipe versions and their chosen results at a phase boundary; repeatable, with cleanup of unretained phase work and selected return tracked separately |

Supplementary measurements, correcting a calculation, improving explanation or
execution efficiency normally stay in the experiment. A new question, comparison
purpose or independently judged conclusion can justify another experiment. A changed
parameter alone does not decide this. A stopped investigation can close its phase;
state the actual evidence/reason, not an invented claim that the method was disproved.

## Repositories and editable files

Each experiment has its own Git repository; its multiple recipes share it. Shared
main code may retain its existing repository: record the exact referenced revision
and obtainability instead of duplicating it. Parent/child management Git excludes
nested experiment repository contents. Remote code is edited remotely; the local
parent keeps selected results, analysis and minimal explicitly chosen recovery material.

Git tracks useful source, scripts, configs and light records, with small explanatory
images when appropriate. Large data, models, bulk images/video and temporary outputs
stay outside Git. Do not hide existing tracked files or invent a universal size or
extension ban. Publishing multiple experiment repositories requires the user's
selected mapping; creating an experiment never creates or pushes a GitHub repository.

Keep an upstream's usable config and launcher. New entries should expose documented
parameters, defaults, overrides and a preview of resolved choices. A recipe may reference
shared code and immutable inputs; it need not contain copied code or a separate repo.
An uncommitted change must be captured by an exact patch/source record or declared a
reproduction gap. A Git commit alone does not include external data or model state.

A small new experiment can use the following example; retain compatible existing
names and combine documents when a separate file adds no useful navigation:

```text
experiment/
  EXPERIMENT.md       question, current phase, result/recipe entries and decisions
  CHANGELOG.md        changes and which results they affect
  recipes/           light configs/asset references; versioned with scripts in Git
  run.py             the project's real entry (or retain its existing launcher)
  results/           interpretable groups with conditions, figures and data
  records/           small execution and phase records
  .build/            declared reproducible intermediates, only when needed
```

This is an example, not a mandatory file count, directory depth or script name.
Keep readable result summaries near their evidence. Model/input/cache locations
can be workspace resources rather than additional copies below each experiment.

## Pair recipes and results

A recipe and the experiment code stay lightweight. Preserve the following in the
recipe or its explicitly linked versioned files, without duplicating shared code:

| Component | What is retained |
|---|---|
| Code and scripts | Obtainable exact revisions, experiment-specific scripts and any required patch |
| Configuration | Effective parameters, overrides, seeds and measurement/output choices |
| Assets | Owning pool, exact asset versions and resolvable locators; no model/dataset/scene payloads |
| Environment and invocation | The relevant environment definition/version, dependencies and actual entry/arguments |

Several recipes may share the same code and assets. Recipes do not embed environment
installations, input data, generated results or complete execution directories.

Every result group identifies its question, actual recipe file and Git revision,
resolved overrides/seeds, relevant code revision(s), input versions and execution
environment. Keep these details in one authoritative execution/result record and
link it from prose. A recipe edit does not relabel old results. Several result files
may share one record; comparisons identify the recipe of each side.
Manage retention at the result level without duplicating a shared comparison figure
or analysis for every contributing recipe.

For each comparison put **common conditions, differences, measured results and
interpretation together**. Explain metric meaning, unit, comparison objects, evidence
scope and limitations using [experiment-review](experiment-review.md). With many
parameters link the actual resolved config and describe the material differences;
do not substitute a bare link for reading the config.

State what can be reproduced: training, reevaluation of a retained model, analysis
of retained observations, or only a plot. An entry is usable only if its code and
required assets can be obtained. Keep useful trustworthy earlier results; retract
invalid results and affected conclusions, with a brief reason in the changelog.
Git can retain light historical records; old large output trees need no automatic copy.

## Select recipe/result pairs at archive points

At a periodic or requested phase review, choose which exact recipe versions and
which of their results to retain. One recipe may have several results with different
retention decisions; retaining it never means keeping every output it produced.
Every selected result keeps its actual producing recipe/code and required asset
references obtainable for the declared reproduction scope, even if the current
editable recipe has advanced.

Use one readable selection in the existing phase record: **recipe/version, result
entry or selected group, remaining purpose, keep/cleanup/undecided choice and required
dependencies**. A recipe may be retained for future use without retaining its trial
results; state that purpose. Reuse existing result and asset records rather than
creating another full archive folder.

After recording and verifying a new archive point, clear the intervening phase work
that was not selected and has no continuing use: abandoned recipe files, unselected
results and reproducible intermediates. Include discarded recipes in the cleanup
decision, not just large output files. The phase is determined by its work/records;
file creation/modification timestamps alone never select deletion candidates.
Preserve earlier retained selections, current work and shared dependencies unless
their retention is explicitly revised. Invalidated results may be withdrawn with
their reason; an archive point does not mandate keeping untrustworthy results.

Removing an unused recipe from the current working tree can be a normal Git change;
light history and archive revisions remain obtainable by commit and path. Update
result entries to distinguish retained, retrievable historical and cleared material;
an old record that once retained a file does not prove it is still available.
Clearing a result for lack of remaining use does not itself invalidate its scientific
conclusion. Do not rewrite Git history,
delete a whole experiment repository or remove shared code as routine phase cleanup.
Keep a brief changelog of discarded work and decisions, not full payload snapshots.
The ordered operation and interruption behavior are defined in
[material operations](../skills/manage-experiments/references/material-operations.md).

## Human inventory and names

Use the existing PROJECT result section for a few experiments. When it becomes
unwieldy, make one `EXPERIMENTS.md` (or the existing equivalent) the detailed inventory
and link it from PROJECT. Do not maintain duplicate independent inventories.
One row per experiment links to its current independently readable result entry.

The visible overview includes:

| Experiment and purpose | Conditions and results | Current phase | Material state |
|---|---|---|---|
| Direct entry with the research question | Common baseline/variant conditions, differences, current result or honest absence, evidence link | Running, supplementing, stopped or archived phase, with date | Where evidence is, relevant local/remote size, retained/temporary/undecided material, and remaining action |

Group or expand rows when needed; do not compress necessary explanation into unreadable
cells. The detailed material list is opened only when storage/retention decisions are
needed. Distinguish measured size from unavailable remote size, selected bytes from
total occupation, and already returned from proposed return. Uninspected files are
uninspected, not disposable. A small readable file can still have no analytical use.

Give an experiment a lasting question-oriented name, such as “Effect of observation
count on line-parameter estimation”. Machine IDs, dates and implementation abbreviations
can remain metadata. Avoid “test2”, “final-new” or success claims as the only name.
An experiment can improve while keeping its identity/name; recipes may name the
specific variant. These are naming criteria, not a compulsory naming formula.

Only a human selects or removes **core experiments**. Show the selected few in the
main result section with their reason and direct evidence, without moving their data
or marking every other experiment disposable. If no selection exists, say so.
Human decisions may cover a group or established retention rule; no per-file or
per-execution approval ceremony is required.

## Workspace, phase operations and selected return

For shared inputs and retained reusable results follow
[workspace assets](workspace-assets.md): the workspace pool owns asset/version
locations and recipes reference them without requiring private payload copies.
Read-only execution reuses the existing version; changed asset content uses a writable
derivative. Registration, relocation and separately selected transfers remain distinct.
Keep a discoverable workspace description and existing environment index; the actual
modifier updates them. Main/child AGENTS entries link the workspace/resource and
experiment entry. Remote access and installed Skills are not inherited merely
because a local agent knows the path.

Use [material operations](../skills/manage-experiments/references/material-operations.md)
for the selection file, read-only checks, SSH return and repeatable phase cleanup.
Preserve necessary inputs, trained models, desired original/organized results,
recipes, useful records and reusable assets according to their remaining use.
Temporary material is removable only when its use has ended and the retained
reproduction scope no longer needs it. Shared consumers and active work are checked.

After the agreed experiment/measurement task produces usable results, or on a
human request, the local main project pulls selected analytical material. Models,
raw unreadable data and intermediates remain remote. No continuous synchronization,
folder mirror or indiscriminate `promote` is part of this model. Return and cleanup
are independent; failure to return is not permission to remove source results.

## Navigation and completion

The agent responsible for results also updates affected links, purpose, state and
interpretation up through the actual child/project hierarchy to the local main
PROJECT. Link actual next-level results; their own summaries can serve as the entry.
Do not manufacture intermediate pages, duplicate full reports, or wait for a PPT.
The workspace is updated when deployment/resource facts change, not inserted as a
research parent. Missing permission or conflict at an ancestor remains incomplete.

Retain the main project's knowledge, single plan, agent context and code/module
navigation. The six-section [PROJECT contract](project-entry.md) still applies.
Scientific records and explanation belong with results; a separately requested
communication report uses [create-report](../skills/create-report/SKILL.md).

Report execution, usable evidence, phase record, cleanup, local receipt, navigation
and human assessment separately. They need not all be complete simultaneously.
An installed Skill supplies this contract and the read-only material helper; it
does not supply a universal scientific launcher, automatic SSH transport, deletion
worker, remote deployment or migration of old archives.
