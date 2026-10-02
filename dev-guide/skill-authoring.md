# Skill Authoring

How to write a new skill in this repo. This is a **development-time** doc — it is
never loaded at skill runtime. Read it when creating or reviewing a skill.

## Principles — single source of truth

General skill-writing craft lives in **`writing-great-skills/`** (vendored verbatim
from Matt Pocock, MIT — see its `SOURCE.md`). It is the canonical vocabulary and the
one place those principles are defined: **predictability** (same process every run),
**leading word**, **completion criterion**, **progressive disclosure**, and the failure
modes — **no-op**, **negation**, **duplication**, **sediment**, **sprawl**. Read it
before authoring; this doc does not restate it.

Its general process advice is subordinate to `AGENT.md`: a skill owns actual operations
(when a workflow exists) and a strict final-output contract, not the model's thinking.
Exploratory tasks need no invented fixed process. Reproducible output does not require
identical reasoning or an identical exploratory path.

This doc covers only what is **specific to this repo**: the directory layout, the
bilingual trigger convention, the two-tier reference system, and the eval loop. When a
craft question arises (how long a description should be, when to split a skill, whether
a line is a no-op), consult `writing-great-skills/` — not a second copy here.

## Directory layout

```
skills/<name>/
├── SKILL.md          # required — frontmatter + trigger, steps, constraints
├── README.md         # English
├── README.zh-CN.md   # Chinese
├── scripts/          # skill-specific executables (if any)
└── references/       # skill-specific operational docs, loaded on demand
```

Shared CLI executables live in top-level `bin/` (e.g. `scholar-workflow`,
`zotero-annotations.py`), not under a skill — put a script in `skills/<name>/scripts/`
only when it is specific to that one skill. (See AGENT.md 插件结构 / Skill Anatomy.)

## SKILL.md structure

1. **Frontmatter** — `name` and `description`. The `description` is the routing
   mechanism. Write it per `writing-great-skills/` (front-load the leading word, one
   trigger per branch, cut identity the body already states). Repo-specific rule: give
   triggers in **both English and Chinese** — the phrases a user would actually type —
   since users work bilingually. Every word is permanent context load, so carry triggers
   and disambiguation ("Not X"), not a restatement of the steps.
2. **Result contract** — make the deliverables, owner/identity, required fields or links,
   completion/failure states, and observable acceptance criteria precise enough to reproduce.
   Treat the selected format as mandatory, not an optional example: preserve its headings,
   hierarchy, node/edge topology and evidence entries. An unsupported or nonconforming
   result is incomplete/failed, even if a tool produced it or old tests passed.
   A reviewed sample can establish appearance or structure, but its paper-specific facts,
   counts, and source verdicts are not generic requirements.
3. **Operational flow, when present** — describe an established business/tool workflow's
   inputs, prerequisites, actions, branches, handoffs and completion conditions. Keep exact
   ordering where operations actually depend on it, along with tool/permission gates.
   An exploratory task has no invented fixed sequence; the model's research, analysis,
   ranking and writing judgments remain unconstrained internal work.
   Additive ingest writes follow the user's ingest instruction; destructive or irreversible
   actions need their own confirmation. See AGENT.md Ask First and GOALS G4/G9/INV9/NG5.
4. **Constraints** — the runtime safety rules this skill must obey.
5. **References** — list the exact files to load at runtime (see below).

## Reference path convention

In a SKILL.md `## References` section:

- **Skill-local** file → `references/<file>.md` (relative to the skill dir).
- **Shared top-level** file → `${CLAUDE_PLUGIN_ROOT}/references/<file>.md`.

The two prefixes make local vs shared unambiguous at a glance and match the
`${CLAUDE_PLUGIN_ROOT}` convention used in `hooks/`. Never point a `## References`
entry into `dev-guide/` or `planning/` — those are development-time layers, never
loaded at skill runtime.

## Runtime references, two tiers

- Cross-skill policies live in top-level `references/` (storage / source / identity
  / security). Do not restate them — link to them.
- Skill-specific detail lives in `skills/<name>/references/`.
- Every rule has exactly one home. If two skills need it, it belongs top-level.

## Writing rules

- SKILL.md body and references: English (trigger words in `description` may be
  bilingual).
- Keep SKILL.md short; push detail into `references/` loaded on demand.
- Keep only project-specific routing, exact tool calls, artifact formats, environment
  facts, and safety/permission boundaries. Do not prescribe generic research, analysis,
  classification, ranking, summarization, or writing methods the host model already has.
- Apply `AGENT.md`'s result-interface rule: headings, fields, schemas, evidence labels,
  and readable layouts constrain the emitted artifact, not the model's internal reasoning
  framework or analysis order.
- After authoring, add a routing case to `evals/routing.json`.

## Development validation scope

Prove a new skill's route, observable output, and safety boundary with synthetic fixtures and
one controlled paper, repository, or `test` Vault object first. Add focused negative cases for
the changed interface. Do not repeatedly run a real batch, scan a whole production collection,
or migrate a formal Vault just to tune the skill. Those are operational or release-acceptance
steps, not the development loop. When full-scope acceptance is required, run it after the
implementation is stable against a current reviewed preview; never reuse a stale digest or skip
a required gate to save time. This rule does not narrow a user's actual runtime batch request.
Before any test run, show its inputs, procedure, expected results, impact and artifacts, and
obtain the user's approval; preparing fixtures alone does not authorize execution.
