# Project Material Context

This is the result contract for integrating one project's code, papers, knowledge,
experiments, and results. It is not a new storage system, Hub catalog, task queue,
or synchronization service. Human output also follows `human-presentation.md`.

## Ownership

- `project-layout.json` owns the stable project identity and accepted source/config
  profile. Its schema remains version 2.
- Optional root-level `project-context.json` owns this project's explicit selection
  of material and each item's purpose. Its schema is version 1, defined in
  `contracts/project-context.schema.json`.
- Project files, experiment records, Zotero objects, and Vault documents keep their
  existing ownership. An index entry never creates a second authoritative body.
- Run/Attempt/Target/Artifact records and promotion/backup state remain governed by
  Project System v2. Referencing an experiment report does not validate its lifecycle.
- An explicit copy is independent content. An external reference is only a locator;
  neither establishes live synchronization or permission to modify the source.

No mandatory homepage is generated. A person may maintain an existing README/note,
or request the read-only overview on demand. Do not scan directories to fill entries,
infer paper identity from similar titles, or invent results to make an index complete.

For an explicitly requested rich internal `PROJECT.md`, use `organize-project` and
`project-entry.md`. It adds a human document with current state, module diagrams,
selected archive links and one plan, not another inventory. Generic initialization
does not create that researched document. Explicit research-parent initialization
creates only an empty six-section PROJECT and empty inventory, with one inline plan;
it does not select materials or inspect research facts. The short `overview` command
does not render the rich document.

## Portable inventory

For research-parent/remote-child organization, use `project-management.md` for the
ownership and capability boundary. Child registration remains in the separate
management declaration, not this inventory. The additive `execution-code` reference
below identifies selected child code without embedding a host, path root or credential.

The inventory contains `schema_version`, matching `project_id`, `title`, `summary`,
optional `language` (`en` by default, or `zh`), and up to 512 explicitly selected
`entries`. Each entry has a unique `entry_id`, `kind`, `title`, `purpose`, and `ref`.

`kind` is one of `code`, `paper`, `analysis`, `note`, `experiment`, `result`, or
`other`. These are small output groups, not a mandatory research taxonomy.
`purpose` explains why this particular material matters to the project.

Three reference forms are supported:

```json
{"kind": "project-file", "relative_path": "docs/design.md"}
```

```json
{"kind": "external-resource", "provider": "zotero", "resource_id": "<verified source identity>", "uri": null}
```

```json
{"kind": "execution-code", "child_project_id": "22222222-2222-4222-8222-222222222222", "relative_path": "src/train.py", "commit": null}
```

- `project-file` permits a project-relative file or directory and an optional full
  lowercase 40-character Git `commit`. No absolute paths, `..`, empty segments,
  backslashes, symlink traversal, or implicit root operations are accepted.
- `external-resource` permits `zotero` or `obsidian`, an explicit stable source ID,
  and an optional reader URI. IDs are not derived from the reader URI.
- `execution-code` belongs only to a `code` entry and identifies a distinct child
  UUIDv4, a safe child-relative POSIX path, and an optional full commit. A path of
  `.` explicitly selects the child root; other paths follow project-file safety.
  No host, credentials, command, URL, Target or absolute path is accepted in this ref.
  Schema 1's existing forms remain unchanged; older installations may reject the
  new form, so check the installed help/version before updating a real inventory.
- Supported read routes are Zotero `open-pdf`/`select`, Obsidian `open`, and a Zotero
  object's Obsidian `zotflow` Library Reader projection. Unknown command routes,
  duplicate/unknown parameters, malformed encoding, or credentials are rejected.
- Obsidian `open` requires a Vault name and Vault-relative `file`; optional `block`
  is a reading locator. ZotFlow requires `vault`, `type` (`open-attachment` or
  `open-annotation`), `libraryID`, and `key`. Attachment navigation may contain only
  a nonnegative `pageIndex` JSON value. Zotero `page` is a positive physical page.
- A ZotFlow reader projection still has provider `zotero`. Its existence does not
  change annotation authority or claim that synchronization has been verified.

