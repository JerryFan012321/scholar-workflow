# Changelog

All notable changes to scholar-workflow are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) — Semver: major.minor.patch

## [0.4.0] — 2026-07-20

Doc/eval alignment for the zotero-mcp pivot, plus an approval-model change ratified in
a live ingest exercise. The 0.2.0/0.3.0 rounds pivoted the goal layer and retired the
Zotero-touching CLI code; this round rewrites every runtime doc (references, SKILLs,
agents) and the safety evals to the zotero-mcp model, so no doc still describes the old
"import is manual / Local API read-only" world. It also changes the approval rule:
additive writes (download, create, import, metadata fill, add-to-collection) now
proceed under the user's standing instruction; only destructive/irreversible actions
(delete, overwrite-conflict, merge) require per-item approval. Verified end-to-end by
repairing a real dirty record (Text2CAD, NeurIPS 2024): filled empty abstract, fixed a
wrong DOI, overrode the arXiv label with the conference venue, and re-attached a ghost
PDF via zotero-mcp.

### Changed
- Approval model — from "every Zotero write needs approval" to "additive writes proceed,
  only destructive actions gate" (G4/G9/INV9/NG5). Mirrored into `~/.claude/CLAUDE.md`
  and `references/security-policy.md`
- `references/security-policy.md` — permission table flipped (create/import/metadata/
  download are additive-allowed; delete/overwrite/merge gate); added fetch-vs-write
  distinction, ask-collection-before-write, zotero-mcp channel, and the itemType caveat
- `references/storage-policy.md` — dropped the resource-cache mirror (INV13) and manual
  import; PDFs ingested via zotero-mcp; live queries, no local mirror
- `references/identity-policy.md` — dedup key is Zotero canonical identity (DOI /
  title+authors), arXiv id demoted to a download-source label; two-step existence check
  (search_library recall → get_item_details confirm); itemType read-layer caveat; new
  items take metadata from authoritative web sources, venue overrides preprint label
- `references/source-policy.md` — metadata acquisition reworded to zotero-mcp + web
  sources; arXiv-only download rule unchanged
- All 5 SKILLs — `find-resource` (locate/catalog/resolve/sync commands → zotero-mcp
  search/semantic/get_details), `ingest-resource` (rewritten to the zotero-mcp write
  flow + 4 lessons: paper = PDF+metadata, venue override, itemType caveat, don't hammer
  unreachable sites), `sync-projections` (rebuild source → zotero-mcp live, not a
  mirror), `check-consistency` (Zotero check via zotero-mcp, ghost-attachment drift),
  `build-literature-tree` (paper set + abstracts via zotero-mcp)
- `agents/library-agent.md` — rewritten (dropped `plan_id` execution gate and the
  Bridge health check; existence-check-before-create, zotero-mcp writes)
- `agents/intake-agent.md` — clarified zotero-mcp queries are reads (allowed); no title
  fabrication for identifier-only inputs
- `evals/safety.json` — removed `no-zotero-write` (contradicts additive writes) and the
  `plan_id`-era `no-unapproved-apply` / `plan-invalidated-on-change`; added
  `no-unapproved-destructive-zotero` and `no-create-without-existence-check`;
  `no-existence-on-unreachable` semantics moved Local API → zotero-mcp
- `GOALS.md` — G3/G4/G9, INV1/INV9/INV10/INV11, NG5, Phase 1 status, F2 updated to the
  new approval model and dedup key; downstream-sync checklist marked complete; added an
  INV16 footnote (doctor is two-layer: CLI checks paths, skill layer checks MCP)

## [0.3.0] — 2026-07-20

First code landing of the zotero-mcp pivot (GOALS.md v2, 0.2.0). All Zotero access
(existence, dedup, metadata, semantic search, writes) is delegated to the host LLM
via zotero-mcp; since the CLI is a standalone subprocess that cannot reach MCP tools,
the Zotero-touching CLI logic is **removed** rather than rewritten. The CLI shrinks to
arXiv-fetch-to-inbox, job state, reporting, and a path-only `doctor`. Docs/SKILL/
references/evals sync and the INV1 dedup-key rewording are staged for the next round.

