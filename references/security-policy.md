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
| Read annotations via `zotero-annotations.py` (`mode=ro&immutable=1`) | Allowed — read-only, export only |
| Read local index / state / files | Allowed |
| Web fetch for metadata/identity | Allowed — read-only |
| Download PDF from arXiv to `paper_inbox` | Allowed — additive |
| Create Zotero item / import PDF / add to collection (Local API) | Allowed — additive |
| Update Zotero metadata: fill empty or correct wrong fields (Local API) | Allowed — additive |
| Write Obsidian managed block / Notion machine fields | Allowed — additive |
| Explicitly save one catalog-registered Vault Markdown/Canvas from the Hub | Allowed — user-authored; exact base revision and atomic replace required |
| Add one Vault asset through the Hub | Allowed — additive; server-derived path and explicit manifest relation only |
| Copy an explicit document into a registered project's `docs/` | Allowed only while a cmux-visible Hub view has a live binding; collision and Git-risk checks apply |
| Move one registered project document to project-local trash | Allowed only while live-bound; recoverable receipt required and every private-directory component must be non-symlink |
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

- Zotero 10+'s Local API is the only channel for Zotero metadata, existence checks,
  indexed full text, and writes. Use the host-neutral `scholar-workflow zotero ...`
  commands. The annotation-export exception remains: `bin/zotero-annotations.py` may
  read the local database with `mode=ro&immutable=1`, only for highlights/comments.
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

## Loopback services

- Zotero Local API and the local-link service are loopback-only.
- `HubDirectory` schema 2 is the only Hub root. `HubCatalog` is its
  `knowledge_catalog` compatibility projection. Relation authority stays with the
  declaring Zotero/Vault/manifest/provider; Hub only aggregates and presents it.
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.
- Hub document writes require same-origin Host/Origin, the process CSRF token, a registered
  artifact ID, the exact content revision returned by the preceding read, and a freshly
  revalidated workspace binding. There is no autosave and no endpoint for creating an
  arbitrary Vault note or choosing a Vault destination path.
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
- Hub launch actions also require an allowed Origin and the process CSRF token. Their opaque
  registry refreshes from the live catalog revision; browser clients never submit a target.
  Workspace-aware actions may additionally accept exactly one process-local opaque
  `workspace_id`; raw cmux window/workspace identifiers are never public request fields.
- cmux workspace discovery is ephemeral runtime state, not `HubDirectory` content. A binding
  uses a single-use nonce, service/lease generation, and server-derived instance fingerprint.
  Every controlled mutation or launch must recompute the fingerprint and resolve the leased
  opaque workspace against a fresh cmux tree. A missing workspace, denied capability, expired
  lease, changed instance, or headless owner disables writes and launches with a visible error;
  it must not weaken socket policy, fall back to another browser, or make reading unavailable.
- Codex requests are defined by a server-registered `TaskRecipe`, bounded UTF-8 brief (at most
  8 KiB), allowed `fast | standard | deep` effort, explicit project/object selection, and
  idempotency key. The client cannot provide a shell command, cwd/path, model, sandbox,
  permission, raw config, environment, terminal target, or `--last`. Briefs go through stdin;
  argv construction uses `shell=False`; resume/fork requires an explicit saved thread ID.
  The long-lived worker is not enabled in the current release, so health must report
  `task_execution=false` and neither API nor UI may claim task execution or expose the legacy
  blank-session action.
- JSON Canvas identity comes from the checked Vault artifact manifest. Missing, invalid,
  escaping, or symlinked manifest entries fail closed rather than exposing a stale path.
- Hub Vault assets are distinct from Zotero attachments. Their bytes remain inside the
  configured Vault, their relation comes only from the checked manifest, and the first
  version exposes additive upload only — no replace, move, or delete endpoint.

## Logging

Never log tokens, Local API keys, paper full text, or sensitive absolute paths. Log
normalized relative paths and resource IDs only.
