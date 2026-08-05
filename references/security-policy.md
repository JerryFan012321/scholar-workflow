# Security Policy (shared)

Canonical safety boundaries. Applies to all skills, agents, and services.

## Claude permission boundary

Fetch and write are judged separately. Read-only acquisition needs no approval.
Additive writes — create, import, add-to-collection, download, metadata fill —
proceed under the user's standing instruction without a per-action prompt. Only
destructive or irreversible actions require approval: delete, overwrite a conflicting
item, merge identities. Overwriting human-authored content is never done.

| Action | Rule |
|---|---|
| Read via zotero-mcp (search / metadata / semantic / content) | Allowed |
| Read annotations via `zotero-annotations.py` (`mode=ro&immutable=1`) | Allowed — read-only, export only |
| Read local index / state / files | Allowed |
| Web fetch for metadata/identity (search, defuddle, MCP) | Allowed — read-only |
| Download PDF from arXiv to `paper_inbox` | Allowed — additive |
| Create Zotero item / import PDF / add to collection (zotero-mcp) | Allowed — additive |
| Update Zotero metadata: fill empty or correct wrong fields (zotero-mcp) | Allowed — additive |
| Write Obsidian managed block / Notion machine fields (additive) | Allowed — additive |
| Delete item/attachment, overwrite a conflicting item, merge identities | Approval required — per item |
| Overwrite human-authored content (Obsidian outside managed block, Notion human fields) | Never |
| Write `zotero.sqlite` directly | Permanently forbidden |

## Approval gate

- Additive writes proceed under the user's standing instruction: a request to ingest
  or update a resource — or a batch of resources — authorizes the create / import /
  metadata / collection writes it entails. Do not re-prompt for the same action.
- A batch request (e.g. N papers) authorizes the whole batch; never re-prompt per
  item within an already-authorized batch. Additive steps run end to end.
- Destructive actions (delete, overwrite-conflict, merge) require in-conversation
  approval, per item. On identity conflict, stop that item without affecting others
  (NG3).
- Before writing a paper into Zotero, ask which collection it belongs to — the target
  collection is an input to the write, not an approval gate.
- All Zotero writes go through zotero-mcp's controlled tools; never write
  `zotero.sqlite` directly (INV8, NG4).

## zotero-mcp boundary

- zotero-mcp is the only channel for Zotero **metadata, existence, semantic search, and
  all writes**. The deterministic CLI is a separate subprocess and cannot reach it —
  Zotero logic lives in the host LLM at the skill layer. The one exception is **annotation
  export**: `bin/zotero-annotations.py` may read the local DB directly in read-only mode
  (`mode=ro&immutable=1`) to pull highlights/comments. This read-only extractor is never
  used for metadata/identity decisions and never writes — all writes still go through
  zotero-mcp's controlled tools.
- `write_item` is pure create (no dedup); run an existence check via zotero-mcp before
  any create to avoid duplicates (see `identity-policy.md`).
- `itemType` reads back empty through zotero-mcp for every item and cannot be set via
  `write_metadata`. It is a read-layer artifact, not corruption — never judge a record
  dirty by an empty `itemType`.
- Writes are controlled tool calls, never raw database access.
- **When zotero-mcp tools are absent** (an existence/write step needs `search_library` /
  `write_item` but no `mcp__zotero-mcp__*` tool exists): this is a connection problem, not
  a config problem. The endpoint is HTTP-transport and registers **only at session start**;
  if it wasn't listening then, it's silently skipped for the whole session and won't
  re-attach. Do not edit `~/.claude.json` (the project-level config is correct; the global
  `mcpServers` is meant to be empty). Instead: run `scholar-workflow doctor` (its advisory
  probe reports whether the `type:http` endpoint answers) or check the endpoint directly
  (`curl --noproxy 127.0.0.1 http://127.0.0.1:23120/mcp`). If the endpoint is down, tell the
  user to start Zotero + its MCP plugin, then **restart the session** so the tools register.
  Never fabricate existence results or fall back to create-without-check when the channel is
  missing (INV12/INV16 — fail-fast, no downgrade).

## Loopback services

- The local-link service binds to `127.0.0.1` only.
- Services accept opaque IDs / canonical paths only; reject `..` and symlink escapes.

## Logging

Never log tokens, paper full text, or sensitive absolute paths. Log normalized
relative paths and resource IDs only.
