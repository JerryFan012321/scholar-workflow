# Standard Skeleton Manifest

Read this reference before planning or applying initialization.

The default remains the generic skeleton below. For research roles use the shared
`references/project-management.md` contract and the explicit role modes described here.
Source-Git ignore policy is not the local parent's management-Git policy.

## Role selection

- `--role research-parent`: create `.agents/skills`, `assets`, `docs/notes`, `docs/plan`,
  `docs/report`, `experiments/profiles/targets` and local-only `backups/code`. Do not
  create source/config/env/data/tool/test trees. Track management docs and lightweight
  archives by default; ignore recovery packs and datasets. No Git remote is added.
  Create a six-section empty PROJECT with one inline plan, a separate public README
  stub and an empty project-context inventory. Do not create a second SCHEDULE or
  pretend that initialization supplies project facts or an inspected module diagram.
- `--role execution-child --parent-project-id UUID [--primary]`: create the generic
  source/profile/toolkit and dataset/experiment structure, without parent `docs`,
  PROJECT, context inventory or recovery directory. Source/config profiles remain
  available. Each child owns independent Git; primary is a declaration, not a push.
- Both roles create a separate schema-1 `project-management.json`, with their UUID
  matching layout schema 2. A new parent starts with no registered children; child
  initialization never updates a parent's manifest or claims mutual registration.
- Role modes accept only a new empty root or the same already-declared role on
  rerun. Without role flags, an existing managed role is retained. Explicit role,
  parent or primary drift refuses before writes; existing nonempty generic projects
  require separately scoped migration. An enclosing Git repository is refused.
- Run the helper on the explicitly authorized filesystem. It does not deploy a remote
  child or make a local synthetic fixture an actual server project. Remote access,
  availability, source publication and installing remote agent context are separate.

`scholar-workflow project validate-management --project-root CHILD --parent-root PARENT`
checks mutually declared identities when both roots are explicitly accessible; omit
the parent only for local declaration checks. No scanning, network or mutation occurs.
The schema checks field structure; runtime validation also checks unique children,
unique archive segments, no self-parenting and at most one primary. `profiles` is
reserved. No role declaration grants file/host/Git permissions.
For explicitly requested registration after scaffolding, use the separate preview/
byte-bound apply in the shared project-management contract. Initialization itself
never edits the parent's child list. A declared mapping is not remote availability.

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
- Generic Git is initialized only when neither the target nor an ancestor already manages
  it. Explicit role modes require independent roots and refuse an ancestor repository.
- No content is staged, committed, pushed, moved, deleted, renamed, or untracked.
