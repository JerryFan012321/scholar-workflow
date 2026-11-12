# Metadata-only Zotero intake and knowledge-management handoff

Use for configuring the recommendation page's receiving collection, processing
human-selected entries, or beginning knowledge management from that collection.
This is distinct from an explicitly requested full paper/PDF import.

## Scope and authority

Discovery agents prepare verified metadata, full abstract translations or sourced
synopses and related links. The person reviews and selects. Code receives that
existing information into Zotero; it does not call a model, redraft a summary,
download/upload original files, capture a webpage or create a Vault unit.

Zotero owns the received bibliography and child note. The recommendation pool owns
human decisions/history and actual write receipts. Project background remains in
the originating project. A received item is the knowledge-management entry, not a
completed analysis or a new replacement identity for an existing asset unit.

## Configure once

```text
scholar-research recommendations --profile personal ingestion targets
scholar-research recommendations --profile personal intake target
scholar-research recommendations --profile personal intake target --input target.json
```

```json
{"collection_key": "<existing Zotero collection key>", "expected_revision": 0, "enabled": true}
```

Select the actual receiving collection; no collection name is hardcoded. Settings
offers the same choice. Configuration binds the current Local API identity and
collection key; it never imports all old selected candidates. New human selections
queue automatically. Rename keeps the collection identity; another provider needs
fresh confirmation. Set `enabled: false` with its current revision to pause intake.

## Human action and automatic execution

A saved decision/evaluation is complete immediately and its feedback is projected
without an agent. For a currently reviewed selection and configured target, code
also creates an intake job in that transaction. The page processes it immediately;
the running headless service continues bounded retryable jobs even with no browser.
An external harness can explicitly call `intake process` without running a model.

```text
scholar-research recommendations --profile personal intake process --limit 5
scholar-research recommendations --profile personal intake history
scholar-research recommendations --profile personal intake process --limit 1 --retry
```

Before writing, verify the current selection/review, target identity, exact work and
version. Reuse an exact item, add the collection, or create it when absent. Ambiguous
identities and conflicting versions require inspection; never merge or overwrite
human metadata. All external writes use the Zotero Local API and existing native
authorization. `test` cannot contact native Zotero; it needs an injected fake adapter.

## Received content

| Content | Destination |
|---|---|
| Title, real item type, authors/organization, date, URL and available DOI/arXiv identity | Standard Zotero fields |
| Actual original abstract/description | Abstract field; no fabricated original |
| Already-reviewed Chinese abstract translation or sourced synopsis | One child note named 收录说明, explicitly identified as 摘要译文 or 资料总结 |
| Human comments, score and classification/use instructions | Same child note; preserve the exact words and attribution |
| Recommendation reasons, source/task and available project association | Same child note, separate from the person's words |
| Existing original/project/Blog/code/model/data/demo/documentation links | Same note's related resources; URLs only |
| Selection time, receiving scope and actual item/note identities | Readable note and machine receipt, without visible hashes/JSON |

Blog maps to `blogPost`, project/release pages to `webpage`, arXiv papers to
`preprint`; explicitly supplied verified item types retain their proper native
type. Missing metadata stays unknown. The generic fallback is diagnosed rather
than inventing a publication venue. A resource need not have a PDF to be received.

The note has these human-readable sections: 中文介绍, 用户意见, 推荐背景, 相关资源,
收录记录. Do not copy the source text into a new original-file attachment. Machine
identity is kept out of the visible prose. A separate managed-note tag permits
idempotent lookup, not a second formal annotation system.

Observed parent identity is saved before note creation. Retry searches the same
parent/note instead of duplicating them. Later feedback on a selected item can
refresh the managed note only while its observed content still matches the last
managed version. Human/external note edits stop automatic replacement.

## Status and failure

`pending` is queued, `running` is executing, `completed` has verified parent,
collection and note identities. Local API/authorization unavailability is retained
as `retry` with bounded backoff; identity conflicts are `conflict`, uncertain
results are `needs_attention`. Inspect before explicit retry. Withdrawal cancels
pending work and never deletes an already-received Zotero item. Changed targets
do not redirect an earlier human selection silently.

A successful metadata receipt does not establish an original PDF/HTML, Vault
registration, analysis pair, scientific support or human acceptance. Keep those
results separate. Source files and knowledge status remain `not_requested` here.

## Knowledge-management entry

```text
scholar-research recommendations --profile personal intake entries --limit 50
```

This reads the configured collection and each returned item's child notes/assets
through Local API, including manual entries added there through mature tools. It
does not execute project tasks or read project background. Use the metadata, exact
human instructions and source links to identify the next authorized management
operation. Expand project context only if the task requires it and its scope permits.

Pages accept `--start` and `--limit` (1-100) and return `next_start` and
`may_have_more`; continue only for the requested scope. A page is not a complete
library scan or a frozen snapshot of concurrent native edits. Received entries
also expose their known recommendation/task locators without reading project text.

Use the existing ingest/registration, analysis, annotation, literature organization
or project Skills as applicable. Preserve complete existing asset units and their
accepted Markdown/Canvas formats. Obtaining originals, filling details, selecting
knowledge ownership and completing analysis belong to this later management task.
Removing a completed queue membership, changing human notes or performing a
destructive operation retains its own authorization; reading this queue does not
authorize those writes.
