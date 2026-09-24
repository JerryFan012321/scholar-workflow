# Hub v3 Runtime Contract

`HubDirectory` schema 3 is the only Hub root. It is a rebuildable control-plane
projection, not a knowledge database or an authority for provider-owned content.

```text
Zotero / Obsidian Field manifests / project manifests / explicit tool registry / Codex
                                      |
                                      v
                              HubDirectory v3
                         aggregate, route, validate
```

Legacy v1/v2 responses are derived read-only views of this root. They never form a
second state store.

## Information architecture

```text
Libraries
├── Papers
└── Fields
Projects
Tools
```

Libraries contain documents only. Projects and Tools are root-level collections, not
libraries. Papers are provided by Zotero Local API. Fields are provided by explicitly
registered Obsidian Sources and portable `.scholar-workflow/fields.yml` manifests.

Public paper types are `Paper`, `Report`, `Book`, `Webpage`, and `Other`. Venue,
conference, journal, and publication status are metadata, not types.

Cross-provider references use:

```json
{"provider_id":"zotero:users:0","entity_type":"paper","entity_id":"ABCD2345"}
```

Loopback URLs, ports, absolute paths, and process-local action IDs are never entity
identity.

## Papers and PDF identity

The Papers provider performs paging, querying, sorting, filtering, and attachment
resolution through Zotero Local API. It does not materialize the whole library first
and does not guess `Zotero/storage/<key>/*.pdf`.

```text
PdfRef {
  provider: "zotero",
  library_id,
  attachment_key,
  content_hash
}
```

A paper card invokes pre-registered actions directly:

- Annotate in ZotFlow (primary when available)
- Open in Zotero
- Read in cmux
- Open in the system PDF reader
- View analysis
- Open annotation note

Normal UI never requires a paper, attachment, or document landing page. `/hub/item`
and `/open/paper/<attachment-key>` survive for one release cycle as legacy resolvers;
new UI and persisted documents must not produce those URLs.

## Knowledge Sources and Fields

The host registry stores only stable Source/folder IDs and trusted local locators:

```text
KnowledgeSourceRegistration {
  source_id,
  provider: "obsidian",
  folder_id,
  enabled,
  capabilities
}
```

A Source can be an entire Vault or an explicitly chosen subdirectory and may expose
multiple Fields. Its portable manifest is:

```yaml
schema_version: 1
source_id: <stable UUID>
fields:
  - field_id: <stable UUID>
    title: World Models
    relative_root: World Models
    home: 00-Field-Home.md
    navigation:
      - label: Core surveys
        items: []
      - label: Papers and resources
        items: []
```

The browser never submits an absolute path. A system folder picker returns a one-use,
short-lived, process-local candidate token. If no manifest exists, Hub must perform a zero-write
preview and show the proposed Fields, home documents, navigation, collisions, ignored
files, template changes, unmapped prose, and link rewrites. Confirmation becomes stale
if the candidate, root inode, or content revision changes.
Each confirmation selects exactly one candidate Field; choosing an entire Vault never
registers all candidates at once. Existing Sources and sibling Fields keep their IDs,
and overlapping registered roots or Field ownership are rejected.
If a portable manifest already exists on a new host, a separate registration-only
preview explicitly shows every existing Field. Confirmation registers that Source in
the host registry without rewriting the manifest, Field IDs, or document content.

Legacy paper-link cleanup is a separate, explicit per-Field CLI transaction. A read-only
plan reports the exact digest, managed Markdown/Canvas changes, unresolved links in
unmapped files, and conflicts. Apply recomputes the plan and requires that digest;
only manifest-owned files can change. It creates an unverified recovery snapshot,
rolls back synchronous failures, and never claims crash-atomic multi-file replacement.
It does not normalize paper-analysis templates or silently migrate another Field.

`home`, `resource`, and `support` are ownership/template roles, not public filters.
Navigation labels and order belong to each Field. The legacy `research_vault_root` is
only a migration candidate, not a required singleton knowledge root.

## Destination, Target, and Action

These types are independent:

```text
CmuxDestination {
  destination_id,
  cmux_instance_fingerprint,
  workspace_id,
  display_name,
  expires_at
}

ExecutionTarget {
  target_id,
  kind: "project" | "vault" | "folder",
  registered_root_id,
  capabilities
}

OpenAction {
  action_id,
  kind: "web" | "pdf" | "file" | "native-app" | "terminal" | "codex",
  entity_ref,
  destination_required
}
```

- A Destination only determines where a cmux browser or terminal surface appears.
- A Target resolves a trusted project/folder root and authorizes file access or cwd.
- An Action is a server-registered operation over an entity and declares whether it
  needs a Destination or Target.

`open-hub` records the caller's current cmux workspace as the browser session's default
Destination when one exists. Each launch may select another live Destination. Closing
a workspace invalidates only actions routed there; reading, Vault writes, and project
document operations retain their own capability results.

Obsidian, Zotero, Preview, and other native applications do not belong to a cmux
workspace. Notion and other Web tools use registered URL recipes. CLI and Codex use
registered terminal recipes, with cwd derived only from the selected Target.

The browser may submit only opaque action/destination/target/recipe IDs, an idempotency
key, an allowed effort value, and a UTF-8 brief of at most 8 KiB. It never submits an
arbitrary URL, command, cwd/path, model, sandbox, permission, environment, or raw Codex
configuration. Briefs use stdin, argv is fixed with `shell=False`, and resume/fork uses
an explicitly saved thread ID rather than `--last`.

