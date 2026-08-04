# Changelog

All notable changes to scholar-workflow are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) — Semver: major.minor.patch

## [0.16.0] — 2026-08-03

### Fixed
- **Zotero read boundary contradicted itself across authority docs (P1-5, third codex
  pass).** AGENT.md and `security-policy.md` both said Zotero read+write go *only* through
  zotero-mcp, but `export-annotations` requires `bin/zotero-annotations.py` to read the
  local DB directly read-only (`mode=ro&immutable=1`) — a runtime skill forced to do what
  the top rule forbade. Carved out an explicit read-only annotation-export exception in
  both docs (all metadata/identity/writes still zotero-mcp only; the extractor never
  decides metadata and never writes), added a permission-table row, and fixed
  `guard-sqlite.sh`'s message (it named the deleted `ZoteroWriteAdapter`; now points to
  zotero-mcp and notes the extractor's read-only path never hits the guard).
- **Safety eval faked CLI exit codes on host-layer cases (P1-3, third codex pass).** Six
  of ten `safety.json` cases carried a CLI `exit_code` for actions the CLI can't reach
  (destructive Zotero, existence checks — all skill-layer via MCP), guarding paths that
  don't exist; `no-path-traversal` even claimed exit 7 while `VaultPathError` is an
  uncaught `ValueError` (bubbles as exit 1). Added an `enforcement_layer` field
  (`hook` / `cli` / `host_llm`) to every case, dropped exit codes from all non-CLI cases,
  and made `test_evals_schema.py` reject an `exit_code` on any non-`cli` case so the bug
  can't recur. Renamed routing's `plan-import` → `additive-import`, dropping its retired
  approval-gate semantics (`expected_phase: plan` / `must_not_write`) — an explicit "加入
  Zotero" is an additive write that executes directly after existence-check + collection
  input (G4/G9). Documented the three-layer model in `dev-guide/eval-loop.md`.
- **Release build could leak untracked dev files into the runtime-only branch (P1,
  third codex pass).** `make-release.sh` clean-check only inspected tracked diffs
  (`git diff` / `--cached`), so untracked files — which `git checkout` carries across
  branches — slipped through, and the unbounded `git add -A` then swept them into the
  release commit (any stray review note or scratch file would ship). Now the guard uses
  `git status --porcelain --untracked-files=all` to reject *any* non-ignored dirt before
  building, and staging is scoped to `git add -A -- "${RUNTIME_PATHS[@]}"` so only the
  runtime manifest can ever be committed.
- **Two comment drifts introduced by the earlier hygiene sweep (third codex pass).**
  (1) `adapters/__init__.py` had been rewritten to call the adapters "network-free /
  filesystem work" — false, since arXiv PDF fetch and Notion projections both reach the
  network; corrected to state the actual split (arXiv fetch + Notion are network; Obsidian
  blocks + local link service are filesystem-only; Zotero is never touched here).
  (2) The sweep missed retired "manual import" language in `workflows/paper.py` (module
  docstring + the no-PDF `reason` string) and `models.py` (`DOWNLOADED` comment); all now
  describe the current model (CLI downloads to inbox; host LLM imports via zotero-mcp).
- **Hygiene sweep from the self-review (`claude-review.md`).** Three low-risk drifts the
  second codex pass missed or under-specified: (1) **version was three-tracked** —
  `plugin.json` at `0.16.0` but `pyproject.toml` / `__init__.py` still `0.1.0`, and
  `click.version_option()` (no arg) read the stale installed dist metadata, so
  `--version` reported `0.1.0`. Synced both Python versions to `0.16.0` and bound
  `version_option(version=__version__)` so the CLI reports the source constant, not
  install-time metadata. (2) **`exit_code: 4` lingered in `evals/safety.json`** for
  `no-unapproved-destructive-zotero`, but AGENT.md retired code 4 ("保留不复用"); changed
  it to `7` (safety-refusal, matching sibling host-layer cases) and dropped `4` from the
  `_EXIT_CODES` enum in `test_evals_schema.py` so the retirement is now test-guarded.
  (3) **Stale retired-architecture comments** in `adapters/__init__.py`, `adapters/arxiv.py`,
  and `resolver.py` still cited a nonexistent `adapters/zotero_local.py` "Zotero Local API"
  and "manual import"; rewritten to the current zotero-mcp model (metadata/existence via
  zotero-mcp at the skill layer; CLI downloads to inbox, host LLM imports).
- **7 skill frontmatters failed YAML parse (P0 release blocker).** `find-resource`,
  `ingest-resource`, `sync-projections`, `build-literature-tree`, `check-consistency`,
  `export-annotations`, and `env-setup` wrote `Triggers: '…'` in the `description` — the
  `: ` made YAML read it as a mapping key inside a plain scalar and drop all frontmatter
  at load time (silently killing auto-trigger). Changed to `Triggers '…'` (colon-free),
  matching the three skills that already parsed. `claude plugin validate` now passes with
  zero skill errors.
- **Vault-path traversal was unguarded (P0 security).** Payload fields that name vault
  files (`root` / `filename` / `index` / `vault_rel`) come from stdin — an untrusted
  boundary — but `ObsidianAdapter._resolve` and `archive_document` joined them onto the
  vault root with no check, so `../…`, an absolute path, or a symlink could write outside
  the vault. Added `safe_vault_path()` + `VaultPathError` in `adapters/obsidian.py`
  (rejects absolute paths and anything that `os.path.realpath`-resolves outside the root,
  covering `..` traversal *and* symlink escape) and routed both write chokepoints through
  it. Backs the `no-path-traversal` safety eval with real enforcement + 6 contract tests.

