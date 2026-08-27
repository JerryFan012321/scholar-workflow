# code-review

An independent review pass on a plan or a code diff by a *different* model (OpenAI Codex).
Different models share fewer blind spots than one model with itself, so a second pass
catches what the first waved through.

## What it does

- **Detects mode** — a plan in the conversation, or a git diff (staged or unstaged).
- **Builds a high-context handoff first** — reads the project's own identity and rules and
  writes the reviewer a package covering what the project is, what changed, decisions
  already made, and constraints not to violate. This is the step that earns the review: an
  external model that doesn't understand the project confidently flags deliberate choices
  as bugs.
- **Calls the reviewer read-only** and **reasons about its feedback** — accepting real
  issues, skipping (with explanation) points that misread a deliberate design choice —
  then re-submits, up to 5 rounds, until it approves.

## Requirements

- **Codex CLI** on PATH — `npm install -g @openai/codex`. Verify with `codex --version`.
- **Credentials** — a ChatGPT login or API key configured for Codex
  (`codex login status`). This skill never reads or passes your credentials.
- **Network** — if your environment needs a proxy to reach the API, export it in your shell
  before running; the skill does not hardcode any proxy address.

## How to use it

With a plan in the conversation, or changes in your working tree, type `/code-review` or
ask in natural language:

- *"get a second opinion on this plan"*
- *"cross-check this diff before I merge"*
- *"让 codex 看看这次改动"*

In **code mode**, the skill proposes a fix list and applies nothing until you approve. In
**plan mode**, it revises the plan across rounds. You see every round and can step in.

## What it is not

- Not whole-project direction review — for that, use `project-review`.
- Not a data-consistency audit across external systems.
- Not an auto-fixer — the external reviewer is read-only, and code fixes wait for your
  approval.
