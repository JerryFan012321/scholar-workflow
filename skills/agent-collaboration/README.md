# agent-collaboration

A host-neutral skill for splitting one user-authorized task across available agents and
integrating their results. Claude Code, Codex, or another supported agent can be either caller or
target; the relationship is not one-way.

## What it does

- Selects a real collaboration channel: a native agent tool, a verified target CLI, or another
  configured adapter.
- Builds a bounded handoff with project rules, current state, decisions, scope, permissions,
  acceptance criteria, and stop conditions.
- Verifies the target's completion signal and actual artifacts before the caller integrates them.
- Preserves the user's authorization boundary across every delegation.

## Usage

Ask explicitly for joint execution or a handoff:

- *"Have Claude Code and Codex split this migration and integrate the result."*
- *"Delegate the test implementation to Codex while you update the runtime code."*
- *"Ask Claude Code to take the documentation part, then finish the task here."*
- *"Give this extraction subtask to another available agent."*

Ordinary single-agent work and requests whose only purpose is a review or second opinion do not
trigger this skill.

## Supported channels

Native collaboration tools are preferred. The bundled references define verified non-interactive
protocols for Codex CLI and Claude Code CLI. Other agents are supported when the current host has
a native tool or configured adapter with explicit working-directory, permission, completion, and
result semantics.

The target never receives broader authority than the caller already has. One caller remains the
integrator and owns final validation and the user-facing result.
