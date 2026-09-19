# Local Hub Contract

`HubCatalog` is the shared contract consumed by the Web Hub, the managed Obsidian
identity layer, and Notion launch actions. It is a rebuildable snapshot, not a fourth
knowledge database.

```text
Zotero Local API ── bibliography / PDF identity ───┐
                                                   ├─> HubCatalog snapshot
validated workflow payload ── topic relations ────┤      ├─> Web Hub
Vault sw_* frontmatter ── Markdown identity ───────┤      ├─> Obsidian projection
Vault artifacts.yml ── JSON Canvas identity ───────┤      ├─> file editor / assets
Vault assets.yml ── explicit note attachments ─────┘      ├─> dynamic actions
Notion upsert result ── page-ID mapping only ──────────────┘

runtime only (never serialized into HubCatalog):
cmux tree ── raw workspace IDs ──> WorkspaceRegistry ── opaque IDs ──> Web Hub
                                                     └─> cmux view / blank Codex session
```

## Authority boundaries

- Zotero owns paper bibliography, PDFs, and formal annotations.
- The Obsidian Vault owns human-readable Markdown/Canvas content and knowledge relations.
- The Vault artifact manifest registers formats such as JSON Canvas that cannot carry YAML
  frontmatter; it does not own their content.
- The Vault asset manifest explicitly relates note images, data, and supplements to
  artifacts; their bytes still belong to the Vault.
- Notion is a simplified, one-way, cross-device projection.
- cmux owns transient workspace/surface state. Raw workspace IDs remain in the Hub process and
  are never persisted in `HubCatalog`, the Vault, or projection state.
- The Hub owns resource/topic/artifact relations and launch actions. It does not cache paper
  full text or note bodies and never stores absolute paths or commands. An explicit Hub save
  writes the body directly and atomically to the authoritative Vault; it does not copy the
  body into the catalog or state directory.

The rebuildable snapshot is `${SCHOLAR_WORKFLOW_HOME}/hub/catalog.json`. The
`resource_id -> notion_page_id` mapping is stored separately in `projection-links.json`;
that file contains IDs only, never titles, bodies, URLs, or credentials.

## Python interfaces

```python
CatalogProvider.load() -> HubCatalog
CatalogSnapshotStore.load() -> HubCatalog
CatalogSnapshotStore.save(catalog) -> None
VaultCatalogProvider.load() -> HubCatalog
VaultArtifactManifestProvider.load() -> HubCatalog
VaultAssetCatalogProvider.load() -> HubCatalog
LinkedCatalogProvider.load() -> HubCatalog

build_topic_catalog_patch(doc, root, port, filename, paperlist_only=...) -> HubCatalog
merge_catalog_patch(base, patch) -> HubCatalog

ActionRegistry.register(kind=..., label=..., target=...) -> PublicAction
CatalogActionService.public_actions() -> dict[str, list[PublicAction]]
CatalogActionService.public_workspaces(instance_token=...) -> WorkspaceListing
CatalogActionService.execute(opaque_action_id, workspace_id=...) -> launch_result
WorkspaceRegistry.resolve(opaque_workspace_id) -> raw_workspace_id
CmuxControl.open(server_validated_target, workspace_id=raw_workspace_id)
CmuxControl.new_codex_session(workspace_id=..., working_directory=trusted_path)
ArtifactContentStore.read(artifact_id) -> ArtifactContent
ArtifactContentStore.write(artifact_id, content=..., base_revision=...) -> ArtifactContent
VaultAssetStore.add_bytes(owner_artifact_id, display_name, content, role=...) -> HubAsset
VaultAssetStore.get(asset_id) -> HubAsset
VaultAssetStore.resolve_path(asset_id) -> Path
```