Public JSON Schema checks structure and basic URI/path shape. Runtime validation
also checks canonical UUIDs, unique IDs, known reader parameters, and file safety.
Neither proves scientific correctness or external object availability.

## Read-only commands

In a released installation containing these commands:

```text
scholar-workflow project context-template --project-root <project> --language zh
scholar-workflow project validate-context --project-root <project>
scholar-workflow project overview --project-root <project>
scholar-workflow project overview --project-root <project> --language en
scholar-workflow project overview --project-root <project> --json
scholar-workflow project validate-context --project-root <project> --context-file project-context-candidate.json
scholar-workflow project overview --project-root <project> --context-file project-context-candidate.json
```

`context-template` prints an empty, editable inventory with the existing project ID.
It does not write a manifest. Explicitly save and populate it only when requested;
never overwrite an existing inventory implicitly. `validate-context` validates the
declared inventory. `overview` checks only its declared local locators, without
network requests, Git execution, directory discovery, copying, or launching tools.

For an explicitly selected draft, `--context-file NAME` chooses one root-level JSON
declaration instead of the active inventory. It uses the same bounded, no-symlink reader
and requires the same project identity; a missing/invalid candidate stops rather than
falling back to `project-context.json`. Names use the existing declaration convention:
lowercase letter first, then lowercase letters, digits or hyphens, followed by `.json`.
Paths and absolute filenames are rejected. Preparing that candidate is separate from
these read-only commands; an existing candidate or active inventory is not overwritten.
Markdown and validation output explicitly state that this is a candidate preview and
the active inventory has not been replaced. Candidate JSON retains the usual overview
fields and adds `preview: true` and `context_file`; default JSON is unchanged.
Preview success is not approval, application, source verification or human acceptance.

The default commands require no Scholar config, Hub, cmux destination, Codex model,
service port, or host registry. `--language` changes only the returned presentation, not the manifest.
The `--json` mode keeps typed references and diagnostics for machine use.

For execution-code, the overview checks whether the child is declared by this
research parent. An undeclared child remains a missing row, not silently adopted;
an unavailable management declaration remains unverified. A declared child is still
unverified remotely. Markdown shows its purpose and relative code location without
machine IDs, fake local links or a generated SSH/VS Code link. Ordinary overview does
not consult server inventory or infer an execution destination.

Default Markdown is human-oriented: project goal, selected material, purpose, and
honest state. It omits machine IDs, hashes, and absolute root paths. Project file
links are relative to the project root: when saving this overview, save it at that
root or explicitly rebase the links for a different destination. Do not promise that
terminal stdout alone provides an interactive reading surface.

## Execution-child code location preview

Use only a normally installed version whose `project --help` exposes this command:

```text
scholar-workflow project remote-code-plan --project-root <parent> --entry-id <code-entry> --target-id <target> --json
scholar-workflow project remote-code-plan --project-root <parent> --entry-id <code-entry> --target-id <target> --env-records-root <existing-ledger-root> --json
```

The selected entry must use execution-code and its child must be registered. This
read-only operation uses exactly the selected existing
`experiments/profiles/targets/<target>.yaml` and its server alias in the existing
private servers.yaml authority. Without an explicit ledger root, use the configured
env-records location. Do not create another registry, discover a server, choose the
first Target, or copy credentials into project files. Unlike ordinary overview, this
explicit operation needs those local declarations to be available.

Only a matching SSH Target with a non-root, absolute POSIX project directory is
accepted. Its safe relative code location is joined as data, never as a command.
Missing/conflicting/unsafe declarations and detected byte changes fail without
writing. JSON returns the qualified identities, selected Target, remote location,
requested commit, nonsecret connection metadata, input baselines, and separate
unverified child/path/commit/access/SSH-config states. It excludes key paths, credential
references, environment bindings and raw ledger contents. Keep this machine locator
private; it is not a human PROJECT body or a portable host registration.

The output status is `declared_not_remote_verified`: choosing a Target does not prove
that its directory contains this child. This command does not connect, inspect remote
files or Git, launch VS Code/cmux, verify an SSH config alias, or grant edit authority.
Native tools retain their routing/authentication policy; verify the remote child's
management identity and requested commit before an authorized edit. Do not generate
a clickable remote link from an unverified alias or call this a successful native open.
This is an operational declaration preview, not a recovery copy or verified backup.

