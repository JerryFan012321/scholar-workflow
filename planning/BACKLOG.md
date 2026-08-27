# Project Backlog

Work items for scholar-workflow. Single source of truth for pending work, decisions, and blockers.

## Schema

- **ID**: `WI-NNN` (auto-increment from 001)
- **Status**: ready | pending-decision | blocked | in-progress | done | deferred
- **Priority**: p0 (urgent) | p1 (high) | p2 (medium) | p3 (low)
- **Type**: code-change | eval | decision | planning | documentation | refactor

## Active Items

### WI-001: Apply codex 6-point revision to new QA skills
- **Status**: pending-decision
- **Priority**: p1
- **Type**: code-change
- **Context**: Dogfooded code-review skill on v0.20.0 uncommitted batch (two new QA skills + resume-claims fixes + README Status section). Codex returned VERDICT: REVISE with 7 findings. Digested against project's three-tier philosophy: accepted 5 (untracked-files detection, resume verification discipline, diff credential scan, config bullet-parsing ambiguity, principles gather-all-root-files), partially accepted 1 (cleanup events-log + optional trap; skipped umask as over-defensive), skipped 1 (chunk-coverage tracking judged as optimization scaffold for rare edge case). Changes limited to skills/code-review/ and skills/project-review/ only.
- **Blocker**: user-decision
- **Next action**: User decides (a) which of the 6 fixes to apply, (b) whether to include optional trap and @-import hint.
- **Related**: v0.20.0, code-review skill, AGENT.md three-tier philosophy

### WI-002: Commit v0.20.0 batch
- **Status**: blocked
- **Priority**: p1
- **Type**: code-change
- **Context**: Two new QA skills (project-review + code-review), resume-claims honesty fixes across 5 files, README Status & limitations section, routing.json +4 cases (10→14), version bumps to 0.20.0, CHANGELOG [0.20.0] entry already written. All code exists uncommitted in main branch. Blocked on WI-001 decision: commit as-is or after applying codex fixes.
- **Blocker**: WI-001
- **Next action**: Once WI-001 resolves, stage all changes and commit with message referencing CHANGELOG [0.20.0].
- **Related**: v0.20.0

### WI-003: Complete P1-3 eval closure
- **Status**: ready
- **Priority**: p1
- **Type**: eval
- **Context**: codex-review.md flagged P1-3: evals/routing.json originally had 14 cases but was missing 4 positive cases for analyze-paper, recommend-papers, sync-projections, env-setup. Session 2026-08-27 added 3 config-setup routing cases (first-run / change / query), bringing total to 17 cases. Still need the original 4 missing cases. Also 13 outcomes marked "pending" have not been validated and promoted to "pass".
- **Blocker**: none
- **Next action**: Add 4 missing routing positive cases to evals/routing.json, run skill-trigger tests to validate, promote 13 pending outcomes to pass where tests confirm, update CHANGELOG.
- **Related**: P1-3 (codex-review.md), GOALS.md eval guard (G7)

### WI-004: Release v0.20.0 to release branch
- **Status**: blocked
- **Priority**: p1
- **Type**: release
- **Context**: After v0.20.0 is committed to main, it must be built into the orphan release branch via scripts/make-release.sh. Release branch ships to users (runtime files only, no dev-guide/planning/tests). Last sync was 0.19.0 (2026-08-05). User must explicitly approve before pushing release branch.
- **Blocker**: WI-002
- **Next action**: Run scripts/make-release.sh from clean main, review release commit, get user approval, push release branch.
- **Related**: v0.20.0, release process (AGENT.md)

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
- **Context**: When project-backlog was first built (this session), the user asked for three more capabilities not yet implemented: (1) a complete, readable conversation-level ProjectStatus presentation (git state, version, dependency-chain tables); (2) surfacing all discovered issues, especially opinions from other agents (codex reviews) and doc sources; (3) document-sync reminders (CHANGELOG / GOALS / AGENT.md kept in step). These were captured as requirements but the skill currently only does the work-queue (add/update/query/report).
- **Blocker**: user-decision (scope of the enhancement)
- **Next action**: User confirms which of the three capabilities to fold into project-backlog vs. project-review; then implement.
- **Related**: project-backlog skill, project-review skill

## Completed

(none yet)
