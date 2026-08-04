# Eval Loop

How skills are tested and pinned. Development-time doc — never loaded at runtime.

## What evals are here

`evals/` holds three JSON suites. Since the zotero-mcp pivot, most cases are
**behavior specifications for the host LLM at the skill layer** — not code the CLI
can assert, because the CLI subprocess cannot reach MCP tools.

| Suite | File | Answers | Enforcement today |
|---|---|---|---|
| Routing | `evals/routing.json` | Does the right skill fire for a given input? | Human/LLM judgment against the `description` fields |
| Safety | `evals/safety.json` | Are forbidden actions blocked? | Per case's `enforcement_layer` (see below); only `cli` cases carry an exit code |
| Outcomes | `evals/outcomes.json` | Do end-to-end acceptance criteria hold? | Behavior spec; all cases currently `pending` |

Every safety case declares an **`enforcement_layer`** so it guards a real path, not a
fictitious one:

- **`hook`** — a Claude Code hook blocks it (e.g. `guard-sqlite.sh`). Enforced by the
  hook protocol (exit 2 to block), *not* a CLI exit code.
- **`cli`** — the deterministic CLI refuses or structurally prevents it. Only these may
  carry an `exit_code` (from the AGENT.md table), and only when the CLI actively raises;
  a structural guarantee (e.g. the Obsidian adapter never writing outside the managed
  block) is a `cli` case with no code, checked by contract tests.
- **`host_llm`** — skill-layer behavior the host LLM must honor via zotero-mcp. There is
  **no CLI exit code to assert** (the CLI subprocess can't reach MCP); the case pins the
  expected refusal/stop in `expected` and a reviewer checks the trace. Never fake a CLI
  exit code here — that was a real past bug (host-layer cases wearing CLI codes).

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
- New safety invariant → set its `enforcement_layer` first (`hook` / `cli` / `host_llm`,
  see the table above), then:
  - **`cli`** → assert the block; add an `exit_code` (AGENT.md table) only if the CLI
    actively raises one, else rely on a contract test for the structural guarantee.
  - **`hook`** → the hook protocol enforces it (exit 2 to block); no CLI exit code.
  - **`host_llm`** (anything touching Zotero via MCP) → pin the host LLM's expected
    behavior in `expected`; there is no CLI exit code to assert.

## Reading results

A routing regression usually means two skills' `description` fields overlap. Fix by
sharpening trigger phrases, not by adding more of them. A safety spec that the LLM
violates is a release blocker — treat it as seriously as a failing test.

## Loop

author/iterate → review evals (routing/safety/outcomes) + run schema & contract
tests → fix regressions → update CHANGELOG + bump version → commit.
