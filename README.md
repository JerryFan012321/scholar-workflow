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
- **Hub Control Plane v3** exposes one `HubDirectory` root. Document Libraries contain only
  Zotero Papers and dynamic Obsidian Fields; Projects and Tools are peer entries. cmux routes
  browser/terminal windows, while registered folders and projects independently authorize files
  and cwd. Zotero, Field manifests, project manifests, explicit registries, and Codex remain the
  authoritative stores.

Knowledge and project documents cross the boundary only through an explicit copy. The copy
receives the destination system's identity, drops managed `sw_*` identity, and then evolves
independently; there is no hidden synchronization or managed provenance relationship.

### Local research Hub

For normal use, one command is enough:

```bash
scholar-workflow open-hub
```

`open-hub` verifies the installed build, starts or safely restarts Scholar Workflow's managed
loopback service, discovers its dynamic port, and opens the Hub. It never needs a source checkout,
`CODE_REPO_ROOT`, a fixed port, nonce, or lease. Run it inside cmux to remember that workspace as
the page's default open location; outside cmux, reading and authorized file operations still work,
while cmux-only actions ask you to choose a destination.

Service controls are explicit and idempotent:

```bash
scholar-workflow hub start
scholar-workflow hub status
scholar-workflow hub restart
scholar-workflow hub doctor
scholar-workflow hub stop
```

`status` reports the real executable, plugin/package/service build, protocol, PID, dynamic port,
generation, start time, and log. `stop` affects only a process whose discovery record and live
identity handshake prove that Scholar Workflow owns it; an unknown listener is never terminated.

The page is organized as `Libraries → Papers / Fields`, plus peer `Projects` and `Tools` entries.
There is no global “workspace bound/read-only” mode. Capabilities such as Vault writes, project
document writes, cmux launches, Codex tasks, ZotFlow annotations, and Zotero Local API are reported
independently. A closed cmux workspace disables only launches routed to it.

To add a research field:

1. Open **Fields → 选择 Vault / 目录** (Select Vault/Folder).
2. Choose an Obsidian Vault or a subdirectory in the system picker. The browser never receives its
   absolute path.
3. Review the zero-write preview: proposed Fields, home page, navigation order, collisions,
   template rewrites, ignored files, unmapped prose, and link changes.
4. Confirm only the Field you want to initialize. One Source may contain multiple Fields, and each
   Field defines its own navigation labels.

If the selected Vault already has a portable Field manifest but is not registered on this host,
the preview instead offers **Register existing Source**. It shows all existing Fields and IDs;
confirmation registers the Source locally without editing that manifest or its documents.

The legacy `research_vault_root` is only offered as a migration candidate. It is not the one
required knowledge root. Field pages show manifest navigation and selected Markdown together,
without a document landing page.

Paper cards act directly. The primary action is **Annotate in ZotFlow**; secondary actions open
Zotero, read in the selected cmux workspace, use the system PDF reader, show the analysis, or open
the annotation note. If ZotFlow is missing, disabled, or incompatible, the primary action falls
back to Zotero and explains why. Zotero remains the annotation authority. Only ZotFlow may hold a
Zotero Web API key, in Obsidian SecretStorage; Scholar Workflow reads annotations through the Local
API and never requests that key. The legacy `/hub/item` and `/open/paper/...` routes remain only for
one-cycle compatibility and are not emitted by the normal UI.

Notion and other Web tools open through registered URL recipes in a selected cmux browser surface.
CLI and Codex recipes open a terminal surface there, but cwd comes only from a registered project,
Vault, or folder target. Browser requests cannot supply URLs, commands, cwd, model, sandbox,
permissions, environment, or raw Codex configuration. Project operations still accept only a
registered `project_id` and a relative path under `docs/`; collisions and symlink escapes fail,
deletion goes to recoverable project trash, and Hub never writes Git.

To enable a Codex task in the Hub, register its working folder once and configure the local Codex
executable. A destination decides where the terminal appears; the registered target decides its
working directory. These administrator commands run on the same host as the Hub:

```bash
scholar-workflow hub target list
scholar-workflow hub target add-source SOURCE_ID --target-id research
# Or use an already registered project:
scholar-workflow hub target add-project PROJECT_ID --target-id project
scholar-workflow hub codex configure --executable /absolute/path/to/codex --model YOUR_MODEL --sandbox workspace-write
scholar-workflow hub codex status
scholar-workflow hub restart
```

`SOURCE_ID` is shown in the **Fields → 选择 Vault / 目录** preview; `PROJECT_ID` comes
from the project's manifest and host registration. Use the target command that matches your work.
`configure` probes the explicitly supplied executable and stores the model and sandbox as private
server policy; it does not search `$PATH`. In the Hub's **Codex tasks** panel, choose the registered
task, target, destination, effort, and a brief of at most 8 KiB, then start the run. The page shows
the run status and the selected cmux terminal. Until configuration, a live destination, and the
worker capability check all succeed, the panel shows the specific unavailable reason. The
administrator can choose `--sandbox read-only` instead for a task that must not write files.

