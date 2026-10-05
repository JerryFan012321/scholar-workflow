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

## Portable inventory

The inventory contains `schema_version`, matching `project_id`, `title`, `summary`,
optional `language` (`en` by default, or `zh`), and up to 512 explicitly selected
`entries`. Each entry has a unique `entry_id`, `kind`, `title`, `purpose`, and `ref`.

`kind` is one of `code`, `paper`, `analysis`, `note`, `experiment`, `result`, or
`other`. These are small output groups, not a mandatory research taxonomy.
`purpose` explains why this particular material matters to the project.

Two reference forms are supported:

```json
{"kind": "project-file", "relative_path": "docs/design.md"}
```

```json
{"kind": "external-resource", "provider": "zotero", "resource_id": "<verified source identity>", "uri": null}
```

- `project-file` permits a project-relative file or directory and an optional full
  lowercase 40-character Git `commit`. No absolute paths, `..`, empty segments,
  backslashes, symlink traversal, or implicit root operations are accepted.
- `external-resource` permits `zotero` or `obsidian`, an explicit stable source ID,
  and an optional reader URI. IDs are not derived from the reader URI.
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

No Scholar config, Hub, cmux destination, Codex model, service port, or host registry
is required. `--language` changes only the returned presentation, not the manifest.
The `--json` mode keeps typed references and diagnostics for machine use.

Default Markdown is human-oriented: project goal, selected material, purpose, and
honest state. It omits machine IDs, hashes, and absolute root paths. Project file
links are relative to the project root: when saving this overview, save it at that
root or explicitly rebase the links for a different destination. Do not promise that
terminal stdout alone provides an interactive reading surface.

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
