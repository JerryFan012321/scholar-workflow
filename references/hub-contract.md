# Hub Control Plane v2 Contract

`HubDirectory` schema 2 is the only Hub root. It is a rebuildable control-plane
projection, not a knowledge database and not an authority for provider-owned
relationships.

```text
Zotero / Vault manifests / project manifests / explicit tool registry / Codex
                                  |
                                  v
                            HubDirectory
                    aggregate, route, validate, project
```

`HubCatalog` schema 1 survives only as the `knowledge_catalog` member of
`HubDirectory`. During migration, `GET /api/v1/catalog` is derived from that member;
there is no second catalog root or independently mutable v1 state.

## Authority and identity

- Zotero owns paper bibliography, PDFs, attachments, and formal annotations.
- The Vault owns human-readable Markdown/Canvas and its checked artifact/asset
  manifests. Those providers own their declared relationships.
- A project's `project-layout.json` owns its stable UUIDv4 `project_id`. The host
  registry maps that ID to one local root and capability set; it is a locator, not a
  portable identity source.
- The explicit `ToolDefinition` registry owns tool registrations. Hub never scans
  `$PATH` for tools.
- Codex owns transcript and thread identity. Hub task records may retain an explicit
  thread ID and approved summary, never a copied transcript.
- cmux owns transient workspace state. Hub keeps only process-local opaque workspace
  handles and a hashed instance fingerprint.
- Hub aggregates and renders relationships supplied by these authorities. It does not
  become their relation owner.

Every cross-library reference has this shape:

```json
{"library_id":"papers","item_type":"paper","item_id":"ABCD2345"}
```

`papers`, `projects`, and `tools` name the three Library providers. The reserved
`knowledge` namespace identifies `knowledge_catalog` artifacts and Knowledge Contexts;
it is not a fourth Library and never routes a Vault artifact through the Zotero provider.

Loopback URLs, including `127.0.0.1:23128`, are presentation entry points and never
object identity.

## Canonical root and libraries

```text
HubDirectory
├── schema_version = 2
├── libraries = [Papers, Projects, Tools]
├── knowledge_catalog
├── knowledge_contexts
├── operations
└── diagnostics
```

The three initial libraries are always present, including when empty or unavailable.
Each descriptor reports authority, availability, count, and a human-readable detail.

- **Papers** pages the Zotero Local API with server-side `start`, `limit`, query,
  bibliographic item-type, sort, and direction parameters. Production must not materialize
  the full `HubCatalog` before paging. For only the parent rows in that page, it resolves
  child PDF attachment keys and exposes their loopback PDF path. If a malformed or
  non-bibliographic row is skipped, the cursor still advances by the number of provider rows
  consumed, so paging cannot repeat or stall.
- **Projects** reads only the explicit host registry. Resolving a project fails closed
  unless its real root contains a regular, non-symlink `project-layout.json` with
  schema 2 and the exact registry `project_id`.
- **Tools** reads only explicit `ToolDefinition` rows. Health checks and recipe IDs are
  registered identifiers, never browser-supplied commands.

Cursors are opaque and bind library, normalized query, filter, sorting, direction,
and offset. Reusing a cursor with different query parameters is rejected.

Paper cards link to a stable `/hub/item` landing keyed by the complete
`TypedEntityRef`. The landing resolves the current Zotero parent and PDF attachment
server-side. The paper landing links to a typed `papers:attachment:*` landing, and only
that attachment landing resolves `/open/paper/<attachment-key>` as an implementation-level
byte stream. Analysis Markdown/Canvas uses a `knowledge:artifact:*` landing and is never
presented as an item owned by the Papers provider.

## Knowledge and project copies

Knowledge and projects never live-sync. A copy is an explicit content transfer and
the result evolves independently.

Knowledge-to-project copies accept registered UTF-8 Markdown and JSON Canvas. Markdown
loses `sw_*` frontmatter, analysis identity comments, managed-block markers, and
generated claim block IDs while retaining readable prose. Canvas is parsed as a graph,
has every node/edge identity regenerated, loses `sw_*` fields and generated claim
markers/backlinks, and rejects file/link or unsupported node types rather than carrying
managed relationships across the boundary. The service copies no sidecar, baseline,
Zotero PDF, annotation, or unselected attachment, and creates no semantic provenance
relation.

Project-to-knowledge promotion is a separate knowledge-ingest operation that creates a
new Vault-native identity. It does not preserve a live backlink or synchronization
contract.

## Project document operations

