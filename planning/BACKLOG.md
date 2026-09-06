# Project Backlog

Work items for scholar-workflow. Single source of truth for pending work, decisions, and blockers.

## Schema

- **ID**: `WI-NNN` (auto-increment from 001)
- **Status**: ready | pending-decision | blocked | in-progress | done | deferred
- **Priority**: p0 (urgent) | p1 (high) | p2 (medium) | p3 (low)
- **Type**: code-change | eval | decision | planning | documentation | refactor

## Active Items

### WI-003: Complete P1-3 eval closure
- **Status**: in-progress
- **Priority**: p1
- **Type**: eval
- **Context**: codex-review.md flagged P1-3: evals/routing.json was missing positive cases. 2026-08-29 added the 4 missing (analyze-paper, recommend-papers, sync-projections, env-setup) + 1 backlog-vs-review disambiguation → 22 cases; test_evals_schema green. REMAINING: the 13 "pending" outcomes in outcomes.json have NO guarding tests, so promoting them to "pass" would be unfounded — each "pass" outcome cites a real test file; the 13 pending do not. Promotion needs real end-to-end validation (WI-007 territory), not a status edit.
- **Blocker**: none (routing done; outcome promotion needs real runs)
- **Next action**: When battle-testing (WI-007) exercises a pending outcome end-to-end, add its guarding test and promote that outcome to pass. Do not bulk-promote without evidence.
- **Related**: P1-3 (codex-review.md), GOALS.md eval guard (G7), WI-007

### WI-005: Decide env-setup scope and static-password model
- **Status**: pending-decision
- **Priority**: p2
- **Type**: decision
- **Context**: codex-review.md P2-2 flagged env-setup skill for two issues: (1) scope creep — original intent was API-key/SSH-server ledger, but current implementation may be broader; (2) static-password model — storing credentials in config or files rather than referencing external vaults/keychains. User has not decided whether to narrow scope, adopt vault-reference model, or defer this entirely.
- **Blocker**: user-decision
- **Next action**: User reviews env-setup skill, decides whether to (a) keep as-is, (b) narrow to API-key ledger only, (c) adopt vault-reference model, or (d) defer to later phase.
- **Related**: P2-2 (codex-review.md), env-setup skill

### WI-006: Long-term polish — redundancy / thin agents / experimental labels
- **Status**: deferred
- **Priority**: p3
- **Type**: refactor
- **Context**: codex-review.md P2 tier flagged: redundancy in skill instructions (P2-1), feed-agent and audit-agent being "thin" (P2-3), no "experimental" labels on untested features (P2-5). These are quality-of-life improvements, not blockers. Deferred until core functionality stabilizes.
- **Blocker**: none (deferred by priority)
- **Next action**: Revisit after Phase 3 completes and battle-testing uncovers real pain points.
- **Related**: P2-1, P2-3, P2-5 (codex-review.md)

### WI-007: Battle-test unexercised implementations
- **Status**: ready
- **Priority**: p2
- **Type**: code-change
- **Context**: README Status & limitations documents three implementations marked "implemented but not yet run end-to-end": (1) build-literature-tree CLI render path, especially the fourth "module" level and the challenge-insight tree written to vault; (2) recommend-papers NotebookLM skim tier; (3) check-consistency audit. These need real use to find gaps.
- **Blocker**: none
- **Next action**: Pick one (likely build-literature-tree since it has the most complex output schema), run it on a real research direction, capture failures, fix, iterate.
- **Related**: INV22 (literature-tree schema), INV23 (recommend-papers ephemeral), check-consistency skill

### WI-008: Step 0 — CLI bootstrap contract (config-UX follow-on)
- **Status**: deferred
- **Priority**: p1
- **Type**: code-change
- **Context**: The config-UX solution (session 2026-08-27) shipped codex's Step 1-3 (CLI `config` group, doctor graceful degradation, thin config-setup skill, tests). Codex's Step 0 was deferred: the CLI is a separate `pip install -e .` from plugin install, so right after plugin install the `scholar-workflow` command may not be on PATH — the whole `config init` path is unreachable until the user pip-installs. Codex proposed a bootstrap contract: an absolute launcher, version detection, a persistent venv under `${CLAUDE_PLUGIN_DATA}` with one-time authorization, and reworking the SessionStart hook (currently `... 2>/dev/null || true` which silently swallows errors) to stay exit-0 non-blocking but inject diagnostics. Changing the SessionStart hook is an AGENT.md "Ask First" item.
- **Blocker**: needs design + user approval (hook change)
- **Next action**: Design the launcher + `${CLAUDE_PLUGIN_DATA}` venv bootstrap; propose the SessionStart hook change for approval; add a bootstrap contract test.
- **Related**: config-setup skill, hooks/hooks.json, bin/scholar-workflow, reference_httpmcp_scope_trap memory