### Changed
- **Agent layer restructured from mechanical-verb split to task-level self-sufficient
  units, and registered as real subagents.** The five `agents/*.md` had no YAML
  frontmatter, so Claude Code never registered them as delegable subagents — they were
  shadow docs. Worse, they were split by mechanical action (discover / ingest / project /
  tree / audit), but real tasks span several actions, so each agent was a fragment that
  couldn't carry a task on its own (e.g. lineage bolted on a "read-only" find-resource
  because building a tree from a bare topic *needs* search). Re-cut agents around whole
  user tasks, each owning every skill that task needs, skills reused across agents freely:
  - **intake** (find + ingest) — targeted acquisition; absorbs the former **library**
    (deleted) since ingest is rarely a task on its own.
  - **lineage** (find + ingest + build-literature-tree) — was "build a tree" only; widened
    to direction-level survey: discovery and ingest are part of building the tree.
  - **feed** (recommend-papers) — new; the daily push feed, split out of intake.
  - **knowledge** (analyze + export + sync-projections) — unchanged scope.
  - **audit** (check-consistency) — unchanged scope.
  All five now carry `name` + `description` frontmatter. Agents do **not** hand off to each
  other; cross-agent chaining is orchestrated by the host LLM or by `survey-topic` (which
  is a top-level orchestration skill, owned by no agent). `survey-topic` and
  `recommend-papers` removed from intake's skill list accordingly.
- **`handoff.schema.json` renamed in-place: `AgentHandoff` → `PreCompactSnapshot`.** It was
  never agent-to-agent state — `from_agent`/`to_agent` are hardcoded to `"precompact"` and
  its only producer is the PreCompact hook (`report --active --handoff`). Title/description
  corrected to say so; the dead fields are left (harmless) and the contract test is
  untouched.
- **Post-restructure drift swept (second codex-review pass).** The agent re-cut left
  stragglers that contradicted the new "agents don't hand off" rule (a true reflection of
  Claude Code's architecture: subagents run isolated and return to the main thread; there
  is no lateral agent-to-agent channel). Fixed: all five agents' `## Handoff` sections
  became `## Boundary` (each states where the agent ends and that the host LLM orchestrates
  what runs next); dropped `library-agent` references still in `knowledge-agent` and
  `sync-projections`; `knowledge-agent` no longer claims it "writes only inside managed
  blocks" (analyze/annotation notes are human-area content — the real rule is *don't
  overwrite* human content, INV4); `cli.py` help/docstring `AgentHandoff` → `PreCompactSnapshot`
  to finish the rename; refreshed the stale `planning/HANDOFF.md` header (v0.15.1 →
  v0.16.0, dropped the "audit is a stub" todo). `identity.py` arXiv-first ordering was
  reviewed and **kept as correct** — `resource_id` is an offline naming key; library dedup
  is a separate DOI-first check via zotero-mcp.

### Removed
- **Dead `audit` CLI path.** `workflows/audit.py` (both functions returned `[]` / were
  never called) and the `cli.py audit` command (`raise NotImplementedError`) deleted. The
  CLI can't reach zotero-mcp, so cross-system audit lives in the check-consistency skill
  (host LLM), never in the CLI — the stub only misled (it fooled a review into calling the
  skill "unimplemented").
- **Personal-name attribution scrubbed from all shipped runtime files.** The literature-tree
  method's origin ("彭思达 / GAMES003") was copied verbatim into `agents/lineage-agent.md`,
  `build-literature-tree` SKILL/README(.zh-CN), `survey-topic` SKILL (×3),
  `literature-tree.schema.json`, and `novelty_tree.py` — a private reference with no
  routing value that ships to users. Removed the attribution; the method itself is
  unchanged. Provenance stays in the dev layer (CHANGELOG / planning), which does not ship.

## [0.15.1] — 2026-08-03

### Changed
- **survey-topic — cold-start breadth-recon sweep named as a pre-scope move.** Real use
  showed a gap: arriving cold, you often can't fix depth/breadth blind, so a quick
  web-inclusive sweep (including non-arXiv sources — models with no paper, benchmark or
  project pages, lab blogs) is what surfaces the landscape's shape *before* the grill can
  scope against it. The Depth→skill map was left untouched (every row routes to a
  downstream skill; the sweep routes nowhere — it is an inline scoping read), and the
  parallel/fan-out *mechanics* were deliberately **not** encoded (intrinsic ability, per
  AGENT.md design philosophy). Three prose edits only: the identity line no longer claims
  "runs no retrieval" (it now delegates acquisition but may do one throwaway read for
  itself), a **Cold-start orientation** note in the Grill section, and an
  **Orientation reads; acquisition is delegated** constraint that defers the
  what/where/from-which-source of acquisition to `source-policy` + `ingest-resource`
  rather than restating arXiv-only (AGENT.md: never duplicate a top-level policy across
  layers). Sweep persists nothing — throwaway like recommend-papers' Reading Report
  (INV23). README/README.zh-CN updated; no new INV (optimization scaffold, not a business
  rule); routing.json unchanged (breadth-recon is an internal mode, not a new route
  target).

## [0.15.0] — 2026-08-03

### Changed
- **Literature-tree rendering form, reshaped from real-vault practice** (Phase 3;
  INV22 rendering clause expanded). A topic's whole output now lives in one folder named
  for the topic (no `-literature-tree` wrapper). Index files carry a **library-code
  prefix**: `01-Paperlist.md` is the fixed flat全集 ledger, and each tree/view is a
  numbered self-contained note (`02-…文献树.md`, `03-…`; the skill assigns the number, the
  CLI only fixes the 01 slot). **One tree = one note** — an inline Mermaid overview then
  nested `##` task / `###` pipeline sections (each with its novelty anchor, an optional
  `内容简介`, and a `论文列表` subpaperlist) — with **no H1** (the filename is the title).
  Multiple trees may coexist; the ledger and each tree cross-link.
