# Scholar Workflow — 开发规则

## 插件结构

```
5 Agents: intake / library / knowledge / lineage / audit
5 Skills: find-resource / ingest-resource / sync-projections / build-literature-tree / check-consistency
确定性 CLI: src/scholar_workflow/ + bin/scholar-workflow
Zotero 写入: integrations/zotero-bridge/（唯一写入后端）
```

## Conventions

### Skill Anatomy

每个 skill 目录须包含：

```
skills/<name>/
├── SKILL.md          # Required — frontmatter (name, description) + trigger, steps, constraints
├── README.md         # English documentation
├── README.zh-CN.md   # Chinese documentation
├── scripts/          # Executable scripts (if any)
└── references/       # Skill-specific operational docs, loaded on demand
```

SKILL.md 的 `description` 字段是 Claude 判断是否触发该 skill 的主要机制，触发词准确性直接影响路由质量。运行期安全约束写在各 SKILL.md 的 Constraints 小节，不放本文。

### References: two tiers

- **Top-level `references/`** — canonical cross-skill policies (storage / source /
  identity / security). One source of truth; every skill and agent obeys them.
- **Per-skill `references/`** — operational detail specific to one skill.

Never duplicate a rule across tiers. When a skill needs a shared rule, its own
reference points to the top-level file rather than restating it.

## Documentation boundary

Two disjoint sets of docs. Keep them separated — never mix authoring guidance into
runtime docs or vice versa.

| Set | Location | Audience | Loaded when |
|---|---|---|---|
| **Development docs** | `dev-guide/` | The developer / Claude authoring or iterating a skill | While working in this repo |
| **Runtime docs** | `references/`, `skills/*/references/` | The Claude executing a user task | When a skill fires |

- `dev-guide/` — how to build and evolve skills: `skill-authoring.md`,
  `skill-iteration.md`, `eval-loop.md`. **Never loaded at skill runtime.**
- Runtime docs describe *what the plugin does*, not *how to develop it*. A skill's
  `## References` section lists exactly which runtime files to load — it must never
  point into `dev-guide/`.
- `GOALS.md` (repo root) — the living **intent layer**: upstream goals, long-term
  invariants, non-goals, phase status. Continuously updated, never archived. It is
  the north star; `evals/` guards each goal by its stable ID (G/INV/NG).
- `project_references/` (DESIGN.md, PROJECT.md) — the **implementation layer** is a
  frozen historical snapshot once development starts; do not maintain or sync it to
  the code. The code is authoritative for architecture. Only DESIGN.md's intent has
  been lifted into `GOALS.md`.

### Lifecycle (dev docs are temporary)

`dev-guide/` and the development-process rules in this file are scaffolding, not
part of the shipped plugin. **When the build targets in `dev-guide/` are met:**

1. Archive `dev-guide/` and add it to `.gitignore`; untrack it (`git rm --cached -r dev-guide`).
2. Strip development-process content from AGENT.md — the `dev-guide` read step in
   Always Do, this Lifecycle note, and any authoring/iteration rules.
3. Leave only what the plugin needs to run and be understood (structure, runtime
   references, behavior boundaries, agent↔skill map, exit codes, changelog rule).

### Language

- **SKILL.md** — Written in English. Chinese trigger words in the `description` field are fine.
- **Agent files (`agents/*.md`)** — English. They are runtime-loaded plugin artifacts, same as SKILL.md.
- **References** (top-level and per-skill) — English.
- **README.md** — English.
- **README.zh-CN.md** — Chinese (use `zh-CN` suffix, not `zh`).
- **Python code, comments, and user-facing string literals** — English.

## Behavior Boundaries

### Always Do

- Read `dev-guide/` (skill-authoring / skill-iteration / eval-loop) before authoring or iterating a skill
- Read the existing SKILL.md / agent file before modifying
- Update `CHANGELOG.md` before every commit — group entries under the skill name
- Bump `.claude-plugin/plugin.json` version on every skill change — minor for new features, patch for fixes
- Update `GOALS.md` when a goal, invariant, non-goal, or phase status changes — keep IDs stable, assign new IDs for new items
- Update the Agent → Skill mapping table when adding or renaming a skill
- Test skill triggering by reviewing the `description` field — it's the primary routing mechanism
- Write contract test before modifying any adapter interface
- Update `contracts/handoff.schema.json` before modifying the state machine
- Run `pytest tests/unit tests/contract` before committing

### Ask First

- Renaming a skill or agent directory (breaks existing references)
- Removing a skill from the plugin
- Changing the `description` field format or triggering strategy
- Switching Zotero write backend implementation (affects all write paths)
- Modifying hook interception rules
- Adding external dependencies to a skill's `scripts/`

### Never Do

- Hardcode API keys, tokens, or user-specific absolute paths in any file
- Write SKILL.md body in Chinese (trigger words in `description` are fine)
- Use `README.zh.md` naming — always use `README.zh-CN.md`
- Skip contract tests when modifying adapter interfaces
- Commit test artifacts, secrets, or sensitive absolute paths to Git

## Agent → Skill 映射

| Agent | 可用 Skills |
|---|---|
| intake | find-resource |
| library | ingest-resource |
| knowledge | sync-projections |
| lineage | build-literature-tree, find-resource（只读） |
| audit | check-consistency |

## CLI 退出码

0 完成 | 2 输入错误 | 3 依赖未运行 | 4 需要批准 | 5 身份冲突 | 6 部分完成可恢复 | 7 安全拒绝 | 8 外部服务错误

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/). Every change must be recorded before committing:

- **Added** — new skills, features, scripts
- **Changed** — rewrites, refactors, behavior changes
- **Fixed** — bug fixes
- **Removed** — deleted features or skills

Bump the version in `plugin.json` when releasing a coherent set of changes. Use semver: major (breaking), minor (new skill or feature), patch (fixes and improvements).