### WI-009: Enhance project-backlog skill — ProjectStatus view + external-findings scan + doc-sync
- **Status**: pending-decision
- **Priority**: p2
- **Type**: code-change
- **Context**: When project-backlog was first built, the user asked for three more capabilities not yet implemented: (1) a complete, readable conversation-level ProjectStatus presentation (git state, version, dependency-chain tables); (2) surfacing actionable findings produced by other agents or project documents; (3) document-sync reminders (CHANGELOG / GOALS / AGENT.md kept in step). The skill currently only manages the work queue. Cross-agent execution now belongs to agent-collaboration; this item only decides what durable findings project-backlog should record.
- **Blocker**: user-decision (scope of the enhancement)
- **Next action**: User confirms which of the three capabilities belong in project-backlog; then implement without recreating a review skill.
- **Related**: project-backlog skill, agent-collaboration skill

### WI-010: check-consistency "orphaned PDF" scope — narrow to paper_inbox, not Zotero storage
- **Status**: done (v0.21.0, 2026-08-29) — Step 8 rewritten to a paper_inbox-only inbox-orphan check; "claimed" defined as arXiv-id/DOI filename identity resolving via zotero-mcp (identity-policy), not a path match; mirrored in consistency-invariants.md. Never reverse-scans Zotero storage/.
- **Priority**: p2
- **Type**: code-change
- **Context**: Codex audit (2026-08-27) originally read as "missing reverse enumeration of storage_root". User correction (2026-08-27): Zotero is the sole authority, so a stray file inside Zotero's storage/ is Zotero's own housekeeping — the plugin must NOT reverse-scan it (that would make the plugin a second authority, violating the authority model). The forward checks (every Zotero claim resolves; relative path; no size-0 ghost) are correct as-is. The ONLY legitimate orphan territory is paper_inbox — the plugin's own download staging area (ingest Step 7 downloads there; nothing cleans it up), which Zotero does not manage. A PDF stranded in paper_inbox (downloaded-never-ingested, or ingested-but-inbox-copy-not-removed) is a real dangling artifact of the plugin's own workflow.
- **Blocker**: none
- **Next action**: Narrow the "orphaned PDFs" drift category to a paper_inbox-only check (enumerate paper_inbox; flag PDFs with no matching Zotero item). Drop any implication of scanning Zotero storage/. Keep read-only.
- **Related**: check-consistency skill, ingest-resource (paper_inbox), project_codex_review_20260803 memory

### WI-011: find-resource — build the technical-document locate branch (index mode)
- **Status**: ready
- **Priority**: p1
- **Type**: code-change
- **Context**: Codex audit (2026-08-27). description + Triggers promise "open resources in cmux" and "locate document" (technical docs), but Steps 1-4 only implement Zotero paper lookup / semantic recall / web discovery — no technical-document branch. User decision (2026-08-27): index mode matters — **build the capability, do not trim the claim**. This is the lookup half of one feature whose registration half is WI-015 (ingest writes the index; find reads it).
- **Blocker**: none (design coupled with WI-015)
- **Next action**: Add a technical-document locate branch that reads the ingest-written doc index (see WI-015) to resolve a doc → its Vault location; then the cmux-open step. Design the index schema jointly with WI-015 before implementing.
- **Related**: find-resource skill, WI-015 (paired: one index, two halves)

### WI-012: sync-projections leaves the Notion topic-page write channel unspecified
- **Status**: deferred
- **Priority**: p2
- **Type**: code-change
- **Context**: Codex audit (2026-08-27). Step 8 has the host assemble the Notion topic-page block body, but the skill never names which authorized component *writes* it to Notion. Constraint (line 93) says bin/notion-project.py is the *only* Notion-API caller — so Step 8's write has no legal channel and superficially contradicts the "only caller" rule. Assembling blocks is intrinsic ability (not the gap); the missing business fact is the write path. Verified in SKILL.md. User (2026-08-27): no direction on Notion yet — deferred.
- **Blocker**: user-decision (deferred by user; no Notion direction yet)
- **Next action**: When Notion is revisited: either extend notion-project.py to accept topic-page presentation blocks in its payload, or explicitly assign that write to a named host-side Notion tool and revise the "only caller" wording to match.
- **Related**: sync-projections skill, bin/notion-project.py

