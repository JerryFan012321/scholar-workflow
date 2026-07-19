# Skill Authoring

How to write a new skill in this repo. This is a **development-time** doc — it is
never loaded at skill runtime. Read it when creating or reviewing a skill.

## Directory layout

```
skills/<name>/
├── SKILL.md          # required
├── README.md         # English
├── README.zh-CN.md   # Chinese
└── references/       # skill-specific operational docs (optional)
```

## SKILL.md structure

1. **Frontmatter** — `name` and `description`. The `description` is the routing
   mechanism: pack it with concrete English + Chinese trigger phrases a user would
   actually type. Vague descriptions cause mis-routing.
2. **Triggers** — bullet list of when this skill fires.
3. **Steps** — the procedure, numbered. Split into phases when there is an approval
   gate (plan → execute).
4. **Constraints** — the runtime safety rules this skill must obey.
5. **References** — list the exact files to load at runtime (see below).

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
