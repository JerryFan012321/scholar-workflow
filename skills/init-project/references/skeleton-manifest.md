# Standard Skeleton Manifest

Read this reference before planning or applying initialization.

## Portable manifest

Every project receives project-layout.json with schema version 2 and a canonical UUIDv4
project_id. The ID is generated once on first apply and preserved on reruns, moves, and copies.
The manifest records only Python package and source-profile selection; host registration belongs
to the Hub-side registry.

## Common tracked source directories

| Path | Required role |
|---|---|
| .agents/skills/ | Project-scoped, host-neutral skills |
| assets/ | Publishable README and project assets |
| configs/components/ | Reusable machine-neutral configuration components |
| configs/recipes/ | Complete reusable configuration recipes |
| env/ | Machine-neutral environment definitions and build scripts |
| src/utils/dataset_toolkit/ | Dataset download, conversion, and preprocessing programs |
| tools/ | Thin human and CLI entry points |
| tests/ | Tests for source and project contracts |

Selected paths from source-profiles.json extend this tracked source layout. Empty tracked
directories receive .gitkeep.

## Common local-first directories

| Path | Required role |
|---|---|
| dataset/ | Host-local data grouped under dataset/<dataset-id>/ |
| docs/notes/ | Human project and experiment notes |
| docs/plan/ | Project strategy and plans |
| docs/report/ | Project reports and external-report drafts |
| experiments/profiles/targets/ | Credential-free execution Target profiles |

New projects ignore dataset/, docs/, and experiments/ in source Git and do not place .gitkeep
inside them. Existing tracked directories are preserved and reported; initialization never
untracks them.

## Baseline files

| Path | Behavior |
|---|---|
| project-layout.json | Portable identity and versioned profile selection; create only when absent |
| AGENTS.md | Canonical project instructions; create only when absent |
| CLAUDE.md | Thin @AGENTS.md import |
| AGENT.md | Compatibility pointer to AGENTS.md |
| .gitignore | Minimal universal and local-first ignores; preserve an existing file unchanged |

## Application contract

- plan, profiles, and migrate-plan perform no writes.
- apply performs a complete preflight and aborts on any collision or incompatible instruction or
  manifest topology.
- Existing regular files are preserved.
- Profile selection is never inferred. A mismatch with an existing manifest requires a migration
  plan.
- Git is initialized only when neither the target nor an ancestor already manages it.
- No content is staged, committed, pushed, moved, deleted, renamed, or untracked.
