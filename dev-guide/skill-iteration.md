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
2. Run `pytest tests/unit tests/contract`.
3. Run the eval loop (see `eval-loop.md`).
4. Record the change in `CHANGELOG.md` and bump `plugin.json` (minor = new
   capability, patch = fix/tuning).

## Self-iteration by Claude

When Claude improves a skill, it reads this guide plus `skill-authoring.md` first,
then follows the same before/during/after checklist. Never skip the eval loop —
a description tweak that helps one case often breaks another.
