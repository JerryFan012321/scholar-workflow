---
name: manage-assets
description: Register, query and reuse personal research assets, starting with owned servers and knowledge libraries. Use for 'manage my research assets', 'remember this server', 'which knowledge libraries do I have', '资产管理', '登记服务器和知识库', '有哪些知识库', or when another task needs a saved personal host or knowledge destination. Not cloud-account inventory, arbitrary disk discovery, paper ingestion or remote execution.
---

# manage-assets

One operational entry for personal research assets, not another database or execution
control plane. Load `${CLAUDE_PLUGIN_ROOT}/references/asset-management.md` before
querying, recording or reusing an asset.

## Observable operations

- **Query/reuse:** read the relevant existing inventory before asking the user for
  asset names, paths or connection details. A unique available match is reused;
  ambiguity shows the actual candidates. Missing or unavailable records are distinct.
- **Capture:** when the user supplies an owned server or explicitly selects it for
  their task, register the supplied non-secret facts as part of that task and report
  the result. Missing facts remain unknown. Incidental third-party hosts are not
  automatically collected. Registering a knowledge folder uses its existing reviewed
  Source/Field operation, not server-ledger writes.
- **Maintain:** add only new facts, or explicitly update the selected record against
  its current revision. Preserve other records, credentials and source content;
  conflicts require a choice rather than silent replacement.
- **Use:** hand the selected stable alias/Source/Field and available metadata to the
  task's owning skill or native tool. Registration alone does not authorize a login,
  command, upload, migration or knowledge-content write.

## Result

Return a compact human table of type, name, location/use, state and the action actually
taken: reused, created, updated, unchanged, unavailable or conflicted. Include only
affected diagnostics and the next necessary choice. No credential values, hash dumps
or machine IDs in ordinary prose; machine output may retain revisions and identities.
Read back a completed write before reporting it as recorded. Report discovery,
registration, reader resolution and actual use separately.

## Supported boundary

Servers and registered Knowledge Sources/Fields have local CLI interfaces. Known
Obsidian Vaults are a separate read-only native inventory. Scholar watchlists and
paper-source settings retain their existing recommendation store; this slice does
not add those providers to `assets list` or create a generic asset registry.

## Constraints

- Queries never initialize, register, connect, scan arbitrary directories or change
  existing permissions. A failed inventory is not an empty one.
- Store non-secret server metadata and credential references only. Existing legacy
  plaintext credentials are neither displayed nor silently migrated/deleted.
- Keep each asset's original authority and the user's selected scope. A Vault known
  to Obsidian is not automatically a registered Source or a paper owner.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/asset-management.md` — actual commands, stores,
  capture/reuse boundaries and extension points.
- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
