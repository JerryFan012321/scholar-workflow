# Standard Skeleton Manifest

Read this reference before planning or applying initialization.

## Directories

| Path | Required role |
|---|---|
| `.agents/skills/` | Project-scoped, host-neutral skills |
| `assets/` | Images, videos, and other assets used by README or reports |
| `configs/` | Pipeline parameter files, normally JSON |
| `dataset/metadata/` | Dataset indexes, provenance, checksums, and split metadata |
| `dataset/raw/` | Downloaded or materialized dataset content |
| `dataset_toolkits/` | Dataset download and preprocessing programs |
| `docs/notes/` | Human experiment notes; preserve them |
| `docs/plan/` | Project strategy, schedule, and plans |
| `docs/report/` | Material prepared for external reporting |
| `env/server/` | Per-server setup notes and known environment issues |
| `experiments/` | One self-contained reproducibility bundle per experiment |
| `src/pipeline/` | End-to-end pipeline integration; multiple pipelines are allowed |

Each intentionally empty leaf directory receives `.gitkeep` so Git can retain the layout.
The initializer never copies folder instruction notes or `.DS_Store` from a source template.

## Baseline files

| Path | Behavior |
|---|---|
| `AGENTS.md` | Canonical project instructions; create only when absent |
| `CLAUDE.md` | Thin `@AGENTS.md` import; accept an existing file only when it imports the canonical file |
| `AGENT.md` | Compatibility pointer to `AGENTS.md`; a different existing file is a conflict |
| `.gitignore` | Minimal universal ignores; preserve an existing file unchanged |

The baseline `.gitignore` covers operating-system metadata, local environment files, and common
Python caches. It deliberately does not guess whether `dataset/raw/`, experiment outputs, logs,
or figures belong in Git.

## Application contract

- `plan` performs no writes.
- `apply` aborts on a directory/symlink collision or incompatible instruction topology.
- Existing regular files are preserved.
- Git is initialized only when neither the target nor an ancestor already manages it.
- No content is staged, committed, or pushed.
