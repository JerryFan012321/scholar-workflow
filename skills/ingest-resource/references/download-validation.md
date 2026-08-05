# Download Validation

Where paper PDFs may come from (arXiv-only), version handling, and the no-PDF case
are in the shared `references/source-policy.md`. This file covers only the
mechanics of validating a download.

## Download flow

1. Download the arXiv PDF directly into `paper_inbox`.
2. Validate (below). On success the PDF stays in the inbox until the host imports it into
   Zotero via zotero-mcp (`write_item import`); on failure it is discarded.

## Validation checks

| Check | Rule |
|---|---|
| Magic bytes | Must start with `%PDF` |
| Size | ≤ 50 MB (abort mid-stream if exceeded) |
| SHA-256 | Compute and record for the attachment record |

## Failure handling

- Any check fails → mark the item `download_failed`, keep the batch going.
- The job is resumable: re-running `apply` on the same input retries only items not
  already downloaded to the inbox, so it does not re-download completed ones.
