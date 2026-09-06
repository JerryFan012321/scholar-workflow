# init-project

Initialize a Git-managed project with the standard research-oriented directory skeleton and
host-neutral project instructions.

## What it creates

- The fixed project layout under `assets/`, `configs/`, `dataset/`,
  `dataset_toolkits/`, `docs/`, `env/`, `experiments/`, and `src/`.
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
```

## Layout decisions

- The local standard names are canonical: `docs/plan` and `docs/report` are not duplicated as
  `docs/plans` or `docs/reports`.
- `dataset/metadata` and `dataset/raw` separate metadata from downloaded data.
- Each `experiments/<id>/` directory owns its reproducibility bundle; a registry may index it
  but does not replace it.
- Raw-data and experiment-output ignore rules are project-specific and are proposed
  interactively rather than guessed.

The workflow was independently implemented after comparing the local standard skeleton with
[sjh-skills/init-project](https://github.com/jiahao-shao1/sjh-skills/tree/main/skills/init-project).
