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
└── references/       # Policy docs loaded into context as needed
```

SKILL.md 的 `description` 字段是 Claude 判断是否触发该 skill 的主要机制，触发词准确性直接影响路由质量。运行期安全约束写在各 SKILL.md 的 Constraints 小节，不放本文。

### Language

- **SKILL.md** — Written in English. Chinese trigger words in the `description` field are fine.
- **README.md** — English.
- **README.zh-CN.md** — Chinese (use `zh-CN` suffix, not `zh`).
- **Python code comments** — English.

## Behavior Boundaries

### Always Do

- Read the existing SKILL.md / agent file before modifying
- Update `CHANGELOG.md` before every commit — group entries under the skill name
- Bump `.claude-plugin/plugin.json` version on every skill change — minor for new features, patch for fixes
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