To give another PDF reader a separate copy with supported Zotero annotations:

```bash
scholar-workflow zotero snapshot-annotations ATTACHMENT_KEY --output /path/to/annotated-copy.pdf
```

This creates a new PDF and hash receipt; it never overwrites the Zotero attachment or syncs edits
made to the copy back into Zotero. Unsupported annotation types fail explicitly.

After a Field has been explicitly registered and its exact migration preview has been accepted,
legacy paper links can be migrated one Field at a time:

```bash
scholar-workflow hub field-migration plan SOURCE_ID FIELD_ID
scholar-workflow hub field-migration apply SOURCE_ID FIELD_ID --approved-digest sha256:PLAN_DIGEST
```

The plan is read-only. Each distinct attachment key must be verified through Zotero's Local API as
an available PDF in the user library before its stable URI is approved. Missing items, group items,
non-PDF or unsupported attachments, and an unavailable Local API are explicit plan conflicts; apply
also reverifies them before any recovery snapshot or write. Apply re-scans the Field and requires the
exact approved digest; it only rewrites legacy links in Markdown/Canvas files named by that Field's
manifest. Unmapped files with remaining legacy links block the operation. It does not reorganize
paper analysis or normalize JEPA templates. A synchronous failure is rolled back, but a process
crash during multi-file replacement requires manual recovery from the snapshot; that snapshot is
not a verified backup.

See [`references/hub-contract.md`](references/hub-contract.md) for the complete runtime contract.
Recovery snapshots created during a Field migration are not verified backups; a separate backup
medium and restore exercise remain required.

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
- **cmux** — optional for routing Web/terminal/Codex/CLI windows to a chosen workspace. It does not
  grant file access and is not required for reading, Vault saves, or registered project-document
  operations.
- **Zotero 10+ with Local API enabled** — the authoritative library. Enable it in
  Zotero's **Settings → Advanced**. No Zotero plugin or MCP server is required. A sandboxed
  Codex run may need localhost/network permission before it can reach port 23119; retry with
  that permission before interpreting exit 3 as Zotero being offline.
- **Optional, per feature:**
  - **Obsidian + ZotFlow** — for in-Obsidian PDF annotation. Hub checks the installed app/plugin
    versions and ZotFlow's `minAppVersion`; it reports incompatibility but never upgrades Obsidian.
    ZotFlow keeps its Zotero Web API key in Obsidian SecretStorage.
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

3. **Create the config.** Ask in-conversation ("configure scholar-workflow") and the
   `config-setup` skill runs it for you, or do it directly:
   ```bash
   scholar-workflow config init
   # add optional settings inline as KEY=VALUE, e.g.:
   #   scholar-workflow config init notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # change one key later
   scholar-workflow config show                                       # inspect effective values
   ```
   This writes `~/.config/scholar-workflow/config.yml` (only the keys you name), validates
   it, and preserves comments on later edits. Override the location with
   `SCHOLAR_WORKFLOW_HOME` if needed. Add each Vault or folder from **Hub → Fields → 选择 Vault / 目录**;
   an old `research_vault_root` value is treated only as a migration candidate.

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
- **Hub v3 replaces the v0.28.1 binding model:** cmux is only an open location; trusted
  folder/project targets authorize files and cwd. Managed lifecycle uses a dynamic port and
  self-identifying discovery rather than a fixed 23128 service or source-tree root.
- **Real data still uses per-Field gates:** the first Source is the current research-document
  Vault, the first Field is World Models, and JEPA/V-JEPA is the acceptance sample. A preview must
  be accepted before that Field changes; other Vaults and projects remain untouched.
- **ZotFlow compatibility is diagnosed, not repaired automatically:** if the installed Obsidian
  version is below the plugin's `minAppVersion`, Hub disables the ZotFlow action and explains the
  required upgrade. It never upgrades Obsidian or removes another plugin.
- **Implemented but not yet exercised on a real end-to-end run:** the `build-literature-tree`
  CLI render path (especially the fourth `module` level and the challenge-insight tree
  written to the vault), the `recommend-papers` NotebookLM skim tier, and `check-consistency`.
- **No cross-run resume:** re-running `apply` starts a fresh job and re-downloads every item;
  it does not pick up where a prior run stopped.
- **Identity safety is enforced twice:** skills preview candidates and `zotero ingest`
  repeats the exact DOI or normalized title+creators check immediately before creation.
  Destructive Zotero commands are not exposed; future destructive actions remain gated.

## Development

The published `release` branch contains runtime files only, including native Codex and
Claude-compatible marketplace metadata and both host manifests. Development conventions,
planning docs, tests, and evals live on `main`. See its `AGENT.md` for contributor guidelines;
run tests there with `pytest tests/unit tests/contract`.
