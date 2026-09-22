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
- **Context**: codex-review.md flagged P1-3: evals/routing.json was missing positive cases. 2026-08-29 added the 4 missing (analyze-paper, recommend-papers, sync-projections, env-setup) + 1 backlog-vs-review disambiguation → 22 cases; test_evals_schema green. REMAINING: the 18 "pending" outcomes in outcomes.json have NO guarding end-to-end evidence, so promoting them to "pass" would be unfounded — each "pass" outcome cites a real test file; the 18 pending do not. Promotion needs real end-to-end validation (WI-007 territory), not a status edit.
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
- **Context**: The first real analyze-paper v0.27.2 run is complete: V-JEPA 2 exposed a contract-level failure rather than a passing acceptance case (194 field markers in 476 Markdown lines; 194-node/35,940px-high Canvas; duplicate Evidence nodes; non-source "对应挑战 / 贡献" fields; no claim-level evidence backlinks). Its redesign is now WI-027/WI-028 and its migration rerun is WI-030. The other three implementations still need real end-to-end use: build-literature-tree's module/challenge render path, recommend-papers NotebookLM skim tier, and check-consistency audit.
- **Blocker**: none
- **Next action**: Keep the analyze-paper outcomes pending until WI-027/WI-028 are implemented and WI-030 reruns the JEPA golden case; meanwhile resume the remaining three battle tests when scheduled.
- **Related**: INV24, INV38, WI-027, WI-028, WI-030, INV22 (literature-tree schema), INV23 (recommend-papers ephemeral), check-consistency skill

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

### WI-019: Research project system v2 — umbrella
- **Status**: in-progress
- **Priority**: p1
- **Type**: planning
- **Context**: The earlier experiment-ledger idea has expanded through the 2026-09-20 discussion into a full research-project contract: a stable common base, per-dataset local layout, machine-independent `env/`, explicit source/config profiles, Run/Attempt/Target separation, local artifact promotion, and safe legacy migration. External repository research informs only source/config profiles; it cannot override the common data, experiment, environment, documentation, backup, or Hub boundaries. The complete draft is `planning/project-system-v2.md`.
- **Blocker**: none for runtime implementation; backup medium and first real migration remain external decision gates
- **Next action**: Keep the implemented WI-020 through WI-023 contracts green through the final regression/release review; keep WI-024 read-only until a real project is selected.
- **Related**: G11, INV27, INV32-INV35, WI-020, WI-021, WI-022, WI-023, WI-024

### WI-020: init-project v2 common contract and declarative initializer
- **Status**: done
- **Priority**: p1
- **Type**: refactor
- **Context**: Replace the old hard-coded `dataset/{metadata,raw}`, top-level `dataset_toolkits/`, `env/server/`, and single generic `src/pipeline/` skeleton with a declarative tracked/local base. Preserve plan-before-apply, idempotency, fail-closed symlink handling, host neutrality, and no stage/commit/push. Existing projects receive diagnostics and proposed patches only.
- **Blocker**: none; `project-layout.json` schema v2 and stable UUID `project_id` are frozen
- **Next action**: Keep the fixture contract green; do not retrofit a real project before WI-024 is explicitly unblocked.
- **Related**: INV27, INV32, `planning/project-system-v2.md` Phase A-B

### WI-021: Source and configuration profile catalog
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Encode the source/config organization learned from TRELLIS, Gaussian Splatting, Detectron2, SAM 2, DreamerV3, and TorchTitan as six primary profiles (`paper-method`, `multi-stage-3d`, `research-framework`, `foundation-model`, `world-model`, `training-platform`) plus orthogonal addons. Profiles may affect only source/config/entrypoint/test-related paths and must never redefine the common outer contract.
- **Blocker**: WI-020 interfaces must land in the same capability batch
- **Next action**: No code action before release review; do not auto-detect a profile or generate algorithm placeholders.
- **Related**: INV27, INV32, `planning/project-system-v2.md` Phase C

### WI-022: Run/Attempt/Target experiment contracts and management skill
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: A Run is the scientific recipe; an Attempt is one real execution on a Target. Multiple Runs may share a commit, and one Run may have local and SSH Attempts. The first implementation manages records, validation, indexing, completion receipts, and migration plans; it does not implicitly launch training or accept arbitrary remote commands.
- **Blocker**: none; choices are frozen in `project-system-v2.md` §13
- **Next action**: Keep fixture/fault tests green; a real experiment remains outside this capability batch. No standalone skill was added.
- **Related**: INV33, INV34, `planning/project-system-v2.md` Phase D

