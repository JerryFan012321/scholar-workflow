# Security Policy (shared)

Canonical safety boundaries. Applies to all skills, agents, and services.

## Permission boundary

Read-only acquisition needs no approval. Additive writes — create, import,
add-to-collection, download, metadata fill — proceed under the user's standing
instruction without a per-action prompt. Only destructive or irreversible actions
require approval: delete, overwrite a conflicting item, or merge identities.
Automated projections never overwrite human-authored content. A human explicitly saving
their current Hub editor buffer is a direct edit, not an automated projection overwrite;
it still requires optimistic concurrency protection.

| Action | Rule |
|---|---|
| Read via Zotero Local API (search / metadata / indexed full text) | Allowed |
| Read annotations through Zotero Local API | Allowed — read-only; may produce a derived `AnnotationIR`/human projection |
| Read local index / state / files | Allowed |
| Web fetch for metadata/identity | Allowed — read-only |
| Download PDF from arXiv to `paper_inbox` | Allowed — additive |
| Create Zotero item / import PDF / add to collection (Local API) | Allowed — additive |
| Update Zotero metadata: fill empty or correct wrong fields (Local API) | Allowed — additive |
| Write Obsidian managed block / Notion machine fields | Allowed — additive |
| Explicitly save one catalog-registered Vault Markdown/Canvas from the Hub | Allowed — user-authored; exact base revision and atomic replace required |
| Add one Vault asset through the Hub | Allowed — additive; server-derived path and explicit manifest relation only |
| Copy an explicit document into a registered project's `docs/` | Allowed from a registered project target; relative-path, capability, collision, CAS, symlink and Git-risk checks apply independently of cmux |
| Move one registered project document to project-local trash | Allowed from a registered project target; recoverable receipt required and every private-directory component must be non-symlink |
| Route a browser/terminal/Codex/CLI window to cmux | Allowed only through a live opaque `CmuxDestination`; this grants no file permission |
| Store or request a Zotero Web API key outside ZotFlow SecretStorage | Never |
| Download a PDF through ZotFlow's Zotero Web API/WebDAV file path for a Hub reading action | Never — require a positively verified local-storage mode and an existing local attachment |
| Delete item/attachment, overwrite a conflicting item, merge identities | Approval required — per item |
| Automatically overwrite human-authored content, or silently replace/delete a Vault asset | Never |
| Write `zotero.sqlite` directly | Permanently forbidden |

## Approval gate

- A request to ingest or update one resource or a batch authorizes the additive create,
  import, metadata, and collection writes it entails. Do not re-prompt per action or item.
- Destructive actions require in-conversation approval per item. On identity conflict,
  stop that item without affecting the rest of the batch (NG3).
- Before writing a paper, ask which collection or organizing direction it belongs to.
  The target is an input to the write, not an approval gate.
- All Zotero writes go through the Local API adapter; never write `zotero.sqlite`.

## Zotero Local API boundary

- Zotero 10+'s Local API is the only Scholar Workflow channel for Zotero metadata,
  existence checks, indexed full text, annotations, and writes. Use the host-neutral
  `scholar-workflow zotero ...` commands. No component may read or write `zotero.sqlite`
  directly; the historical annotation-export exception has been removed.
- Reads need no key. Writes obtain a key from Zotero's `/api/local/authorize` prompt.
  A remembered key is stored in macOS Keychain, never in config or git. For multi-step
  attachment import, choose **Always Allow**; a single-use key cannot span all phases.
- The adapter accepts only an HTTP loopback `/api` base URL, disables environment
  proxies, refuses redirects, validates upload URLs as loopback, and never prints keys.
- `scholar-workflow zotero ingest` performs an exact DOI or normalized title+creators
  existence check before create. More than one exact match exits 5; never auto-merge.
- Metadata corrections use `zotero update` with the current item version from `zotero get`.
  Protected structural fields and empty replacement values are rejected; the CLI exposes
  no destructive metadata-clear path.
- If a Zotero command exits 3, start Zotero and enable the Local API in
  **Settings → Advanced**, then retry the command. Unlike MCP registration, this does
  not require restarting the agent session. Never treat unavailability as "not found".
- The Local API has no native semantic/vector endpoint. Use `zotero search --fulltext`
  for broad recall and expose the observable match signals for returned candidates. Any
  ordering states its basis. A fuzzy candidate never proves identity; exact field
  confirmation still decides create/skip.
- Writes are HTTP API calls, never raw database access. Destructive commands are not
  exposed by the current CLI.

## ZotFlow and annotation boundary

- Zotero is the sole authority for formal paper annotations. ZotFlow is an optional local-PDF
  human editor and the only client allowed to hold a Zotero Web API read/write key.
  That key remains in Obsidian SecretStorage. Hub, CLI, agents, config, process
  environment, logs, and diagnostics must neither request nor expose it.
- The Web API key exclusivity does not replace Scholar Workflow's existing Zotero Local
  API authorization for explicit ingest. That separate key stays in macOS Keychain and
  is governed by the Local API rules above.
- Agent reads use Local API annotation rows and may build a read-only `AnnotationIR`.
  The IR and rendered Markdown are projections, not another annotation authority.
