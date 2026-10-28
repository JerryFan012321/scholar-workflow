# Native-tool separation — 2026-10-28

## Confirmed direction

Retain Skills, deterministic content operations and accepted paper/Canvas,
Field-library, project and experiment output contracts. Stop expanding the
self-built Hub/explorer application. Zotero, Obsidian, cmux, VS Code and agent
hosts retain their native ownership, editing, configuration and session roles.
The current installed 0.49.0 remains unchanged by source edits in this batch.

## Implementation slices

1. Retire embedded Codex configuration, task mutation and worker entry points.
   Existing configuration must not reactivate execution. Preserve history reads
   and unrelated native-open/document operations.
2. Expose the supported Field content plans/transactions locally. Keep exact
   scopes, digests, CAS, external-writer assertions and journal recovery. Extract
   content cores with compatibility aliases, without rewriting data formats.
   Unsupported joint legacy staging stays unavailable, not silently simulated.
3. Move plugin-development Skill discovery outside runtime payloads. Keep generic
   project-management Skills in the product; actual projects own their execution
   task Skills and reference shared output contracts.
4. Record complete knowledge asset units and the local-parent pull decision in
   shared runtime references. This does not create a new generic asset registry,
   migrate owners or claim SSH/result-export automation exists.

## Decisions that are settled

- The local parent pulls human-recognizable analytical results: actual configs,
  metrics, representative result tables/figures and necessary records. Model,
  weights and checkpoint bytes stay remote. Large raw data stays remote too.
- Existing paper/blog/document identities identify complete asset units with
  explicit associated context. Management, analysis, viewing and editing have
  separate observable results. Source/Field is a container/location layer.
- Lab/researcher watchlists and monitored sources remain separate documents or
  databases. A selected update is not automatically a knowledge archive.

## Open and excluded work

Multidimensional viewing/editing is not decided. Preserve current dimensions,
records, evidence, relationships and saved queries without choosing another UI
or changing their schema. Agentero compatibility requires its own later review.
Selective result export, actual SSH pulling and delivery triggers need separate
implementation and acceptance; no remote operation is part of this batch.

No existing paper package, formal Vault/Zotero data, server, service process or
main branch is changed. Publication and normal installation are separate steps.

## Verification boundary

Use synthetic runtime configurations, registered temporary Source/Field fixtures
and a disposable release Git repository. Before running, declare input/actions,
expected refusal or successful local transaction, impact and result artifact.
Test old activation paths, local content operation without HTTP/cmux/token,
stale-plan/interruption safety and runtime Skill packaging. Preserve source-data
format compatibility. Tests that require installation remain pending until a
normally installed hotfix is explicitly delivered and checked.