`RegisteredAction.target` exists only in process memory. The browser receives only
`PublicAction.id`, `label`, `kind`, and `workspace_policy`. A second process-local registry maps
raw cmux workspace IDs to opaque workspace IDs and exposes only a display label plus
`is_current` / `contains_hub` hints. The action service rebuilds its catalog-derived registry
whenever the live catalog revision changes, so a long-running Hub sees new Vault artifacts and
Notion page IDs without a restart.

The default provider order is:

```text
snapshot
  -> Markdown sw_* overlay
  -> explicit JSON Canvas artifact manifest
  -> explicit Vault asset manifest
  -> Notion page-ID overlay
```

None of these providers parses human prose or Canvas nodes to infer catalog relationships.

## Managed Obsidian Markdown

The Hub owns only the following frontmatter layer; human properties and the body remain
unchanged:

```yaml
---
sw_schema: 1
sw_kind: literature-tree
sw_catalog_id: topic:world-models:tree:02-world-models
sw_topic_id: world-models
sw_revision: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
sw_tree_kind: technical
---
```

The allowlist is `sw_schema`, `sw_kind`, `sw_catalog_id`, `sw_topic_id`,
`sw_resource_id`, `sw_zotero_item_key`, `sw_attachment_key`, `sw_parent_id`,
`sw_revision`, and `sw_tree_kind`. Unknown `sw_*` fields, absolute paths, `..`, and symlink
escape are rejected. An invalid declaration masks a stale snapshot record with the same ID or
path; it cannot silently fall back to the older registration.

The body may continue using the existing Markdown tables, Mermaid diagrams, sections, and
human notes. The Hub never derives structure from free-form text. Current artifact kinds are
`collection-index`, `paper-list`, `paper-hub`, `literature-tree`, `paper-analysis`,
`analysis-canvas`, `annotation-note`, `reading-note`, `direction-note`, and
`technical-document`.

## JSON Canvas registration

JSON Canvas 1.0 stays a standard object with `nodes` and `edges`; Hub-only metadata must not be
inserted into the Canvas JSON. Register an analysis Canvas in the human-checkable Vault file
`.scholar-workflow/artifacts.yml`:

```yaml
schema_version: 1
artifacts:
  - artifact_id: analysis:paper-one:canvas
    kind: analysis-canvas
    format: canvas
    vault_path: world-models/paper-one-analysis.canvas
    resource_id: paper:one
    topic_id: world-models
    parent_id: analysis:paper-one
```

The current manifest contract accepts analysis Canvas entries only. IDs and paths must be
unique; the target must be an existing, regular `.canvas` file inside the Vault with no
symlink traversal. A move or rename updates only `vault_path`; the stable `artifact_id` is
preserved. Invalid entries are diagnosed and mask stale snapshot records with the same ID.

## Vault note attachments

Paper PDFs and formal annotations remain Zotero attachments. The Hub reads a paper PDF only
through its opaque Zotero `attachment_key` and never replaces it.

Images, data, and supplements belonging to a Vault note are separate `HubAsset` objects. Their
relationship comes only from `.scholar-workflow/assets.yml`:

```yaml
schema_version: 1
assets:
  - asset_id: asset:0123456789abcdef
    owner_artifact_ids: [analysis:paper-one]
    vault_path: attachments/analysis-paper-one-a1b2c3d4/figure.png
    display_name: figure.png
    media_type: image/png
    size: 12345
    sha256: sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
    role: embed
```

A Markdown `![[attachments/...]]` is presentation only and is never relationship authority.
The server derives the destination from the artifact ID; the client submits only one portable
filename and the bytes. A same-name upload becomes `-2`, `-3`, and so on instead of
overwriting. The first version intentionally exposes no replace, move, or delete operation.
Missing files, path/symlink violations, and size/hash drift produce diagnostics rather than a
fabricated catalog asset.

## HTTP interface

