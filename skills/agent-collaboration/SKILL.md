---
name: agent-collaboration
description: Coordinate a bounded task with another available agent. Use when the user explicitly asks agents to work jointly, delegates a subtask to Claude Code, Codex, or another agent, or continues the same task across agent runtimes. Caller and target are symmetric. Triggers 'agent collaboration', 'delegate to Codex', 'delegate to Claude Code', 'multi-agent', '跨 agent 协作', '让 Claude 和 Codex 一起做', '交给另一个 agent'. Not for ordinary single-agent work or review-only requests.
---

# agent-collaboration

Coordinate peer agents around one user-owned outcome. The caller remains responsible for
integrating and verifying the result.

## Step 1: Establish the collaboration contract

Identify the caller, target agent, objective, assigned deliverable, working root, and allowed
side effects. Preserve a user-named target. Otherwise use only an agent that is actually
available through the current host, a verified CLI, or a configured adapter.

Choose the channel in this order:

1. A native agent/subagent tool exposed by the current host.
2. A verified non-interactive CLI for the named target.
3. Another configured adapter that exposes an explicit working directory, permission model,
   completion signal, and result channel.

If no valid channel exists, report the missing capability instead of inventing a command or
credential flow.

**Completion criterion:** caller, target, objective, deliverable, channel, and permission level
are all known before dispatch.

## Step 2: Build the handoff

Read the applicable project instruction chain and prepare the task package described in
`references/handoff-contract.md`. Point to project rules and source files when the target can
read them; do not duplicate whole files into the handoff.

Use a uniquely named temporary handoff for CLI calls. Exclude credentials, private keys, raw
sensitive logs, and unrelated repository content. Record pre-existing user changes so the
target preserves them.

## Step 3: Dispatch the bounded work

Assign an independently checkable result. When several agents run concurrently, give them
disjoint write scopes or read-only questions; one caller owns integration.

The target receives no authority beyond the user's existing instruction. Use read-only access
for analysis or extraction. Grant workspace writes only when the delegated implementation is
already authorized. Destructive actions, external publication, credential access, or scope
expansion return to the caller for the required decision.

For CLI targets, load only the matching protocol:

- Codex target: `references/codex-cli.md`
- Claude Code target: `references/claude-code-cli.md`

Other agents follow the same contract only through an available native tool or a verified
adapter. Do not infer flags from the Codex or Claude Code examples.

## Step 4: Verify the return

Check the channel's real completion signal: process exit status and structured completion
event when available. Then inspect the returned files, diff, data, or command results against
the assigned acceptance criteria. Natural-language confidence is not proof of completion.

If the target changed shared files, confirm that its diff stays within scope and preserves
pre-existing work before integration.

## Step 5: Integrate and finish

The caller resolves conflicts, runs the final task-level validation, and reports one integrated
outcome to the user. Reuse a target session only while the objective and authorization remain
the same; create a new handoff when either changes. Remove temporary handoff/output files when
the collaboration ends.

## Constraints

- **Symmetric peers.** Claude Code, Codex, and other supported agents may each be caller or
  target; no protocol assumes a permanent orchestrator.
- **Explicit collaboration.** Invoke this skill only from a user request or an already-declared
  workflow assignment, not merely because a task is complex.
- **No authority amplification.** Delegation preserves or narrows scope and permissions;
  it never broadens them.
- **One integrator.** Multiple agents may contribute, but the caller owns the final workspace
  state, validation, and user response.
## References

Load on demand.

- `references/handoff-contract.md` — shared task-package fields and return contract
- `references/codex-cli.md` — invoke Codex as the target agent
- `references/claude-code-cli.md` — invoke Claude Code as the target agent
