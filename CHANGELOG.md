# Changelog

All notable changes to scholar-workflow are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) — Semver: major.minor.patch

## [0.1.1] — 2026-07-19

### Added
- README.md + README.zh-CN.md for each of the 5 skills (Skill Anatomy compliance)
- Root README.md + README.zh-CN.md with architecture overview and skill table

### Changed
- All 5 SKILL.md bodies rewritten in English (AGENT.md Never Do: no Chinese in SKILL.md body); bilingual trigger words retained in the `description` frontmatter

## [0.1.0] — 2026-07-19

### Added
- Phase 0 scaffold: full plugin directory structure
- 5 agents: intake / library / knowledge / lineage / audit
- 5 skills with routing frontmatter (name + bilingual trigger description): find-resource / ingest-resource / sync-projections / build-literature-tree / check-consistency
- 7 JSON Schema contracts: resource / action-plan / zotero-import / index-entry / notion-projection / literature-graph / handoff
- 8 reference policy files: storage / source / classification / security / zotero-fields / obsidian-index-format / notion-schema / literature-edge-evidence
- Python package skeleton: models / config / identity / state / planning / approvals / cli
- 6 adapters: arxiv / zotero_local / zotero_bridge / obsidian / notion / local_links
- 4 workflow stubs: paper / document / lineage / audit
- ZoteroWriteAdapter interface with BridgeAdapter implementation
- hooks/hooks.json in official event-keyed format: SessionStart doctor, PreToolUse SQLite guard, PreCompact handoff
- scripts/guard-sqlite.sh: hook script blocking direct zotero.sqlite writes (exit 2)
- evals: routing / safety / outcomes
- .claude-plugin/plugin.json manifest with userConfig (papers_root / vault_root / notion_enabled)
- AGENT.md: development conventions (Skill Anatomy, Language, Behavior Boundaries, Changelog) adapted from sjh-skills
- CLAUDE.md referencing AGENT.md
- pyproject.toml with pinned dependencies
- integrations/zotero-bridge/manifest.json