### WI-013: analyze-paper whole-paper rerun must evolve/supplement, never overwrite
- **Status**: done (v0.21.0, 2026-08-29) — Step 4 + constraint rewritten to "one evolving note; never replace the whole note": both whole-paper and focused runs grow the single note; in-place section revision allowed (note what changed), but the note as a whole only accretes.
- **Priority**: p2
- **Type**: code-change
- **Context**: Codex audit (2026-08-27). Step 4 whole-paper path says "write the note body" with no branch for an already-existing note, so a rerun after focused sections were appended (line 30) could overwrite them. User design intent (2026-08-27): one-paper-one-analysis, each run **evolves and supplements** the existing note — never a destructive rewrite. This confirms the fix direction: the whole-paper branch is not "write fresh" but "merge into / grow the existing analysis". Verified in SKILL.md.
- **Blocker**: none
- **Next action**: Rewrite Step 4 so BOTH whole-paper and focused runs are additive-evolving on an existing note (update/append preserving prior sections), matching the one-paper-one-evolving-analysis model. Remove the "write the note body" phrasing that implies a fresh overwrite.
- **Related**: analyze-paper skill

### WI-014: project-review ↔ project-backlog trigger collision on "project status"
- **Status**: done (v0.21.0, 2026-08-29) — bare "project status"/"项目状态"/"当前进度" removed from project-backlog; backlog-qualified triggers + a redirect-to-project-review line added; both READMEs synced; routing regression case `review-bare-project-status` added.
- **Priority**: p2
- **Type**: code-change
- **Context**: Codex audit (2026-08-27), cross-skill seam. Both descriptions claim near-identical status phrases: project-review has "what's the project status" / "项目现在什么状态" / "现在整体进展"; project-backlog has "project status" / "项目状态" / "当前进度". A bare "项目状态" routes ambiguously between a strategic snapshot and the work-queue. Verified by reading both frontmatter descriptions.
- **Blocker**: none
- **Next action**: Reserve generic whole-project status for project-review; require backlog/work-item language ("待办"/"work-item"/"哪些等我决策") for project-backlog, or add an explicit disambiguation line to each description.
- **Related**: project-review skill, project-backlog skill

### WI-015: ingest-resource — build the technical-document index (registration half of WI-011)
- **Status**: ready
- **Priority**: p1
- **Type**: code-change
- **Context**: Codex audit (2026-08-27), cross-skill seam paired with WI-011. Verified against ingest-resource/SKILL.md: Phase 3 Step 9 collapses the whole technical-document (non-paper) workflow to "copy into the Vault category; write source/time/hash metadata" — no collision handling, destination/category resolution, or metadata schema. User decision (2026-08-27): index mode matters — build it. This is the **registration** half: when a tech doc is ingested, record it in a doc index so find-resource (WI-011, the lookup half) can locate it later. Non-paper materials = technical docs, web snapshots, draw.io, etc. (Triggers line 10). Note: tech docs go to the Vault, NOT Zotero (papers-only in Zotero); the index is the plugin's own registry.
- **Blocker**: none (design coupled with WI-011)
- **Next action**: Design one doc-index schema (doc id → Vault path + source/time/hash + category); give the CLI ownership of writing it during Step 9; flesh out Step 9's collision/destination/metadata rules. Design jointly with WI-011 (the reader) before implementing.
- **Related**: ingest-resource skill, find-resource skill, WI-011 (paired: one index, two halves)

### WI-016: analyze-paper — user-initiated code-reading source boundary
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Done**: 2026-08-29 (v0.21.0). code_repo_root config key + test; analyze-paper Step 2b opt-in code branch + description triggers + constraint; source-policy Code repositories section. 146 tests pass.
- **Context**: Discussion 2026-08-27. analyze-paper Step 2 currently allows ONLY get_content (no PDF parse, metadata from authoritative sources). New business rule: reading the paper's code repo is permitted **but strictly opt-in** — the skill NEVER autonomously fetches; it fetches only when the user actively mentions/asks for it. Two modes: **ephemeral** (read then discard, default) / **persist** (save under a configurable `code_repo_root`, only when the user asks to keep it). Repo URL comes from the user or is resolved from arXiv abs / Papers-with-Code. Reading the paper text stays get_content-only; code is a separate, read-only comprehension aid.
- **Blocker**: none
- **Next action**: (1) add `code_repo_root` config key (same pattern as research_vault_root / env_records_root); (2) add an opt-in code-reading branch to analyze-paper triggered only by explicit user mention, with ephemeral-default / persist-on-request; (3) constraint: read-only — clone/read source to understand, NEVER execute, pip install, or run setup; (4) source-policy note: code repo = read-only comprehension aid, distinct from the arXiv-only PDF rule.
- **Related**: analyze-paper skill, config.py, references/source-policy.md, WI-013

