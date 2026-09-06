# scholar-workflow

A Claude Code and Codex plugin for scholarly resource management. It discovers and imports
papers, keeps Obsidian indexes and Notion projections in sync, builds literature
novelty trees, recommends daily papers from four sources, and writes detailed paper
analyses. It also initializes Git-managed research-project skeletons and coordinates
bounded work across agent runtimes, with deterministic scripts doing testable file work
while the host LLM handles understanding, recommendation, and judgment.

[中文文档](./README.zh-CN.md)

## Architecture

The host LLM handles understanding, classification, and recommendation; a deterministic CLI
(`src/scholar_workflow/`) performs testable file operations and never touches your Zotero
library directly. Its core projection/state commands make no network calls; the only
outbound access is scoped and declared — `apply` fetches PDFs from arXiv, and the separate
`bin/notion-project.py` / `bin/recommend-papers.py` reach their own declared services.
**Zotero is the authoritative library** — metadata, existence checks, and semantic search
all go through [zotero-mcp](https://github.com/54yyyu/zotero-mcp). Additive writes (create /
import / metadata) run through zotero-mcp's controlled tools; destructive actions require
your approval. Paper PDFs download into an inbox, then the host imports them into Zotero via
zotero-mcp (`write_item import`). **Obsidian** holds knowledge notes and derived indexes;
**Notion** holds an optional cross-device projection.

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
- **Zotero + [zotero-mcp](https://github.com/54yyyu/zotero-mcp)** — the authoritative
  library. The plugin hard-depends on it for read/write/semantic search; without it the
  library-facing skills fail fast.
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
   Start a new Claude Code or Codex session after installation so bundled skills, hooks,
   and MCP tools are loaded.

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

4. **Provide credentials** as needed (see [Requirements](#requirements)). Tokens/cookies
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

- **Battle-tested end to end:** paper ingest (find → dedup-verify → import into Zotero) and
  the Obsidian / Notion projections.
- **Implemented but not yet exercised on a real end-to-end run:** the `build-literature-tree`
  CLI render path (especially the fourth `module` level and the challenge-insight tree
  written to the vault), the `recommend-papers` NotebookLM skim tier, and `check-consistency`.
- **No cross-run resume:** re-running `apply` starts a fresh job and re-downloads every item;
  it does not pick up where a prior run stopped.
- **Library-safety rules live at the skill layer, not in code:** the dedup check before
  create and the approval gate on destructive Zotero actions are followed by the host LLM per
  the skill instructions — the CLI cannot reach zotero-mcp to enforce them.

## Development

This is the `release` branch (runtime only), including both host manifests. Development — conventions, planning docs,
tests, and evals — lives on the `main` branch. See its `AGENT.md` for contributor
guidelines. Run tests there with `pytest tests/unit tests/contract`.
