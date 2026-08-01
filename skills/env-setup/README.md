# env-setup

Scaffold and maintain a personal **env-records** directory that tracks API keys
and SSH servers — kept entirely outside the plugin repo.

- **Scaffold** — `scholar-workflow env-init` lays down a uniform skeleton under
  `env_records_root` (from config): committed templates (`*.example.yaml`),
  gitignored real records (`servers.yaml` / `apis.yaml`), a `setup/` script tree,
  README and `.gitignore`, then a local `git init` (never pushes).
- **Servers** — three blocks per host: connection (host/user/port/key/jump/password),
  environment inventory (conda envs + python/cuda/key_packages/compat_notes, host
  cuda_driver, proxy), and meta. Rebuild recipes live in external `setup/<alias>/<env>.sh`.
- **APIs** — name / env_var / value / owner / scope, one entry per key.

The plugin owns no private data — the directory location is the only input. Templates
are committed; real records stay gitignored and local. Adding a server is
record-on-consent. Idempotent: `env-init` never overwrites existing files.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
