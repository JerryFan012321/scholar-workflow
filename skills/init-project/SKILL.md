---
name: init-project
description: Initialize or retrofit a Git-managed project with the standard host-neutral directory skeleton and instruction topology. Use for 'init project', 'bootstrap project', 'create project skeleton', '初始化项目', '创建项目骨架'. Not for configuring scholar-workflow or env-records.
---

# init-project

`AGENTS.md` is canonical. `CLAUDE.md` imports it and `AGENT.md` is a compatibility
pointer.

## Steps

1. Resolve the target root, inspect hidden entries, and read existing `AGENTS.md`,
   `AGENT.md`, `CLAUDE.md`, and `.gitignore`.
2. Read `references/skeleton-manifest.md` and `references/source-layout.md`, then run
   `scripts/init_project.py plan TARGET`. Pass a user-selected `--source-profile`,
   `--package`, and repeatable `--addon` explicitly; omit them for the common base.
3. Present every reported file/directory/symlink or instruction-topology conflict.
   Missing standard paths and `git init` are authorized by the initialization request;
   existing-content conflicts require a decision.
4. Preserve existing content by default. Apply an approved instruction migration using
   `references/project-instructions.md`; never replace a collision to make room.
5. Run `scripts/init_project.py apply TARGET` with the same layout selection. It creates the
   portable project UUID and only missing paths, and initializes Git only when no enclosing
   repository already manages the target.
6. New baseline `AGENTS.md` markers remain unresolved until the user approves a proposed
   patch grounded in existing project files.
7. Re-run the identical `plan`, inspect `project-layout.json` and `git status --short`, and
   report the stable project ID, selected profiles, created/preserved paths, unresolved legacy
   diagnostics, and Git state.

## Constraints

- Use exactly the local skeleton; do not create parallel `plan/plans`,
  `report/reports`, or `scripts/data` layouts.
- `experiments/<id>/` is the run source of truth; registries are indexes only.
- Preserve `project-layout.json` identity and profile versions. A different selection requires
  `migrate-plan`; ordinary `apply` cannot change it.
- New `dataset/`, `docs/`, and `experiments/` trees are local-first. Existing tracked trees are
  diagnosed, never silently untracked.
- Never scaffold credentials, custom agents, hooks, or `.DS_Store`.
- The initializer never deletes, overwrites, stages, commits, or pushes.

## Project material context

Initialization creates layout, not research facts. When project materials are explicitly selected,
the project may own a separate `project-context.json` inventory of code, papers, knowledge notes,
experiments and results. Follow the shared project-context result contract; keep external content
in Zotero/Vault and keep experiment records in their Run/Attempt bundles. The inventory does not
authorize synchronization, copies, execution or registration with the legacy Hub.

`scholar-workflow project context-template --project-root TARGET` prints an editable template;
`project overview --project-root TARGET` reads the declared inventory as Markdown. Neither command
writes a project file or starts an application. Do not turn a missing inventory into invented
project facts or a mandatory homepage. Project integration is not a new initializer side effect.

## References

For an explicitly requested reproducible project/experiment package, load
`references/reproducibility.md`. The installed portable example is optional and separate
from ordinary initialization; preparation never commits or runs it. A real experiment
keeps its own recipe and scientific facts rather than adopting the example's data or failure.

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/project-context.md` — when explicitly organizing project materials
- `references/skeleton-manifest.md`
- `references/source-layout.md`
- `references/experiment-records.md`
- `references/project-instructions.md`
- `references/research-layout.md`
- `references/reproducibility.md` — only for a requested reproduction package or example
