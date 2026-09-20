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
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.
- Hub document writes require same-origin Host/Origin, the process CSRF token, a registered
  artifact ID, and the exact content revision returned by the preceding read. There is no
  autosave and no endpoint for creating an arbitrary note or choosing a destination path.
- Hub launch actions also require an allowed Origin and the process CSRF token. Their opaque
  registry refreshes from the live catalog revision; browser clients never submit a target.
  Workspace-aware actions may additionally accept exactly one process-local opaque
  `workspace_id`; raw cmux window/workspace identifiers are never public request fields.
- cmux workspace discovery is ephemeral runtime state, not `HubCatalog` content. A missing
  socket, denied cmux capability, or expired workspace handle disables only cmux-dependent
  actions with a visible error; it must not change cmux socket policy, fall back to another
  browser, or make the read-only Hub unavailable.
- A Hub Codex action creates a new blank native cmux agent session in a server-trusted working
  directory. The client cannot provide a prompt, command, path, model, sandbox, config flag,
  session identifier, or terminal target, and the server never sends keys into an existing
  terminal. Future task buttons must resolve a server-registered recipe rather than browser
  command text.
- JSON Canvas identity comes from the checked Vault artifact manifest. Missing, invalid,
  escaping, or symlinked manifest entries fail closed rather than exposing a stale path.
- Hub Vault assets are distinct from Zotero attachments. Their bytes remain inside the
  configured Vault, their relation comes only from the checked manifest, and the first
  version exposes additive upload only — no replace, move, or delete endpoint.

## Logging

Never log tokens, Local API keys, paper full text, or sensitive absolute paths. Log
normalized relative paths and resource IDs only.
