---
name: env-setup
description: Scaffold, maintain — AND consult — a personal env-records directory that tracks API keys and SSH servers (with per-host conda/CUDA/proxy inventory). Before connecting to one of the user's OWN recorded servers, uploading to it, or using a user-owned recorded API key, check this ledger FIRST for an existing host/key. NOT for uploading to Zotero or a managed service, and NOT for calling a public keyless API. Templates are committed; real records stay gitignored and local. Triggers 'env records', 'record a server', 'register an api key', 'set up env records', 'track this server', 'ssh server ledger', 'find a server', 'list servers', 'look up a server', 'which servers do I have', 'what api keys are recorded', 'upload to my server', 'ssh into my server', 'connect to my server', 'use my api key', 'which of my servers', '环境记录', '登记服务器', '登记 api', '记录服务器环境', '初始化环境记录', '查找服务器', '查服务器', '有哪些服务器', '服务器列表', '有哪些 key', '查一下 key', '传到我的服务器', '上传到我的服务器', '连我的服务器', '登录我的服务器', '用我的 key', '我哪台服务器'.
---

# env-setup

## Triggers
- User wants to scaffold the personal env-records directory (first-time setup)
- User wants to register a new API key or record a new SSH server
- User wants to note a server's environment (conda envs, CUDA, proxy) after logging in
- User wants to look up / list which servers or API keys are already recorded (read-only ledger query)
- Before a task on one of **the user's own** hosts/keys (ssh in, upload to *their* server, an API call needing *their* recorded credential): consult the ledger first to resolve which host or key to use. Not for Zotero/managed-service uploads or public keyless APIs.

**Trigger boundary** — two kinds of intent route here differently:
- A **generic verb** (upload / connect / call an API) needs a *"my / recorded"* qualifier
  to fire, so it never over-captures Zotero/managed-service uploads or public keyless APIs.
- A **noun that directly names the ledger** (find/list/look-up + server/key) fires with no
  qualifier — "server ledger" is unambiguous in this project, so a bare "find a server" is
  a ledger query, not something to route elsewhere.

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

0. **Consult before use.** When a task needs one of **the user's own** servers or API
   keys — ssh into their host, upload/deploy to it, or an API call that needs a credential
   they hold — read `servers.yaml` / `apis.yaml` under `env_records_root` FIRST and use the
   recorded host / key / env if one matches. Only if nothing matches do you fall back to
   asking the user — and then offer to record it (registration steps below). Never hardcode
   a host or key the ledger already holds. This does **not** apply to uploading to Zotero or
   a managed service, or to calling a public keyless API — those aren't ledger entries.

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
- **Ledger-first on use.** For a task on the user's own hosts/keys (ssh, upload to *their*
  server, an API call needing *their* recorded credential), the recorded `env_records_root`
  entries are the first place to look; do not ask the user for a host or key already on
  file. Not triggered by Zotero/managed-service uploads or public keyless API calls.
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
