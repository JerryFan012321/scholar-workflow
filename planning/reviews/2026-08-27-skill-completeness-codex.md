# Codex functional-completeness audit — all 14 skills (2026-08-27)

Raw external findings, VERDICT: REVISE. Preserved verbatim; digest/triage lives in BACKLOG.

## Per-skill audit

- `skills/survey-topic/SKILL.md` — Complete.

- `skills/find-resource/SKILL.md` — Incomplete. The frontmatter and Triggers claim technical-document location and opening resources in cmux, but Steps 1–4 only implement Zotero paper lookup, semantic recall, and web discovery. The referenced state mapping has no CLI owner, and cmux is never invoked. Add an explicit technical-document branch backed by a deterministic mapping lookup plus a cmux-open step, or remove those claims.

- `skills/recommend-papers/SKILL.md` — Incomplete. “Watchlist registration” writes directly to `recommend.yml` without a deterministic file-operation command, validation, or concurrent-update handling. Add a CLI operation such as `recommend watchlist add --author-id … --scope …`; keep author disambiguation in the host.

- `skills/ingest-resource/SKILL.md` — Incomplete. Phase 3 Step 9 reduces the entire technical-document workflow to “copy into the Vault; write source/time/hash metadata.” It does not define collision handling, destination/category resolution, metadata schema, or the CLI operation that performs the copy. Add a separate non-paper branch with a deterministic CLI payload and receipt.

- `skills/build-literature-tree/SKILL.md` — Incomplete. Step 6 instructs the host to create every `paper_assets/*.md` note directly, while the renderer only creates the ledger/tree. This leaves path safety, existing-note preservation, and idempotent backlink updates outside the CLI. Extend `project-literature-tree` or add a companion-note CLI operation.

- `skills/analyze-paper/SKILL.md` — Incomplete. Step 4 defines append behavior only for focused analysis. A repeated whole-paper analysis has no existing-note branch and can overwrite prior human-area content, contrary to the Constraints. Define whole-paper reruns as safe append/versioned sections and route persistence through a deterministic note-update operation.

- `skills/export-annotations/SKILL.md` — Incomplete. Steps 4–5 handle an existing analysis note but not an existing annotations note. Re-export therefore has no defined merge, replacement, or versioning behavior. Add an idempotent refresh policy that preserves human additions and updates provenance/cross-links without overwriting them.

- `skills/sync-projections/SKILL.md` — Incomplete. Steps 6–7 and Constraints say `bin/notion-project.py` is the only Notion API caller, but Step 8 requires the host to assemble and write the topic page after that script returns; no authorized execution channel exists for that write. Either extend the script payload to include topic-page presentation blocks or explicitly assign that write to a separate host-side Notion tool and revise the “only caller” rule.

- `skills/check-consistency/SKILL.md` — Incomplete. Steps 2–7 inspect outward references but never enumerate storage and projection records in reverse. Consequently Step 8 cannot actually identify orphaned PDFs or stale/orphaned Notion entries promised by the description. Add per-system inventory collection followed by bidirectional Zotero↔files, Zotero↔Obsidian, and Zotero↔Notion set comparisons.

- `skills/config-setup/SKILL.md` — Complete.

- `skills/env-setup/SKILL.md` — Incomplete. Model and Steps 2–4 store API `value` fields and possibly static passwords in YAML. Gitignore does not satisfy the governing rule that tokens/cookies exist only in environment variables. Store only the environment-variable name and non-secret metadata; place actual values in the environment or an approved secret store.

- `skills/project-review/SKILL.md` — Incomplete. Step 1 stops discovery when `.project-review.md` exists, so a configured source list that omits `AGENT(S).md` or `CLAUDE.md` bypasses the project rules that the Model says must govern the review. Always load and resolve the root instruction chain first; use the configured list only for the remaining strategic sources.

- `skills/code-review/SKILL.md` — Incomplete. Step 1’s fixed priority can select a conversational plan despite an explicit request to review a diff, and staged changes suppress unstaged changes without declaring that exclusion. Explicit user scope must win; when scope is unstated and multiple review targets exist, ask or clearly review both staged and unstaged changes.

- `skills/project-backlog/SKILL.md` — Incomplete. Steps 2–4 have the host rewrite `planning/BACKLOG.md` directly while claiming atomic updates. No deterministic CLI operation enforces parsing, stable IDs, atomic replacement, or concurrent-update detection. Add CLI-backed `add`, `update`, `query`, and `report` operations.

## Cross-skill seams

- `ingest-resource` does not create the state mapping that `find-resource` relies on to locate technical documents. Define one deterministic mapping schema and give one CLI component ownership of both registration and lookup.

- `project-review` and `project-backlog` both claim “project status” / “项目状态”. Reserve generic whole-project status for `project-review`; require backlog/work-item language for `project-backlog`, or add an explicit disambiguation rule.

- Persistent local mutations are split inconsistently: config and projections use the CLI, while watchlists, technical documents, paper assets, analysis notes, annotation notes, environment records, and backlog updates are assigned directly to the host. Add deterministic writer operations for these artifacts or document a narrower, explicit exception to the fixed CLI/file boundary.

- `survey-topic` routes “track an author/lab” to the watchlist sub-mode, while `recommend-papers` defines only stable Semantic Scholar author IDs. Either restrict the upstream route to authors or define how a lab resolves to a maintained set of author IDs.

VERDICT: REVISE