### WI-017: analyze-paper ↔ literature-tree linkage (tree-aware analysis)
- **Status**: done (v0.21.0, 2026-08-29) — BOTH halves landed. (1) tree-aware Step 7: reads the direction's tree, positions the paper, surfaces milestone/challenge candidates, never writes the tree. (2) hub-name reconciliation (user chose convention B, 2026-08-29): unified the per-paper hub to `paper_assets/<year>-<first-author>-<title>.md`; rewrote INV20 in GOALS.md, pointed analyze-paper Steps 3/6 at it, migrated the tracer-bullet vault file `上汽标注/Text2CAD论文相关资料.md` → `上汽标注/paper_assets/2024-khan-text2cad.md` with back-link updated.
- **Priority**: p1
- **Type**: code-change
- **Context**: Discussion 2026-08-27. analyze-paper produced an isolated note; it is now tree-aware and shares one per-paper hub with build-literature-tree. The two skills had named the same paper's asset hub differently (analyze-paper `<论文名>论文相关资料.md` per INV20 vs build-literature-tree `paper_assets/<year>-<author>-<title>.md` per INV22/INV25), so INV20 back-links didn't connect. Resolved 2026-08-29 by user picking convention B (`paper_assets/…`): it was a deliberate migration (rewrote INV20 in GOALS.md + renamed the validated vault file), not a mechanical edit.
- **Blocker**: none (resolved)
- **Next action**: none — done. Future papers use the `paper_assets/<year>-<first-author>-<title>.md` hub by default.
- **Related**: analyze-paper skill, build-literature-tree skill, INV20

### WI-018: Terminology library + interactive knowledge/learning skill family (new direction)
- **Status**: pending-decision
- **Priority**: p2
- **Type**: planning
- **Context**: Discussion 2026-08-27. A terminology-accumulation store: technical terms met while reading, each tagged with a **fixed three-tier mastery level**, driven by the user's natural-language commands (user marks mastery; the model does not auto-score). Stored inside the knowledge Vault (exact path TBD — under discussion). User frames this as the FIRST member of a new **knowledge-management & learning** skill family, to expand toward *interactive knowledge accumulation & learning* (a stateful study mode, not one-shot generation). Three-tier philosophy split: extracting/defining a term = intrinsic (don't encode); the store location, format, the three fixed tiers, dedup/update mechanics, and how mastery attaches to literature-tree nodes = external rules (encode). CLI owns the deterministic term-store ops (add/dedup/set-mastery/query); host owns extraction + the interactive dialogue. Open forks: (a) storage location & shape within the Vault; (b) scope of the learning family — what interactive study modes come next (quiz/recall, mastery-driven study path, spaced review of 了解-but-not-掌握 items) and whether it warrants its own agent.
- **Blocker**: user-decision (storage location; learning-family scope)
- **Next action**: Resolve the two forks in discussion, then split into concrete WIs (term-store CLI + skill; later interactive-learning skills). Keep three fixed mastery tiers, user-commanded.
- **Related**: analyze-paper (feeds terms), build-literature-tree (mastery↔milestone), knowledge agent, WI-013

### WI-019: Experiment management (ledger, not execution) — deferred
- **Status**: deferred
- **Priority**: p3
- **Type**: planning
- **Context**: Discussion 2026-08-27. The plugin will NOT run experiments to find failure cases (explicitly rejected). But an **experiment-management** artifact is on the agenda: a ledger of experiments the user runs by hand (config, results), linkable to a paper's failure-case / limitations discussion. Needs its own scoping pass; not started.
- **Blocker**: none (deferred by priority)
- **Next action**: When revisited: design an experiment-ledger schema (experiment id → config, dataset, result, linked paper/failure-case) and decide CLI vs vault-note ownership. Management/tracking only — never execution.
- **Related**: analyze-paper (limitations/failure-case), WI-018 (learning family)

## Completed

### WI-001: Apply codex 6-point revision to new QA skills
- **Status**: done (superseded 2026-09-06 by v0.23.0 removal of the review-class skills)
- **Priority**: p1
- **Type**: code-change
- **Context**: The proposed revisions targeted project-review and code-review. Both skills were later removed; their reusable handoff and cross-agent execution ideas moved into agent-collaboration.
- **Blocker**: none
- **Next action**: none
- **Related**: v0.20.0, v0.23.0, agent-collaboration skill

### WI-004: Release v0.20.0 to release branch
- **Status**: done (v0.20.0)
- **Priority**: p1
- **Type**: release
- **Context**: The v0.20.0 runtime snapshot was built and released; later releases have superseded it.
- **Blocker**: none
- **Next action**: none
- **Related**: v0.20.0, release process (AGENT.md)

### WI-002: Commit v0.20.0 batch
- **Status**: done (v0.20.0)
- **Priority**: p1
- **Type**: code-change
- **Context**: The v0.20.0 batch was committed and subsequently released.
- **Blocker**: none
- **Next action**: none
- **Related**: v0.20.0