### WI-023: Artifact promotion and verified local backup policy
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Experiment reports, resolved configs, metrics, parameters, environment summaries, and selected high-value outputs must return from execution servers to local storage. Copying back to the workstation is artifact promotion, not yet a verified backup. Large reproducible intermediates may remain manifest-only.
- **Blocker**: verified-backup transition remains blocked on backup medium/frequency; promotion is unblocked
- **Next action**: Keep the implemented explicit selection, atomic verified copy, no-overwrite promotion receipts and cross-process race/fault tests green. `backup.state=verified` is rejected by both runtime and schema until WI-041 defines an independent medium and restore exercise.
- **Related**: INV35, `planning/project-system-v2.md` Phase E

### WI-024: Legacy layout diagnostics and one-project pilot migration
- **Status**: blocked
- **Priority**: p1
- **Type**: planning
- **Context**: Existing `dataset/raw`, `dataset/metadata`, `dataset_toolkits`, `env/server`, tracked docs/experiments, and legacy experiment bundles are semantically ambiguous. Migration must preserve every byte, keep old output/log paths in place, and stop on multiple scripts/configs or unknown commits. No batch migration of unrelated projects is authorized.
- **Blocker**: user choice of the first real project after the completed temporary-project fixture rehearsal
- **Next action**: After the user selects one real project, run the existing read-only migration planner and present its exact patch; do not apply it implicitly.
- **Related**: INV27, INV32-INV35, `planning/project-system-v2.md` Phase F

### WI-025: Research knowledge system v2 — umbrella
- **Status**: in-progress
- **Priority**: p1
- **Type**: planning
- **Context**: The 2026-09-21 V-JEPA 2 run showed that the existing paper-centric Vault, field-heavy analysis contract, 194-node Canvas, and raw 23128 links do not yet form a coherent human-first knowledge system. The new design separates core charter/survey/catalog documents, atomic paper/technical-document/blog resources, attached artifacts, human-readable Markdown, machine sidecars, and managed resource actions. The complete draft is `planning/knowledge-system-v2.md`; this work is separate from the research-project skeleton in WI-019.
- **Blocker**: none for runtime contracts; K6 real JEPA migration remains an external decision gate
- **Next action**: Finish the WI-028 visual golden pilot and WI-032 scheduler/repair-plan seam; keep the completed WI-026/WI-027/WI-029/WI-031 contracts green. Do not migrate real Vault data or switch 23128.
- **Related**: G12, INV17, INV24, INV37-INV39, WI-007, WI-011, WI-015, WI-018, WI-026, WI-027, WI-028, WI-029, WI-030

### WI-026: Knowledge object model and multi-resource HubCatalog assembler
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: HubCatalog currently assembles paper resources from literature-tree payloads, while technical documents do not become resources and Blog/Web articles have no formal kind. Existing `ResourceKind` also mixes semantic resources with `snapshot/drawio/image/dataset` file-like kinds. Define core-document roles (`charter`, `survey`, `catalog`), atomic resource kinds (`paper`, `technical-document`, `blog-post`), rendition/asset compatibility mappings, attached-artifact ownership, stable IDs, and reverse relations without parsing filenames or free Markdown. Reuse the technical-document index direction from WI-011/WI-015 and the knowledge-family scope from WI-018 rather than creating a second registry.
- **Blocker**: none; object and authority decisions are frozen in `knowledge-system-v2.md`
- **Next action**: Keep the implemented strict object/owner schemas and CAS/idempotent `KnowledgeChangeSet` apply-to-provider snapshot green, including receipt-content validation, state-root inode rebinding, manifest/catalog closure and ID/path collision tests. Projects remain a separate Library; never infer relations from prose or paths, and do not initialize a real provider/Vault migration before WI-030 approval.
- **Related**: INV29, INV37, WI-011, WI-015, WI-018, `planning/knowledge-system-v2.md` K-B

### WI-027: Human-readable knowledge artifact and machine-sidecar contract
- **Status**: done
- **Priority**: p1
- **Type**: refactor
- **Context**: V-JEPA 2's Markdown contains 194 per-field baseline comments in 476 lines, so the nominal text artifact is not human-first. Persistent notes need independently readable prose, thin identity frontmatter, inline evidence, and external section/claim baseline state. Machine structure may remain available as a manifest/sidecar or rebuildable export, but must not become a second editable body.
- **Blocker**: none; sidecar and claim/backlink result contracts are frozen
- **Next action**: Keep the implemented human-first renderer and canonical Markdown/Canvas/sidecar transaction green. Real Vault writes remain prohibited until WI-030 presents and receives approval for the exact JEPA patch.
- **Related**: INV24, INV38, WI-028, `planning/knowledge-system-v2.md` K-C