- **Shared table renderer (`projection.py`) — DOI column dropped, Importance star-badged.**
  DOI is retained only as a dedup identity field (INV1), never a rendered column;
  Importance is three-tier text (`founding`/`milestone`/`representative`) to which the
  renderer appends a `★★★/★★/★` badge. Because the renderer is shared, the **sync-projections
  Zotero-mirror index also goes 10 → 9 columns** — this is intentional (both indexes stay
  column-aligned). An Assets column is opt-in (`assets=True`), so only the literature-tree
  paper list / subpaperlists show the paper-assets wikilink, not the Zotero mirror.
- **Paper-assets back-link hub.** Each paper gets a companion note at
  `paper_assets/<year>-<first-author>-<title>.md` inside the topic folder; one `#` heading
  per resource type, and always a `# 相关文献树` heading holding back-links to the
  pipeline section(s) where the paper sits (INV20 hub, literature-tree landing).
- **`novelty_tree.py` rewritten** from a multi-file hierarchy to single-file section
  rendering: `render_tree_note` (Mermaid + nested sections, no H1) + `render_paperlist`
  (flat ledger) + `plan/project_novelty_tree` + `plan/project_paperlist`.
  `ObsidianAdapter.ensure_managed_block` now accepts an empty heading (writes no H1 line).
- **`project-literature-tree` CLI** takes `{root, filename, doc, paperlist_only?}`; `root`
  defaults to the doc's topic; `paperlist_only` writes the fixed `01-Paperlist.md` ledger,
  otherwise `filename` (required) names the tree note. `--dry-run` prints the plan.
- **`build-literature-tree` SKILL/README/README.zh-CN + `lineage-agent`** rewritten to the
  new layout (topic folder, library-code prefix, single self-contained note, paper_assets
  back-links). `sync-projections` SKILL + `obsidian-index-format.md` updated to the 9-column
  table (DOI removed, star-badged Importance).
- **`literature-tree.schema.json`** gains `summary` on concepts (prose intro, stored in
  JSON so re-render is idempotent) and `asset_note` on papers (path to the assets note);
  `doi` documented as retained-for-dedup, not-rendered.

## [0.14.0] — 2026-08-03

### Added
- **New skill `survey-topic`** (skill count 9 → 10) — the orchestration entry for an
  open-ended "research X" request. A broad ask ("调研世界模型") previously triggered no
  skill; all nine existing skills match specific mechanical verbs. `survey-topic` fills
  that gap: it **grills** the request — converging on scope *with the user* (propose,
  correct, confirm) across depth / breadth / time window — then proposes an ordered plan
  and **routes** each step to the skill that owns it (recommend-papers /
  find-resource / ingest-resource / build-literature-tree / analyze-paper). It is a
  conductor — it runs no research, writes no file, and produces no artifact of its own.
  A depth→skill map is the one external prescription it encodes; how to research is left
  to the model (intrinsic ability, not encoded — AGENT.md design philosophy).
  - `build-literature-tree` stays independent: "draw a tree" routes straight there;
    survey-topic is only one upstream caller and hands off scope, letting the tree run
    its own gates (INV22).
  - **Research-methodology absorption** (sjh-skills + 彭思达 GAMES003 / learning_research /
    Notion literature-tree). The grill's depth axis is reframed around a researcher's two
    legs of field-vision (technical-evolution → build-literature-tree; key-problem →
    recommend-papers) plus a stance dial (hypothesis-driven close read vs. cold-start wide
    mapping); a named seeding move is added — the **citation snowball** (mine a milestone
    paper's introduction + related-work for same-direction references, feed find-resource).
    All four are external prescriptions only; the intrinsic research abilities they came
    packaged with (causal-chain analysis, three-level paper reading, taxonomy tagging,
    NotebookLM orchestration) were deliberately *not* copied in — they already live in
    analyze-paper / build-literature-tree. No new INV (optimization scaffolding, guarded by
    routing evals); description unchanged (avoids duplication + the Ask-First trigger gate).
  - Wiring: `skills/survey-topic/{SKILL.md,README.md,README.zh-CN.md}`; added to
    intake-agent skills + AGENT.md plugin structure / Agent→Skill map; both root READMEs
    (skill table + usage example); two `evals/routing.json` cases (one positive open-ended
    survey, one negative proving an explicit "tree" verb bypasses it).

## [0.13.1] — 2026-08-03

### Added
- **`dev-guide/writing-great-skills/`** — vendored verbatim (byte-for-byte, SHA-256
  verified) from Matt Pocock's `mattpocock/skills` (MIT): `SKILL.md`, `GLOSSARY.md`,
  `agents/openai.yaml`, plus a `SOURCE.md` (provenance + no-in-place-edit policy) and
  `THIRD_PARTY_LICENSES` (full MIT text). It is a development-time authoring reference —
  `disable-model-invocation: true`, never shipped to `release`, never loaded at runtime.
  Now the single source of truth for general skill-writing craft (predictability,
  leading word, progressive disclosure, no-op / negation / duplication / sprawl).

### Changed
- **dev-guide aligned to writing-great-skills.** `skill-authoring.md` gains a
  "Principles — single source of truth" section pointing at the vendored reference and
  no longer restates description craft (kept only the repo-specific bilingual-trigger +
  two-tier-reference conventions); the "pack it" wording that contradicted the
  context-load principle is fixed. `skill-iteration.md` gains a "Diagnosing a skill"
  step that runs a change against the vendored failure modes.
- **Pruned two skill descriptions** (routing unaffected — every trigger phrase kept).
  `analyze-paper` and `recommend-papers` descriptions restated their own step
  mechanics (duplication + context load at the most expensive location); trimmed to
  identity + triggers + "Not X" disambiguation per the writing-great-skills rule.

## [0.13.0] — 2026-08-02

### Removed
- **BREAKING (config schema):** dropped the `papers_root` userConfig key. It was a
  pre-zotero-mcp relic — no live workflow read it; PDFs now flow `paper_inbox` →
  zotero-mcp `write_item(import)` → Zotero storage (`~/Zotero/storage`, served by the
  link-service via `link_service.storage_root`). Only `doctor.py` health-checked the
  path and a never-wired `audit_papers_root` stub referenced it. Removed the field +
  validator (`config.py`), the doctor check (`doctor.py`), the dead `audit_papers_root`
  stub (`workflows/audit.py`), the plugin.json userConfig entry, both READMEs' config
  examples, and the `papers_root` mentions in check-consistency / sync-projections docs
  + `models.py` FileInfo.root comment. Existing `config.yml` files should delete the key.
  GOALS: reworded INV2/INV3 to anchor on Zotero storage (`~/Zotero/storage`) +
  `link_service.storage_root` instead of `papers_root` (intent unchanged); evals
  `papers-root-remap` / `tech-doc-isolation` descriptions + routing assertion
  `must_not_enter_papers_root` → `must_not_enter_zotero_paper_flow` follow suit.

### Changed
- **BREAKING (config schema):** renamed the userConfig key `vault_root` →
  `research_vault_root`. The prefix disambiguates the plugin's research vault from any
  other Obsidian vault a user may keep, and its plugin.json description now clarifies the
  plugin only writes its own folders + managed blocks (the vault may hold unrelated
  content). Existing `config.yml` files must rename the key or the CLI will fail to load.
  Threaded through `config.py` (field + validator), `cli.py` (3 adapter builds),
  `doctor.py` (health check), `models.py` (FileInfo.root doc), plugin.json userConfig,
  both READMEs, `storage-policy.md`, and the export-annotations / ingest-resource /
  analyze-paper skill docs. Internal function params stay the generic `vault_root`.

## [0.12.0] — 2026-08-02

Phase 5 start: **two-tier AI paper reading** (feature-ai-reading). A skim tier for
recommendation upstream and a detailed-analysis tier for persistent vault notes. Design
philosophy: encode only external prescriptions (which source, where output lands, format,
network path, dependencies) — never the model's intrinsic abilities (reading, summarizing,
comparing, classifying).

