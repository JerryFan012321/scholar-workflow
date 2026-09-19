# scholar-workflow

A Claude Code and Codex plugin for scholarly resource management. It discovers and imports
papers, keeps Obsidian indexes and Notion projections in sync, builds literature
novelty trees, recommends daily papers from four sources, and writes detailed paper
analyses. It also initializes Git-managed research-project skeletons and coordinates
bounded work across agent runtimes, with deterministic scripts doing testable file work
while the host LLM handles understanding, recommendation, and judgment.

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

### Local research Hub

The Hub is cmux-first. Start it from a cmux terminal, then open it from another terminal
surface in the same workspace:

```bash
scholar-workflow serve-hub
# in another cmux terminal surface
scholar-workflow open-hub
```

The workspace selector routes PDF, Markdown/Canvas, and Notion viewing to the Hub workspace
or another selected cmux workspace. Separate buttons open Vault documents in Obsidian and
paper records in Zotero for native editing. A confirmed Codex action creates only a blank,
visible native agent session in the selected workspace; it never accepts a browser-supplied
prompt, command, model, permission, or working directory. If the server was not launched
from cmux, these workspace actions are visibly unavailable while the Hub's built-in reading
and controlled Vault editor remain usable.

At `http://127.0.0.1:23128/hub/`, the Hub searches resources, streams read-only Zotero PDFs,
previews catalogued Markdown/Canvas files, and explicitly edits an existing Vault document
with conflict protection and a responsive live preview. Standard JSON Canvas files remain
unmodified and are registered through `.scholar-workflow/artifacts.yml`. A document's images,
data, and supplements can be added from a collapsed asset panel; they stay in the Vault and
are related through a human-checkable manifest. Notion never silently falls back to Safari.
HubCatalog governs machine identity across projections, while Obsidian keeps its readable
Markdown body and receives only a thin `sw_*` frontmatter layer. See
[`references/hub-contract.md`](references/hub-contract.md). The former `serve-links` command
and `/open/paper/<attachment-key>` URLs remain compatible.

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
| analyze-paper | In-depth analysis of a paper, written as a companion vault note |
| env-setup | Scaffold — and consult — a personal API-key / SSH-server env-records ledger |
| agent-collaboration | Coordinate bounded work bidirectionally between Claude Code, Codex, or another available agent |
| init-project | Initialize a host-neutral, Git-managed research project skeleton without custom agents or hooks |
| config-setup | Initialize, query, and update the plugin configuration |
| project-backlog | Maintain the repository's persistent work-item queue |

## Requirements

- **Claude Code or Codex** (Codex CLI or the Codex app; the IDE extension does not load plugins).
- **Python ≥ 3.11** — the deterministic CLI is a Python package.
- **Git** — required when `init-project` creates or verifies a project skeleton.
- **cmux** — required for workspace-targeted PDF/document/Notion viewing and the blank Codex
  session action. Without a live cmux socket, the catalog and registered Vault-document reader
  remain available, as do the Obsidian/Zotero editor jumps; cmux-only actions are visibly disabled.
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
- **Live-tested in cmux:** `open-hub` created the Hub browser surface in the caller's workspace,
  the selector identified the Hub workspace, and the confirmed Codex action created a blank
  native agent session in that same workspace without sending a prompt.
- **Implemented but not yet exercised on a real end-to-end run:** the `build-literature-tree`
  CLI render path (especially the fourth `module` level and the challenge-insight tree
  written to the vault), the `recommend-papers` NotebookLM skim tier, and `check-consistency`.
- **No cross-run resume:** re-running `apply` starts a fresh job and re-downloads every item;
  it does not pick up where a prior run stopped.
- **Identity safety is enforced twice:** skills preview candidates and `zotero ingest`
  repeats the exact DOI or normalized title+creators check immediately before creation.
  Destructive Zotero commands are not exposed; future destructive actions remain gated.

## Development

This is the `release` branch (runtime only), including both host manifests. Development — conventions, planning docs,
tests, and evals — lives on the `main` branch. See its `AGENT.md` for contributor
guidelines. Run tests there with `pytest tests/unit tests/contract`.
