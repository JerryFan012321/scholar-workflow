# scholar-workflow

Plan-first scholarly resource management for Claude Code. Import papers, archive
technical documents, keep Obsidian indexes and Notion projections in sync, and
build evidence-based literature lineage trees — with deterministic safety checks
and an explicit approval gate before any download.

[中文文档](./README.zh-CN.md)

## Architecture

Claude handles understanding, recommendation, and approval interactions; a
deterministic CLI (`src/scholar_workflow/`) performs testable, resumable
execution. Zotero (and its PDF storage) is the authoritative library for papers;
metadata and existence come from the Zotero Local API (read-only). Zotero has no
local write API, so approved papers download into `paper_inbox` and the user
imports them into Zotero manually. Obsidian holds knowledge and derived indexes;
Notion holds a management projection.

## Skills

| Skill | Purpose |
|---|---|
| find-resource | Search for papers, verify identity, and locate existing resources |
| ingest-resource | Import papers / archive technical documents (plan then execute) |
| sync-projections | Rebuild Obsidian index tables and sync Notion projections |
| build-literature-tree | Build evidence-based literature lineage graphs |
| check-consistency | Audit cross-system consistency (read-only) |

## Development

See [AGENT.md](./AGENT.md) for development conventions and behavior boundaries,
and [CHANGELOG.md](./CHANGELOG.md) for version history.

```
pytest tests/unit tests/contract
```
