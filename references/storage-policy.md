# Storage Policy (shared)

Canonical rule for where every object lives. Applies to all skills and agents.

## Source-of-truth allocation

| Object | Authoritative store | Root |
|---|---|---|
| Paper bibliography, tags, attachment links | Zotero (read/write via zotero-mcp) | Zotero-managed |
| Paper PDFs (after ingest) | Zotero storage | Zotero-managed |
| Downloaded paper PDFs (awaiting ingest) | Inbox | `paper_inbox` |
| Personal knowledge, notes, technical docs | Obsidian Vault | `vault_root` |
| Knowledge outline, projects, tasks | Notion | Notion cloud |
| Plugin runtime state (mappings, cursors, jobs, audit) | State store | `SCHOLAR_WORKFLOW_HOME` |

## Invariants

1. Downloaded paper PDFs land only in `paper_inbox`; ingest into Zotero goes through
   zotero-mcp (`write_item` import), which relocates the file into Zotero storage.
   Technical documents live in the Vault even when they are PDFs. Never swap.
2. A paper has at most one identity in the authoritative library (one Zotero item).
   Collections are many-to-one projections of items, not separate identities.
3. The Obsidian paper table is a rebuildable derived index, not source of truth.
4. Notion stores no files and never overwrites human-authored fields.
5. The state store holds only mappings, cursors, job state, and audit — never
   knowledge content and never a mirror of Zotero. Existence, metadata, and semantic
   recall are fetched live from zotero-mcp, never cached locally (INV13 deprecated the
   old resource cache).

## PDF handling

The plugin downloads PDFs into `paper_inbox`, then ingests them into Zotero via
zotero-mcp `write_item import`, which places a copy under `storage/<attachmentKey>/`.
The authoritative current path of an attachment comes from Zotero attachment relations
(via zotero-mcp `get_item_details`), queried live — never assume `storage/`.

## Attachment storage model (linkMode)

An attachment's `linkMode` decides where its bytes live and whether it is portable
across machines:

| linkMode | Meaning | Path form | Cross-machine |
|---|---|---|---|
| 0 | imported file | `storage/<key>/` | via Zotero File Syncing |
| 1 | imported URL (snapshot) | `storage/<key>/` | via Zotero File Syncing |
| 2 | **linked file** (external dir) | relative `attachments:…` **iff** inside base dir, else absolute | via the external dir's own sync only |
| 3 | linked URL | — | n/a |

Ingested paper PDFs stay imported (mode 0) so Zotero File Syncing carries them across
machines. A linked file (mode 2) is portable only when its stored path is relative
(`attachments:…`), and its bytes never travel via Zotero File Syncing — so a linked
attachment with an absolute path (`/Users/…`) is cross-machine drift to report.
