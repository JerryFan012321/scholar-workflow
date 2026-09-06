# Agent Handoff Contract

Use one task package per target. Keep durable rules in the project's instruction files; the
handoff contains only the state and decisions specific to this assignment.

```markdown
# Agent Collaboration Handoff

## Invocation
- Caller: <agent/runtime>
- Target: <agent/runtime>
- Repository or working root: <path>
- Applicable instruction files: <paths to read in precedence order>
- Branch/base revision and working-tree state: <state>
- Permission level: read-only | workspace-write
- Previous target session: none | <session id>

## Shared outcome
<The user-visible result this collaboration contributes to.>

## Assigned deliverable
<One bounded result owned by this target.>

## Scope
### In scope
- <files, components, questions, or commands>

### Out of scope
- <unrelated changes, external writes, destructive actions, or other limits>

## Current state
- <what already exists or was attempted>
- <pre-existing user changes that must be preserved>
- <smallest useful paths to source artifacts>

## Decisions already made
- <user-approved choices the target must preserve>

## Acceptance criteria
- <observable result>
- <required checks>
- No unrelated files changed.

## Stop conditions
Stop and return to the caller if project rules conflict with the assignment, required input or
authorization is missing, an out-of-scope/destructive action becomes necessary, or overlapping
workspace changes cannot be preserved safely.

## Return contract
Lead with the outcome. List changed artifacts or concrete findings, report checks and their
results, and state unresolved blockers. Include the session identifier when follow-up is valid.
```

Do not include credentials, tokens, private keys, full secret-bearing configuration files, or
raw sensitive logs. Point to readable project files instead of copying large content.
