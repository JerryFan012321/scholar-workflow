# Storage Policy (shared)

Canonical rule for where every object lives. Applies to all skills and agents.

## Source-of-truth allocation

| Object | Authoritative store | Root |
|---|---|---|
| Paper bibliography, tags, attachment links | Zotero (read/write via Local API) | Zotero-managed |
| Paper PDFs (after ingest) | Zotero storage | Zotero-managed |
| Downloaded paper PDFs (awaiting ingest) | Inbox | `paper_inbox` |
| Personal knowledge, notes, technical docs | Obsidian Vault | `research_vault_root` |
| JSON Canvas Hub identity (content stays in Canvas) | Obsidian Vault | `.scholar-workflow/artifacts.yml` |
| Images, data, and supplements attached to Vault notes | Obsidian Vault | `research_vault_root/attachments/` + `.scholar-workflow/assets.yml` relation manifest |
| Knowledge outline, projects, tasks | Notion | Notion cloud |
| Plugin runtime state (mappings, cursors, jobs, audit) | State store | `SCHOLAR_WORKFLOW_HOME` |

## Invariants

1. Downloaded paper PDFs land only in `paper_inbox`; ingest into Zotero goes through
   `scholar-workflow zotero ingest`, which uploads the file into Zotero storage.
   Technical documents live in the Vault even when they are PDFs. Never swap.
2. A paper has at most one identity in the authoritative library (one Zotero item).
   Collections are many-to-one projections of items, not separate identities.
3. The Obsidian paper table is a rebuildable derived index, not source of truth.
4. Notion stores no files and never overwrites human-authored fields.
5. The state store holds only mappings, cursors, job state, and audit — never
   knowledge content and never a mirror of Zotero. Existence, metadata, and semantic
   recall are fetched live from the Zotero Local API, never cached locally (INV13
   deprecated the old resource cache).
6. Vault assets are not Zotero attachments. Their bytes stay in the Vault and their
   owner relation is declared in `.scholar-workflow/assets.yml`; a Markdown wikilink is
   presentation only and is never parsed as relationship authority. Hub uploads use a
   server-derived relative path and never write into Zotero storage.
7. JSON Canvas remains a standard `nodes`/`edges` document. Hub identity for an analysis
   Canvas is declared in `.scholar-workflow/artifacts.yml`, never injected as private
   top-level Canvas fields or inferred from its filename.

## PDF handling

The plugin downloads PDFs into `paper_inbox`, then ingests them with
`scholar-workflow zotero ingest`. The Local API creates an imported attachment and uses
Zotero's three-phase upload flow; Zotero owns the resulting bytes. The authoritative
attachment record comes from `scholar-workflow zotero get <item-key> --children`, queried
live — never derive identity or state by assuming a `storage/` path.

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