### Removed
- `adapters/zotero_local.py` — the Zotero Local API HTTP client (all reads now via zotero-mcp, host LLM)
- `workflows/sync.py` — `sync_cache` + helpers (INV13 deprecated; no local cache mirror)
- `dedup.py` — `check_existence` / `_search` / `decide_operation` / `Match` / `ExistenceResult` / `DependencyError` (existence + dedup move to the skill layer; `run_paper_import` already skips non-create ops on its own)
- `cli.py` commands `sync` / `catalog` / `resolve` / `plan` / `locate`, plus `_zotero_reader()` and the `DependencyDown` exception
- `state.py` — `resources` cache table + `upsert_resource` / `find_exact` / `catalog` / `oldest_sync` / `_rows` (jobs table retained)
- `config.py` — `ZoteroConfig` / `zotero.local_api_url` (CLI no longer connects to Zotero directly; stale `zotero:` blocks in config.yml load fine — Pydantic ignores unknown keys)
- `doctor.py` — `_probe_local_api` and the `zotero_local_api` check (MCP reachability is a skill-layer check the CLI cannot perform)
- Tests: `test_dedup.py` (8), `test_sync.py` (5), `test_zotero_local.py` (6); the just-added `tests/eval/test_cli_exit_codes.py` was rewritten (its `locate`/`plan` targets retired)

### Changed
- `planning.generate_plan(resources, config_version)` — dropped the `zotero`/`state` params and the existence check; plans are now purely deterministic (every resource → `create`), dedup decided upstream by the host LLM
- `cli.py apply` — resolves inputs → builds a deterministic all-`create` plan (no existence check) → downloads arXiv PDFs to `paper_inbox`; the host LLM does dedup via zotero-mcp before invoking `apply`
- `doctor` — now checks only local config paths; exit 3 survives but its meaning shifts from "Zotero unreachable" to "a required local path is missing"
- `workflows/audit.py` — dropped the `ZoteroLocalAdapter` import and the unused `zotero` params on the two Phase-6 stubs
- `tests/eval/test_cli_exit_codes.py` — rewritten: `doctor` exits 3 on a missing local path; `apply ""` exits 2 (input error). Full suite 19 passed

## [0.2.0] — 2026-07-20

Goal-layer pivot: adopt zotero-mcp (a third-party Zotero 7 MCP server exposing read /
write / semantic-search tools to the host LLM) as the way scholar-workflow reaches
Zotero. This removes the premises several invariants rested on ("Zotero has no local
write API, no semantic search") — GOALS.md F2's "reinstate programmatic writes once a
local write API exists" is now fulfilled, third-party. **This entry rewrites the goal
layer only (GOALS.md); no code, MCP wiring, or downstream references/SKILL/evals were
touched — those are staged for later phases.** Three user-ratified decisions: writes
go through zotero-mcp and require user approval (batchable); semantic recall is
delegated to zotero-mcp's `semantic_search`; zotero-mcp is a hard dependency (doctor
must check it, fail-fast on exit 3, no degrade branch).

### Changed
- GOALS.md — G4/G8/G9 rewritten (approved-write import, MCP-provided Zotero access, CLI shrinks to arXiv/inbox/projection); INV1 reworded (dedup via zotero-mcp); INV9 rewritten (writes only via zotero-mcp, per-write user approval, no bypass); INV10/INV12 authority moved Local API → zotero-mcp; INV14 rewritten (delegate semantic_search, no self-ban on embeddings); INV15 display-name path via zotero-mcp; NG5 narrowed ("any programmatic write" → "unapproved write / bypassing the approval gate"); Phase 1 status and F2 updated
- GOALS.md — added INV16 (hard dependency on zotero-mcp + doctor fail-fast)
- GOALS.md — deprecated INV13 (local resource cache dropped; existence/metadata/semantic all delegated live to zotero-mcp; ID retained, not reused)
- GOALS.md — added a downstream-sync checklist under 维护规则 (security/storage/identity policies, find/ingest/sync-projections SKILLs, evals/safety.json, and code retirement of zotero_local.py / sync.py / dedup.check_existence / CLI sync·locate·resolve·catalog) to align in later phases

## [0.1.21] — 2026-07-20

Backs the `no-existence-on-unreachable` eval case (evals/safety.json) with a real
CLI-boundary test: commands run through CliRunner must exit 3 when the Zotero Local
API is unreachable, never silently treating it as "not found" (INV12). This is the
first test to cover the `DependencyError → exit 3` mapping in `cli.py` itself, not
just the logic layer. Scope was deliberately limited to eval cases that have a real
CLI trigger path — the exit-4 cases (`no-unapproved-apply`, `plan-invalidated-on-change`)
have none (the `apply` command signs its own plan in-process), so their guard stays
at the logic layer (`approvals.assert_executable`).

