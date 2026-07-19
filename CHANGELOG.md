# Changelog

All notable changes to scholar-workflow are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) — Semver: major.minor.patch

## [0.1.6] — 2026-07-19

### Removed
- `project_references/` (DESIGN.md, PROJECT.md, design image) archived out of the repo to `archived/scholar-workflow/project_references/`; intent layer already lives in GOALS.md, architecture layer is a frozen snapshot

### Changed
- GOALS.md and AGENT.md references updated to point at the archived location instead of the in-repo path

## [0.1.5] — 2026-07-19

### Added
- `GOALS.md` — living intent layer at repo root: upstream goals (G1–G9), long-term invariants (INV1–INV11), non-goals (NG1–NG8), phase status; each linked to its guarding eval by stable ID
- AGENT.md: GOALS.md added to the documentation boundary as the north star; Always Do rule to update GOALS.md (with stable IDs) on any goal/scope change

### Changed
- Documentation boundary now distinguishes the living intent layer (GOALS.md) from the frozen implementation-layer snapshot (project_references/DESIGN.md § architecture)

## [0.1.4] — 2026-07-19

### Added
- `## References` section in all 5 SKILL.md, with `${CLAUDE_PLUGIN_ROOT}/references/` prefix for shared policies and `references/` for skill-local docs
- AGENT.md Language: extended to cover agents, references, and user-facing string literals (English)
- dev-guide/skill-authoring.md: documented the `${CLAUDE_PLUGIN_ROOT}` vs `references/` path convention

### Changed
- All 5 `agents/*.md` rewritten in English (runtime-loaded artifacts, same language rule as SKILL.md)
- `obsidian.py` table headers aligned to English column names matching obsidian-index-format.md spec

## [0.1.3] — 2026-07-19

### Added
- `dev-guide/`: development-time docs (skill-authoring, skill-iteration, eval-loop) — never loaded at runtime
- AGENT.md: Documentation boundary section separating dev-time docs from runtime docs
- AGENT.md: Lifecycle note — dev-guide is scaffolding, to be archived + untracked once its build targets are met

## [0.1.2] — 2026-07-19

### Added
- Per-skill `references/` dirs with tailored operational docs (11 files)
- Top-level `references/`: storage-policy, source-policy, identity-policy, security-policy (4 canonical shared policies)
- AGENT.md: two-tier references convention documented

### Changed
- Replaced 8 original Chinese top-level reference files with 4 English canonical policies
- Removed all cross-tier duplication — per-skill references point to shared policies rather than repeating rules
- Renamed ingest acquisition-policy → download-validation (focused on mechanics only)

### Removed
- `references/classification-policy.md` → absorbed into `skills/ingest-resource/references/resource-model.md`
- `references/literature-edge-evidence.md` → `skills/build-literature-tree/references/edge-evidence.md`
- `references/notion-schema.md` → `skills/sync-projections/references/notion-schema.md`
- `references/obsidian-index-format.md` → `skills/sync-projections/references/obsidian-index-format.md`
- `references/zotero-fields.md` → `skills/ingest-resource/references/zotero-fields.md`

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
