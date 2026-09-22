# Research Project Layout

Use this reference when filling directory responsibilities or project-specific artifact rules.

## Dataset contract

Data is grouped under `dataset/<dataset-id>/` with `source/`, `intermediate/`, `prepared/`, and
`metadata/`. `src/utils/dataset_toolkit/` owns download and preprocessing programs; training-time
Dataset/DataLoader code belongs to the project package. A data change is complete only when
toolkit output and metadata still agree.

Git treatment of raw data and outputs is project-specific. The recorded rule states any
applicable size, licensing, privacy, or reproducibility constraints; without a recorded
decision, do not add a blanket ignore rule.

## Experiment contract

Each Run lives under `experiments/<run-id>/` and is the source of truth for its machine-neutral
recipe. It accounts for:

- the run script, resolved config, dataset selection, seed, environment definition, source commit,
  and recipe hash;
- a report covering purpose, data and splits, method, parameters, comparisons, results, figures,
  and affected source files;
- outputs and metrics;
- logs and warnings;
- human experiment notes, which agents preserve and never delete.

Execution server, device, runtime, status, output/log location, and retry information belong to
Attempts. An optional index may point to Run bundles but is never a competing record.

## Environment and source contract

`env/` holds machine-neutral environment definitions and setup scripts. Personal host/API
inventory stays in env-records; credential-free Target profiles only select where an Attempt runs.

`src/` contains cohesive implementation modules. `src/pipeline/` contains end-to-end pipeline
integrations. Independently runnable entries expose their input, output, and intermediate-
artifact boundaries.
