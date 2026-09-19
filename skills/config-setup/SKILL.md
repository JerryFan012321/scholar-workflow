---
name: config-setup
description: Initialize, inspect, or change scholar-workflow's non-secret config.yml through the CLI. Use for 'configure scholar-workflow', 'set my vault', 'set paper inbox', 'where is the config', '配置插件', '设置知识库目录', '初始化配置'.
---

# config-setup

`config.yml` is the only non-secret configuration surface. The CLI owns schema
validation and file writes.

## Commands

- First run:
  `scholar-workflow config init --research-vault-root PATH [KEY=VALUE ...]`.
- Change one value:
  `scholar-workflow config set KEY VALUE`.
- Inspect:
  `scholar-workflow config show`,
  `config show --raw`,
  `config get KEY`,
  `config path`.

Use dotted schema keys. `config init` writes only named values; `config set` preserves
comments.

## Constraints

- Never create a second config store or mirror values into plugin manifests.
- Secrets never enter config or Git. Use environment variables; the Notion token is
  `SCHOLAR_WORKFLOW_NOTION_TOKEN`.
- This skill covers core `config.yml`, not `recommend.yml`.
- `config init` never overwrites a different existing file. Use `config set` for an
  existing configuration.
- Zotero, web, and projection work belongs to their owning skills.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
