# Project Layout v2

Read this reference when selecting a source profile or interpreting `project-layout.json`.

These paths describe the implemented generic source layout. Parent/child ownership
and its current capability gaps are in the shared `references/project-management.md`;
profile selection alone does not create either new role.

## Portable identity

Every initialized project has a root `project-layout.json`. Its `project_id` is a canonical
lowercase UUID generated once by `apply`; copying or moving the project preserves that identity.
Host paths and Hub registration never enter this portable manifest.

The manifest uses schema version 2 and records only the language, optional package, one optional
source profile, and ordered addon selections. It does not contain datasets, experiments, targets,
servers, credentials, or global-Knowledge relations.

## Shared boundaries

- `src/utils/dataset_toolkit/` owns offline dataset acquisition and preparation programs.
- `dataset/<dataset-id>/{source,intermediate,prepared,metadata}/` is materialized on each host and
  remains outside source Git.
- `env/` contains machine-neutral definitions; Target profiles describe where an Attempt runs.
- Parent knowledge and collected archives are local-first, not deployed as a second
  server truth. A remote execution child registers its own experiments independently;
  this does not deploy the parent's archive or add a child-reception mode to this helper.
- `configs/` contains reusable recipes. Resolved per-Run inputs belong in the Run bundle.

The profile catalog in `source-profiles.json` is the machine-readable source of truth for profile
and addon directories. A profile may add source/configuration boundaries but cannot claim
`dataset/`, `docs/`, `env/`, or `experiments/`.

## Selection and migration

Initialization accepts at most one source profile plus zero or more addons. With no profile
arguments it creates the shared base and does not infer a project type. A request that differs
from an existing manifest is a migration request: ordinary `apply` refuses it and `migrate-plan`
reports the legacy and requested shapes without moving, deleting, untracking, or overwriting.
