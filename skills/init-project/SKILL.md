---
name: init-project
description: Initialize a Git-managed project with the standard host-neutral directory skeleton and project instructions. Use for 'init project', 'bootstrap this project', 'create the project skeleton', '初始化项目', '创建项目骨架', or '初始化项目结构'. Not for configuring scholar-workflow itself or the personal env-records ledger.
---

# init-project

Create the standard project structure without installing custom agents or hooks. `AGENTS.md`
is the instruction source; `CLAUDE.md` and `AGENT.md` are compatibility entry points.

## Triggers

- Initialize or retrofit a project with the standard directory skeleton.
- Establish project-level instructions and Git management for a new project.

## Steps

1. **Resolve the target.** Identify the intended project root, inspect hidden entries, and
   read any existing `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, and `.gitignore`. Read
   `references/skeleton-manifest.md` for the exact layout.
2. **Preflight.** Run this skill's `scripts/init_project.py plan TARGET`. Present every
   reported structural or instruction-topology conflict. The initialization request already
   authorizes missing directories, baseline files, and `git init`; only an existing-content
   conflict needs a decision.
3. **Resolve conflicts.** Preserve existing files by default. For each conflicting instruction
   file, propose the exact migration or merge needed to make `AGENTS.md` canonical and wait for
   approval before editing it. Never replace a directory, file, or symlink to make room.
4. **Apply.** Run `scripts/init_project.py apply TARGET`. It creates only missing paths,
   initializes Git only when the target is not already managed by a repository, and never
   stages or commits.
5. **Fill project-specific context.** If the baseline `AGENTS.md` was created, inspect the
   project and draft only the unresolved overview, commands, extra boundaries, and artifact
   policy. Follow `references/project-instructions.md` and confirm the processed rules with the
   user before replacing its markers. Existing project instructions use the same confirmation
   gate.
6. **Verify.** Re-run `plan`, inspect `git status --short`, and report created, preserved,
   unresolved, and Git-management state. Completion means every standard path exists or is an
   explicitly accepted exception, no existing content changed without approval, and Git has no
   staged changes from initialization.

## Constraints

- The local standard skeleton wins over alternate `plan/plans`, `report/reports`, or
  `scripts/data` layouts. Do not create duplicate directory systems.
- `experiments/<id>/` is the experiment source of truth; optional registries are indexes only.
- Never copy `.DS_Store` or scaffold credentials, custom agents, or hooks.
- The script is additive and idempotent. It never deletes, overwrites, stages, commits, or
  pushes.

## References

Load only the reference needed for the current phase.

- `references/skeleton-manifest.md` — exact paths and generated baseline files
- `references/project-instructions.md` — canonical instruction topology and merge/fill rules
- `references/research-layout.md` — dataset, experiment, environment, and source-code roles
