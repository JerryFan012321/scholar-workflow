# manage-assets

The shared entry for finding, recording and reusing personal research assets. It
checks existing records before asking you to repeat a server name or library path.

Start with `scholar-workflow assets list --language en`. To record an explicitly
selected owned server, supply its non-secret JSON metadata to
`scholar-workflow assets server register --spec server.json --language en`.
Show/check commands and exact update semantics are in the shared
[asset contract](../../references/asset-management.md).

Servers remain in the configured personal ledger; knowledge remains in the existing
Source/Field registry and Vault manifests. No remote login or Vault migration is
implied. `assets list --kind research` also queries the non-paper channel authority;
`track-research` owns its registration/check workflow. Recommendation author IDs
and paper-feed settings remain in `recommend.yml`, without automatic migration.
