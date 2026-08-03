---
name: env-setup
description: Scaffold and maintain a personal env-records directory that tracks API keys and SSH servers (with per-host conda/CUDA/proxy inventory). Templates are committed; real records stay gitignored and local. Triggers 'env records', 'record a server', 'register an api key', 'set up env records', 'track this server', 'ssh server ledger', '环境记录', '登记服务器', '登记 api', '记录服务器环境', '初始化环境记录'.
---

# env-setup

## Triggers
- User wants to scaffold the personal env-records directory (first-time setup)
- User wants to register a new API key or record a new SSH server
- User wants to note a server's environment (conda envs, CUDA, proxy) after logging in

## Model

The plugin owns **no private data**. It reads one location from config
(`env_records_root`, default `~/dev/env-records`) and scaffolds a uniform skeleton
there. Real records live only in that directory, never in the plugin repo.

```
<env_records_root>/
├── servers.example.yaml    # template (committed) — how a server entry looks
├── apis.example.yaml       # template (committed) — how an API entry looks
├── servers.yaml            # REAL records (gitignored, local only)
├── apis.yaml               # REAL records (gitignored, local only)
└── setup/<alias>/<env>.sh  # env rebuild scripts (committed; recipes, no secrets)
```

A server entry has three blocks: **connection** (host/user/port/key/jump/password),
**environment inventory** (a list of conda envs, each with python/cuda/key_packages/
compat_notes + a pointer to its rebuild script; plus host-level cuda_driver and proxy),
and **meta** (purpose/added/notes). An API entry records name/env_var/value/owner/scope.

## Steps

1. **Scaffold** (first run): `scholar-workflow env-init`. It lays down the skeleton
   under `env_records_root`, seeds real record files from templates once, and runs a
   local `git init` (never pushes). Idempotent — existing files are never overwritten.
2. **Register an API key**: append an entry to `apis.yaml` (the real, gitignored file).
   Record `owner` (whose key) and `scope` (what it is for). The value stays local.
3. **Record a server** — *record-on-consent*: before adding a host, confirm with the
   user that it is worth tracking (most SSH hosts are throwaway; do not auto-capture).
   On yes, append a connection block to `servers.yaml`.
4. **Note the environment**: after logging into a recorded host, fill its `environments`
   list (conda envs + python/cuda/key_packages/compat_notes), host `cuda_driver`, and
   `proxy`. Large rebuild recipes go in an external `setup/<alias>/<env>.sh`, referenced
   by `setup_script` — not inlined into the YAML.

## Constraints
- The plugin never stores private data; the only input is `env_records_root` from config.
- Templates (`*.example.yaml`) are committed; real records (`servers.yaml`, `apis.yaml`)
  are gitignored and never pushed. Do not `git add -f` a real record.
- SSH private keys and static passwords live only in the gitignored real files (or in
  `~/.ssh/`); never commit them.
- `env-init` is additive and idempotent: it never overwrites an existing file, so real
  records survive re-runs.
- record-on-consent applies to **servers**: confirm before adding a host to the ledger.
- Changing `env_records_root` (moving the directory) is a migration — propose and get
  approval before relocating; the CLI only reads the path, it does not move data.

## References

Load on demand.

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md` — where records and scripts live
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — additive writes are the normal path
