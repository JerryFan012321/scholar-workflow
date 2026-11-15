# Workspace Asset Pool

Load when a selected experiment references shared inputs, registers reusable results,
relocates assets or considers shared-material cleanup. This extends
[experiment management](experiment-management.md); it does not change knowledge-unit
ownership, legacy archives or the separate selected-result return policy.

## Scope and location

The selected workspace has one discoverable asset entry for models, dataset indexes
and retained reusable experiment results. Reuse an existing suitable pool/index.
An `assets/` directory with an entry document and optional `models/`, `datasets/`
and `results/` areas is an example, not a required tree. A small pool can use one
readable index; its format follows the actual project's existing tools.

The entry can manage physical assets or references to assets already held on a
shared volume, in a native model cache or another authorized location. Registration
records those locations without copying their contents. Remote workspaces retain heavy
assets; the local research parent keeps selected analytical results and locators.
Cross-workspace references preserve the owning pool and version, not a second
independent inventory. Existing environment registrations stay in their own index;
link them rather than cloning environments or making another environment registry.

Expose the pool entry through the workspace/project AGENTS navigation and relevant
experiment entry when those files are in the task's authorized scope. An index is
not access permission. No global asset database, new service or automatic scan of
other projects is required. Ordinary project initialization does not populate a pool.

## Versioned references in recipes

For each referenced asset retain the following information in its owning index or
existing native catalog; recipes and result records refer to that entry/version:

- Stable identity within the owning pool, readable name, purpose and exact version.
- Actual location or obtainable source, and availability/verification state.
- Origin; for generated assets, the producing experiment, actual recipe/code version
  and result entry. A materially changed derivative records its source version.
- Appropriate integrity evidence, when verified, and known consumers/retention uses.
  Unknown consumers or unverified bytes remain explicit gaps, not invented checks.

Recipes reference identity plus an exact version, not only a mutable path or `latest`.
The actual execution/result record preserves the version resolved for that execution.
Relocation changes its locator, not its content identity. Changed content gets a new
version; do not relabel old results or silently replace bytes under an existing version.
Names such as `vehicle-a2@v1` are illustrative, not a new implemented resolver syntax.
Use the actual launcher's supported mapping/config; document a missing resolver rather
than pretending the identifier alone can be executed.

A recipe also retains obtainable code revisions, scripts, effective configuration,
environment and invocation for its reproduction scope. Asset references do not replace
these. Read-only experiments reference inputs without copying them. Check relevant metadata and
integrity according to the operation; routine lookup need not hash every large asset.
Visible summaries show useful names, versions and links; keep technical digests in
records rather than filling human prose with them.

## Read-only reuse and writable versions

Read-only use references the existing asset version directly. Inference, evaluation,
rendering from unchanged inputs, another seed/configuration, experiment registration
or phase archiving does not create another on-disk input copy. Loading an asset into
memory/device memory is not a retained filesystem replica. Do not copy inputs merely
to make each run directory self-contained or label a per-run copy an execution cache.

Create a writable derivative only when the task changes the asset's own content and
the original must remain available. Preserve the shared source version; write only
the changed files or independently usable delta when the native format supports it.
If an adapter/configuration is sufficient, retain it with the base-version reference
rather than duplicating the unchanged base. A full modified asset may require a new
full file; record that actual requirement, its source and resulting version.

Checkpoint/result retention follows its actual continuation, comparison or archive
purpose; modifying an asset does not require retaining every intermediate version.
Do not pre-copy an unchanged model just to run inference or before a tool can write
its new output separately. Newly generated outputs are not copies of the input.

## Registering results and handling copies

An experimental result with a declared retention/reuse purpose can become a pool
asset. The experiment continues to own its conditions, interpretation and provenance;
the pool owns the asset's location/version entry. Registration is not a scientific
approval, backup certificate or selection as a core experiment. Record actual validation
and limits. Only the human selects core experiments; not every result enters the pool.

Distinguish the requested operation:

| Operation | Required outcome |
|---|---|
| Register in place | Record the existing asset/version/location and purpose; do not create another payload copy. |
| Relocate into the pool | Use an explicit authorized source/destination plan, preserve concurrent edits, verify the destination and update affected locators/links before retiring the old location. Keep interrupted transfer state; an incomplete move is not a completed registration/cleanup. |
| Create a writable derivative | Only for changes to the asset itself; preserve the source and produce the required changed portion or full output as described above. Record its source, producing recipe and resulting version. |
| Perform a separately selected transfer | Selected local analysis, cross-host placement, delivery or backup has its own authorized destination and material scope. Reuse an available identical version at that destination; record origin/version, purpose and retention condition. Ordinary execution, registration or archiving does not authorize such a transfer. |

Keep one canonical payload location per retained asset version; any transfer replica
retains the same origin/version and an explicit purpose. An exact byte match does not alone authorize deletion; a copy
may serve an offline delivery or recovery purpose. An independently edited copy is
not interchangeable with its source. Do not invoke legacy `promote` to copy whole
result trees as a shortcut for pool registration. Do not move old archives implicitly.

## Phase cleanup and result return

Before removing a shared asset/version or replica, check declared recipe/result
references, active work and other retention purposes across its known consumers.
Use the experiment's selected archive-point pairs as retention inputs: removing an
unselected recipe/result does not implicitly select its shared asset for removal.
Closing one experiment does not retire assets used by another. No references is not
proof of no remaining value; unresolved uses stay undecided. Mark known invalid
assets/results and affected references honestly instead of silently retargeting them
to a new version. Update affected result entries through the main PROJECT as required
by the experiment contract.

Use [material operations](../skills/manage-experiments/references/material-operations.md)
for phase records, explicit file selection, interruption and selected return. The
current helper validates listed regular files under one selected root; it does not
resolve pool IDs, traverse shared references, validate all consumers or permit unsafe
paths/symlinks. Inspect an external asset only within its separately authorized root.

The local parent pulls useful selected analysis materials. Pool registration does
not authorize returning model weights, unreadable raw data or intermediate files.
Repeated local uses should reference the already-received version when suitable;
preserve local analysis and human edits. Report registration, physical location,
copy/transfer status and checks performed separately. No automatic mover, deduplicator
or pool-aware cleanup engine is supplied by this contract.
