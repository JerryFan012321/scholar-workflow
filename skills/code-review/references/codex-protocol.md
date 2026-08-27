# Codex Invocation Protocol

How `code-review` drives the external reviewer (OpenAI Codex CLI). Self-contained: no
personal endpoints, tokens, or pinned model strings. Verify against the installed CLI —
flags evolve between versions.

## Prerequisites

- `codex` on PATH. Check `codex --version`; if absent, tell the user
  `npm install -g @openai/codex`.
- Credentials configured. `codex login status` printing `Logged in using ChatGPT` (or a
  configured API key) means `codex exec` reuses that login. The skill never reads, copies,
  or passes credentials.
- Network reachable. If the environment needs a proxy to reach the API, the *user's*
  environment supplies it (e.g. `https_proxy` / `http_proxy` already exported in the
  shell). Do not hardcode a proxy address in the skill — it is machine-specific.

## Round 1: fresh review

Run from the repository root so Codex discovers the project's config and rules. Pass the
handoff on stdin; keep the reviewer read-only.

```bash
codex exec \
  -C "$(git rev-parse --show-toplevel)" \
  --sandbox read-only \
  --json \
  "Read the project's own rules first (AGENTS.md / AGENT.md / CLAUDE.md at the repo root, if present). The stdin block is a review handoff: project context, the change under review, decisions already made, and constraints not to violate. Review the change along the mode-appropriate lens (plan: goal alignment, completeness, risk, ordering, testability; code: correctness, security, edge cases, error handling, compatibility, test coverage). Reference specific step numbers or file:line, suggest concrete fixes, skip what looks fine, no praise. Respect the stated constraints as intentional. End with exactly one line: 'VERDICT: APPROVED' or 'VERDICT: REVISE'." \
  < /tmp/code-review-handoff-${REVIEW_ID}.md \
  > /tmp/code-review-output-${REVIEW_ID}.md 2>/tmp/code-review-events-${REVIEW_ID}.log
```

- **Model:** omit `-m` — Codex uses the account/config default. Pin a model only if the
  user names one; do not bake a model string into the skill (availability shifts by
  account and version).
- **Read-only:** always `--sandbox read-only`. The reviewer inspects, never writes.
- **Result:** with `--json`, stdout is a JSONL event stream. The final assistant message
  carries the verdict; parse it out (last `agent_message` / `item.completed` text event).
  If you prefer plain text, drop `--json` and read stdout directly.

## Verify success — don't guess from prose

- Check the process **exit code** is 0.
- With `--json`, confirm a `turn.completed` event exists and there is no `turn.failed` or
  unhandled `error` event.
- Capture the **session id** from the event stream (or startup line) for resuming.

Never infer success from the natural-language reply alone.

## Rounds 2–5: resume with context

Resume the same session so the reviewer keeps prior rounds in mind:

```bash
codex exec resume "${CODEX_SESSION_ID}" \
  "I've addressed your feedback. The updated handoff is on stdin. Changes made: [...]. Skipped with rationale: [...]. Re-review and end with 'VERDICT: APPROVED' or 'VERDICT: REVISE'." \
  < /tmp/code-review-handoff-${REVIEW_ID}.md 2>&1 | tail -100
```

If resume fails (session expired), fall back to a fresh `codex exec` whose handoff
summarizes the prior rounds.

## Cleanup

Remove all UUID-scoped temp files at the end of the run:
`/tmp/code-review-handoff-*.md`, `/tmp/code-review-output-*.md`,
`/tmp/code-review-events-*.log` for this `REVIEW_ID`.