### Added
- **`recommend-papers` skill** (@intake) — daily multi-source paper feed. Aggregates four
  sources (Semantic Scholar Recommendations seeded by the Zotero library, Scholar Inbox
  personalized digest, S2 author watchlist, HuggingFace Daily Papers), merges/dedups by
  arXiv id, and skims a user-picked shortlist via NotebookLM into an ephemeral Reading
  Report (INV23). SKILL.md + README + README.zh-CN + `references/recommend.example.yml`.
- **`analyze-paper` skill** (@knowledge) — in-depth analysis of one ingested paper via
  zotero-mcp `get_content`, written as a companion vault note outside managed blocks
  (INV4), distinct from and `related`-linked to the annotations note, hung on the paper's
  related-docs hub (INV20). Focused passes append sections (INV24). SKILL + both READMEs.
- `src/scholar_workflow/adapters/recommend_sources.py` — normalized-candidate adapters:
  `fetch_hf_daily`, `fetch_s2_recommendations` (Zotero seeds), `fetch_s2_author_papers`,
  `normalize_scholar_inbox`, `merge_candidates` (dedup by arxiv_id, records all sources).
  arXiv-only; per-source network paths (HF via proxy, S2 direct).
- `bin/recommend-papers.py` — mechanical aggregator, the sole outbound-network entry; the
  CLI stays network/MCP-free (INV18). Reads `recommend.yml` toggles, takes optional stdin
  `{seed_arxiv_ids}` (host LLM gathers via zotero-mcp), emits `{candidates, count, skipped}`.
- `config.py` — `RecommendConfig` + `load_recommend_config` (two-layer YAML: global
  `recommend.yml` + per-cwd project overlay; interests/watchlist additive).
- Vendored Scholar Inbox client `skills/recommend-papers/scripts/scholar_inbox/`
  (api/auth/config, stdlib-only) with attribution headers + `THIRD_PARTY_LICENSES`
  (MIT, Copyright (c) 2026 Jiahao Shao; upstream cli.py not vendored).
- `tests/unit/test_recommend_sources.py` (6) — HF/S2/Scholar-Inbox normalization + merge.
- GOALS: INV23 (skim ephemeral) + INV24 (detailed-analysis source/destination); Phase 5
  row; future items F3 (challenge-insight tree) + F4 (skim closed-loop / watchlist / doctor).
- `.claude-plugin/marketplace.json` — single-repo distribution manifest (marketplace
  `jerry-plugins`); plugin source is self-referential to the `release` branch
  (`github`, repo `JerryFan012321/scholar-workflow`, `ref: release`). Users install via
  `/plugin marketplace add JerryFan012321/scholar-workflow@release`. The manifest is a
  build input on `main` and ships to `release` via `make-release.sh`.

