---
name: env-setup
description: Consult or maintain the personal env-records ledger for recorded SSH servers, API keys, and host environments. Use for 'record a server', 'register an API key', 'which servers do I have', 'connect/upload to my server', '查找服务器', '有哪些服务器', '登记服务器', '用我的 key'. Do not use for cloud/Kubernetes/~/.ssh/config inventories, Zotero or managed-service uploads, or public keyless APIs.
---

# env-setup

## Ledger

The plugin reads `env_records_root` from config (default `~/dev/env-records`):

```text
servers.example.yaml
apis.example.yaml
servers.yaml
apis.yaml
setup/<alias>/<env>.sh
```

Real YAML files are local and gitignored. A server record contains connection,
environments (Python/CUDA/packages/compatibility/setup script), host CUDA driver, proxy,
purpose, and notes. An API record contains name, environment variable, value, owner, and
scope.

## Operations

Server operations now use the shared `manage-assets` entry and
`${CLAUDE_PLUGIN_ROOT}/references/asset-management.md`. Keep this legacy skill usable
without maintaining a second server procedure.

1. **Query or use:** read the relevant ledger before asking for recorded details.
   Server queries use the sanitized `assets` CLI; API records retain their existing
   store. Reading never initializes or mutates a ledger. Unavailable is not no-match.
2. **Initialize:** only on request, run `scholar-workflow env-init`. It creates missing
   templates/records and a local Git repository without overwriting or pushing.
3. **Register API:** append the key record to `apis.yaml`, including owner and scope.
4. **Register server / environment:** use the shared asset capture/update contract and
   deterministic server interface. Long rebuild procedures remain explicit
   `setup/<alias>/<env>.sh` references, not commands executed during registration.

## Routing boundary

Bare ledger queries such as “查找服务器” or “which servers do I have” route here.
Connect/upload/API actions route here only when they refer to the user's own or a recorded
host/key. Inventory owned by AWS, Kubernetes, another cloud system, or `~/.ssh/config`
uses that system instead.

## Constraints

- The plugin repository stores no private ledger data.
- Never commit `servers.yaml`, `apis.yaml`, private keys, passwords, or key values.
- `env-init` is additive and idempotent. Do not run it merely because a read finds no
  record.
- Changing `env_records_root` is a migration and requires approval before moving data.
- Use the shared owned-server capture boundary; do not auto-record incidental hosts.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/asset-management.md` — server inventory, capture,
  safe updates and reuse; load for server operations.
- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
