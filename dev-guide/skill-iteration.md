# Skill Iteration

How to change an existing skill safely. Development-time doc — never loaded at
runtime.

## Before you touch a skill

1. Read the current `SKILL.md` and its `references/` in full.
2. Read the relevant top-level `references/` policies it depends on.
3. Check `evals/` for the cases that currently pin this skill's behavior.

## Making the change

- **Description / triggers** — this changes routing. After any edit, re-check every
  case in `evals/routing.json` still routes correctly, and that no other skill now
  mis-fires. Changing triggering strategy is an "Ask First" action (see AGENT.md).
- **Result contract / constraints** — keep observable outputs and runtime safety invariants
  intact. Preserve actual business/tool workflows where they exist, including their inputs,
  branches, handoffs and completion conditions; do not invent a fixed exploratory process or
  prescribe internal reasoning. If a constraint duplicates a top-level policy, link instead of restating.
- **References** — if a rule becomes shared by another skill, promote it to
  top-level `references/` and replace both copies with a pointer.
- **Output formats** — keep exact fields and layouts when they are user-visible contracts,
  as hard completion requirements. Remove prose that turns those fields into a mandatory
  internal reasoning process, not the required fields/topology themselves. A renderer limitation
  or a passing old test does not authorize a simplified output.

## After the change

1. Update the skill's `README.md` and `README.zh-CN.md` if behavior changed.
2. Prepare and show the affected unit/contract test plan: synthetic inputs, commands, expected
   results, impact, and visible artifacts. Follow the global test rule when running it. For integration
   behavior, use one controlled object (one paper, one repository, or one `test` Vault sample)
   and focused boundary cases only where warranted. Do not repeat a full real-library batch or
   formal Vault migration on every edit. Explain the required full unit/contract suite before
   commit; an untested change is not ready to commit. Testing does not authorize data migration.
3. Review the eval suites (see `eval-loop.md`) — routing/safety/outcomes are mostly
   host-LLM behavior specs judged by review, not an automated pass/fail. Re-check the
   cases your change touches.
4. Record the change in `CHANGELOG.md` and bump `plugin.json` (minor = new
   capability, patch = fix/tuning).

Development validation is not the runtime skill invocation. A runtime request for a batch still
processes that batch; a development test uses the smallest representative fixture that proves the
changed contract. If release acceptance explicitly requires a real collection migration, freeze
the implementation first, then produce one current full-scope preview and one reviewed execution.
Any later change that invalidates its digest requires a fresh preview and acceptance, not reuse of
stale evidence or a skipped safety check.

## Diagnosing a skill

Run the change against `writing-great-skills/`'s failure modes: is a new line a
**no-op** (the model already does it)? Did an edit add **duplication** of a top-level
policy? Is a prohibition a **negation** that should be phrased positively (keep it only
as a hard safety guardrail)? Has the file grown into **sprawl** that a reference pointer
would cure? Sharpen a **completion criterion** before adding steps.

## Self-iteration by Claude

When Claude improves a skill, it reads this guide plus `skill-authoring.md` and
`writing-great-skills/` first, then follows the same before/during/after checklist.
Never skip the eval review — a description tweak that helps one routing case often
breaks another.
