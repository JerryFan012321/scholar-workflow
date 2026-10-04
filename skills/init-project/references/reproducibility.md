# Project and Experiment Reproduction

Load for an explicitly requested reproducible project or experiment package. Ordinary
initialization does not add an example, launch a process, or invent research material.
Layout, record lifecycle and external-material ownership remain in the existing
`skeleton-manifest.md`, `experiment-records.md`, and shared project-context contract.

## Required package

- Portable project identity and explicit layout selection; no host paths or credentials.
- Committed source, machine-neutral resolved recipe and environment, selected dataset identity
  and hashes; separately record real Target and Attempt observations.
- Frozen non-secret inputs, installed product version, public commands, declared prerequisites
  and expected output/format. Preserve actual failures and unavailable inputs.
- An independently readable report stating purpose, input/split, method, parameters,
  comparisons, results and affected code. Logs, hashes and machine receipts are separate files.
- Rebuild in a new root without copying old outputs. State whether identity is preserved
  (same-project clone) or a genuinely independent new project is initialized.
- Separate automatic checks and human assessment. Replay demonstrates this package, not
  scientific validity, external app usability, or independent backup.

## Installed portable example

For a specifically selected small demonstration, the installed skill includes
`scripts/example_project.py` and `assets/experiment-example/`. It prepares a four-number
example, not a universal experiment design or paper implementation. From the installed
skill directory (not a source checkout):

```sh
python3 scripts/example_project.py plan /chosen/new-project
python3 scripts/example_project.py apply /chosen/new-project
```

`plan` writes nothing. `apply` accepts only a nonexistent root, rejects ancestor Git trees
and symlinks, then calls the installed initializer and exclusively creates the example files.
The helper itself uses Python's standard library; it reads the installed CLI console entry
to use that product's Python environment for initialization. It does not install dependencies
into the system Python. An unavailable or unsupported launcher is reported before target creation.
It neither stages/commits nor executes the experiment. If preparation stops partway, inspect
the reported destination; preserve it and choose a new root rather than deleting or overwriting.
Generated project-rule markers remain unresolved under `project-instructions.md`.

The generated README provides the scoped local commit and `python3 tools/replay.py` steps.
Running that explicit example is separate execution authorization: it uses only this selected
arithmetic code and installed public `scholar-workflow experiment` commands, never paper code,
remote commands, Hub workers or credentials. This example requires a POSIX shell (macOS/Linux).
Its actual CLI version is recorded. Missing or
old CLI, uncommitted source, input collision or an existing Run stops with a diagnostic.

Expected outputs: one frozen Run, local Target, wrong-cwd failed Attempt, two succeeded
Attempts, separate logs, `artifacts/metrics.json`, `report.md`, `acceptance.json`, and
`cli-receipts.json`. Independent expected metrics are count=4, sum=10, mean=2.5; success/replay
bytes and promoted hash agree, and backup stays `not-verified`. The example report and context
are human-readable Chinese; machine identifiers keep schema spelling.

For a same-project new-root replay, clone the committed source, use installed
`scripts/init_project.py plan/apply` with its unchanged selection to restore local-first
directories, then run the clone's replay entry. Dataset and experiment state are regenerated,
not copied; project ID and frozen recipe stay stable if source and inputs stay unchanged.
New initialization intentionally generates a new project ID instead.

## Other real experiments

The bundled arithmetic failure scenario is only an example. A real experiment's inputs,
entrypoint, expected result and acceptable comparisons are selected for that actual request,
not inferred from this fixture. Do not deliberately break real training to imitate the example.
Use the record commands for observed execution only; a changed recipe needs a new Run.
Referenced papers/analyses keep their owning format, evidence, folder and Canvas contracts.
Do not generate fake outputs or force a reasoning process to match a sample.
