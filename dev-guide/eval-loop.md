# Eval Loop

How skills are tested and pinned. Development-time doc — never loaded at runtime.

## The three eval suites

| Suite | File | Answers |
|---|---|---|
| Routing | `evals/routing.json` | Does the right skill fire for a given input? |
| Safety | `evals/safety.json` | Are forbidden actions blocked (correct exit code)? |
| Outcomes | `evals/outcomes.json` | Do end-to-end acceptance criteria hold? |

## When to run which

- **After a description/trigger edit** → routing (mis-routing is the top risk).
- **After a constraint or adapter edit** → safety.
- **After a workflow change** → outcomes.
- **Before any commit that touches `skills/`** → all three.

## Adding cases

- New skill → add at least one positive routing case and one negative case proving
  it does *not* fire for unrelated input.
- New safety invariant → add a case asserting the block and its exit code
  (see the CLI exit-code table in AGENT.md).

## Reading results

A routing regression usually means two skills' `description` fields overlap. Fix by
sharpening trigger phrases, not by adding more of them. A safety failure is never
acceptable to merge — treat it as a release blocker.

## Loop

author/iterate → run evals → fix regressions → update CHANGELOG + version → commit.
