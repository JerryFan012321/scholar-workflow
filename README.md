# scholar-workflow

A Claude Code and Codex plugin for scholarly resource management. It combines a human-first
knowledge system, reproducible research-project records, and a local typed Hub control plane.
It discovers and imports papers, maintains Obsidian and Notion projections, builds literature
trees, recommends papers, renders validated Markdown/Canvas analyses, initializes Git-managed
projects, and coordinates bounded work across agent runtimes.

[中文文档](./README.zh-CN.md)

## Architecture

The host LLM handles understanding, classification, ranking, and recommendation; a
deterministic CLI (`src/scholar_workflow/`) performs testable file and Zotero operations.
Its Zotero adapter connects only to Zotero 10+'s loopback Local API; other outbound access
is scoped and declared — `apply` fetches PDFs from arXiv, and the separate
`bin/notion-project.py` / `bin/recommend-papers.py` reach their own declared services.
**Zotero is the authoritative library** — metadata, existence checks, indexed full text,
and additive writes use the official Local API. Topic recall combines Local API full-text
quicksearch with host-model ranking; no MCP server or local vector database is required.
Destructive actions still require your approval. **Obsidian** holds knowledge notes and
derived indexes; **Notion** holds an optional cross-device projection.

### Three-system boundary

- **Knowledge System** keeps readable Markdown as the primary knowledge artifact. Papers,
  technical documents, and blog posts are atomic resources; analyses, Canvas overviews, and
  attachments are explicitly owned supporting artifacts. Whole-paper analyses cover task,
  input, workflow, output, and boundary, with evidence inline beside each claim.
- **Project System** keeps a stable `project_id`, host-neutral source/config profiles, and
  separate Run, Attempt, Target, artifact-promotion, and backup records. A promoted artifact
  is not called a verified backup without an independently checked copy.
- **Hub Control Plane** exposes one `HubDirectory` root with typed Papers, Projects, and Tools
  libraries plus knowledge contexts. Zotero, the Vault, project manifests, explicit host
  registries, and Codex remain the authoritative stores.

Knowledge and project documents cross the boundary only through an explicit copy. The copy
receives the destination system's identity, drops managed `sw_*` identity, and then evolves
independently; there is no hidden synchronization or managed provenance relationship.

### Local research Hub

The Hub is cmux-first. Start it from a cmux terminal, then open it from another terminal
surface in the same workspace:

```bash
scholar-workflow serve-hub
# in another cmux terminal surface
scholar-workflow open-hub
# inspect the actual running build and provider/worker capabilities
scholar-workflow hub-doctor --json
# optional temporary-port, headless/read-only canary; never occupies 23128
scholar-workflow serve-hub --canary --port 0
# canary an already initialized provider; this never creates or migrates one
scholar-workflow serve-hub --canary --port 0 \
  --knowledge-provider-state-root /path/to/provider-state
```

For normal use, keep `serve-hub` in the foreground and press `Ctrl-C` in that terminal to stop
it. `open-hub` identifies the caller's current cmux workspace, opens a page with an opaque
one-time view identity, and completes the nonce/lease binding automatically. It exits successfully
only after the service confirms that binding and prints:

```text
[ok] Hub opened and bound to the current cmux workspace
```

No manual workspace selection is required for the initial binding. A manually entered
`http://127.0.0.1:23128/hub/` is an explicit read-only entry point, not a writable Hub view; the
page directs the user to run `scholar-workflow open-hub` from a cmux terminal. If automatic
binding fails, the command exits non-zero with a diagnostic instead of reporting success while the
page remains read-only. In `scholar-workflow hub-doctor --json`, `owner_mode=cmux-visible` and
`workspace_binding_available=true` mean that the service can bind views; the successful
`open-hub` receipt confirms the binding for that specific browser view.

The v2 API exposes the canonical directory at `/api/v2/directory`, paged library items below
`/api/v2/libraries/`, and self-describing health at `/api/v2/health`. The old
`/api/v1/catalog` response is derived from `HubDirectory.knowledge_catalog`; it is not a
second state root. Empty libraries remain visible with provider diagnostics, and Projects and
Tools come only from explicit registries rather than disk or `$PATH` scans.
If `$SCHOLAR_WORKFLOW_HOME/knowledge-provider/knowledge-provider.snapshot.json` already exists,
the Hub validates and reads it at startup; otherwise it retains the legacy read-only compatibility
provider. Starting the Hub never creates a snapshot or migrates the Vault.

