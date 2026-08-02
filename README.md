# scholar-workflow

A Claude Code plugin for scholarly resource management. It discovers and imports
papers, keeps Obsidian indexes and Notion projections in sync, builds literature
novelty trees, recommends daily papers from four sources, and writes detailed paper
analyses — with a deterministic CLI doing the testable, resumable work while Claude
handles understanding, recommendation, and judgment.

[中文文档](./README.zh-CN.md)

## Architecture

Claude handles understanding, classification, and recommendation; a deterministic CLI
(`src/scholar_workflow/`) performs testable, resumable file operations and never makes
network calls or touches your library directly. **Zotero is the authoritative library**
— metadata, existence checks, and semantic search all go through
[zotero-mcp](https://github.com/54yyyu/zotero-mcp). Additive writes (create / import /
metadata) run through zotero-mcp's controlled tools; destructive actions require your
approval. Approved paper PDFs download into an inbox for you to import. **Obsidian** holds
knowledge notes and derived indexes; **Notion** holds an optional cross-device projection.

## Skills

| Skill | Purpose |
|---|---|
| find-resource | Search for papers, verify identity, locate existing resources |
| ingest-resource | Import papers / archive technical documents |
| sync-projections | Rebuild Obsidian index tables + sync the Notion projection |
| build-literature-tree | Build a novelty tree (task → pipeline → paper) + flat paper list |
| check-consistency | Audit cross-system consistency (read-only) |
| export-annotations | Turn a paper's Zotero annotations into a structured vault note |
| recommend-papers | Daily multi-source paper feed + NotebookLM skim → Reading Report |
| analyze-paper | In-depth analysis of a paper, written as a companion vault note |
| env-setup | Scaffold a personal API-key / SSH-server env-records ledger |

## Requirements

- **Claude Code** (this is a plugin for it).
- **Python ≥ 3.11** — the deterministic CLI is a Python package.
- **Zotero + [zotero-mcp](https://github.com/54yyyu/zotero-mcp)** — the authoritative
  library. The plugin hard-depends on it for read/write/semantic search; without it the
  library-facing skills fail fast.
- **Optional, per feature:**
  - Notion integration token — only if you enable the Notion projection.
  - `notebooklm-py` + a Google login — only for the `recommend-papers` skim tier and
    NotebookLM-assisted literature-tree batch reading.
  - A Scholar Inbox account — only for that one recommendation source.

## Installation

1. **Install the plugin.** Add this repository as a Claude Code plugin (via the plugin
   marketplace, or point Claude Code at a local clone / the repo URL).

2. **Install the CLI** (provides the `scholar-workflow` command the skills call):
   ```bash
   pip install -e .        # from a clone
   # or: pipx install scholar-workflow
   ```
   Verify: `scholar-workflow --help`.

3. **Create the config** at `~/.config/scholar-workflow/config.yml`:
   ```yaml
   papers_root: ~/path/to/managed/paper/pdfs   # required
   vault_root:  ~/path/to/obsidian/vault        # required
   paper_inbox: ~/path/to/download/inbox        # optional
   # notion: { enabled: true, ... }             # optional, see docs
   ```
   Override the config location with `SCHOLAR_WORKFLOW_HOME` if needed.

4. **Provide credentials** as needed (see [Requirements](#requirements)). Tokens/cookies
   live in environment variables or each tool's own login store — **never in config or
   git**. E.g. Notion: `export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`.

## Updating

The plugin is versioned via `.claude-plugin/plugin.json` (see [CHANGELOG.md](./CHANGELOG.md)
for what changed). Pull the latest `release` branch, then re-run `pip install -e .`
(or `pipx upgrade scholar-workflow`) if the CLI version changed. Your `config.yml` and any
credentials live outside the repo and are unaffected by updates.

## Usage

Just talk to Claude Code in natural language — each skill triggers on intent, e.g.:

- *"find the DreamerV3 paper and import it"* → find-resource → ingest-resource
- *"recommend today's papers on world models"* → recommend-papers
- *"analyze the method section of this paper"* → analyze-paper
- *"build a literature tree from NeRF to 3DGS"* → build-literature-tree
- *"export my annotations on this paper"* → export-annotations
- *"sync the Obsidian index and Notion"* → sync-projections

Each skill's own `README` (under `skills/<name>/`) documents its options and setup in
detail. Recommendation reports are ephemeral; papers you keep flow into the normal
find/ingest pipeline so nothing enters your library without the dedup check.

## Development

This is the `release` branch (runtime only). Development — conventions, planning docs,
tests, and evals — lives on the `main` branch. See its `AGENT.md` for contributor
guidelines. Run tests there with `pytest tests/unit tests/contract`.
