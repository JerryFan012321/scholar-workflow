# Project Instruction Topology

Use this reference when project instruction files already exist or when filling the generated
markers.

## Canonical topology

`AGENTS.md` is the only project-rule source. `CLAUDE.md` imports it with `@AGENTS.md`.
`AGENT.md` is a human-facing compatibility pointer. Do not maintain duplicate rule bodies.

Existing states resolve as follows:

| Existing state | Action |
|---|---|
| Non-empty `AGENTS.md` | Preserve it as canonical; add missing thin entry points |
| Full `AGENT.md` but no `AGENTS.md` | Propose moving/merging its rules into `AGENTS.md`, then replace it with the pointer only after approval |
| `CLAUDE.md` without an `@AGENTS.md` import | Propose a merge that preserves Claude-specific content while adding the canonical import |
| File or symlink where a required directory belongs | Stop; never replace it automatically |

## Generated markers

The standard `AGENTS.md` leaves four project-specific markers:

- project overview;
- development commands;
- additional behavior boundaries;
- raw-data and experiment-artifact Git policy.

Proposed marker content must distinguish repository-backed facts from unresolved user choices,
omit generic coding advice, and be presented as one patch for confirmation. A user may leave
any marker unresolved.

Project-specific rules belong in `AGENTS.md`. Do not add them to global user instructions or
to a host-specific adapter.
