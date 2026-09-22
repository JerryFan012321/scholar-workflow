# Experiment Records

Read this reference when initialization is followed by Run, Attempt, Target, artifact, or backup
record management. These commands manage records only; they never launch training or construct
remote shell commands.

## Authority and mutability

- experiments/<run-id>/run.yaml is the machine-neutral recipe authority.
- The first Attempt freezes its Run recipe. A changed commit, script, resolved config, dataset
  selection, seed, or environment definition requires a new Run.
- experiments/<run-id>/attempts/<attempt-id>/attempt.yaml records one execution or retry and
  snapshots the selected Target profile hash.
- experiments/profiles/targets/<target-id>.yaml separates execution placement from env/.
  Targets are explicit local or ssh profiles and contain no credentials or arbitrary command.
- experiments/index.yaml is rebuildable and never outranks the Run bundles.

Run IDs use YYYYMMDD-HHMM-slug; Attempt and Target IDs are lowercase slugs.

## Deterministic commands

Use scholar-workflow experiment:

- new-run snapshots a clean committed recipe into a new Run.
- target-add validates and registers one Target YAML.
- new-attempt freezes the Run and records the Target hash.
- start-attempt records the transition from planned to running and the actual start time; it does
  not launch a process.
- finalize-attempt accepts an explicit observed-runtime JSON record and optional output inventory.
- validate recomputes recipe, input, Target, and artifact checksums.
- promote copies one selected artifact atomically into the Run and leaves backup state unverified.
- record-remote records a large artifact as manifest-only.
- index rebuilds the optional index.
- migrate-plan reports legacy candidates without writes.

The commands accept paths and structured fields, not a free-form execution command. Promotion
rejects absolute or escaping destinations, symlinks, and same-name different-content collisions.

## Retention and backup

- local-required: metadata and the local file are required.
- local-selected: the user selected this result for local promotion.
- manifest-only: only identity and remote location are retained locally.

Promotion proves that one local copy matches its source. It never sets backup state to verified.
The public CLI has no backup-verification writer until a trusted backup-medium registry,
retention schedule, and recovery contract are approved.