## Optional registered ownership check

Available from 0.42.0. Verify the normally installed version and its
`project overview --help` before using these options:

```text
scholar-workflow project overview --project-root <project> --resolve-knowledge
scholar-workflow project overview --project-root <project> --resolve-knowledge --knowledge-registry <sources.json> --json
```

`--resolve-knowledge` checks selected `obsidian` object IDs against the existing
registered Source/Field and provider declarations. The default registry is the
existing `hub/sources.json` beneath `SCHOLAR_WORKFLOW_HOME`; this legacy path does
not require a Hub service. `--knowledge-registry` explicitly selects another state
domain and requires `--resolve-knowledge`. No registry, lock, directory, or copy is
created. An unavailable registry path is an input error.

This initial check covers primary Markdown, declared supporting documents, and
provider artifacts, including analysis Canvas and sidecars. Asset ownership remains
in the existing `assets.yml` contract; this command does not inspect image relations
or add Field references.

The check reads bounded declarations only and inspects the selected files and their
primary owner files without reading their bodies. It rejects symlink traversal in
declarations, registered roots, and object paths. It observes declarations again to
detect changes during inspection, without claiming a filesystem-wide atomic snapshot.
Disabled, unreadable, inconsistent, or changed registered Sources prevent confirmation
of uniqueness; a known duplicate primary remains a conflict. It does not scan disk,
infer identity from filenames, query Zotero, or launch readers.

JSON adds `knowledge_ownership`, keyed by project `entry_id`, while retaining the
existing entries, refs, and states. Each check has `object_id`, `status`, `locations`,
`owner_candidates`, `issues`, and `reader_state: unverified`. Locations keep Source,
Field, object and primary owner identities, Source-relative paths, and `file_state`.
Human Markdown separates declaration ownership, selected file state, primary owner
file state, and the unverified reader, without exposing machine IDs or absolute roots.

| Ownership status | Meaning |
|---|---|
| `resolved` | The selected stable ID and its primary owner have unique checked declarations. |
| `not_found` | No matching ID appears in the completely checked declarations. |
| `conflict` | Multiple locations or primary owners are declared; none is selected. |
| `incomplete` | Some declarations cannot be checked; uniqueness is not asserted. |

File states are `available`, `missing`, `unsafe`, or `not_checked`. A missing file
does not erase its declared identity; an available analysis does not hide a missing
primary owner. Declaration resolution does not verify body metadata, scientific
support, reader URI correctness, or whether different IDs refer to the same paper.
Cross-Source registration deduplication and Field reference writes are separate
operations under `paper-registration.md` and `knowledge-registration.md`, never
side effects of this read-only check. Check the installed version's supported entries.

## State and failure meaning

| State | Meaning and safe next action |
|---|---|
| `available` | Local file/directory exists. Content and execution are not evaluated. |
| `missing` | Declared local locator is absent. Correct the inventory or restore the file. |
| `unsafe` | Locator cannot be inspected safely, e.g. a symlink. Resolve explicitly; do not follow it. |
| `unverified` | External object/reader was not queried, or a declared commit was not checked. Verify in the owning tool. |

A missing/invalid layout or inventory, duplicate ID, identity mismatch, or invalid
reader URI stops the command with an input error. Individual missing/unsafe local
entries remain visible in an otherwise valid overview. A printable external link is
not an assertion that the app, plugin, attachment, or account is available.

The optional inventory grants no execution or write capability. Native cmux actions
and external Codex/CLI use remain separate, under the host's ordinary authorization;
none are launched by these commands.

## Current delivery boundary

This contract ships in the 0.31.0 project-centered hotfix. Its source unit/contract
regression passed 1,313 cases; human and installed-product functional evaluation remain
separate. Editing these files alone never updates an installation. Legacy Hub entry points remain for
compatibility, including some existing Field transaction paths; their retention does
not make Hub the owner of the new project overview.
Candidate preview is a later capability; use it only when the installed command's
help exposes `--context-file`, not by importing private models or changing the active
inventory just to render a draft.
