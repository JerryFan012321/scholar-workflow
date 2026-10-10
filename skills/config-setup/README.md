# config-setup

Configure the plugin's non-secret settings through the CLI, and bootstrap `config.yml`
on a fresh install — so you can set things up by asking, without hand-writing YAML.

- **First run** — `scholar-workflow config init` creates a minimal `config.yml` plus any
  `KEY=VALUE` extras you name. It writes only what you set, never a full dump of defaults,
  and refuses to clobber a differing existing file.
- **Legacy migration candidate** — add `--research-vault-root PATH` only when an old
  singleton Vault must remain available to pre-v3 projection commands. Dynamic Sources
  and Fields use the independent `knowledge` CLI instead. Preview, review the exact
  single-Field plan, then register with its current digest; see
  [knowledge registration](../../references/knowledge-registration.md). No Hub is needed.
  A genuinely new Source explicitly initializes an empty provider; attaching an
  existing Source never treats a missing inventory as empty. Interrupted creation
  retries use the original reviewed command and digest.
  Schema-2 Field references reuse existing objects without another owner or copy.
  `knowledge list --resolve-references` optionally checks their declared ownership
  and file states; readers remain unverified. The
  `knowledge reference-plan/reference` pair previews and confirms one reference
  addition/removal; only the referencing manifest changes, not its target. These
  commands are available from 0.43.0.
- **Change a value** — `scholar-workflow config set KEY VALUE` sets one dotted key
  (e.g. `notion.enabled`, `link_service.port`), preserving comments in the file.
- **Inspect** — `config show` (effective values), `config show --raw` (file as written),
  `config get KEY`, `config path`.

`config.yml` is the single source of truth for non-secret config. Secrets (tokens,
cookies, API keys, passwords) never go in it — set them as environment variables
(the Notion token is `SCHOLAR_WORKFLOW_NOTION_TOKEN`); the CLI refuses secret-looking
keys. The recommend-papers feature has its own `recommend.yml` and is out of scope here.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
