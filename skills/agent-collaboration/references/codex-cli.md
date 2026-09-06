# Codex CLI Target Protocol

Use this reference when any caller delegates a bounded task to Codex. Verify the installed
interface with `codex exec --help`; CLI flags can change.

## Preconditions

- `codex` is on `PATH` and `codex login status` succeeds.
- The subprocess runs as the user whose existing Codex login/config should be reused.
- The repository root, handoff, and permission level are known.

Never read or copy Codex credential files. The CLI reuses its own configured authentication.

## Fresh task

For read-only work:

```bash
codex exec -C "$REPO_ROOT" --sandbox read-only --json - < "$HANDOFF_FILE"
```

For an already-authorized implementation, change the sandbox to `workspace-write`. Do not use
`--dangerously-bypass-approvals-and-sandbox`. Add `--ephemeral` only when no follow-up session
will be needed.

The handoff must tell Codex which project instruction files to read. This matters when a project
uses a nonstandard filename such as singular `AGENT.md` that Codex may not auto-discover.

## Verify and continue

With `--json`, require all of the following:

- process exit status `0`;
- a `turn.completed` event;
- no unhandled `turn.failed` or `error` event;
- an extracted final agent message and session identifier when persistence is enabled.

Continue the same assignment with:

```bash
codex exec resume --json "$SESSION_ID" - < "$HANDOFF_FILE"
```

Use a fresh session if the objective or authorization changed. The caller must inspect any Codex
diff or artifacts and run the final project checks.
