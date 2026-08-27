---
name: code-review
description: Cross-model second opinion from an external reviewer (OpenAI Codex) on a plan or a code diff. Different models have different blind spots, so an independent pass catches what the first model missed. Auto-detects plan vs. diff, feeds the reviewer a high-context handoff first, then iterates until it approves or 5 rounds pass. Use for architecture decisions, non-trivial refactors, risky changes, pre-merge review. Triggers '/code-review', 'code review', 'second opinion', 'cross-check', 'let codex look', '让 codex 看看', '交叉审查', '第二意见'. Not for trivial fixes, formatting, or whole-project direction (that's project-review).
---

# code-review

An independent review pass by a *different* model. The first model that wrote a plan or a
diff shares blind spots with itself; a second model with different priors catches what the
first waved through. This skill sends the work to an external reviewer (Codex), but its real
value is two things the reviewer can't do alone: **feeding it enough context to judge well**,
and **actively reasoning about its feedback** rather than relaying it.

An external reviewer that doesn't understand the project gives confident, wrong feedback —
flagging deliberate design choices as mistakes. So the pivotal step is not the call; it is
the **handoff** built before the call.

## Step 1: Detect mode

Check, in priority order, and tell the user which mode fired:

1. A plan in the conversation → **plan mode**.
2. Staged changes (`git diff --cached --stat`) → **code mode**.
3. Unstaged changes (`git diff --stat`) → **code mode**.
4. Nothing → ask what to review.

If the user passed a model name as an argument, use it; otherwise let the reviewer use its
account default (do not pin a model string — see `references/codex-protocol.md`).

## Step 2: Build the handoff (the step that earns the review)

Before calling anything, assemble the context that lets an outside model judge *this*
project rather than a generic one. Read the project's own identity and rules — its
`AGENT(S).md` / `CLAUDE.md` / `README` — and write a handoff covering:

- **What the project is** — 2–4 lines, enough that a cold reader understands the domain.
- **What changed** — the plan, or a summary of the diff and why it exists.
- **Decisions already made** — choices the user approved, so the reviewer doesn't relitigate them.
- **Constraints not to violate** — the project's own load-bearing rules (business rules,
  invariants, safety boundaries). This is what stops the reviewer from calling an
  intentional constraint a bug.

**Completion criterion:** the handoff names the project's domain, the change, and at least
the constraints a stranger would otherwise misread. A handoff that is just the raw diff
fails this step — that is the low-context call that produces low-quality review.

Write it to a UUID-scoped temp file so concurrent runs don't collide:

```bash
REVIEW_ID=$(uuidgen | tr '[:upper:]' '[:lower:]' | head -c 8)
# → /tmp/code-review-handoff-${REVIEW_ID}.md
```

See `references/handoff-template.md` for the section layout.

## Step 3: Send to the reviewer (round 1)

Invoke Codex read-only from the repo root, passing the handoff on stdin, per
`references/codex-protocol.md` (exact command, `--json` result parsing, exit-code and
`turn.completed` checks). Read-only always — the reviewer inspects, never writes.

The review lens differs by mode:

- **Plan** — goal alignment, completeness (missing steps, rollback, migration), risk,
  ordering & dependencies, testability.
- **Code** — correctness, security, edge cases, error handling, compatibility, test coverage.

Ask the reviewer to reference specific step numbers or file/line, suggest concrete fixes
(not "consider handling this"), skip what looks fine, and end with exactly one line:
`VERDICT: APPROVED` or `VERDICT: REVISE`. Capture the session id for later rounds.

## Step 4: Digest the verdict — reason, don't relay

Present the reviewer's feedback to the user, preserving its structure, then **judge each
point against the project's own principles**:

- A real issue → fix it (plan mode) or add it to a proposed fix list (code mode).
- A point that misreads a deliberate design choice or a stated constraint → skip it, and
  say *why* it doesn't apply. A cross-model reviewer ignorant of the project's rules will
  flag intentional decisions; catching those is exactly the judgment this step exists for.

Then branch:

- `APPROVED`, or only-positive comments → Step 6.
- `REVISE` → Step 5.
- Round 5 reached → Step 6, listing unresolved concerns.

## Step 5: Revise, then re-submit (rounds 2–5)

- **Plan mode:** edit the plan to address each accepted issue; rewrite the handoff.
- **Code mode:** do **not** edit files (the user hasn't approved) — record a proposed fix
  list with rationale, noting any skipped false-positives.

Summarize revisions for the user (what changed, what was skipped and why). If a suggested
change contradicts the user's explicit requirement, skip it and explain. Then resume the
same reviewer session (per the protocol reference) so it keeps prior-round context, and
return to Step 4.

## Step 6: Present the result & clean up

Report the final status — approved after N rounds, or 5 rounds with remaining concerns —
and, for code mode, the accumulated proposed fix list as an actionable checklist for the
user to approve. Do not apply code fixes until the user says so. Remove the temp files:

```bash
rm -f /tmp/code-review-handoff-${REVIEW_ID}.md /tmp/code-review-output-${REVIEW_ID}.md
```

## Constraints

- **Handoff before call.** The review is only as good as the context it gets. Never send a
  bare diff with no project framing — that is the failure this skill exists to prevent.
- **Reason, don't relay.** Weigh every point against the project's own principles; skip and
  explain the ones that misread a deliberate choice. The value is judgment, not a relay.
- **Reviewer is read-only.** It inspects, never writes files. In code mode, propose fixes;
  apply nothing until the user approves.
- **Bounded loop.** Max 5 rounds. If one issue recurs 3+ rounds unresolved, surface it as a
  judgment call for the user rather than looping.
- **Show every round.** The user sees each round's feedback and can intervene.
- **No hardcoded environment.** No personal proxy ports, tokens, or model strings baked into
  the flow; take those from the environment or the account default (see the protocol ref).

## References

Load on demand.

- `references/codex-protocol.md` — how to invoke the external reviewer (Codex CLI): exact
  command, sandbox, stdin handoff, `--json` parsing, session resume, exit-code checks
- `references/handoff-template.md` — the high-context handoff section layout