### Added
- `tests/eval/test_cli_exit_codes.py` (3) — `locate`/`plan` exit 3 on unreachable Zotero (fail-closed, INV12); empty identifier exits 2 (input error). 40 tests pass

## [0.1.20] — 2026-07-20

Makes the resolver contract self-describing: for identifier inputs (arXiv/DOI) the
offline resolver no longer fabricates a placeholder title (`arXiv:<id>` / `doi:<id>`)
that could be mistaken for a real one. `Resource.title` is now nullable and set to
`null` for those inputs. Titles never affect any decision (dedup and planning read
identifiers only), so a real display title is an optional display-layer enrichment:
EXACT hits read it from the catalog / Zotero, new items use the conversation or an
arXiv fetch, and when unavailable the identifier is shown as-is. This fails safe on
port to any host — a null can never be misread as a title. See GOALS.md INV15.

### Changed
- `models.py` — `Resource.title: str` → `str | None` (null when the offline resolver has no real title)
- `resolver.py` — arXiv/DOI branches set `title = None` instead of a placeholder string; url/title inputs still keep the user's text
- `skills/find-resource/SKILL.md` + `skills/ingest-resource/SKILL.md` — document display-layer title enrichment (optional; show identifier when no real title is available) and add the null-title constraint
- GOALS.md — added INV15 (self-describing resolver contract: null title, display-layer enrichment, never a decision input)
- `tests/unit/test_resolver.py` — assert `title is None` for arXiv/DOI inputs (added a DOI case); 34 tests pass

## [0.1.19] — 2026-07-20

Existence is now decided by the Zotero Local API (the authority), not the local
cache — fixing a phantom-cache bug where dedup queried an empty SQLite table (no
production code ever populated it) and so always judged papers as new. Adds a
user-triggered cache sync and a catalog projection for host-LLM semantic recall.
Splits identity work into two disjoint tools: exact existence (deterministic
identifier query, fail-closed) and fuzzy recall (host LLM reads the catalog, no
embeddings). See GOALS.md INV1/INV12/INV13/INV14.

### Added
- `adapters/zotero_local.py` — `search_by_arxiv(arxiv_id)` (field-verified against DOI/url/extra to reject text false-positives) and `get_items(start, limit)` paging; client is now injectable for tests
- `dedup.py` — `DependencyError` (maps to exit code 3); `check_existence` queries the Local API and fails closed when unreachable (INV12 — never returns `none` on error)
- `workflows/sync.py` — `sync_cache(zotero, store, page_size=100)`: pages Zotero top-level items into the derived cache (user-triggered, fail-closed); `_resource_from_item` maps an item → cache row (arXiv id pulled from DOI/url/extra), skipping identity-less items
- `state.py` — `resources` cache gains `title`/`abstract`; `catalog()` (title + abstract projection for semantic recall) and `oldest_sync()` (staleness signal)
- `cli.py` — `sync` (refresh the cache from Zotero) and `catalog` (emit the projection with `oldest_sync` for the host LLM); `DependencyDown` (exit code 3)
- `tests/contract/test_zotero_local.py` (6) + `tests/unit/test_sync.py` (5); rewrote `tests/unit/test_dedup.py` (8, fake Zotero). 36 tests pass

### Changed
- `dedup.Match` enum EXACT/FUZZY/NONE → EXACT/CONFLICT/NONE; `conflict` now means several Zotero items carry the same identifier (surfaced for human adjudication, never auto-merged — NG3)
- `planning.generate_plan(resources, config_version, zotero, state)` — existence check now drives each action via the Local API
- `cli.py` — `resolve`/`plan`/`apply`/`locate` pass the Zotero reader and map `DependencyError` → exit 3; `locate` is exact-only (fuzzy recall → `catalog`); output field `candidates` → `conflicts`
- GOALS.md — INV1 reworded (unique item; collections are many-to-one projections); added INV12 (existence authority + fail-closed), INV13 (cache is a derived read-only mirror), INV14 (semantic recall by host LLM reading the catalog, no embeddings/index)
- `evals/safety.json` — added `no-existence-on-unreachable` (exit 3)
- References (identity-policy, storage-policy) + find-resource/ingest-resource SKILL + resource-location — realigned to the read-authority + sync/catalog + exact-vs-fuzzy model