```text
GET        /hub/
GET        /api/v1/catalog
GET        /api/v1/actions
GET        /api/v1/session
GET        /api/v1/cmux/workspaces?instance=<opaque-instance>
GET        /api/v1/health  includes capability cmux-workspace-actions-v1
GET        /api/v1/artifacts/<artifact-id>/content
PUT        /api/v1/artifacts/<artifact-id>/content  {content, base_revision}
GET        /api/v1/artifacts/<artifact-id>/assets
POST       /api/v1/artifacts/<artifact-id>/assets?name=...&role=...  raw file bytes
GET | HEAD /api/v1/assets/<opaque-asset-id>/content
POST       /api/v1/actions/<opaque-action-id>  body is {} or {"workspace_id":"<opaque>"}
GET | HEAD /open/paper/<attachment-key>  legacy-compatible; PDF Range is supported
```

The server binds only to `127.0.0.1`, validates `Host`, rejects CORS, and requires an allowed
same-origin `Origin` plus the process CSRF token for every state-changing request and launch
action. Preview and write endpoints resolve only catalog-registered Vault-relative paths.

PUT accepts existing registered Markdown/Canvas files only and requires the raw-file
`sha256:` revision returned by the read endpoint. An Obsidian or external edit causes HTTP
409 instead of silent overwrite. Saves use a same-directory temporary file, `fsync`, and
atomic replace. Canvas content must remain a JSON object; client code cannot add, remove, or
change managed Markdown `sw_*` fields. The HTTP `revision` is a whole-file concurrency token;
`sw_revision` remains the projector output revision and is unchanged by a manual save. There
is no autosave.

The UI is reading-first. It renders a safe Markdown subset through DOM construction and
`textContent`, never `innerHTML`; editing and the attachment panel are secondary, and the
editor has a responsive live preview. Only explicit HTTP/HTTPS Markdown links become
clickable. Obsidian wikilinks and embeds render as inert readable tokens in the Web view.

Workspace-scoped POST bodies accept exactly one process-local opaque `workspace_id`; actions
that do not use cmux reject it, and actions that require cmux reject an empty body. The server
resolves both action and workspace targets. The client cannot submit raw workspace UUIDs,
URLs, paths, prompts, commands, models, or permission settings.

Notion page IDs are converted server-side into allowlisted HTTPS URLs and executed as
`cmux open <url> --workspace <server-resolved-id> --focus true`. PDF and registered Vault
preview actions use the same selected-workspace contract. Obsidian and Zotero are separate
native-editor actions and never consume a workspace selection. The global Codex action is
available only when `serve-hub` starts in a real cmux terminal; after explicit confirmation it
uses cmux's native `agent-session` surface with provider `codex` and the server's trusted startup
directory, without `--command` or a prompt. Any cmux failure is visible and never falls back to
Safari or another system browser. HTML, SVG, and unknown asset types are download-only; only
allowlisted images, PDF, JSON, and plain-text types may render inline.

All cmux, Obsidian, and Zotero launches use argv with `shell=False` and a small child-process
environment allowlist. Hub credentials and unrelated host environment variables are not inherited;
the cmux adapter receives only the socket/workspace variables it needs.

`scholar-workflow open-hub` is the explicit cmux entry point. It requires the caller's cmux
workspace/socket environment, health-checks an already-running loopback Hub, generates a
URL-safe opaque browser-instance token, and opens that URL in the caller's workspace. It never
starts the Hub or cmux implicitly and has no system-browser fallback. The health check requires
the `cmux-workspace-actions-v1` capability marker, so an older long-running Hub is rejected with
an explicit restart instruction instead of opening a stale UI.

## Migration boundary

New generated `01-Paperlist.md` and literature-tree notes carry managed `sw_*` frontmatter.
New analysis pairs register the Markdown note in frontmatter and the standard JSON Canvas in
the artifact manifest. Legacy tables and filenames may be consumed only by a versioned,
one-time importer; they must never become the long-term Hub API. Remaining work includes the
explicit legacy-Vault migration command and a paginated Zotero-library assembler.
