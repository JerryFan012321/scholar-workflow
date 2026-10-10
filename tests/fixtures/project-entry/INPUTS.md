# Project-entry raw synthetic inputs

## Preparation boundary

These handwritten inputs were prepared after EXPECTED.md and before any runtime skill output candidate. They are synthetic source material, not generated PROJECT results, real papers, an initialized experiment archive or executed experiments. No tests, project source, experiment/CLI commands, readers, services, network calls, registration, migration or publication were run during preparation. Original experiment-review inputs and EXPECTED.md were not modified.

The only PROJECT.md here is the pre-existing-content stand-in in preservation-conflict; it is protected raw input, not a candidate. Each scenario has a managed project/ directory and a distinct sibling knowledge-source/ directory. Creating this synthetic fixture is not a project-to-knowledge copy or an ownership registration.

JSON records reuse existing Project System RunRecord/AttemptRecord/ArtifactManifest and project-layout/project-context field shapes; no public schema or new CLI is introduced. Selected .json record names are explicit test inputs, not a claim that runtime experiment commands discover this small directory structure. Paper notes and two tiny native editable Canvas files are navigation inputs, not full paper-analysis/template conformance fixtures.

## Scope and declared states

| Scenario | Plan authority | Existing internal entry | Selected Runs / Attempts / Artifacts | Reader and backup |
|---|---|---|---|---|
| complete-inline | REQUEST.md supplies frozen input for a first inline PROJECT plan; no separately maintained SCHEDULE | No PROJECT exists | Baseline: failed, success, replay; variant: success. Two report Artifact records bind the existing handwritten result.md files to success, not replay | Reader not queried; both backups not-verified |
| sparse-external-plan | project/SCHEDULE.md is the sole detailed authority; no dates recorded | No PROJECT exists | One Run with success and replay; one local-required report declaration points to a deliberately missing file | Reader not queried; backup not-verified |
| preservation-conflict | Undecided; existing PROJECT and SCHEDULE directly conflict about 2026-11-05 | Protected raw PROJECT exists; preview-only request | One Run with success; one manifest-only remote report declaration, content/address unavailable | Reader not queried; backup not-verified |

All recorded outcomes, timestamps, scores, promotion times and frozen states are handwritten declarations. No process produced them. Source commit 111…111, recipe hashes and target-profile zero hashes are explicitly unverified synthetic placeholders. The complete scenario file snapshots and result Artifact sizes/hashes were computed from prepared static bytes, not from execution. The sparse missing config/report hashes and size are synthetic unverified declarations, not existence or integrity evidence. Config.json carries the small dataset/environment role declarations; reuse of its bytes does not certify a real dataset or environment. No log files, source revisions, host observations, reader mappings or external backups are supplied.

## Qualified paper-unit selections

The Source ID plus object ID is the explicit qualified declaration. Paths are scenario-relative, not identity, ownership proof, read/write permission or a verified reader route. The knowledge folders are not registered with a host registry and must not be silently registered during this test.

- complete-inline: Source 88888888-8888-4888-8888-888888888881; resource:fixture:alpha → knowledge-source/paper-alpha/Source.md; analysis:fixture:alpha → knowledge-source/paper-alpha/Analysis.md; canvas:fixture:alpha → knowledge-source/paper-alpha/Analysis.canvas (native text input, unobserved in editor).
- sparse-external-plan: Source 88888888-8888-4888-8888-888888888882; resource:fixture:beta → knowledge-source/paper-beta/Source.md; analysis:fixture:beta → knowledge-source/paper-beta/Analysis.md; canvas:fixture:beta → knowledge-source/paper-beta/Analysis.canvas (deliberately absent).
- preservation-conflict: Source 88888888-8888-4888-8888-888888888883; resource:fixture:gamma → knowledge-source/paper-gamma/Source.md; analysis:fixture:gamma → knowledge-source/paper-gamma/Analysis.md; canvas:fixture:gamma → knowledge-source/paper-gamma/Analysis.canvas (native text input, unobserved in editor).

## Complete prepared file inventory

Paths below are relative to tests/fixtures/project-entry/. EXPECTED.md is the pre-existing independent oracle; INPUTS.md is this preparation inventory. The scenario files listed below are raw inputs only.

### complete-inline — 20 files

