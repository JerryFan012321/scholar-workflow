# Paper Analysis Batch Contract

Load this file only for a user-selected batch of already-ingested papers. The unit of validation,
repair, cleanup, and success is one paper; a failing item never rolls back a conformant sibling.

## State and staging

Persist state under the plugin state root, separate from the arXiv download job state. Observable
item states are:

```text
queued → running → validated
                 → repaired
                 → failed
```

Run the deterministic gate with:

```bash
scholar-workflow analysis batch-run --request <batch.json>
```

The request must conform to `analysis-batch.schema.json`. If the host has produced one targeted
repair IR for each failed item, pass it once with `--repair-request <batch.json>`; the persistent
repair budget is claimed before the repair callback runs. The command exits nonzero for a partial
or failed batch, so emitting files alone can never be interpreted as success.

For each item:

1. Build the complete Markdown/Canvas pair under the batch's controlled staging directory.
2. Run hard conformance before any canonical Vault write or catalog registration.
3. When all findings are repairable, allow one targeted repair and run conformance once more.
4. On success, retain the staged pair for the later commit boundary and record `validated` or
   `repaired`.
5. On failure, persist structured diagnostics first, delete only files owned by that item's stage
   receipt, then record `failed`. If cleanup itself fails, retain the exact stage path in state so
   the read-only audit can report the residue; never hide it by clearing the pointer.

`repair_count` is persistent and never exceeds one. Replaying the same completed or failed batch
returns its recorded result; it does not regenerate content or open another repair loop. Reusing a
batch ID with different input is an identity conflict.

## Canonical commit

`validated` and `repaired` mean that the staged bundle passed conformance; they do not mean it is
already canonical. Commit one staged bundle with:

```bash
scholar-workflow analysis commit-bundle \
  --request <analysis-commit-request.json> \
  --vault-root <research-vault-root> \
  --state-db <analysis.db> \
  --stage-root <stage-root>
```

The request declares all three Vault-relative targets, their exact base hashes, and every relation
or projection to record. The command rechecks the persisted batch state, staged conformance
sidecar, base revisions, and paths before replacing anything. It writes a transaction journal
first and returns an `AnalysisCommitReceipt` containing an idempotent `KnowledgeChangeSet`.
Reusing the same commit ID and input returns the same receipt; reusing the ID for different input
or changing a canonical file after its receipt is an identity conflict.

Markdown, Canvas, and sidecar form one recoverable commit unit. Rollback restores a file only
while its current hash is still the hash written by this transaction. A concurrent human edit is
retained and the commit becomes a partial/manual-recovery result. Paths outside the Vault, missing
parent directories, symlinks, and stale base hashes fail closed. The change set contains only the
three committed artifacts and caller-supplied relations/projections; prose and wikilinks are never
scanned for authority.

## Isolation and safety

- A batch aggregates per-paper results as `completed`, `partial`, or `failed`; it is not an
  all-or-nothing transaction.
- Staging accepts only controlled item IDs and known filenames. Path escape, symlink traversal,
  and unknown files fail closed.
- Failure cleanup removes staged analysis drafts only. It never deletes or changes a Zotero item,
  attachment, PDF, canonical analysis pair, annotation, or literature tree.
- A conformance failure after one repair stays failed until the user creates a new batch. Preserve
  its bounded findings; do not preserve the full failed analysis in the state database.
- Source gaps are valid evidence states. They are not automatically repairable by invention.
- A human-edit/revision conflict is non-repairable and remains outside automatic batch repair.

The versioned contracts are `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-batch.schema.json`,
`analysis-commit-request.schema.json`, `analysis-commit-receipt.schema.json`,
`knowledge-change-set.schema.json`, and `knowledge-audit-manifest.schema.json`. The batch database
contains identities, states, hashes/paths, and diagnostics only; it never mirrors paper text or
analysis prose. Transaction backups live only in the separate commit-state boundary.

## Read-only maintenance audit

The maintenance audit receives an explicit manifest-derived target list; it does not scan the
Vault or project directories. For each pair it reuses hard conformance, reports missing files,
invalid Canvas JSON, unsafe symlinks, and Markdown/Canvas drift, then returns a versioned report
matching `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-audit.schema.json`.

`scholar-workflow analysis audit-batches` opens the batch database read-only and reports unfinished
items plus retained failed stages. `scholar-workflow analysis audit-knowledge --manifest <json>
--vault-root <root>` audits an explicit Knowledge inventory for duplicate identities/paths,
orphaned supporting documents, unresolved template markers, raw port-23128 links, pair
conformance, and catalog projection/revision drift. A catalog outside the Vault must use the
separate explicit `--catalog-root`; neither command discovers project directories.

The audit performs no repair and writes no Zotero, Vault, Notion, catalog, or state content. A
weekly scheduler may call it, but scheduling is an operational opt-in rather than a side effect of
analysis. Unchanged findings should not generate repeated notifications.
