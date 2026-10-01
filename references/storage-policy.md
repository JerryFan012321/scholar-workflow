# Storage Policy (shared)

Canonical rule for where every object lives. Applies to all skills and agents.

## Source-of-truth allocation

| Object | Authoritative store | Root |
|---|---|---|
| Paper bibliography, tags, attachment links, formal annotations | Zotero (read/write via Local API; annotations edited by ZotFlow/Zotero) | Zotero-managed |
| Paper PDFs (after ingest) | Zotero storage | Zotero-managed |
| Downloaded paper PDFs (awaiting ingest) | Inbox | `paper_inbox` |
| Personal knowledge, notes, technical docs | Registered Obsidian Source/Field | trusted `folder_id` + `.scholar-workflow/fields.yml` |
| JSON Canvas identity (content stays in Canvas) | Registered Obsidian Source | `.scholar-workflow/artifacts.yml` |
| Images, data, and supplements attached to Vault notes | Registered Obsidian Source | Source-relative `attachments/` + `.scholar-workflow/assets.yml` relation manifest |
| ZotFlow Source Notes | ZotFlow-owned path inside its registered Obsidian Source | disjoint from Better Notes and Scholar-managed paths |
| Annotated PDF snapshots for external readers | Derived snapshot store | hash-bound copy; never the Zotero attachment path |
| Reusable knowledge navigation, outline, prose and Canvas | Obsidian Source/Field | owned Markdown and explicit Knowledge manifests |
| Project identity, layout, project-local notes and experiment archives | Project | `project-layout.json`, `docs/`, `experiments/` |
| Explicit project material associations | Project | independent `project-context.json`; references only, not external content |
| Human-maintained project/task management views | Notion | Notion cloud; not authority for project code, archives or knowledge prose |
| Machine Notion projections | Original Zotero/Vault/project records | one-way summaries and stable native links; no second content store |
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
   presentation only and is never parsed as relationship authority. Any remaining legacy
   Hub upload uses a server-derived relative path and never writes into Zotero storage.
7. JSON Canvas remains a standard `nodes`/`edges` document. Knowledge identity for an analysis
   Canvas is declared in `.scholar-workflow/artifacts.yml`, never injected as private
   top-level Canvas fields or inferred from its filename.
8. One Obsidian Source may expose multiple Fields. The legacy `research_vault_root`
   is a migration candidate, not a required singleton root. Host paths stay in the
   folder registry; portable Source/Field identity and navigation stay in
   `.scholar-workflow/fields.yml`.
9. ZotFlow Source Notes, Better Notes output, and Scholar analysis/annotation documents
   have separate writer ownership and non-overlapping path prefixes.
10. ZotFlow may read an imported PDF from Zotero's local `storage` only when its desktop
    local-storage mode is positively verified. Hub actions must not download a missing
    attachment through Zotero Web API/WebDAV; metadata/annotation sync remains separate.
    Zotero native and ZotFlow launches revalidate the Local API attachment locator and
    the presence of local bytes before opening. This does not change the user's independent
    Zotero File Syncing configuration.
11. A project may explicitly reference existing Zotero/Obsidian materials for navigation
    and context use without copying their bodies or taking over their ownership. The
    independent `project-context.json` binds the same `project_id` as the layout manifest;
    project-local files use safe relative paths and external entries use stable provider
    identities. Registration alone is not source availability or content verification.
12. Removing a project reference never deletes, moves or edits the referenced object.
    References grant no cross-system write permission and create no automatic sync or
    cascading deletion. Explicit copies/archive operations still create independently
    evolving target content, with no implicit overwrite or required provenance tracking.
13. Project overview Markdown is a rebuildable navigation view, not a new authoritative
    store. Reading project context does not require Hub, a cmux workspace, a new homepage
    or Scholar-managed Codex tasks; native tools retain their own content and configuration.

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

## Annotated PDF snapshots

Zotero annotations are database objects, not edits to the authoritative PDF bytes.
When another reader needs visible annotations, generate an explicit derived snapshot
identified by `source_pdf_hash + annotation_set_hash`. Never replace the imported
attachment, automatically import the snapshot into Zotero, or treat edits to the
snapshot as synchronization. Unsupported annotation types make the export incomplete
or failed and must be reported explicitly.
