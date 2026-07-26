# Skill Authoring

How to write a new skill in this repo. This is a **development-time** doc — it is
never loaded at skill runtime. Read it when creating or reviewing a skill.

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
   mechanism: pack it with concrete English + Chinese trigger phrases a user would
   actually type. Vague descriptions cause mis-routing.
2. **Triggers** — bullet list of when this skill fires.
3. **Steps** — the procedure, numbered. Additive writes (download / create / import /
   metadata / add-to-collection) run directly once the user has given the ingest
   instruction — no per-write gate. Split into an approval phase only around a
   **destructive / irreversible** action (delete, overwrite-conflict, merge identity),
   which must be confirmed one by one. See AGENT.md Ask First, GOALS G4/G9/INV9/NG5.
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
- After authoring, add a routing case to `evals/routing.json`.