## Independent capabilities

There is no global `bound/read-only` state. Directory and health report each capability
independently, including at least:

```text
vault_writes
project_document_writes
cmux_launches
codex_tasks
zotflow_annotations
zotero_local_api
```

Each reports availability, a structured reason, dependencies, and a suggested remedy.
Failure of one capability cannot hide or disable unrelated capabilities.

## Project document boundary

Project operations accept only `project_id` plus POSIX paths relative to the checked
project `docs/` root. They reject absolute paths, `..`, backslashes, missing or mismatched
manifests, unknown/disabled projects, symlink traversal or swaps, implicit overwrite,
and automatic rename. A cmux Destination is irrelevant to authorization.

Knowledge-to-project copies strip `sw_*` identity, sidecars, generated markers,
managed relationships, and generated Canvas identities. They copy no Zotero PDF or
formal annotation unless a separate explicit operation says so. The result evolves
independently and creates no managed provenance relation.

Delete means recoverable project-local trash:

```text
.scholar-workflow/trash/docs/<UTC timestamp>/<original relative path>
```

Receipts include original relative path, hash, deletion time, and Git state. Tracked or
dirty files produce an operation-specific warning. Hub never runs a Git write and does
not expose permanent deletion in this version.

## ZotFlow and annotation authority

Zotero owns formal annotations. ZotFlow is the preferred editor and the only client
allowed to hold the Zotero Web API read/write key; that key remains in Obsidian
SecretStorage. Hub, CLI, agents, configuration, environment, logs, and diagnostics must
not obtain it. Scholar Workflow's separate Local API ingest authorization remains in
macOS Keychain.

`ZotFlowReaderAdapter` opens `obsidian://zotflow` attachment and annotation actions only
after checking Obsidian version, ZotFlow version, `minAppVersion`, and enabled state.
It reports an upgrade requirement but never upgrades Obsidian. Obsidian CLI is optional.

Agents read annotations from Zotero Local API and may render a read-only `AnnotationIR`.
The IR is not another authority. ZotFlow Source Notes, Better Notes files, and Scholar
analysis/annotation files must have separate owners and non-overlapping path prefixes.

Other PDF readers receive only explicit annotated snapshots. A snapshot binds
`source_pdf_hash + annotation_set_hash`, never overwrites or auto-imports into the Zotero
attachment, and treats edits as independent. Highlight, note, underline, ink, and image
annotations are validated by type; unsupported types cause a visible incomplete/failed
result rather than a false complete export.

## Managed service lifecycle

Public commands are:

```bash
scholar-workflow open-hub
scholar-workflow hub start
scholar-workflow hub status
scholar-workflow hub stop
scholar-workflow hub restart
scholar-workflow hub doctor
```

`open-hub` verifies the installed package/build, starts or safely restarts its managed
service, discovers the current URL, and opens the Hub. It does not accept or depend on a
code repository root.

The service binds a dynamically selected loopback port. A mode-0600 runtime discovery
record includes port, PID, executable, package/plugin/service build, protocol,
generation, start time, and log path. Browser authentication is separate from cmux
Destination state.

`status` reports actual process facts. `stop` is idempotent and removes a stale record
only after validation. Stop/restart may signal a PID only when discovery and a live
identity/generation handshake prove it is the Scholar Workflow managed process. Unknown
listeners, PID reuse, or mismatched builds fail closed and are never terminated.

## HTTP and browser boundary

The v3 minimum surface is:

```text
GET  /hub/
GET  /api/v1/session
GET  /api/v3/directory
GET  /api/v3/libraries/papers/items
GET  /api/v3/libraries/fields/items
GET  /api/v3/destinations
GET  /api/v3/actions
GET  /api/v3/execution-targets
GET  /api/v3/task-actions
POST /api/v3/actions/<action-id>
POST /api/v3/fields/select
POST /api/v3/fields/confirm
GET  /api/v3/health
```

State-changing routes require loopback Host validation, same-origin `Origin`, the
service's anti-CSRF token, strict schemas, and bounded bodies. Task creation additionally
uses an idempotency key. Folder candidate tokens are one-use/short-lived process-local
handles; Action and Destination IDs are server-generated, and Destinations expire and
revalidate their cmux instance. The anti-CSRF token is shared by same-origin Hub pages
for one service generation, not a per-browser session identity.

The UI label is “default open location”, never “workspace bound”. Fields display manifest
navigation and selected Markdown together. Cards expose primary actions immediately;
metadata drawers are optional rather than required landing pages. Raw UUIDs, absolute
paths, ports, tokens, shell text, and unfiltered stderr are not displayed.

## Migration boundary

The first Source is the current research-document Vault; the first Field is World Models,
with JEPA/V-JEPA as its acceptance sample. Each Field is previewed and transacted alone.
A recovery snapshot is explicitly not a verified backup. Unmapped original prose is
preserved in original order under a retained-content section.

Existing fixed loopback links are rewritten only inside an approved Field transaction:
human Markdown uses stable `zotero://open-pdf/...` (or ZotFlow's own `obsidian://zotflow`
protocol where it owns the content), while machine relations store only `PdfRef`.

This contract does not authorize automatic Obsidian upgrades, plugin removal, another
Vault/project migration, permanent deletion, or a verified-backup claim.