### WI-028: analyze-paper Markdown and Canvas v2
- **Status**: in-progress
- **Priority**: p1
- **Type**: code-change
- **Context**: Redesign the detailed paper artifact around readable prose plus a compact visual overview. Evidence belongs with its claim and links back; Method steps form one continuous flow; standalone Evidence nodes and pipeline "对应挑战 / 贡献" are removed. JSON Canvas remains standard and editable, preserves user layout/nodes, uses headings and larger semantic nodes, and keeps detailed content in Markdown rather than mirroring every field.
- **Blocker**: WI-027 interface in the same capability batch; private CSS is explicitly not required in v1
- **Next action**: The output contract, renderer, conformance gate and sidecar-aware conflict plan are implemented. Complete the temporary V-JEPA 2 golden fixture and real Obsidian screenshot/readability check; do not write the real Vault analysis yet.
- **Related**: INV24, INV38, WI-007, WI-027, WI-030, `planning/knowledge-system-v2.md` K-D

### WI-029: Knowledge catalog provider and stable Hub/PDF entry
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Knowledge System v2 must expose a versioned `knowledge_catalog` inside the unique HubDirectory and keep stable resource/artifact identities separate from raw loopback URLs. Service lifecycle, workspace binding and task control now belong to WI-033–WI-040 rather than this knowledge work item.
- **Blocker**: WI-026 provider model
- **Next action**: Keep typed paper/attachment/knowledge-artifact landings, the v1-derived projection, and the authoritative provider-snapshot apply contract green through release review. `serve-hub` now selects that provider only when its explicit snapshot already exists; do not initialize live provider state, switch 23128, or rewrite stored raw links in this batch.
- **Related**: INV17, INV29, INV43, WI-026, WI-033, WI-035, `planning/knowledge-system-v2.md` K-E

### WI-030: Knowledge-system migration planner and JEPA golden pilot
- **Status**: blocked
- **Priority**: p1
- **Type**: planning
- **Context**: Existing `01-Paperlist.md`, literature trees, `paper_assets/`, analysis notes, Canvas layouts, and raw 23128 links are live user data. Migration must preserve bytes until an exact plan is approved, keep user prose/layout/custom nodes, and distinguish runtime release from Vault conversion. V-JEPA 2 is the first evidence-rich pilot because it exposes every target defect.
- **Blocker**: WI-026-WI-029; K6 confirmation of the JEPA pilot and each real patch
- **Next action**: Build a read-only migration plan against a temporary fixture, including a scan for same-resource analysis/Canvas copies across topics. Identical hashes may only produce an alias/dedup proposal; differing hashes remain unresolved and must be shown as canonical-vs-topic-context candidates without automatic selection. Then present the exact V-JEPA 2 Markdown/Canvas/catalog/link diff before any real Vault write. Do not batch-migrate other topics.
- **Related**: INV37-INV42, WI-007, WI-026, WI-027, WI-028, WI-029, WI-031, WI-032, `planning/knowledge-system-v2.md` K-G

### WI-031: Per-paper analysis conformance and batch isolation
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: A batch must not report success merely because files were emitted. Whole/focused profiles, required observable roles, evidence placement, Canvas graph validity, node budget and human-readable output need one deterministic validation boundary applied independently to every paper.
- **Blocker**: WI-027/WI-028 result contracts in the same capability batch
- **Next action**: Keep profile/IR validation, per-item state, one-repair maximum, cleanup and mixed-success isolation tests green. Crash-stale `running` batches remain report-only until a lease/recovery contract is separately approved.
- **Related**: G13, INV40, INV41, WI-027, WI-028

### WI-032: Knowledge maintenance and template-version audit
- **Status**: in-progress
- **Priority**: p1
- **Type**: code-change
- **Context**: The library needs a repeatable way to find orphan artifacts, broken manifests, duplicate canonical analyses, template drift, raw loopback identity leakage and unfinished batch items without rewriting content automatically.
- **Blocker**: WI-026 and WI-031 data surfaces
- **Next action**: The explicit-manifest, strictly read-only audit surface is implemented. Add the optional weekly scheduler and an explicit single-use repair-plan/apply contract later; all real repairs and Vault writes remain separate approved actions.
- **Related**: G13, INV42, WI-026, WI-031

### WI-033: Hub Control Plane v2 — umbrella and formal contract
- **Status**: in-progress
- **Priority**: p1
- **Type**: planning
- **Context**: `hub-investigation-conclusion.md` established evidence but is not an activated specification. `planning/hub-control-plane-v2.md` freezes HubDirectory, typed Libraries, registries, bindings, project-doc boundaries and task control as a third system alongside Project and Knowledge.
- **Blocker**: none
- **Next action**: Keep the implemented WI-034–WI-040 contract surfaces aligned through full regression and the release-artifact canary. Do not fold control-plane ownership back into Knowledge System or enable production task execution implicitly.
- **Related**: G14, INV43-INV46, WI-034-WI-040

