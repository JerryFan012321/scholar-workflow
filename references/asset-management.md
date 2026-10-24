# Personal research asset operations

`manage-assets` is the common entry; asset-specific stores remain authoritative.
This contract describes observable reads, writes and handoffs, not internal reasoning.

## Existing inventory before questions

```sh
scholar-workflow assets list --language en
scholar-workflow assets list --kind server --format json
scholar-workflow assets list --kind knowledge --format json
```

Query the relevant type before requesting an asset's name/path or connection data.
Reuse a unique available match. Only unresolved ambiguity, missing required facts,
unavailable access or an actual write conflict needs a question; show the discovered
candidates or specific gap. Do not ask the user to reconstruct an available inventory.
Do not select the first of several matches or treat an unavailable provider as empty.

For knowledge destinations, the list is the existing registered Source/Field inventory,
not a disk scan or an Obsidian Vault inventory. If native Vault discovery is needed,
use the available Obsidian CLI's read-only `obsidian vaults verbose` (check its help),
or its existing non-secret native Vault registry. Do not read plugin secret settings.
Questions about which libraries exist or whether registration missed one require
this native-inventory comparison, not another request for the user to supply a name.
Report known-but-unregistered Vaults separately; no query automatically registers them.
Registered-folder availability does not prove a native reader works or paper ownership.

## Stores and responsibility

| Asset | Authority | Current operation |
|---|---|---|
| Owned SSH server and recorded environments | `env_records_root/servers.yaml` from `config get env_records_root` | `assets server` commands below |
| Knowledge Source/Field | existing host registry and `.scholar-workflow/fields.yml` | assets read-only overview; `knowledge` owns registration and references |
| Known native Vault | Obsidian's own Vault inventory | read-only lookup; not a file-access grant |
| Scholar watchlist | global/project `recommend.yml` watchlist | existing `recommend-papers` author-ID workflow; not yet an assets CLI provider |
| Paper discovery/recommendation sources | existing `recommend.yml` sources and source-policy | existing recommendation configuration; not yet an assets CLI provider |
| Non-paper research publication channels | `research-sources.yml` | assets read-only overview; `track-research` owns registration and observation |

Adding a future asset type adds its real lookup/write adapter and result contract;
it does not copy that type into a generic registry. Zotero remains authoritative for
papers and attachments. Project Targets keep their own execution/output/environment
snapshots and reference server aliases, not credentials or another server inventory.
A registered Target is not proof that its alias exists or a remote connection works.

For explicitly selected researcher blogs, lab/company pages, releases or model
lists, `assets list --kind research` reads their actual authority. Load
`research-tracking.md` for registration/checks; no second generic asset entry,
automatic paper-watchlist migration, knowledge registration or scheduled task.

## Server capture, maintenance and reuse

An explicit request to record a server, or supplied connection information identifying
an owned server for the user's task, authorizes recording those non-secret facts.
This avoids a second generic “should I remember it?” prompt. Merely mentioning a
third-party host, encountering a URL, reading an imported document or seeing an SSH
log does not authorize capture. Existing uniquely matching records are reused first.
Match the recorded alias and supplied host/user/port; do not create a second server
merely because the user did not repeat its saved alias.
Conflicting aliases/connection facts need a specific choice; do not create another
alias to hide a conflict. Missing optional environment details remain unknown.

```sh
scholar-workflow assets server show gpu-example --language en
scholar-workflow assets server check --language en
scholar-workflow assets server register --spec server.json --language en
```

A minimal explicit registration input is:

```json
{"alias":"gpu-example","host":"gpu.example.test","user":"researcher","port":22}
```

