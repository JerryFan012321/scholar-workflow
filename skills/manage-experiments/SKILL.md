---
name: manage-experiments
description: Maintain selected experiments, recipe/result links, material choices and phase archives. Use for 'manage experiment outputs', 'archive this experiment phase', '实验产物管理', '配方与结果登记', '阶段存档', or an authorized selected-result return. Not for automatically launching experiments or a read-only scientific comparison.
---

# manage-experiments

Deliver maintained experiment records and a readable material decision, using
[experiment management](../../references/experiment-management.md). That contract
defines experiment boundaries, recipe/result pairing, phase archives and the human
inventory. Load [material operations](references/material-operations.md) only for
inventory, return or cleanup. Existing Run/Attempt bundles retain their legacy
identity and command semantics; never convert them implicitly.

For shared inputs, reusable result assets or shared-material cleanup, follow
[workspace assets](../../references/workspace-assets.md). Reuse the selected pool's
versioned entries directly for read-only use. Only changes to asset content need a
writable derivative; registration and separately selected transfers remain distinct.

## Operations

- Resolve the selected project, child, experiment and actual workspace. Read their
  AGENTS entry and existing recipes, result records and resource index. Reuse the
  existing plan and scientific launcher; initialization or a record is not execution.
- Record the exact recipe version and resolved input references in each result record.
  Register supplementary measurements in the same experiment when its question is
  unchanged. Explain substantive changes in its changelog without copying old output
  trees. Result validity, execution success and human importance are separate facts.
- At a phase archive, select exact recipe versions and their individual results;
  verify their retained dependencies before clearing unselected intervening work,
  including discarded recipes. Follow the shared archive-point contract.
- For return/phase operations, make the selected files and their uses explicit.
  Use the read-only material helper for byte/selection previews; native SSH, Git
  and file tools perform only the authorized operation. Reuse established choices;
  unresolved retention or broader deletion needs a decision, not a guessed policy.
- After creating, revising or invalidating results and their records, update affected
  direct links, purposes and conclusions along every actual ancestor to the local
  main PROJECT. Report inaccessible/conflicted ancestors as incomplete.

## Completion and boundaries

The reader can identify the question, actual recipe for each result, comparable
conditions, conclusion, storage location and current material decisions without
chat history. Present the exact changed files, verified operation states and
remaining choices. Core-experiment selection belongs to the human; visual review
remains pending until their assessment.

Management permission does not launch scientific code, publish repositories,
connect an unselected server, migrate old records or delete undecided assets.
Return selected analyzable results after the agreed measurement task or a human
request; do not mirror folders, return model payloads or treat promotion as backup.
Every phase may be archived again. Preserve needed inputs and trustworthy results;
cleanup progress is separate from archive and return status.

Use [project-entry](../../references/project-entry.md) for the main entry,
[experiment-review](../../references/experiment-review.md) for substantive comparison
and [content and style](../content-and-style/SKILL.md) when producing explanatory
prose. The Skill holds operations and output requirements, not a research method,
mutable project context or a new execution service.