### WI-034: Hub service identity, diagnostics and temporary-port canary
- **Status**: in-progress
- **Priority**: p1
- **Type**: code-change
- **Context**: The user explicitly stopped and disabled the old 0.18.0 LaunchAgent. Port 23128 is now held by a manually started cmux-visible Hub; 0.28.1 makes `open-hub` wait for a verified binding instead of returning after page creation. A managed, self-identifying start/stop lifecycle is still absent.
- **Blocker**: decide the durable managed owner and explicit start/status/stop mechanism; the old LaunchAgent must not be silently revived
- **Next action**: Keep the current cmux foreground lifecycle documented and observable, then design a managed replacement with explicit stop/restart semantics and rollback evidence before enabling it.
- **Related**: INV39, INV44, WI-040

### WI-035: HubDirectory, Papers Library and v1 compatibility
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Replace the mixed root with one versioned HubDirectory and typed/paged Library providers. Papers must page through Zotero Local API; old `/api/v1/catalog` remains a derived read-only projection.
- **Blocker**: none for the HubDirectory/Papers seam; the broader Knowledge provider apply remains WI-026/WI-029
- **Next action**: Keep the completed typed Papers paging, authority namespaces, provider diagnostics, v1-derived projection and optional authoritative Knowledge-provider selection tests green; live provider initialization and 23128 cutover remain separate gates.
- **Related**: INV29, INV43, WI-026, WI-029

### WI-036: Projects Library and safe project-doc operations
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Projects come only from portable `project_id` plus explicit host registry. Hub file operations are limited to registered `docs/`; knowledge/project copies become independent, and deletion is recoverable trash.
- **Blocker**: WI-020 project-layout contract
- **Next action**: Do not register or modify a real project until selected; retain the cross-process/race/fault no-overwrite tests.
- **Related**: INV46, WI-020, WI-027, WI-035

### WI-037: ToolDefinition registry and Tools Library
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Scholar Workflow, Codex, cmux, Zotero, Obsidian and future tools require explicit provider/capability/health/recipe declarations. PATH scanning is prohibited.
- **Blocker**: none
- **Next action**: Populate real ToolDefinition rows only through explicit host configuration after release; never scan `$PATH`.
- **Related**: INV43, NG13, WI-039

### WI-038: WorkspaceProfile, Lease and HubViewBinding
- **Status**: done
- **Priority**: p1
- **Type**: code-change
- **Context**: Existing opaque workspace mappings are process-local but do not express service generation, lease expiry or cmux instance identity. Executable views need exactly one verified primary binding.
- **Blocker**: WI-034 service identity
- **Next action**: Validate the implemented nonce/generation/socket-instance invalidation against the formal cmux canary before cutover.
- **Related**: INV44, WI-034, WI-039

### WI-039: TaskRecipe, LogicalTask, TaskRun and Codex worker
- **Status**: in-progress
- **Priority**: p1
- **Type**: code-change
- **Context**: Replace blank-session-only action with server-registered recipes, bounded brief/effort and explicit Codex thread IDs while preserving the prohibition on browser commands, paths and security configuration.
- **Blocker**: WI-036–WI-038 contracts
- **Next action**: Internal schemas/store/worker, explicit-thread parsing, cross-process locks, cancel/timeout and process-group recovery are implemented with fake-worker tests. Next is a separately gated production worker manager/HTTP surface and real capability canary; do not launch a real task in this batch.
- **Related**: INV31, INV45, NG15

### WI-040: Library-first UI, compatibility rollout and 23128 cutover gate
- **Status**: in-progress
- **Priority**: p1
- **Type**: code-change
- **Context**: The Hub UI currently assumes a whole catalog loaded client-side. It must navigate Libraries, Knowledge Contexts and Operations, with server pagination and visible disabled actions when unbound.
- **Blocker**: WI-035–WI-039; live cutover additionally needs explicit user approval
- **Next action**: Library/Knowledge/Operations UI and fixture canary are implemented. Run the formal release-artifact canary and compatibility baseline, then stop for explicit approval before replacing 23128.
- **Related**: G14, INV43-INV45, WI-034-WI-039

### WI-041: Verified backup backend and retention policy
- **Status**: blocked
- **Priority**: p2
- **Type**: decision
- **Context**: Artifact promotion to the workstation is not an independent backup. A verified transition requires a selected second medium, retention rule and restore exercise.
- **Blocker**: user choice of backup medium/frequency/retention
- **Next action**: Keep promotion receipts at backup-pending; implement verified transitions only after the decision.
- **Related**: INV35, WI-023

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
