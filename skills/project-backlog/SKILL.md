---
name: project-backlog
description: Manage this repository's persistent work queue in planning/BACKLOG.md. Use only for explicit backlog/to-do/decision-queue requests such as 'add this to backlog', 'what needs my decision', 'mark WI-003 blocked', '待办概览', '加入待办'. Not for general project status, strategic goals, or conversation-only tasks.
---

# project-backlog

`planning/BACKLOG.md` is the sole work-item store.

## Operations

1. Read the complete file before every operation. If absent, initialize headings
   `# Project Backlog`, `## Schema`, `## Active Items`, and `## Completed`.
2. **Add:** mint the next stable `WI-NNN` and append it under Active Items.
3. **Update:** locate by exact ID (or unambiguous title), update fields, and move a
   completed item to the top of Completed.
4. **Query:** filter existing items and print a concise `ID — title — status — blocker`
   list. “Needs decision” means `pending-decision`; “ready” means status `ready` and
   no blocker.
5. **Report:** print counts plus pending-decision, ready, blocked, and in-progress groups.
   Do not create another report file unless asked.
6. After a mutation, write `planning/BACKLOG.md` once and report the change.

## Item format

```markdown
### WI-NNN: Title
- **Status**: ready
- **Priority**: p2
- **Type**: code-change
- **Context**: Why it matters and what it affects.
- **Blocker**: none
- **Next action**: Observable next step.
- **Related**: Optional goal IDs or references.
```

Allowed values:

- status: `ready | pending-decision | blocked | in-progress | done | deferred`;
- priority: `p0 | p1 | p2 | p3` (default `p2`);
- type: `code-change | eval | decision | planning | documentation | refactor`.

## Constraints

- IDs never change or get reused.
- Read the full file, modify in memory, and write once.
- Do not duplicate backlog state into memory, scratch files, or another task system.
- This skill does not inspect Git or CHANGELOG and calls no other skill.
