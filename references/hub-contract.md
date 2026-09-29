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
second state store. Legacy v1 artifact PUT, asset upload, and action POST are retired with
`410 Gone`; writes and launches must use the corresponding v3 capability-checked routes.

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

- Open the local PDF in Zotero (primary; revalidate the attachment at launch)
- Annotate in ZotFlow (optional, only after local-storage mode is positively verified)
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

The browser never submits an absolute path. A system folder picker returns a bounded-lifetime,
process-local candidate token. If no manifest exists, Hub must perform a zero-write
preview and show the proposed Fields, home documents, navigation, collisions, ignored
files, template changes, unmapped prose, and link rewrites. Confirmation becomes stale
if the candidate, root inode, or content revision changes.
Each confirmation selects exactly one candidate Field; choosing an entire Vault never
registers all candidates at once. Existing Sources and sibling Fields keep their IDs,
and overlapping registered roots or Field ownership are rejected.
If a portable manifest already exists on a new host, a separate registration-only
preview explicitly shows every existing Field. Confirmation registers that Source in
the host registry without rewriting the manifest, Field IDs, or document content.

For a first registration containing legacy links or a managed legacy analysis pair,
the browser's compatibility confirmation must not split registration from migration.
The trusted local operator instead reviews one `hub field-transaction plan`: its digest
covers the portable manifest, host registry, managed Markdown/Canvas/sidecar changes,
and link rewrites. A legacy analysis candidate must pass separate old-field/node/edge
conservation and new bundle conformance before it can join the same Field plan. Its
candidate is reviewed and staged through the local operator CLI, not the browser. A
proposed navigation change cannot silently omit any previewed managed document.
Commit requires the exact plan digest, a manually arranged external-writer pause,
per-file CAS, an unverified recovery snapshot, and a private per-Field journal.
An interrupted commit blocks new plans/applies until explicit recovery. The
`hub field-transaction recover SOURCE_ID FIELD_ID --confirm-recovery --external-writers-paused`
command requires the operator's external-writer pause assertion and conditionally restores
journal-owned files; external edits or damaged recovery data fail closed. Multi-file replacement is
not instantaneously atomic to external Vault readers. The local operator credential
and interactive CLI confirmation assume processes running as that OS user are trusted;
they do not cryptographically prove an independent human approval.

The older `hub field-migration` command is link-only compatibility for an already
registered Field. It cannot normalize an analysis pair or initialize a Field in one
transaction. Managed analysis Markdown/Canvas/sidecar cannot be changed through a
single-file Hub editor; use the paired Knowledge update workflow.

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

Zotero owns formal annotations. ZotFlow is an optional local-PDF editor and the only client
allowed to hold the Zotero Web API read/write key; that key remains in Obsidian
SecretStorage. Hub, CLI, agents, configuration, environment, logs, and diagnostics must
not obtain it. Scholar Workflow's separate Local API ingest authorization remains in
macOS Keychain.

`ZotFlowReaderAdapter` opens `obsidian://zotflow` attachment and annotation actions only
after checking Obsidian version, ZotFlow version, `minAppVersion`, enabled state, and a
non-secret positive proof that the desktop local-storage mode points at the attachment's
actual Zotero storage root. It revalidates the local PDF at launch, fails closed if missing
or changed, and never falls back to Web API/WebDAV PDF download. A narrow Obsidian CLI probe
may provide the mode proof; its absence only disables ZotFlow, not Zotero or Hub reading.
Zotero native actions also revalidate the local attachment before launch. Metadata and
annotation Web API synchronization remain distinct from PDF file download. The adapter
reports upgrade requirements but never upgrades Obsidian.

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
record includes port, PID, executable, installed package version and build hash,
protocol, generation, start time, and log path. Plugin manifest versions are checked
by release validation, not claimed as a runtime discovery field. Browser
authentication is separate from cmux Destination state.

`status` reports actual process facts. `stop` is idempotent and removes a stale record
only after validation. Stop/restart may signal a PID only when discovery and a live
identity/generation handshake prove it is the Scholar Workflow managed process. Unknown
listeners, PID reuse, or mismatched builds fail closed and are never terminated.
The v3 identity handshake is independent of providers and cmux; detailed health is
diagnostic only and cannot invalidate a verified service merely because a provider or
window router is slow.

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
GET  /api/v3/identity
GET  /api/v3/health
```

State-changing routes require loopback Host validation, same-origin `Origin`, the
service's anti-CSRF token, strict schemas, and bounded bodies. Task creation additionally
uses an idempotency key. Folder candidate tokens are bounded-lifetime process-local
handles; Action and Destination IDs are server-generated, and Destinations expire and
revalidate their cmux instance. The anti-CSRF token is shared by same-origin Hub pages
for one service generation, not a per-browser session identity.

The UI label is “default open location”, never “workspace bound”. Fields display manifest
navigation and selected Markdown together. Cards expose primary actions immediately;
metadata drawers are optional rather than required landing pages. Raw UUIDs, absolute
paths, ports, tokens, shell text, and unfiltered stderr are not displayed.
All human-visible Hub content also follows `references/human-presentation.md`: a displayed
link must be actionable in that surface, or have a distinct supported open action or
unavailable reason. Diagnostics and machine identifiers do not substitute for the
object's readable content and status.

## Migration boundary

The first Source is the current research-document Vault; the first Field is World Models,
with JEPA/V-JEPA as its acceptance sample. Each Field is previewed and transacted alone.
A recovery snapshot is explicitly not a verified backup. Unmapped original prose is
preserved in original order under a retained-content section.

Existing fixed loopback links are rewritten only inside an approved Field transaction.
The managed v4 analysis renderer defaults to stable `zotero://open-pdf/...` links and
may explicitly project verified `obsidian://zotflow` Library Reader page links into its
paired Markdown and Canvas. The target Vault, audited local-PDF mode, attachment, and
reader route must be verified; using that reader does not transfer writer ownership
of the note. Machine relations store only `PdfRef`. The optional v4 projection is not
an automatic Field-wide link migration target.

This contract does not authorize automatic Obsidian upgrades, plugin removal, another
Vault/project migration, permanent deletion, or a verified-backup claim.