Workspace-bound mutations are fail-closed: an unbound or headless Hub can still read
libraries, documents, PDFs, and diagnostics, but cannot write project files or run tasks.
Project file operations accept only a registered `project_id` plus a relative path under
`docs/`; collisions and symlink escapes are rejected, and deletion moves content to the
project trash. The Projects Library exposes these copy, paste, Knowledge-copy, and trash
operations only while the view has a live binding. Paper, PDF attachment, and analysis links
use typed landing pages; the raw `/open/paper/...` byte route stays inside the attachment
landing page. Task contracts accept only a registered recipe, typed targets, an 8 KiB brief,
and `fast`/`standard`/`deep` effort. The service owns cwd, model, sandbox, permissions, argv,
and explicit Codex thread IDs; raw commands and `--last` are rejected.

The current source tree contains the v2 contracts and canary-safe runtime. It does not
silently replace an existing port-23128 service, migrate a Vault/project, execute a real Codex
worker, or claim a backup medium is verified. Those actions require their separate rollout
gates. See [`references/hub-contract.md`](references/hub-contract.md). The `serve-links`
command and `/open/paper/<attachment-key>` URLs remain compatibility routes.

## Skills

| Skill | Purpose |
|---|---|
| survey-topic | Scope an open-ended "research X" request, then route it through the other skills |
| find-resource | Search for papers, verify identity, locate existing resources |
| ingest-resource | Import papers / archive technical documents |
| sync-projections | Rebuild Obsidian index tables + sync the Notion projection |
| build-literature-tree | Build a novelty tree (task → pipeline → paper) + flat paper list |
| check-consistency | Audit cross-system consistency (read-only) |
| export-annotations | Turn a paper's Zotero annotations into a structured vault note |
| recommend-papers | Daily multi-source paper feed + NotebookLM skim → Reading Report |
| analyze-paper | Project detailed paper analysis into paired Markdown + editable Canvas |
| env-setup | Scaffold — and consult — a personal API-key / SSH-server env-records ledger |
| agent-collaboration | Coordinate bounded work bidirectionally between Claude Code, Codex, or another available agent |
| init-project | Initialize a host-neutral, Git-managed research project skeleton without custom agents or hooks |
| config-setup | Initialize, query, and update the plugin configuration |
| project-backlog | Maintain the repository's persistent work-item queue |

## Requirements

- **Claude Code or Codex** (Codex CLI or the Codex app; the IDE extension does not load plugins).
- **Python ≥ 3.11** — the deterministic CLI is a Python package.
- **Git** — required when `init-project` creates or verifies a project skeleton.
- **cmux** — required for workspace-targeted viewing, bound mutations, and any controlled Codex
  task worker. Without a valid workspace binding, library and document reading remains available,
  while workspace, project-write, and task actions are disabled.
- **Zotero 10+ with Local API enabled** — the authoritative library. Enable it in
  Zotero's **Settings → Advanced**. No Zotero plugin or MCP server is required. A sandboxed
  Codex run may need localhost/network permission before it can reach port 23119; retry with
  that permission before interpreting exit 3 as Zotero being offline.
- **Optional, per feature:**
  - Notion integration token — only if you enable the Notion projection.
  - `notebooklm-py` + a Google login — only for the `recommend-papers` skim tier and
    NotebookLM-assisted literature-tree batch reading.
  - A Scholar Inbox account — only for that one recommendation source.
  - A target agent's CLI and existing login — only when `agent-collaboration` crosses
    host runtimes instead of using a native agent tool.

## Installation

1. **Install the plugin in your host.**

   The release ships separate native marketplace metadata for Codex and a
   Claude-compatible marketplace entry; both install the same plugin root and version.

   Claude Code:
   ```text
   /plugin marketplace add JerryFan012321/scholar-workflow@release
   /plugin install scholar-workflow@jerry-plugins
   ```

   Codex CLI:
   ```bash
   codex plugin marketplace add JerryFan012321/scholar-workflow --ref release
   codex plugin add scholar-workflow@jerry-plugins
   ```
   Start a new Claude Code or Codex session after installation so bundled skills and hooks
   are loaded.

2. **Install the CLI** (provides the `scholar-workflow` command the skills call):
   ```bash
   pip install -e .        # from a clone
   # or: pipx install scholar-workflow
   ```
   Verify: `scholar-workflow --help`.

