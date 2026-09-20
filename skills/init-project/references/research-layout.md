# Research Project Layout

Use this reference when filling directory responsibilities or project-specific artifact rules.

## Dataset contract

`dataset/metadata/` holds the index and provenance; `dataset/raw/` holds actual downloaded or
materialized data. `dataset_toolkits/` owns download and preprocessing programs. A data change
is complete only when the toolkit output and metadata index still agree.

Git treatment of raw data and outputs is project-specific. The recorded rule states any
applicable size, licensing, privacy, or reproducibility constraints; without a recorded
decision, do not add a blanket ignore rule.

## Experiment contract

Each experiment lives under `experiments/<id>/` and is the source of truth for its run. It
should account for:

- a report covering purpose, environment/server, duration, data and splits, method, parameters,
  comparisons, results, figures, exact command, and affected pipeline files;
- the run script and referenced config;
- outputs and metrics;
- logs and warnings;
- human experiment notes, which agents preserve and never delete.

An optional registry may point to these bundles. It is an index, not a competing experiment
record.

## Environment and source contract

`env/` holds reproducible environment configuration and setup scripts. `env/server/` records
server-specific setup and known issues, but credentials remain outside Git.

`src/` contains cohesive implementation modules. `src/pipeline/` contains end-to-end pipeline
integrations. Independently runnable entries expose their input, output, and intermediate-
artifact boundaries.