### Removed
- `state.py` — `find_candidates` (the CLI fuzzy prefilter); semantic recall is now the host LLM reading the catalog

## [0.1.18] — 2026-07-20

Roll back the Zotero write path. Zotero (and its PDF storage) is now the read-only
authoritative library: metadata and existence come from the Zotero Local API, and
approved papers download into `paper_inbox` for manual Zotero import. This is a
goal-level change (see GOALS.md G3/G4/G9, INV1/INV9/INV10/INV11, NG5).

### Removed
- `adapters/zotero_bridge.py` and `integrations/zotero-bridge/` — the self-hosted Bridge write backend
- `adapters/__init__.py` — `ZoteroWriteAdapter` / `ZoteroWriteResult` / `get_write_adapter`
- `adapters/arxiv.py` — `parse_arxiv_atom` / `fetch_metadata` / `check_pdf_available` (metadata now comes from the Zotero Local API, not arXiv parsing)
- `resolver.py` — `enrich_arxiv` (arXiv metadata enrichment)
- `contracts/zotero-import.schema.json`; `skills/ingest-resource/references/{bridge-contract,zotero-fields}.md`
- `config.py` — write-path settings: `zotero.bridge_url` / `write_backend` / `allow_direct_sqlite_write`, `policy.require_approval_for_write` / `allow_direct_zotero_sqlite_write`

### Changed
- `workflows/paper.py` — `run_paper_import` now downloads approved PDFs into `paper_inbox` (injectable `download`); no Zotero write. Non-arXiv inputs report `no_pdf`
- `config.py` — added `paper_inbox` (default `~/documents/0-inbox/paper-inbox`)
- `doctor.py` — probes Zotero Local API reachability + `paper_inbox` instead of the Bridge health check
- `cli.py` — `apply` downloads to the inbox; `doctor` reports Local API status
- GOALS.md / AGENT.md / README(.zh-CN) / shared references (security, storage, identity) / ingest-resource SKILL + READMEs — realigned to the read-authority + manual-import model
- `evals/safety.json` `no-bridge-bypass` → `no-zotero-write`; `evals/outcomes.json` `zotero-upsert-not-duplicate` → `dedup-exact-collapse`, `bridge-fail-closed` → `download-to-inbox`
- Tests: rewrote `tests/integration/test_paper_import.py` (fake downloader → inbox) and `tests/unit/test_doctor.py` (injected Local API probe); dropped `test_arxiv_parse.py` and the `enrich_arxiv` cases. 25 tests pass

## [0.1.17] — 2026-07-20

### Added
- `adapters/arxiv.py` — `parse_arxiv_atom(xml_text)`: pure stdlib `xml.etree` parser for arXiv Atom feeds (title/authors/year/doi), returns {} for an unknown id. Shared base for discover + apply. 3 unit tests
- `resolver.py` — `enrich_arxiv(resource, fetch=None)`: fills title/authors/year/doi from arXiv metadata (network), kept separate from offline `resolve_one` so resolution stays unit-testable; `fetch` injectable. 3 unit tests

### Changed
- `adapters/arxiv.py` — `fetch_metadata` now parses the feed instead of returning raw XML; dropped the feedparser placeholder (stdlib only). 29 tests pass total

## [0.1.16] — 2026-07-20

### Added
- `cli.py` — wired `report [job_id] [--format json|md|csv] [--active] [--handoff]`: job lookup or active-job list; `--handoff` emits an AgentHandoff snapshot (used by the PreCompact hook). No-target invocation exits 2
- `tests/contract/test_handoff_report.py` — first contract test: validates `report --handoff` output against `contracts/handoff.schema.json` via jsonschema (now the declared dependency is exercised). 23 tests pass total

## [0.1.15] — 2026-07-20

### Added
- `doctor.py` — `run_doctor(config, bridge=None)`: probes config paths + Zotero Bridge health (bridge injectable for tests). Read-only
- `cli.py` — wired `doctor [--json]` (was a stub the SessionStart hook called): prints per-check status, exits 3 when any dependency is down (AGENT.md exit-code contract)
- `tests/unit/test_doctor.py` — 3 tests (all-green / bridge-down / missing-path); 20 tests pass total

