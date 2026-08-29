---
name: project-backlog
description: Manage the persistent work-item queue for this project — add, update, query, and report on pending work items, decisions, blockers, and priorities. Use when the user asks 'what needs my decision', 'what's ready to work', 'add this to backlog', 'mark X as blocked', 'backlog status', 'backlog overview', 'what's pending', '待办是什么', '哪些等我决策', '把这个加入待办', '标记 X 被阻塞', '待办概览', '待办状态', '还有什么要做'. For whole-project strategic status (「项目状态/整体进展」) use project-review instead. Not for ephemeral conversation tasks (use TaskCreate), not for strategic goals (those live in GOALS.md), not for shipped changes (those go in CHANGELOG.md).
---

# project-backlog

Maintains the persistent work queue at `planning/BACKLOG.md` — the single source of truth for pending work items, their status, decision dependencies, and blockers. Solves the problem where project state scatters across CHANGELOG (what shipped), git (what's staged), GOALS.md (long-term intent), scratch files (ad-hoc notes), and conversation history (decisions made but not recorded).

This is a **project-specific** skill that operates on *this* repository's backlog file. It is not a generic task tracker.

## Step 1: Determine operation

Recognize the user's intent from the request:

- **Add** — "add X to backlog", "记一下这个待办", "新增工作项 Y"
- **Update status** — "mark X as done", "close WI-NNN", "X blocked by Y", "X 等我决策", "start WI-NNN"
- **Query** — "what needs my decision", "what's ready to work", "show blocked items", "哪些等决策", "能做什么"
- **Report** — "backlog status", "backlog overview", "待办概览", "当前待办概览"

If ambiguous, clarify with the user.

## Step 2: Read the backlog file

Read `planning/BACKLOG.md`. If it does not exist, initialize it with the schema header:

```markdown
# Project Backlog

Work items for scholar-workflow. Single source of truth for pending work, decisions, and blockers.

## Schema

- **ID**: `WI-NNN` (auto-increment from 001)
- **Status**: ready | pending-decision | blocked | in-progress | done | deferred
- **Priority**: p0 (urgent) | p1 (high) | p2 (medium) | p3 (low)
- **Type**: code-change | eval | decision | planning | documentation | refactor

## Active Items

[Work items with status != done go here]

## Completed

[Done items, most recent first]
```

## Step 3: Execute the operation

### Add

Mint a new work-item ID (increment from the last used `WI-NNN`). Capture:

- **Title** — one-line summary
- **Type** — code-change / eval / decision / planning / documentation / refactor
- **Status** — start with `ready` or `pending-decision` depending on whether user input is needed
- **Priority** — p0 / p1 / p2 / p3 (default p2 if not stated)
- **Context** — 2–4 lines: why this matters, what led to it, what it affects
- **Blocker** — if status is `blocked`, name what it waits on (another WI-ID, external dependency, or user decision)
- **Next action** — what moves this forward

Write the item under `## Active Items` in this format:

```markdown
### WI-NNN: [Title]
- **Status**: ready
- **Priority**: p1
- **Type**: code-change
- **Context**: [2–4 lines of why/what/affect]
- **Blocker**: (none | WI-MMM | user-decision | external-dependency)
- **Next action**: [What moves this forward]
- **Related**: [Optional: goal IDs from GOALS.md, phase names, external refs]
```

### Update status

Locate the work item by ID or title. Update the `Status` field and, if applicable, the `Blocker` or `Next action` fields. When marking `done`, move the entire item block from `## Active Items` to `## Completed` (prepend so most recent is first).

### Query

Filter items by the query criteria:

- `status:pending-decision` → "what needs my decision"
- `status:ready AND blocker:(none)` → "what's ready to work"
- `status:blocked` → "what's blocked"
- `priority:p0 OR priority:p1` → "high-priority items"

Print the matching items to the terminal in a concise list (ID, title, status, blocker if any).

### Report

Generate a structured overview:

```
================================================
  PROJECT BACKLOG — scholar-workflow | YYYY-MM-DD
================================================

## Summary
- Active: N items (M ready, K pending-decision, J blocked)
- Completed: C items

## Needs decision (pending-decision)
[List WI-NNN: title]

## Ready to work (ready, not blocked)
[List WI-NNN: title]

## Blocked
[List WI-NNN: title — blocked by X]

## In progress
[List WI-NNN: title]
```

Print to terminal. Do not write a new file unless explicitly asked.

## Step 4: Confirm and write

After adding or updating items, write the modified `planning/BACKLOG.md` back. Report what changed in one sentence.

## Constraints

- **Single file, single source of truth.** All work items live in `planning/BACKLOG.md`. Do not duplicate state into TaskCreate, memory, or scratch files.
- **IDs are stable.** Once assigned, a `WI-NNN` ID never changes. Completed items keep their IDs.
- **Atomic updates.** Read the full file, modify in memory, write once. Never partially edit.
- **No external dependencies.** This skill reads and writes one file. It does not call other skills, does not query git, does not parse CHANGELOG. It trusts the user to tell it what to record.
- **Project-specific.** This skill is for *this* repository's backlog. It hardcodes the path `planning/BACKLOG.md` and the schema above.
