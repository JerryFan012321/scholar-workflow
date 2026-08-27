# config-setup

Configure the plugin's non-secret settings through the CLI, and bootstrap `config.yml`
on a fresh install — so you can set things up by asking, without hand-writing YAML.

- **First run** — `scholar-workflow config init --research-vault-root PATH` creates
  `config.yml` with the vault plus any `KEY=VALUE` extras you name. It writes only what
  you set, never a full dump of defaults, and refuses to clobber a differing existing file.
- **Change a value** — `scholar-workflow config set KEY VALUE` sets one dotted key
  (e.g. `notion.enabled`, `link_service.port`), preserving comments in the file.
- **Inspect** — `config show` (effective values), `config show --raw` (file as written),
  `config get KEY`, `config path`.

`config.yml` is the single source of truth for non-secret config. Secrets (tokens,
cookies, API keys, passwords) never go in it — set them as environment variables
(the Notion token is `SCHOLAR_WORKFLOW_NOTION_TOKEN`); the CLI refuses secret-looking
keys. The recommend-papers feature has its own `recommend.yml` and is out of scope here.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