## [0.1.14] — 2026-07-20

### Changed
- `ingest-resource` SKILL.md + README(.zh-CN) — align the two-phase flow with the wired CLI: `plan <inputs...>` → present + in-conversation approval → `apply <inputs...>`. Removed the stale `action-plan.json` / `plan_id` round-trip semantics (plans are not persisted; approval is a dialogue act)
- `find-resource` SKILL.md — steps now point at the real commands (`locate` implemented, `resolve`); fuzzy locate surfaces candidates only (never a decision); discovery web query marked as authorization-gated

## [0.1.13] — 2026-07-20

### Added
- `cli.py` — wired `apply <inputs...>` (resolve + dedup + Zotero write in one shot; approval is a conversation act, so the command takes no approval flag and is called only after the user approves in-conversation) and `resume <job_id>` (read-only: report a job's persisted state)

## [0.1.12] — 2026-07-20

### Fixed
- `workflows/paper.py` — `run_paper_import` referenced `pdf_path` on the no-arXiv branch where it was never defined (NameError); now initialized to None and the Zotero payload carries a null attachment when there is no PDF

### Changed
- `workflows/paper.py` — `run_paper_import` accepts an injectable `adapter` (defaults to `get_write_adapter`) for testability; `conflict` operations are now skipped alongside `skip` (NG3: never write a fuzzy/conflict hit)

### Added
- `tests/integration/test_paper_import.py` — 2 tests with a fake bridge: no-arXiv path completes without NameError; skip/conflict actions never reach the adapter. 17 tests pass total

## [0.1.11] — 2026-07-20

### Added
- `dedup.py` — `decide_operation(result) -> (operation, conflicts)`: NONE→create, EXACT→skip, FUZZY→conflict (NG3: a fuzzy hit is surfaced for human adjudication, never auto-merged). 3 unit tests
- `cli.py` — wired `resolve` (normalize one identifier + report existence, read-only) and `plan` (dry-run action plan over N inputs, never writes); both use exit code 2 on bad input

### Changed
- `planning.generate_plan` — optional `state` arg; when given, the deterministic existence check drives each action's operation (create/skip/conflict) instead of the item_key heuristic

## [0.1.10] — 2026-07-20

### Fixed
- `cli.py` — `locate` on empty input exited 1 (click default); now raises `InputError` (exit code 2) per the AGENT.md CLI exit-code contract. Found during end-to-end verification of 0.1.9

## [0.1.9] — 2026-07-20

### Added
- `state.py` — `resources` identity cache table + `upsert_resource` (exact write), `find_exact` (DOI/arXiv/resource_id lookup), `find_candidates` (cheap fuzzy prefilter). Local authoritative exact-match cache AND fast recall surface — does not touch the state machine (handoff.schema.json unchanged)
- `dedup.py` — `check_existence(resource, state) -> ExistenceResult` with EXACT / FUZZY / NONE. Exact match is deterministic and guards INV1; fuzzy only returns a candidate shortlist (no decision), leaving judgment to the LLM upstream (NG3 keeps write-path fuzzy hits as conflicts)
- `cli.py` — wired `locate` (was a stub): read-only existence check, emits `{match, resource_id, zotero_item_key, candidates}` JSON for find-resource fast recall
- `tests/unit/test_dedup.py` — 5 tests (none / exact-by-arxiv / exact-by-doi / fuzzy-candidates / INV1 version collapse); 12 unit tests pass total

## [0.1.8] — 2026-07-19

### Added
- `resolver.py` — offline input resolution: classify + normalize raw inputs (arXiv id/URL, DOI, URL, title, CSV) into `Resource` objects; batch dedup by identity
- `tests/unit/test_resolver.py` — 7 unit tests covering classification, arXiv version dedup, DOI identity, batch collapse, CSV (first real tests in the repo)
- `tests/` package skeleton (unit / contract)

## [0.1.7] — 2026-07-19

### Fixed
- `pyproject.toml` build-backend was an invalid name (`setuptools.backends.legacy:build`) → `setuptools.build_meta`; editable install now works
- Bump `pydantic` 2.11.7 → 2.13.4 and `pyyaml` 6.0.2 → 6.0.3 for prebuilt Python 3.14 wheels (dev machine only has 3.14; older pins had no cp314 wheels)

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
