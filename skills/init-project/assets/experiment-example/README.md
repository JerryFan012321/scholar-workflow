# Reproducible Project Example

A small deterministic example connects code, experiment reports and results through an
explicit material inventory. No Hub is required; this is not a paper-training reproduction.

[Chinese execution and replay instructions](README.zh-CN.md)

Preparation creates files and Git structure only. Separately commit the new example's
declared source and run `python3 tools/replay.py` from its root, as described in the
Chinese instructions. Prerequisites: installed Scholar Workflow 0.32.3 or newer,
Python 3.11 or newer, Git, and a POSIX shell (macOS/Linux). No network or third-party calculation dependencies.

Expected count=4, sum=10, mean=2.5. One wrong-cwd Attempt fails; two correct-cwd
Attempts succeed with identical output. Independent expectations live in
[tests/expected.json](tests/expected.json). Existing Runs/inputs are never overwritten.

- [Computation](src/example_computation.py)
- [Experiment report](experiments/20261004-0000-sum-example/report.md), generated only after execution
- [Selected metrics](experiments/20261004-0000-sum-example/artifacts/metrics.json), generated only after promotion
- Read the explicit inventory with `scholar-workflow project overview --project-root .`.

Clone the same committed source into a new root, restore local-first directories with
the installed initializer's plan/apply, and rerun without copying old outputs.
Project identity is preserved; actual host locations and timestamps may differ.

Data, documents and experiment state are local-first, not included in default source Git.
Promotion verifies a copy, not an independent backup. Project-rule placeholders and
human assessment remain pending. External papers/notes are added only by explicit selection;
the inventory never authorizes synchronization or paper-code execution.
