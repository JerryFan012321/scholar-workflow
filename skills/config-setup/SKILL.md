---
name: config-setup
description: Configure the scholar-workflow plugin — set the research vault, paper inbox, Notion, and other non-secret settings via the CLI, or bootstrap config.yml on a fresh install. Triggers 'configure scholar-workflow', 'set my vault', 'set the research vault', 'first-time setup', 'set the paper inbox', 'enable notion', 'change a config value', 'configure the plugin', '配置插件', '设置知识库目录', '设置收件箱', '初始化配置', '第一次使用配置'.
---

# config-setup

## Triggers
- First-time setup after install: no config.yml exists yet.
- User wants to set or change any non-secret setting (vault, inbox, Notion, link-service port, policy).
- User asks where the config lives or what the current values are.

## Model

Non-secret configuration is a single file, `config.yml`, written and validated only
through the CLI's `config` command group. There is exactly one config surface — do not
invent a second (no plugin.json userConfig, no env-var shadow copy); a parallel store
would drift from config.yml.

The CLI resolves and validates dotted keys against its own schema, so you never need a
key list here — map the user's request to the obvious dotted key and run the command.

## Steps

1. **First run** — if there is no config.yml (a business command or `doctor` reports
   "not configured", exit 3): run
   `scholar-workflow config init --research-vault-root PATH` with the vault the user
   names, plus any settings they mention as `KEY=VALUE` extras. It writes only what you
   name, never a full dump of defaults.
2. **Change a value** — `scholar-workflow config set KEY VALUE` (dotted keys, e.g.
   `notion.enabled`, `link_service.port`). Comments in the file are preserved.
3. **Inspect** — `config show` (effective values), `config show --raw` (file as written),
   `config get KEY`, `config path`.

## Constraints
- config.yml is the sole source of truth for non-secret config. Never add a second
  parallel config mechanism.
- Secrets (tokens, cookies, API keys, passwords) NEVER go in config.yml or git. The
  CLI refuses secret-looking keys and points at the env var (the Notion token is
  `SCHOLAR_WORKFLOW_NOTION_TOKEN`). Set secrets as environment variables.
- This skill covers **core** config.yml only. The recommend-papers feature has its own
  file (recommend.yml); it is out of scope here.
- `config init` never clobbers a differing existing file (no `--force`). If it refuses,
  edit the existing file with `config set` rather than re-initializing.
- The CLI does file work; anything needing Zotero/web/MCP is a different skill.

## References

Load on demand.

- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — secrets stay in env vars, never in config/git
