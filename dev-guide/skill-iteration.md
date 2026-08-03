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
- **Steps / constraints** — keep the runtime safety invariants intact. If a
  constraint duplicates a top-level policy, link instead of restating.
- **References** — if a rule becomes shared by another skill, promote it to
  top-level `references/` and replace both copies with a pointer.

## After the change

1. Update the skill's `README.md` and `README.zh-CN.md` if behavior changed.
2. Run `pytest tests/unit tests/contract` (schema + contract assertions).
3. Review the eval suites (see `eval-loop.md`) — routing/safety/outcomes are mostly
   host-LLM behavior specs judged by review, not an automated pass/fail. Re-check the
   cases your change touches.
4. Record the change in `CHANGELOG.md` and bump `plugin.json` (minor = new
   capability, patch = fix/tuning).

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