The host is a non-executable example, not a live service. The JSON may add recorded
environments, purpose, notes and credential/key references supported by the server
interface. `credential_ref` accepts `env:NAME`, `keychain:NAME`, `secret-service:NAME`
or `credential-manager:NAME`; the identifier is a reference, never its value. `key`
is an SSH key file path, never key contents. These references are not resolved during
inventory or registration. New records require `alias`, `host` and `user`; `port`
is an integer 1–65535 when supplied (otherwise the display uses SSH's default 22).
Optional fields are `key`, `jump`, `credential_ref`, `environments`, `cuda_driver`,
`proxy`, `purpose`, `added` and `notes`. An environment contains `name` and optional
`python`, `cuda`, `key_packages`, `compat_notes`, `setup_script`; scripts remain safe
relative references under `setup/<alias>/`. Registration specs are bounded UTF-8 JSON
objects with unique keys, at most 64 KiB; unknown submitted fields are refused.
Use `--format json` for the actual current revision. A different same-alias
patch requires `--expected-revision REVISION`; omitted fields preserve existing facts.
An identical repeat is unchanged. New plaintext passwords/tokens are refused; a legacy
password is preserved but never returned. Do not pass secrets on the command line,
in specs or in a report. Credential storage/migration is separately scoped.

Reads do not initialize a missing ledger. An authorized registration may create its
missing private server ledger; it does not initialize API records, run Git or SSH,
read private-key contents or execute an environment script. Unsafe/symlinked roots,
duplicate aliases, malformed records and stale updates refuse rather than overwrite.
Read back the selected alias after success. Report recording and remote availability
separately: this interface does not test reachability or execute a task.

When a later task needs that server, use its saved alias, connection and available
environment metadata. Ask only for unresolved fields. Native SSH/cmux and the host's
permissions still govern the requested action; the ledger is not an execution broker.
Record newly supplied or observed facts only within that task's authorized scope;
do not probe a server merely to fill every field or invent a complete environment.

## Knowledge capture and reuse

Use the registered identity and actual folder mapping discovered above. For a native
open, `knowledge reader SOURCE_ID --format json` must resolve the containing Vault;
failure is distinct from a missing Source and must remain visible. Never rewrite the
host registration or choose another Vault silently to make a reader action succeed.

For a new explicitly selected knowledge folder, load `knowledge-registration.md`:
produce the zero-write preview/current registration plan and present its exact scope
before the existing confirmation. Do not re-ask a supplied/discoverable name or path.
Existing portable Sources use attachment, not new IDs. Native Vault selection alone
does not adopt papers, initialize lost provider inventory, move folders or migrate
old analyses. Paper ownership still uses `paper-registration.md` when actually needed.

## Human result

Use a compact table: **type, name, location/use, state, action**. Include relevant
diagnostics once, and state any provider/reader/ownership checks not performed. Distinguish
reused, created, updated, unchanged, uninitialized, unavailable and conflicted results.
Keep machine revisions/UUIDs in JSON or a requested technical supplement; credentials
never appear. A successful register receipt plus read-back proves recording, not SSH
reachability, GUI display or human approval. No extra persistent summary is required.

## Machine result interface

- `assets list --format json` returns `{schema_version: 1, status, providers}`.
  `providers.server` is `{schema_version: 1, status, revision, servers, diagnostics}`;
  `providers.knowledge` contains `status`, `revision`, `sources`, `diagnostics` and
  the inventory-only `scope`. Each Source retains its stable `source_id`, `folder_id`,
  enabled state, declared root/verification state, Fields and diagnostics. `--kind`
  includes only the requested provider. A provider failure stays visible and makes
  the combined result partial, without discarding the other provider's entries.
- `server show --format json` returns `{schema_version: 1, status: "available",
  revision, server, diagnostics}`. `server` is the single sanitized record, not a
  raw YAML blob. Unknown aliases are input errors; absent ledgers are dependency gaps.
- `server register --format json` returns `{schema_version: 1, status, revision,
  server}` with `created`, `updated` or `unchanged`. `revision` is the top-level
  whole-ledger `sha256:<64 hex>` value, not a per-record version. Identical replay is
  byte-stable; mappings patch submitted fields, while explicitly submitted lists replace
  that list. Omitted fields, unrelated records and legacy secret values are preserved.
- `server check --format json` returns the sanitized server inventory. It does not
  initialize or connect. Missing ledger exits 3; invalid/unsafe state exits 7. Same-alias
  change without explicit current revision exits 5, stale approved revision exits 7,
  invalid input exits 2, and an uncertain post-publication write exits 6. No refusal
  message repeats raw parser/spec/credential values. Legacy recognizable secret presence
  and missing/unsafe declared setup paths remain diagnostics, not remote probes.
