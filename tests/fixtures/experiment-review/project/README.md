# Synthetic experiment review input

This project is a handwritten, offline review fixture. Nothing in this folder was
produced by executing an experiment. Statuses, timestamps, runtime observations and
scores are invented test inputs, not real scientific observations.

Review only these explicitly selected records:

- Baseline: Run `20261009-1000-baseline`, result Attempt `primary`.
- Variant: Run `20261009-1100-variant`, result Attempt `primary`.
- Retain the baseline `wrong-cwd` and `replay` Attempts in the review's status account.

The synthetic source commit `1111111111111111111111111111111111111111` is a
placeholder, not a known Git commit. There is no Git repository, executable result,
host environment or claim of installed-product validation here. Do not run the
entrypoint, create records, rebuild indexes, download anything or repair the fixture.

Raw records and inputs:

- [Baseline recipe](experiments/20261009-1000-baseline/run.yaml)
- [Variant recipe](experiments/20261009-1100-variant/run.yaml)
- [Baseline report](experiments/20261009-1000-baseline/report.md)
- [Variant report](experiments/20261009-1100-variant/report.md)
- [Baseline configuration](configs/baseline.json)
- [Variant configuration](configs/variant.json)
- [Dataset declaration](dataset/synthetic/metadata/manifest.json)
- [Environment declaration](env/synthetic.json)

Each Attempt holds its own frozen `target.yaml`. The root Target profile is only
the declared profile used to form those snapshots, not proof of a live machine.
The metrics JSON carries explicit protocol, scale, unit, direction and selection
metadata; do not infer those from the score or filename.
