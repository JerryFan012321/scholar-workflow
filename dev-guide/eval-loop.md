# Eval Loop

How skills are tested and pinned. Development-time doc — never loaded at runtime.

## What evals are here

`evals/` holds three JSON suites. Since the zotero-mcp pivot, most cases are
**behavior specifications for the host LLM at the skill layer** — not code the CLI
can assert, because the CLI subprocess cannot reach MCP tools.

| Suite | File | Answers | Enforcement today |
|---|---|---|---|
| Routing | `evals/routing.json` | Does the right skill fire for a given input? | Human/LLM judgment against the `description` fields |
| Safety | `evals/safety.json` | Are forbidden actions blocked? | Mostly skill-layer LLM behavior; only CLI-reachable cases have an exit code |
| Outcomes | `evals/outcomes.json` | Do end-to-end acceptance criteria hold? | Behavior spec; all cases currently `pending` |

The one thing that actually **runs** is `tests/unit/test_evals_schema.py` — it
validates the JSON structure of all three suites (via `pytest`). It does not judge
routing/safety/outcomes correctness; that is still a human-in-the-loop review.

## When to review which

- **After a description/trigger edit** → routing (mis-routing is the top risk).
- **After a constraint / skill-layer rule edit** → safety.
- **After a workflow change** → outcomes.
- **Before any commit that touches `skills/`** → review all three + run
  `pytest tests/unit tests/contract` (schema + contract assertions).

## Adding cases

- New skill → add at least one positive routing case and one negative case proving
  it does *not* fire for unrelated input.
- New safety invariant → decide the enforcement layer first:
  - **CLI-reachable** action → assert the block and its exit code (see the CLI
    exit-code table in AGENT.md).
  - **Skill-layer** action (anything touching Zotero via MCP) → the case pins the
    host LLM's expected behavior; there is no CLI exit code to assert. State the
    expected refusal/stop explicitly so a reviewer can check it.

## Reading results

A routing regression usually means two skills' `description` fields overlap. Fix by
sharpening trigger phrases, not by adding more of them. A safety spec that the LLM
violates is a release blocker — treat it as seriously as a failing test.

## Loop

author/iterate → review evals (routing/safety/outcomes) + run schema & contract
tests → fix regressions → update CHANGELOG + bump version → commit.
