# project-backlog

A project management skill for maintaining the persistent work-item queue at `planning/BACKLOG.md`.

## What it does

Tracks concrete pending work, decisions, and blockers that aren't captured elsewhere:
- GOALS.md holds long-term intent and invariants
- CHANGELOG.md records what shipped
- Git shows staged/unstaged changes
- This skill fills the gap: **what's pending, what needs a decision, what's blocked, what's ready to work**

Every work item gets a stable ID (`WI-NNN`), a status (ready/pending-decision/blocked/in-progress/done/deferred), priority, context, and a next-action note.

## Usage

Talk to Claude Code or Codex in natural language:

- *"Add a work item: add checksum validation to imported documents"* → new item with context
- *"What needs my decision?"* → lists all `status:pending-decision` items
- *"Mark WI-003 as done"* → moves it to Completed
- *"WI-005 is blocked by user decision on the scope"* → updates status and blocker
- *"Backlog status"* / *"backlog overview"* → full backlog overview (summary + categorized lists)
- *"What's ready to work?"* → items with status `ready` and no blockers

## Schema

Each work item has:
- **ID**: `WI-NNN` (auto-increment, stable forever)
- **Title**: one-line summary
- **Status**: ready | pending-decision | blocked | in-progress | done | deferred
- **Priority**: p0 (urgent) | p1 (high) | p2 (medium) | p3 (low)
- **Type**: code-change | eval | decision | planning | documentation | refactor
- **Context**: 2–4 lines explaining why it exists, what it affects
- **Blocker**: what it's waiting on (another WI, user decision, external dependency, or "none")
- **Next action**: what moves it forward
- **Related**: optional links to GOALS.md IDs, phase docs, external refs

## File location

`planning/BACKLOG.md` — single source of truth, checked into git alongside GOALS.md and HANDOFF.md.

## Integration with other project artifacts

- **GOALS.md** — work items can reference goal IDs (G1, INV5, NG3) in their `Related` field
- **CHANGELOG.md** — when a work item completes and ships, its changes go into CHANGELOG; the work item itself moves to Completed in the backlog
- **TaskCreate/TaskUpdate** — those are ephemeral, conversation-scoped. Use them for short-lived implementation steps. Use this skill for persistent cross-conversation tracking.

## Example work item

```markdown
### WI-020: Add checksum validation to imported documents
- **Status**: ready
- **Priority**: p1
- **Type**: code-change
- **Context**: Imported technical documents need a stable content-integrity check before the index records them.
- **Blocker**: none
- **Next action**: Define the checksum field, implement it in the ingest path, and add a contract test.
- **Related**: ingest-resource skill
```
