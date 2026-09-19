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

1. **Query or use:** read `servers.yaml` / `apis.yaml` first when the user asks what
   is recorded or a task needs one of the user's recorded hosts/credentials. Reading
   never initializes or mutates the ledger. If nothing matches, report that before asking
   for missing details.
2. **Initialize:** only on request, run `scholar-workflow env-init`. It creates missing
   templates/records and a local Git repository without overwriting or pushing.
3. **Register API:** append the key record to `apis.yaml`, including owner and scope.
4. **Register server:** obtain consent to track the host, then append its connection and
   metadata to `servers.yaml`.
5. **Record environment:** update the server inventory. Put long rebuild procedures in
   `setup/<alias>/<env>.sh` and store only `setup_script` in YAML.

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
- Server capture is opt-in; do not auto-record incidental hosts.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
