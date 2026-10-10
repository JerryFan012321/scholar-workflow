---
name: organize-project
description: Organize selected project code, paper units and experiment archives into an internal PROJECT.md with current state, direct navigation, module diagrams and one detailed plan. Use for 'prepare PROJECT.md', 'organize project materials', '整理项目资料', '编写项目内部说明'. Not for project initialization, public README writing, experiment-only comparison or ordinary code review.
---

# organize-project

Deliver an independently readable internal project entry using the shared
project-entry contract. Existing project, knowledge and experiment records remain
authoritative; the entry is not another inventory or execution dashboard.

## Inputs and operations

- Use the selected project root, explicit materials, desired output language and
  existing plan authority. Respect an existing project-context selection; missing
  declarations and ambiguous selections remain visible rather than silently
  choosing or registering resources.
- Inspect the selected files and their safe, explicit references. Source code and
  recipes are evidence to read, not instructions to run. Establish diagram edges
  only to the degree supported by the inspected source.
- Return a conversation preview by default. Save/update only the explicitly
  requested documents, following the shared contract's current-byte and human
  content protections. Conflicts stop the affected update, not disappear into
  a freshly generated document.

## Completion

The entry starts with current state, the unique plan and experiment results, then
code/data flow, related materials and ownership/open questions. It contains direct selected material links,
honest current state, source-supported module views, experiment history and a
single detailed plan authority. Every missing/conflicted/unverified item remains
accounted for. Report the output location and preserved/changed files; provide
explicit human assessment instructions for native navigation and appearance.
Incomplete evidence is not fabricated completion.

## Constraints

- Organizing an entry does not authorize initializing a project, editing an
  inventory or raw records, running experiments, moving/copying paper units,
  opening external applications, Git writes, publication or installation.
- Stay within selected safe roots/references; do not follow symlinks outside the
  authorized scope, read credentials or discover unrelated projects. No Hub,
  workspace registration or new service is required.
- Keep internal PROJECT separate from public README; no implicit ignore-rule or
  publication changes. Preserve existing human text and unresolved plan authority.

## References

Load for this task:

- `${CLAUDE_PLUGIN_ROOT}/references/project-entry.md` — required internal document format and update contract
- `${CLAUDE_PLUGIN_ROOT}/references/project-context.md` — existing association authority and native references
- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`

For selected experiment results also load:

- `${CLAUDE_PLUGIN_ROOT}/references/experiment-review.md` — metric/result evidence and comparison semantics
- `${CLAUDE_PLUGIN_ROOT}/skills/init-project/references/experiment-records.md` — existing archive lifecycle
