# Download Validation

Where paper PDFs may come from (arXiv-only), version handling, and the no-PDF case
are in the shared `references/source-policy.md`. This file covers only the
mechanics of validating a download before any write.

## Temp-dir flow

1. Download the arXiv PDF into a temp dir under `papers_root/.tmp` — never write the
   final location directly.
2. Validate (below). Only on success does `ZoteroWriteAdapter` finalize the path.

## Validation checks

| Check | Rule |
|---|---|
| Magic bytes | Must start with `%PDF` |
| Size | ≤ 50 MB (abort mid-stream if exceeded) |
| SHA-256 | Compute and record for the attachment record |

## Failure handling

- Any check fails → mark the item `download_failed`, keep the batch going.
- The job is resumable: a re-run with the same approved `plan_id` retries only the
  failed item and does not duplicate completed side effects.
