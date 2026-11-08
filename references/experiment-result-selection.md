# Readable experiment-result selection

Use for an explicit parent-initiated collection request, not a read-only experiment
review. Check the normally installed CLI help for `--selection-file` on
`experiment collection-plan`, `receive-run`, `update-plan` and `update-run`.
Missing support is an installation gap; do not substitute a source checkout or
silently copy the whole Run. This interface does not connect to a server, export
remote files, schedule collection or certify actual execution.

## Editable selection

Keep the operator's YAML or JSON outside the selected Run. It is a transfer
selection, not another scientific recipe or execution/artifact inventory.

```yaml
schema_version: 1
include:
  - path: artifacts/metrics.json
    kind: metrics
    purpose: Compare the recorded measurements under the captured configuration.
  - path: artifacts/comparison.png
    kind: image
    purpose: Inspect the representative visual result.
defer: []
```

The entries are examples, not files to fabricate. Include paths are exact,
Run-relative paths with `kind` and a readable `purpose`. Supported kinds are
`metrics`, `parameters`, `report`, `image`, `video` and `log`, with their supported
text/raster/PDF/video formats. The public schema is
`contracts/experiment-result-selection.schema.json`. Unknown keys, duplicate or
overlapping paths, missing selected files, unsafe paths and mismatched formats
refuse. No wildcards, absolute paths or commands are accepted inside the selection.

The collector always retains original Run/artifact records, all Attempt/Target
records, captured entry/config/environment/data-identity snapshots and execution
report/notes. Those required context files cannot be deferred. Readable artifacts
declared `local-required` must be selected or explicitly deferred with a reason:

```yaml
defer:
  - path: artifacts/full-results.csv
    reason: The large result table remains at the source pending selected transfer.
```

Deferral is not successful receipt of that evidence. The collected index retains
valid archive integrity but reports incomplete required results; an explicit
`collected --require-run` check exits 6 until those required results are available.
Do not use this branch to silently omit ordinary small required evidence.

Model/checkpoint roles and recognized serialized-model/array payloads cannot be
included, even under a different display kind. Unknown opaque formats are not
assumed readable. Text must be UTF-8 without binary control data; supported media
must have the expected format signature. These are format/scope checks, not full
media decoding, arbitrary payload-semantic detection or scientific validation.
Required binary context cannot be made readable by renaming or rewriting its
frozen record; report the incompatible capture instead.

## Plan, receive and read back

1. `experiment collection-plan --project-root PARENT --child-root CHILD --run-id RUN
   --selection-file SELECTION --json` is read-only. Review received files, all
   recorded Attempts and every omitted path/reason. The evidence digest binds the
   normalized selection, received bytes and omitted declarations. Models and other
   omitted bytes are not opened or hashed. An omitted hash/size, when present, is
   copied from the original artifact declaration and remains **unverified**.
2. `experiment receive-run` uses the same selection and the three existing
   `--expected-parent-sha256`, `--expected-child-sha256` and
   `--expected-evidence-sha256` values from that exact plan. Stale scope, changed
   inputs or conflicts refuse before publication; no implicit overwrite occurs.
3. Read `experiment collected --project-root PARENT --child-project-id CHILD_UUID
   --require-run RUN --language en` (or `zh`). Open the actual received metrics,
   config and execution-report links; local report/notes remain independent.
   Dispatch, integrity, execution, scientific analysis and human assessment are
   distinct outcomes.

The child root is explicitly accessible evidence with matching child/parent
declarations. A separately staged readable subset may retain a model's original
artifact declaration without its bytes; the new receipt records it as omitted.
This does not prove the remote path, deployment or omitted bytes actually exist.
Native transfer needs its own authorized scope, identity checks and stable selection;
there is no blanket recursive-mirror or automatic SSH capability here.

## Stored result and updates

Selective reception writes schema-2 `.collection.json`, retaining the original
source-to-local mapping and adding `result_delivery`: the normalized selection,
omitted paths with original declared metadata, reasons, and
`omitted_byte_verification: not-performed`. Run/Attempt/artifact source records
remain byte-identical. A child's `local-required` retention is an original child
fact, not proof that the parent received its bytes. The parent reader uses the
receipt to distinguish actual local results from unreceived source declarations.

Schema-1 archives remain readable in place, including previously stored payloads;
this feature neither deletes them nor rewrites their receipts. New default whole-Run
collection refuses model/unclassified payloads before opening them and accepts only
supported readable results. A schema-1 write is not a fallback around selection.

For later versions, use `update-plan` and `update-run` with the explicit selection
and the existing four byte baselines. Already received evidence cannot disappear
when the selection changes. Existing frozen-recipe, lifecycle, artifact-identity,
local-analysis and collision protections remain. A selective archive cannot silently
downgrade to schema 1. The existing journal stages original before/after bytes;
recovery uses its two full receipt versions and works without the source child.
Interrupted updates remain pending until explicit commit/rollback. Recovery material
is not verified backup, and a pending marker is not proof of a live worker.