- `complete-inline/REQUEST.md`
- `complete-inline/knowledge-source/paper-alpha/Analysis.canvas`
- `complete-inline/knowledge-source/paper-alpha/Analysis.md`
- `complete-inline/knowledge-source/paper-alpha/Source.md`
- `complete-inline/project/README.md`
- `complete-inline/project/config.json`
- `complete-inline/project/experiments/20261009-1000-baseline/artifacts.json`
- `complete-inline/project/experiments/20261009-1000-baseline/artifacts/result.md`
- `complete-inline/project/experiments/20261009-1000-baseline/attempts/failed.json`
- `complete-inline/project/experiments/20261009-1000-baseline/attempts/replay.json`
- `complete-inline/project/experiments/20261009-1000-baseline/attempts/success.json`
- `complete-inline/project/experiments/20261009-1000-baseline/run.json`
- `complete-inline/project/experiments/20261009-1100-variant/artifacts.json`
- `complete-inline/project/experiments/20261009-1100-variant/artifacts/result.md`
- `complete-inline/project/experiments/20261009-1100-variant/attempts/success.json`
- `complete-inline/project/experiments/20261009-1100-variant/run.json`
- `complete-inline/project/project-context.json`
- `complete-inline/project/project-layout.json`
- `complete-inline/project/src/main.py`
- `complete-inline/project/src/prepare.py`

### sparse-external-plan — 15 files

- `sparse-external-plan/REQUEST.md`
- `sparse-external-plan/knowledge-source/paper-beta/Analysis.md`
- `sparse-external-plan/knowledge-source/paper-beta/Source.md`
- `sparse-external-plan/project/README.md`
- `sparse-external-plan/project/SCHEDULE.md`
- `sparse-external-plan/project/config.json`
- `sparse-external-plan/project/docs/module-claim.md`
- `sparse-external-plan/project/experiments/20261009-1200-sparse/artifacts.json`
- `sparse-external-plan/project/experiments/20261009-1200-sparse/attempts/replay.json`
- `sparse-external-plan/project/experiments/20261009-1200-sparse/attempts/success.json`
- `sparse-external-plan/project/experiments/20261009-1200-sparse/run.json`
- `sparse-external-plan/project/project-context.json`
- `sparse-external-plan/project/project-layout.json`
- `sparse-external-plan/project/src/main.py`
- `sparse-external-plan/project/src/prepare.py`

### preservation-conflict — 15 files

- `preservation-conflict/REQUEST.md`
- `preservation-conflict/knowledge-source/paper-gamma/Analysis.canvas`
- `preservation-conflict/knowledge-source/paper-gamma/Analysis.md`
- `preservation-conflict/knowledge-source/paper-gamma/Source.md`
- `preservation-conflict/project/PROJECT.md`
- `preservation-conflict/project/README.md`
- `preservation-conflict/project/SCHEDULE.md`
- `preservation-conflict/project/config.json`
- `preservation-conflict/project/experiments/20261009-1300-conflict/artifacts.json`
- `preservation-conflict/project/experiments/20261009-1300-conflict/attempts/success.json`
- `preservation-conflict/project/experiments/20261009-1300-conflict/run.json`
- `preservation-conflict/project/project-context.json`
- `preservation-conflict/project/project-layout.json`
- `preservation-conflict/project/src/main.py`
- `preservation-conflict/project/src/prepare.py`

## Deliberately absent or unavailable entrances

- complete-inline/project/PROJECT.md and complete-inline/project/SCHEDULE.md: absent before candidate creation. Plan source is REQUEST.md; do not mistake the request for another maintained schedule.
- sparse-external-plan/project/PROJECT.md: absent before candidate creation.
- sparse-external-plan/project/configs/benchmark.json: selected configuration deliberately absent; config.json is contextual data, not a silent replacement for that selection.
- sparse-external-plan/project/experiments/20261009-1200-sparse/artifacts/missing-report.md: deliberately absent despite the local-copy declaration; do not create it, treat it as zero, or claim integrity.
- sparse-external-plan/knowledge-source/paper-beta/Analysis.canvas: deliberately absent despite its explicit object reference; do not hide the entry or produce a substitute.
- sparse-external-plan/project/src/gpu_optimizer.py: not supplied. The docs/module-claim.md assertion is unverified and is not a static code edge.
- preservation-conflict: remote Artifact content and a callable remote address are unavailable. Do not fetch, generate a local copy or treat a same-named file as its content.
- All scenarios: process logs, actual host/runtime/commit observations, a Zotero PDF, reader/Vault binding, host Source registry and verified backup evidence are not supplied. Unqueried reader does not mean missing paper; missing data must not be filled by registration or execution.

## Permitted later output and preservation

A later, separately scoped skill exercise may prepare an independent readable PROJECT candidate for complete-inline/sparse-external-plan and a preview-only proposal for preservation-conflict. This input preparation does not execute that exercise or authorize publication. Existing inputs, especially README, the conflict PROJECT/SCHEDULE and knowledge units, remain unchanged. Direct relative file navigation is possible without an app/reader success claim; no ambiguous cross-Source wikilink or fabricated protocol route is needed.

Before executing the future exercise, record current input byte baselines and its exact output boundary, as required by the independent plan. Compare against EXPECTED.md, not a product validator's success flag. Native editing, VS Code link behavior, visible clarity and installed-skill behavior remain separate pending assessments.

Prepared inventory: 20 complete-inline files, 15 sparse-external-plan files, 15 preservation-conflict files; 50 raw scenario files plus this INPUTS.md. No candidate result or test report has been generated.
