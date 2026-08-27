# Handoff Template

The context package that lets an external model review *this* project instead of a generic
one. Fill every section from what you actually read this run — do not paste whole rule files
(that wastes the reviewer's budget and buries the signal). Point to paths; state the rules
that bear on this change.

Never include credentials, tokens, private keys, or raw sensitive logs.

```markdown
# Review Handoff

## Project context
[2–4 lines: what the project is, its domain, the layer this change touches. Enough for a
cold reader to judge relevance. Drawn from the repo's README / AGENT(S).md / CLAUDE.md.]

## Under review
[Plan mode: the full plan.]
[Code mode: a 1–2 sentence summary of what the diff does and why, then the diff itself
(git diff --cached, or git diff). Note file count and total lines; if the diff exceeds
~3000 lines, tell the user the reviewer may not cover it all and suggest smaller chunks.]

## Decisions already made
[User-approved choices the reviewer must not relitigate. Separate confirmed facts from
assumptions. Record a rejected alternative only when revisiting it would waste effort.]

## Constraints not to violate
[The project's load-bearing rules that touch this change — business rules, invariants,
safety boundaries, stated non-goals. This is the section that stops the reviewer from
flagging an intentional design choice as a defect. Cite where each rule comes from.]

## What to check
[Mode-appropriate lens. Plan: goal alignment, completeness, risk, ordering, testability.
Code: correctness, security, edge cases, error handling, compatibility, test coverage.]

## Acceptance
[What "approved" looks like: passing tests/commands, no unrelated files changed, the
verdict line. State the verification the caller will run afterward.]
```

## Why this is the pivotal step

A reviewer handed only a diff evaluates it against generic best practices — and confidently
flags the project's deliberate constraints as mistakes (the exact false-positives this skill
must filter out in its digest step). The constraints section pre-empts most of them: state
the rule as intentional up front, and the reviewer spends its attention on real problems
instead. Context quality in equals review quality out.
