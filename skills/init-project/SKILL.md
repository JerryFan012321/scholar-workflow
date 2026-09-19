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
2. Read `references/skeleton-manifest.md`, then run
   `scripts/init_project.py plan TARGET`.
3. Present every reported file/directory/symlink or instruction-topology conflict.
   Missing standard paths and `git init` are authorized by the initialization request;
   existing-content conflicts require a decision.
4. Preserve existing content by default. Apply an approved instruction migration using
   `references/project-instructions.md`; never replace a collision to make room.
5. Run `scripts/init_project.py apply TARGET`. It creates only missing paths and
   initializes Git only when no enclosing repository already manages the target.
6. If a baseline `AGENTS.md` was created, inspect the project and propose content for
   its unresolved markers. Replace markers only after user confirmation.
7. Re-run `plan` and inspect `git status --short`. Report created, preserved,
   conflicted/unresolved, and Git state.

## Constraints

- Use exactly the local skeleton; do not create parallel `plan/plans`,
  `report/reports`, or `scripts/data` layouts.
- `experiments/<id>/` is the run source of truth; registries are indexes only.
- Never scaffold credentials, custom agents, hooks, or `.DS_Store`.
- The initializer never deletes, overwrites, stages, commits, or pushes.

## References

- `references/skeleton-manifest.md`
- `references/project-instructions.md`
- `references/research-layout.md`