Hub accepts only `project_id` plus POSIX paths relative to the registered project's
`docs/`. It rejects absolute paths, `..`, backslashes, symlinks in any traversed path,
missing manifests, disabled/unregistered projects, implicit overwrite, and automatic
rename. It never accepts a client absolute path and never performs `git add`, commit, or
push.

Copy, paste, and trash inspect relevant Git paths. A tracked, modified,
tracked-deleted, or unknown source/destination requires explicit confirmation for that
operation. Paste accepts bounded UTF-8 text into a new relative path only; it does not
overwrite or accept a client absolute path.

Delete means recoverable trash only:

```text
.scholar-workflow/trash/docs/<UTC timestamp>/<original relative path>
```

The private directory and every descendant are checked before any move or directory
creation; a symlink or non-directory fails closed. Each moved file has a receipt with
the original path, content hash, deletion time, and Git state. Permanent deletion and
automatic trash cleanup are not exposed in v2's initial surface.

## Workspace ownership and binding

`HubService` is one process generation. A browser view becomes writable only through:

```text
server nonce -> opaque workspace selection -> server resolution -> WorkspaceLease
```

The lease records service generation, lease generation, profile, opaque workspace, and
the server-derived cmux fingerprint. Nonces are single-use and bounded. On every
controlled mutation or launch, Hub recomputes the current fingerprint and resolves the
opaque workspace against a fresh cmux tree. A missing workspace, changed instance,
expired lease, or restarted service invalidates the binding.

Only a service started from a clean cmux workspace/socket environment may report
`owner_mode=cmux-visible`. A headless service is permanently read-only even if stale or
forged in-memory lease state exists. The Web UI may request a nonce and bind its selected
opaque workspace; without a successful bind it keeps all write/launch controls disabled.

## Task contracts and current execution gate

The stable model is:

```text
TaskRecipe -> LogicalTask -> TaskRun -> explicit codex_thread_id
```

A browser task request may contain only a registered recipe, an allowed project or
typed object, an idempotency key, one of `fast | standard | deep`, and a UTF-8 brief of
at most 8 KiB. The server maps effort to fixed configuration and derives cwd from the
project registry. Brief text goes over stdin. Process launch uses an argv array with
`shell=False`; resume/fork requires the saved thread ID and never uses `--last`.

The repository currently implements and tests these schemas, validators, command
construction, capability probe, durable task store, cross-process thread exclusion,
idempotency, heartbeat/cancel/timeout state, and process-group recovery primitives with
fake subprocesses. It does **not** expose a production worker manager or task execution
endpoint and has not run a real Codex task. Health reports `task_execution=false`, the UI
exposes no task button, and the legacy blank-session action is not registered. Wiring the
long-lived cmux workers into production HTTP, supervising them across service restarts,
and real capability/cancel/recovery canaries remain release gates rather than claimed
runtime capabilities.

## HTTP surface

```text
GET  /hub/
GET  /hub/item?library_id=<id>&item_type=<type>&item_id=<id>
GET  /api/v2/directory?instance=<opaque-view-instance>
GET  /api/v2/libraries/<papers|projects|tools>/items
GET  /api/v2/health
POST /api/v2/workspaces/nonce
POST /api/v2/workspaces/bind
POST /api/v2/projects/<project-id>/docs/copy
POST /api/v2/projects/<project-id>/docs/copy-knowledge
POST /api/v2/projects/<project-id>/docs/paste
POST /api/v2/projects/<project-id>/docs/trash

GET  /api/v1/catalog          derived compatibility projection
GET  /api/v1/session
GET  /api/v1/actions
GET  /api/v1/cmux/workspaces
GET  /api/v1/artifacts/<id>/content
PUT  /api/v1/artifacts/<id>/content
GET  /api/v1/artifacts/<id>/assets
POST /api/v1/artifacts/<id>/assets
GET | HEAD /api/v1/assets/<id>/content
GET | HEAD /open/paper/<attachment-key>
```

All state-changing routes require loopback Host validation, an allowed same-origin
`Origin`, the process CSRF token, and (in production) a freshly validated workspace
binding. The browser cannot submit shell commands, cwd, arbitrary paths, model names,
sandbox/permission settings, raw Codex configuration, environment variables, or raw
cmux IDs.

`GET /api/v2/health` separates service, package, build, protocol, HubDirectory schema,
owner mode, cmux fingerprint, provider capabilities, worker capabilities, and log
location. Unknown build revisions or log locations are explicit `null` values with a
detail, never silently omitted.

## Migration boundary

This contract does not authorize switching the live `23128` listener, changing a
LaunchAgent, rewriting existing raw-port links, migrating projects or knowledge, or
enabling task execution. Those actions require canary verification and the separate
approval gates in the implementation plan.
