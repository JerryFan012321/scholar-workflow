# init-project

Initialize a Git-managed project with the standard research-oriented directory skeleton and
host-neutral project instructions.

## What it creates

- A shared source layout under `assets/`, `configs/`, `env/`, `src/`, `tools/`, and `tests/`.
- Local-first `dataset/`, `docs/`, and `experiments/` trees.
- `project-layout.json` with a stable portable project UUID and versioned profile selection.
- `AGENTS.md` as the canonical instruction file.
- Thin `CLAUDE.md` and `AGENT.md` compatibility entry points.
- A minimal `.gitignore` and `.gitkeep` files for intentionally empty directories.
- A Git repository when the target is not already managed by Git.

It does **not** create Claude Code agents, Codex agents, or hooks.

## Usage

Ask Claude Code or Codex:

```text
Initialize this project
Create the standard project skeleton in ./my-project
```

The skill first runs a read-only plan. Existing files are preserved, and conflicting project
instructions are shown for approval before any merge. Applying the plan creates only missing
paths and never runs `git add`, `git commit`, or `git push`.

The deterministic helper can also be run directly:

```bash
python3 skills/init-project/scripts/init_project.py plan /path/to/project
python3 skills/init-project/scripts/init_project.py apply /path/to/project
python3 skills/init-project/scripts/init_project.py profiles
python3 skills/init-project/scripts/init_project.py apply /path/to/project \
  --source-profile multi-stage-3d --package my_project --addon native-kernels
```

## Layout decisions

- The local standard names are canonical: `docs/plan` and `docs/report` are not duplicated as
  `docs/plans` or `docs/reports`.
- Data is grouped by dataset under `dataset/<dataset-id>/`; preparation code lives in
  `src/utils/dataset_toolkit/`.
- Six explicit source profiles and six orthogonal addons can extend the common layout. Existing
  profile selections never change through ordinary `apply`.
- Each `experiments/<run-id>/` owns a machine-neutral Run recipe; runtime retries are Attempts and
  execution placement is an explicit Target.
- `scholar-workflow experiment` creates and validates records and promotes selected artifacts. It
  never launches training or marks a backup verified before a trusted-medium contract exists.
- New projects keep data, docs, and experiment records outside source Git; existing tracked
  policies are preserved and only diagnosed during migration.

The workflow was independently implemented after comparing the local standard skeleton with
[sjh-skills/init-project](https://github.com/jiahao-shao1/sjh-skills/tree/main/skills/init-project).