- ZotFlow's Web API metadata/annotation sync does not authorize a cloud PDF download.
  Hub must prove the desktop local-storage mode through a fixed non-secret probe and
  revalidate the attachment's Local API locator before enabling or launching that action;
  an unproven mode, missing file, or changed PDF fails closed. Zotero native launch also
  revalidates its local attachment so a stale card cannot trigger implicit retrieval.
- ZotFlow Source Notes, Better Notes outputs, and Scholar-managed analysis/annotation
  paths must have disjoint writer ownership and path prefixes. Hub never resolves a
  conflict by guessing which writer wins.
- Annotated PDFs for other readers are explicit snapshots. They bind the source PDF hash
  and annotation-set hash, never overwrite or auto-import into the Zotero attachment,
  and must report unsupported annotation types rather than claiming a complete export.

## Loopback services

- Zotero Local API and the managed Hub service are loopback-only.
- `HubDirectory` schema 3 is the only Hub root. Document Libraries are Papers and
  dynamic Fields; Projects and Tools are root-level collections. v1/v2 responses are
  read-only compatibility projections from v3, never independent state. Relation
  authority stays with Zotero/Field manifests/providers; Hub only aggregates and presents it.
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.
- Hub document writes require same-origin Host/Origin, browser-session authentication,
  the process CSRF token, a registered source/folder/artifact ID, the exact content
  revision returned by the preceding read, and a freshly revalidated trusted root.
  A cmux destination is irrelevant to this authorization. There is no autosave and no
  endpoint for creating an arbitrary Vault note or choosing a client path.
- Project operations accept only `project_id` plus paths relative to that project's checked
  `docs/`. Absolute paths, `..`, symlink traversal, implicit overwrite, and writes outside
  `docs/` are rejected. Delete always moves into checked project-local trash; the service
  must reject a symlink or non-directory anywhere in `.scholar-workflow/trash/docs/...`
  before moving bytes or writing a receipt. Hub never performs a Git write.
- Knowledge-to-project copy produces independent content. Markdown loses `sw_*`, analysis
  identity comments, managed-block markers, and generated block IDs; sidecars and managed
  relationships are not copied. Canvas node/edge identities are regenerated, `sw_*` fields
  and generated backlinks are removed, and file/link or unsupported nodes fail closed.
  Project paste is bounded UTF-8, additive only, and receives the same destination-path and
  Git-state checks as copy.
- Hub launch actions require an allowed Origin, browser-session authentication and the
  process CSRF token. Their opaque registry refreshes from live provider/recipe revisions.
  Browsers may submit only an `action_id`, an allowed `target_id`, and an optional
  process-local `destination_id`; never a URL, path, command, cwd or raw cmux ID.
- cmux discovery is ephemeral. A `CmuxDestination` contains a server-resolved workspace and
  instance fingerprint and only routes a window. A missing/expired destination or changed
  instance disables actions that require cmux; it must not disable reading, Vault writes,
  project-document operations or any other independently authorized capability.
- `ExecutionTarget` resolves a registered project, Vault or folder root and its capabilities.
  All cwd/file authorization comes from this target plus relative paths, CAS and symlink
  defenses. Destination selection must never alter the result.
- Codex requests are defined by a server-registered `TaskRecipe`, bounded UTF-8 brief (at most
  8 KiB), allowed `fast | standard | deep` effort, explicit project/object selection, and
  idempotency key. The client cannot provide a shell command, cwd/path, model, sandbox,
  permission, raw config, environment, terminal target, or `--last`. Briefs go through stdin;
  argv construction uses `shell=False`; resume/fork requires an explicit saved thread ID.
  Task execution is available only after an administrator explicitly registers a trusted
  ExecutionTarget and Codex executable, configures the server-owned recipe/policy, and the
  runtime capability probe, broker, and destination checks pass. A long-lived cmux terminal
  worker runs each slot; health reports task availability from the actual runtime, never from
  the mere presence of task code. The legacy blank-session action remains unavailable.
- JSON Canvas identity comes from the checked Vault artifact manifest. Missing, invalid,
  escaping, or symlinked manifest entries fail closed rather than exposing a stale path.
- Hub Vault assets are distinct from Zotero attachments. Their bytes remain inside the
  configured Vault, their relation comes only from the checked manifest, and the first
  version exposes additive upload only — no replace, move, or delete endpoint.
- Knowledge Sources are added through a system folder picker that returns a bounded,
  one-use candidate token. The browser cannot send an absolute path. Without an existing
  `.scholar-workflow/fields.yml`, the service must show a zero-write preview and require
  explicit confirmation before creating a Source/Field registration.
- The Hub service runs from the installed package on a dynamically selected loopback port.
  Its discovery record is mode 0600 and separates browser authentication from cmux
  destinations. Stop/restart may signal only a PID proven by discovery plus a matching
  service identity/generation handshake; unknown listeners and stale/reused PIDs fail closed.

## Logging

Never log tokens, Local API keys, paper full text, or sensitive absolute paths. Log
normalized relative paths and resource IDs only.
