---
name: agent-collaboration
description: Delegate a bounded subtask to another available agent or continue one task across agent runtimes. Use only when the user or an established workflow explicitly requests multi-agent collaboration, Codex, Claude Code, or another agent. Not for ordinary single-agent work or review-only requests.
---

# agent-collaboration

The caller owns integration, validation, and the final user-visible result.

## Steps

1. Fix the collaboration contract: caller, target, objective, deliverable, working root,
   allowed side effects, and acceptance criteria. Preserve a user-named target.
2. Select an available channel in order:
   1. native agent/subagent tool;
   2. verified non-interactive CLI for the named target;
   3. configured adapter with explicit working directory, permission model, completion
      signal, and result channel.
   If none exists, report the missing capability.
3. Read the applicable project instructions and create one task package using
   `references/handoff-contract.md`. Point to readable files instead of copying them;
   record pre-existing user changes; exclude credentials and unrelated content.
4. Dispatch an independently checkable result. Parallel writers must have disjoint file
   scopes; otherwise delegate read-only work.
5. For CLI targets, load only the matching protocol:
   - Codex: `references/codex-cli.md`;
   - Claude Code: `references/claude-code-cli.md`.
6. Verify the actual completion signal, returned artifact/diff, scope, and acceptance
   criteria. Then integrate, run final task checks, and remove temporary handoff/output
   files.

## Constraints

- Collaboration must be explicitly requested or already declared by the workflow.
- Delegation preserves or narrows the user's scope and permissions. Destructive actions,
  publication, credential access, or scope expansion return to the caller.
- The caller remains the sole integrator and reports one combined outcome.
- Reuse a target session only while objective and authorization are unchanged.

## References

- `references/handoff-contract.md`
- `references/codex-cli.md`
- `references/claude-code-cli.md`
