# Claude Code CLI Target Protocol

Use this reference when any caller delegates a bounded task to Claude Code. Verify the installed
interface with `claude --help`; CLI flags can change.

## Preconditions

- `claude` is on `PATH` and its own authentication is configured.
- Start the subprocess with its working directory set to the repository root; Claude Code has no
  Codex-style `-C` flag.
- The handoff names the project instruction chain and permitted tools/side effects.

Never read or copy Claude credential files. The CLI reuses its own configured authentication.

## Fresh task

For read-only work:

```bash
claude -p --output-format json --permission-mode plan < "$HANDOFF_FILE"
```

For an already-authorized implementation:

```bash
claude -p --output-format json --permission-mode acceptEdits < "$HANDOFF_FILE"
```

Restrict `--allowedTools` to the task when the caller can express a reliable allowlist. Never use
`--dangerously-skip-permissions`. Use `--no-session-persistence` only for a one-shot assignment.

## Verify and continue

Require process exit status `0`, a non-error structured result, the final `result`, and the
`session_id` when persistence is enabled. Continue the same assignment with:

```bash
claude -p --resume "$SESSION_ID" --output-format json < "$HANDOFF_FILE"
```

Use a fresh session if the objective or authorization changed. The caller must inspect any Claude
Code diff or artifacts and run the final project checks.