### Changed
- `build-literature-tree` SKILL Step 2 gains a NotebookLM batch-read orchestration hint
  (reuse the skim engine for large paper sets; classification/first-proposer stay the
  model's; fall back to `get_content`).
- `export-annotations` SKILL: forward-reference `paper-analyzer` → `analyze-paper`.
- `intake-agent` gains `recommend-papers`; `knowledge-agent` gains `export-annotations` +
  `analyze-paper`, with matching Forbidden entries (ephemeral report, no PDF-body parse,
  no analysis/annotation merge).
- AGENT.md plugin structure 7 → 9 skills; Agent→Skill map updated; bin list gains
  `recommend-papers.py`.
- `plugin.json` description extended with recommendation + analysis capabilities.

## [0.11.0] — 2026-08-02

New **env-setup** skill: scaffold and maintain a personal env-records ledger for API
keys and SSH servers, kept entirely outside the plugin repo. The plugin owns no private
data — it reads one location from config (`env_records_root`) and lays down a uniform
skeleton where templates are committed and real records stay gitignored and local.

### Added
- `env-setup` skill (SKILL.md + README.md + README.zh-CN.md) — user-invoked, no agent.
  Scaffolds the env-records directory; register API keys / record servers into gitignored
  real files. Servers carry a per-host environment inventory (conda envs, python/cuda,
  key_packages, compat_notes, host cuda_driver, structured proxy) with large rebuild
  recipes externalized to `setup/<alias>/<env>.sh`; adding a server is record-on-consent.
- `src/scholar_workflow/workflows/env_setup.py` — `scaffold(root)`, idempotent: lays down
  `.gitignore` / `README.md` / `*.example.yaml` templates / seeded real records / `setup/`
  tree, and never overwrites an existing file (real records survive re-runs).
- `env-init` CLI command — scaffolds under config `env_records_root` and runs a local
  `git init` (never pushes).
- `config.py` gains `env_records_root` (default `~/dev/env-records`).
- `tests/unit/test_env_setup.py` (5) — skeleton, gitignore split, template YAML shape,
  idempotent no-overwrite, setup/ dir.

### Changed
- AGENT.md plugin structure 6 → 7 skills; Agent→Skill map gains an "(no agent, user-invoked)"
  row for env-setup.
- `plugin.json` description extended with the env-records ledger capability.

## [0.10.0] — 2026-08-01

Phase 3 start: replace the citation-graph literature model with a **novelty tree** per
彭思达's GAMES003 literature-tree method. The tree is a 3-level classification
(milestone task → pipeline/representation → paper leaf) whose internal nodes are abstract
concepts, each recording its novelty anchor (the first paper that proposed it), plus a flat
paper list. The old citation-graph was Phase-0 scaffolding — an unimported stub, no GOALS
invariant, no eval pin — so this is a clean reshape, not a migration.

### Added
- `contracts/literature-tree.schema.json` — novelty-tree contract: `paper_list` (flat 全集
  ledger with a `classified` flag) + a recursive `concept` tree (`kind` ∈ topic/task/pipeline,
  `novelty_anchor`, optional `anchor_note`, paper-id leaves) + a reserved `challenge_insight_tree`
  seam for the deferred companion tree.
- `src/scholar_workflow/workflows/novelty_tree.py` — `render_mermaid` (inline flowchart of
  task→pipeline→paper, ⭐-marked anchor nodes), `plan_novelty_tree` (pure planner), and
  `project_novelty_tree` (apply via ObsidianAdapter). Reuses `projection.render_table` and the
  managed-block machinery; the topic root note carries the Mermaid overview + the flat paper list.
- `project-literature-tree` CLI command mirroring `project-tree` (stdin `{root, doc}` → adapter
  → stats, with `--dry-run`).
- Tests: `tests/contract/test_literature_tree_schema.py` (8) + `tests/unit/test_novelty_tree.py` (9).
- GOALS **INV22** pinning the novelty-tree topology + paper-list-alongside requirement, guarded
  by `evals/outcomes.json` `novelty-tree-topology-and-paperlist`.
- `build-literature-tree` SKILL gains a **Grill** section — a scope-locking dialogue run before
  Step 1 that fixes four gates coarse-to-fine (purpose / boundary / resolution / time window),
  plus the anchor-ownership rule (anchor belongs to the highest layer that can explain it) and
  the polysemy rule (pick the cut-axis before cutting a boundary). Only the external dials are
  encoded; the task-vs-pipeline judgment stays an intrinsic ability per AGENT.md 上位准则.

### Changed
- `build-literature-tree` SKILL.md, README.md, README.zh-CN.md and `agents/lineage-agent.md`
  rewritten from the citation-graph/edge-evidence model to the novelty tree. The new SKILL is
  leaner: only external rules (topology, novelty anchor, paper-list, render target, arXiv-only
  metadata) — classifying papers and picking the first-proposer are intrinsic abilities, left
  unconstrained per AGENT.md 上位准则.
- GOALS Phase 3 status ⏳未开始 → 🚧进行中; NG7 clarified (the novelty anchor is a verifiable
  "which paper came first" fact, distinct from the anti-hype "no breakthrough badge" rule).
- `plugin.json` description "literature lineage trees" → "literature novelty trees".

### Removed
- Citation-graph edge model: the `edges` array, the 6-value `relation` enum
  (cites/follow-up/method-extension/representation-shift/benchmark-successor/contradicts),
  and per-edge `evidence` / `confidence` / `review_status`.
- `skills/build-literature-tree/references/edge-evidence.md` (deleted, not replaced — it taught
  intrinsic classification abilities).
- `src/scholar_workflow/workflows/lineage.py` — the dead Phase-5 `build_graph` stub (unimported).
- `contracts/literature-graph.schema.json` (renamed to `literature-tree.schema.json`).

## [0.9.0] — 2026-08-01

Subtraction batch: retire the dead approval chain left over from the pre-zotero-mcp
pipeline, and cement the constraint-design philosophy that governs it.

### Changed
- AGENT.md gains a top-level **设计哲学(上位准则)** section governing all downstream rules
  (skill / reference / INV / NG). A three-layer filter for any constraint: (1) *intrinsic
  ability* the model already has (similarity judgement, summarizing, classification,
  assembling JSON) — never write it; (2) *optimization scaffolding* that helps the agent
  execute efficiently (orchestration hints, token/discovery tuning, process gates) — write
  if useful but **ablate periodically, since it depreciates as models improve**; (3)
  *business constraint* the user sets on outputs (format, feature requirements, dedup key,
  storage, arXiv-only, safety) — write and **maintain stably, never depreciates**. The
  "simplify / subtract" trend applies only to layer 2. Self-check: "is this the user's
  requirement on the result (business), or my guidance on the agent's process (optimization)?"

### Removed
- **Approval chain (dead scaffolding).** Post zotero-mcp pivot the CLI generates,
  "approves", and consumes a plan inside a single `apply()` call — nothing external
  ever tampers with or ages the plan, so the tamper/expiry checks guarded a threat
  model that no longer exists. Real destructive-op approval lives in the skill layer
  (host LLM via zotero-mcp), one action at a time.
  - Deleted `src/scholar_workflow/approvals.py` (`approve_plan` + `assert_executable`).
  - `ActionPlan` slimmed: dropped `expires_at`, `input_digest`, `config_version`,
    `approved_at`, and the `is_approved()` / `is_expired()` methods. It is now just
    `plan_id` + `created_at` + `actions`.
  - `planning.generate_plan` dropped the `config_version` param and `validate_plan` /
    `_input_digest` / `PLAN_TTL_HOURS`; `paper.run_paper_import` no longer calls
    `assert_executable`; `cli.apply` no longer wraps the plan in `approve_plan`.
  - `TaskState` reduced 20 → 4 (`approved` / `downloaded` / `no_arxiv_pdf` /
    `download_failed`) — the pipeline/dedup/sync/conflict states were never written
    after the pivot.
  - `jobs.input_digest` column dropped from the state DDL; `active_jobs` no longer
    filters on terminal states that were never written (behavior-preserving).
- **Exit code 4 (needs-approval) retired from the CLI contract.** No CLI path emitted
  it after the pivot; approval is a skill-layer concern. Code 4 is reserved, not reused.

## [0.8.2] — 2026-08-01

Phase 2 wrap-up: lock the Notion two-DB orchestration behind an executable test, guard
INV19/INV21 in evals, and retire the `discover` CLI stub to the skill layer. No new
feature — test/quality hardening plus one small behavior change.

### Added
- `tests/unit/test_notion_project.py` — orchestration-layer test for `bin/notion-project.py`
  (the sole Notion API caller): papers upserted before related docs, `Paper` relation wired
  from the captured page_id map, exit 3 on missing token, empty-payload no-op, exit 2 on a
  doc referencing an unknown paper. Imports the hyphenated script by path with a fake
  adapter/config (no network). 71 → 76 tests.
- `evals/outcomes.json` `notion-two-db-relation-order` (status `pass`) — guards INV21,
  pointing at the test above.
- `evals/safety.json` `no-notion-writeback` + `no-notion-full-body` — guard INV19
  (one-way local→Notion; summary + backlink only, no full body).

### Changed
- CLI `discover` retired to a signpost: it no longer raises `NotImplementedError` but exits
  2 with a message pointing to the `find-resource` skill. Discovery needs zotero-mcp
  (existence, semantic recall) + web metadata, which the CLI subprocess cannot reach; the
  host LLM owns it via the skill. Routing eval already sent discovery queries there.
- GOALS `INV19` guard `（待补，Notion ticket）` → `safety: no-notion-writeback / no-notion-full-body`;
  `INV21` guard → `outcomes: notion-two-db-relation-order`.

### Removed
- Redundancy sweep. Dead contract schemas with zero live references: `contracts/`
  `notion-projection.schema.json` (single-DB era, contradicts the live two-DB model now
  authoritative in `references/notion-schema.md` + contract tests), `action-plan.schema.json`
  (the pre-zotero-mcp plan/expire/digest mechanism, retired), `resource.schema.json`,
  `index-entry.schema.json`. Kept `handoff.schema.json` (jsonschema-validated in tests) and
  `literature-graph.schema.json` (Phase 3 output contract).
- Stale dev log `log/2026-07-20.md` (documented `dedup.py` / `resources` table / `locate` —
  all removed in the zotero-mcp pivot) and the empty `integrations/` directory.

## [0.8.1] — 2026-07-30

Notion two-DB projection model, wired live against a real workspace. Related-materials
documents now project as their own Notion rows, relation-linked to papers, carrying a
summary + backlink instead of full note bodies. Validated end-to-end with the text2cad
topic (8 papers): built the Related Docs DB, upserted the papers + related-materials hub,
and assembled a callout-card topic page with per-paper links (Papers row · local PDF ·
arXiv). Part of Phase 2 (projection sync), not a standalone release.

### Added
- `bin/notion-project.py` — the mechanical two-DB upsert, and the *only* component that
  calls the Notion API (the CLI still makes no outbound network calls). Reads
  `{papers, related_docs}` JSON on stdin, upserts papers then related docs (auto-wiring the
  `Paper` relation from `paper_resource_id`), prints resource_id/doc_id → page_id. Token via
  `SCHOLAR_WORKFLOW_NOTION_TOKEN` only. Topic-page assembly stays in SKILL.md (host LLM).
- `Related Docs` DB in the Notion schema — one row per companion document (reading /
  direction / supplementary), keyed by `Doc ID` (vault-relative path), `Paper` relation
  back to the Papers DB row. Orchestration: upsert paper → capture page_id → upsert docs
  with relation.
- `NotionConfig.related_docs_database_id` / `related_docs_data_source_id`.
- Two contract tests (`test_related_doc_upserts_by_doc_id_and_links_paper_relation`,
  `test_papers_db_still_defaults_to_resource_id_key`) — 3 → 5.
- GOALS `INV21` (Notion two-DB model) + `INV20` (related-materials hub, tracer-verified).

### Changed
- `NotionAdapter.upsert_page` gained a `key_property` param (default `Resource ID`, so
  Papers-DB behavior is unchanged) so the Related Docs DB can key on `Doc ID`.
- GOALS `INV19` rewritten: related docs project a one-paragraph summary + Vault backlink;
  full note bodies stay in Obsidian and are never sent to Notion (was: full body rendered
  as native Notion page blocks).
- GOALS `INV17` revised: Notion now carries **both** a `Web Source` (arXiv/DOI, reachable
  cross-device) **and** a `Local URL` (loopback link-service, opens the annotated PDF
  instantly on the host Mac) — was "Notion never uses loopback URLs". URL still stores only
  the opaque attachment key, never an absolute path.
- `references/notion-schema.md` single-DB → two-DB; `sync-projections/SKILL.md` Notion
  steps aligned to the paper-then-doc upsert order.
- Version-bump rule relaxed (AGENT.md): bump per coherent capability batch, not per commit
  — avoids the 0.6→0.7→0.8 same-day triple-jump.

## [0.8.0] — 2026-07-26

Link service auto-start (macOS launchd). The loopback PDF service now survives login and
process death, so Obsidian/Notion PDF links stop breaking between sessions.

### Added
- `scholar-workflow install-service` — writes a per-user LaunchAgent
  (`com.scholar-workflow.link-service`) with RunAtLoad + KeepAlive pointing at
  `serve-links`, then loads it. Idempotent (unload+replace). macOS only.
- `workflows/service.py` — pure `render_plist()` (XML-escaped, optional
  SCHOLAR_WORKFLOW_HOME env injection) + `tests/unit/test_service.py` (3)

### Notes
- The service must run from a venv **outside** `~/Documents`: macOS TCC denies launchd
  read access to Documents, crashing a venv there on `pyvenv.cfg` (`PermissionError`).
  Install target is a self-contained venv at `~/.local/share/scholar-workflow/venv`
  (non-editable install), so the running service never touches Documents. Code changes
  require reinstalling that venv to take effect.

## [0.7.0] — 2026-07-26

T4 polish + first real-vault projection. `project-tree` gained a dry-run gate, hub notes
moved to nested `index.md` (fixes the same-named folder/note collision in Obsidian's file
tree), leaf headings gained a `相关论文` suffix. Rendered the real `科研项目 → 上汽标注 →
text2cad` branch (8 papers, importance column) into the vault's `paper/` tree.

### Added
- `project-tree --dry-run` — prints every planned file (path/heading/body) as JSON and
  writes nothing; re-run without the flag to apply. Backed by a pure `plan_tree()`
  (no filesystem) that `project_tree()` also consumes, so preview == apply (zero drift)
- `tests/unit/test_hierarchy.py` — dry-run purity + heading-suffix assertions

### Changed
- `hierarchy.py` — hub node (has children) renders to `<parent>/<name>/index.md`, leaf to
  `<parent>/<name>.md`; MOC links resolve hub children to their `index`. Leaf heading =
  `<name>相关论文`, hub heading = bare name. (Heading is written only on file creation;
  re-runs rewrite the managed block, not the `# heading`.)
- `sync-projections` SKILL + `obsidian-index-format.md` — document both projection shapes,
  the dry-run gate, the serve-links dependency for PDF links, and the nested-index layout
- `HANDOFF.md` — status refreshed to Phase 2 / v0.6.0+; added an "immediate TODO" list

## [0.6.0] — 2026-07-26

T4 core — hierarchical index (option C). Mirror the Zotero collection tree as a folder
of managed-block notes: each collection becomes one file, parent collections get a MOC
(map-of-content) wikilink list to their children, leaf collections get a paper table.
Adds an Importance column (Zotero `prio:★★★`). Rendered in tmp dirs + tests only — not
yet run against the real vault (awaiting dry-run preview). Note-URL (`/open/note/...`)
is a later ticket.

### Added
- `src/scholar_workflow/workflows/hierarchy.py` — `project_tree` walks a tree JSON
  `{root, tree:{name, collection_key, papers[], children[]}}` and renders one file per
  node at `<parent>/<name>.md`; a node's block = MOC wikilink section (children) +
  10-column paper table (direct papers). CLI owns all path computation (INV18); names
  sanitized so a stray collection name can't escape the mirror root
- CLI `project-tree` — read the tree JSON (stdin/`--input`), render the folder mirror
- `render_table` in `projection.py` — full table body (header + rows) for one block
- `tests/contract/test_obsidian.py` (6) — pins the generalized adapter contract
- `tests/unit/test_hierarchy.py` (3) — folder mirror, MOC-vs-table placement, idempotency

### Changed
- `adapters/obsidian.py` — generalized: `update_managed_block(path, body:str)` replaces
  the inter-marker region with a caller-supplied body (was: hardcoded 9-col header);
  `ensure_managed_block` creates an empty block. Lets one adapter serve both paper tables
  and non-table MOC blocks
- `projection.py` `format_row` — 10 columns; adds Importance between Venue and Zotero
- `skills/sync-projections/references/obsidian-index-format.md` — 10-column table +
  concrete folder-mirror/MOC structure (replaces the old 9-col + aspirational hierarchy)

## [0.5.0] — 2026-07-26

Phase 2 tracer-bullet: project ingested papers into an Obsidian managed-block index,
and open each paper's raw PDF one-click in the local browser via a loopback link
service. Planner (host LLM + zotero-mcp) and executor (CLI) stay split — they exchange
JSON only; the CLI never touches MCP (INV18). Hierarchical/Notion projections deferred
to a later round.

### Added
- `src/scholar_workflow/adapters/local_links.py` — loopback PDF link service:
  `GET /open/paper/<attachment-key>` globs `<storage_root>/<key>/*.pdf` and streams it
  inline (`application/pdf`). Binds `127.0.0.1` only; validates key against `[A-Z0-9]+`
  before touching the filesystem (blocks path traversal); 404 on no-PDF, 400 on bad key
- `src/scholar_workflow/workflows/projection.py` — pure `format_row` (deterministic;
  `Synced` from the input row, not `now()`, so re-projection is idempotent) +
  `project_obsidian` (ensure managed block → replace rows; content outside markers
  untouched, INV4)
- CLI `serve-links` — run the link service in the foreground (Ctrl-C to stop)
- CLI `project-obsidian` — read `{index, heading, entries}` JSON (stdin/`--input`) and
  render the managed-block table into the vault index
- `config.LinkServiceConfig` — `link_service.port` (23128) + `storage_root`
  (`~/Zotero/storage`)
- `tests/unit/test_local_links.py` (7) + `tests/unit/test_projection.py` (5)
- `planning/` — permanent planning layer; migrated `GOALS.md` + `HANDOFF.md`, added
  `planning/phase2-sync-projections.md` spec + DR-1 (loopback link-service decision)
- `GOALS.md` — INV17 (loopback link service, opaque attachment key) + INV18
  (planner/executor split, CLI never reaches MCP); Phase 2 marked in progress
- `evals/outcomes.json` — `obsidian-projection-idempotent` + `pdf-link-inline-local` cases

### Changed
- `skills/sync-projections/` — SKILL.md step 5 and both reference docs
  (`link-format.md`, `obsidian-index-format.md`) aligned to the shipped design:
  attachment-key link-service URL (not item key / relative path), `31-paper` path,
  `; `-joined authors, idempotent `Synced`
- `skills/check-consistency/references/consistency-invariants.md` — Obsidian audit now
  checks link-service URLs resolve, not relative paths
- `dev-guide/{skill-authoring,skill-iteration,eval-loop}.md` — reflect reality: pytest
  guards schema/contract, eval suites are review-judged; planning/ is a permanent layer
- `AGENT.md` — added planning-docs row; dev-guide and planning both permanent

## [0.4.3] — 2026-07-23

Provenance-preservation rule for export-annotations, learned from the first real run
(Text2CAD, 44 annotations). The user corrected three drifts in turn: I had paraphrased
and supplemented their comments, blurred my own additions into their words, and padded
with restatements of what a comment or highlight already said. Codifies the fix.

### Added
- `tests/unit/test_annotations.py` — unit tests for the annotation extractor: `clean()`
  translation stripping, `page()` fallback, `TYPE` map, and `annotations()` parent-filter
  + sortIndex ordering against an in-memory SQLite (no real Zotero DB)
- `tests/unit/test_evals_schema.py` — schema-validation for `evals/*.json` (valid JSON,
  unique ids, required fields, `expected_skill` points to a real skill, `exit_code` within
  the AGENT.md set). Guards structure only; LLM-behavior cases stay un-asserted

### Changed
- `skills/export-annotations/SKILL.md` — split provenance out of Step 5 into a new Step 6:
  three sources kept distinct — user comments reproduced **verbatim** (never paraphrase /
  condense / supplement / drop), highlights as plain quotes, Claude's additions only in an
  explicitly-labeled `补充（Claude）` callout. Additions are information-only (never evaluate
  the user's comments) and non-padding (add nothing if comment/highlight already says it)
- `skills/ingest-resource/SKILL.md` + `skills/find-resource/SKILL.md` — slimmed Constraints
  by removing cross-tier duplication (AGENT.md rule): rules that fully restated a top-level
  reference are now one-line pointers to their canonical policy. Ingest 12→7 constraints,
  find 7→4; no change to `description`, Steps, or References

## [0.4.2] — 2026-07-21

Approval-model wording tightened after a 26-paper batch ingest (CAD literature tree),
where the user repeatedly asked to stop per-item approval prompts. Clarifies that one
task-level request authorizes the whole batch, and records the real gate (the
`settings.local.json` allow-list) so future rounds don't re-litigate it in prose.

### Changed
- `AGENT.md` — new `### Approval & auto-run` subsection: a task-level request authorizes
  the whole batch of read-only + additive writes end to end (no per-item/mid-process
  prompt); read-only never gates; only destructive/out-of-scope stops; notes that the
  tool-permission popup is gated by `settings.local.json` `permissions.allow`, not by docs
- `references/security-policy.md` — Approval gate extended: a batch request authorizes the
  whole batch, never re-prompt per item within it
- `skills/ingest-resource/SKILL.md` — Constraints: N-paper batch = one authorization, no
  per-item re-prompt
- `AGENT.md` "Ask First" — replaced the stale "Zotero is read-only / import is manual" line
  (a zotero-mcp-pivot leftover) with "adding a destructive Zotero op to a skill/agent";
  additive zotero-mcp writes are the normal, ungated path

### Fixed
- `.claude/settings.local.json` — added unscoped `Read` to the allow-list (only `/tmp` and one
  Zotero storage subdir were pre-authorized before); MCP write tools were already allow-listed

## [0.4.1] — 2026-07-21

### Fixed
- Replaced deprecated `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`
  across `models.py`, `approvals.py`, `planning.py`, `state.py`, `cli.py`, and the paper-import
  test. Clears all 18 DeprecationWarnings under Python 3.14; the handoff snapshot keeps its
  `Z`-suffixed UTC timestamp via `.isoformat().replace("+00:00", "Z")`. No behavior change.

### Changed
- Fixed two stale docs from the zotero-mcp pivot: rewrote `HANDOFF.md` (was still describing
  the abandoned ZotMoov linked-file workflow as required and claiming changes were uncommitted;
  now reflects imported attachments via Zotero File Syncing + committed state), and reworded the
  `outcomes.json` download-to-inbox case that wrongly claimed the plugin does no programmatic
  Zotero writes (writes happen in the host LLM via zotero-mcp, just not in the CLI).

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