3. **Create the config.** Just ask in-conversation ("configure scholar-workflow, my
   vault is ~/path/to/vault") and the `config-setup` skill runs it for you, or do it
   directly:
   ```bash
   scholar-workflow config init --research-vault-root ~/path/to/obsidian/vault
   # add optional settings inline as KEY=VALUE, e.g.:
   #   scholar-workflow config init --research-vault-root ~/vault notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # change one key later
   scholar-workflow config show                                       # inspect effective values
   ```
   This writes `~/.config/scholar-workflow/config.yml` (only the keys you name), validates
   it, and preserves comments on later edits. Override the location with
   `SCHOLAR_WORKFLOW_HOME` if needed.

4. **Authorize Zotero writes.** Start Zotero, then run:
   ```bash
   scholar-workflow zotero probe
   scholar-workflow zotero authorize
   ```
   Choose **Always Allow** in Zotero for multi-step PDF imports. The key is stored in
   macOS Keychain and is never printed or written to config/git. Read commands need no key.

5. **Provide other credentials** as needed (see [Requirements](#requirements)). Tokens/cookies
   live in environment variables or each tool's own login store — **never in config or
   git**. E.g. Notion: `export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`.

## Updating

The host manifests (`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`) share one
version (see [CHANGELOG.md](./CHANGELOG.md) for what changed). Refresh the marketplace or
pull the latest `release` branch, then re-run `pip install -e .`
(or `pipx upgrade scholar-workflow`) if the CLI version changed. Your `config.yml` and any
credentials live outside the repo and are unaffected by updates.

## Usage

Talk to Claude Code or Codex in natural language — each skill triggers on intent. In Codex,
you can also invoke a skill explicitly with `$skill-name`, e.g.:

- *"survey the field of world models"* → survey-topic → (recommend / find / tree …)
- *"find the DreamerV3 paper and import it"* → find-resource → ingest-resource
- *"recommend today's papers on world models"* → recommend-papers
- *"analyze the method section of this paper"* → analyze-paper
- *"build a literature tree from NeRF to 3DGS"* → build-literature-tree
- *"export my annotations on this paper"* → export-annotations
- *"sync the Obsidian index and Notion"* → sync-projections
- *"have Claude Code and Codex split this migration and integrate it"* → agent-collaboration
- *"initialize this project with the standard skeleton"* → init-project

Each skill's own `README` (under `skills/<name>/`) documents its options and setup in
detail. Recommendation reports are ephemeral; papers you keep flow into the normal
find/ingest pipeline so nothing enters your library without the dedup check.

## Status & limitations

The plugin is in active `0.x` development. What's solid vs. still settling:

- **Live-tested on Zotero 10.0.2:** the Local API path has passed probe, search, collection
  listing, remembered write authorization, item creation, imported-PDF upload, exact DOI
  reuse, and attachment reuse. The same ingest payload returns the original item and
  attachment without re-uploading.
- **The v0.27 cmux compatibility path was live-tested:** `open-hub` created a Hub browser surface
  and its legacy action could create a blank native agent session. The v2 lease/binding and
  bounded TaskRecipe contracts are covered by tests, but a real worker and port-23128 cutover are
  deliberately not activated by this source change.
- **The v2 knowledge/project contracts are fixture-tested, not migrated:** existing Vaults and
  projects remain untouched until an explicit migration plan is approved; the first knowledge
  pilot remains JEPA and the first real project is still a user decision.
- **Implemented but not yet exercised on a real end-to-end run:** the `build-literature-tree`
  CLI render path (especially the fourth `module` level and the challenge-insight tree
  written to the vault), the `recommend-papers` NotebookLM skim tier, and `check-consistency`.
- **No cross-run resume:** re-running `apply` starts a fresh job and re-downloads every item;
  it does not pick up where a prior run stopped.
- **Identity safety is enforced twice:** skills preview candidates and `zotero ingest`
  repeats the exact DOI or normalized title+creators check immediately before creation.
  Destructive Zotero commands are not exposed; future destructive actions remain gated.

## Development

This is the `release` branch (runtime only), including the native Codex marketplace,
the Claude-compatible marketplace, and both host manifests. Development — conventions,
planning docs, tests, and evals — lives on the `main` branch. See its `AGENT.md` for
contributor guidelines. Run tests there with `pytest tests/unit tests/contract`.
