# Project Layout v2

Read this reference when selecting a source profile or interpreting `project-layout.json`.

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
- `docs/` and `experiments/` are local-first records and are not deployed to execution servers.
- `configs/` contains reusable recipes. Resolved per-Run inputs belong in the Run bundle.

The profile catalog in `source-profiles.json` is the machine-readable source of truth for profile
and addon directories. A profile may add source/configuration boundaries but cannot claim
`dataset/`, `docs/`, `env/`, or `experiments/`.

## Selection and migration

Initialization accepts at most one source profile plus zero or more addons. With no profile
arguments it creates the shared base and does not infer a project type. A request that differs
from an existing manifest is a migration request: ordinary `apply` refuses it and `migrate-plan`
reports the legacy and requested shapes without moving, deleting, untracking, or overwriting.
