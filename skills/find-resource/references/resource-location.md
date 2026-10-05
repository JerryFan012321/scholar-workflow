# Resource Location

How to resolve an existing resource to a local path (locate mode).

## Papers

1. Resolve the Zotero item key with `scholar-workflow zotero search` by DOI or
   title+authors, then confirm it with `scholar-workflow zotero get <key> --children`.
   See `identity-policy.md` for the exact check.
2. Read the item's child attachment record from the `get --children` result. Its key is
   the stable input for a direct reader action or attachment-key URI; data is queried live.
3. A paper that has been downloaded but not yet ingested has only its `paper_inbox`
   path; it is not in Zotero yet, so the existence check returns `none`.

## Technical documents

1. Look up the resource in the state mapping by `resource_id`.
2. Read the recorded Vault relative path.

## Output

Return the resolved path and do not copy the file:

- For imported papers, the child attachment key and a stable attachment-key reader URI
  (or the direct registered action when opening now), never a persistent Hub port URL.
- For technical documents, the Vault-relative path — see shared
  `references/storage-policy.md` for which root holds what.

If a resource is not found via the Local API or the state mapping, report it as missing
rather than guessing a path.

## Requested native opening

Locating a resource alone does not launch an application. When opening is requested,
use the user's chosen reader and location; native tool use needs no Hub, Scholar
workspace binding, or TaskRecipe registration. The workspace routes the window only.

### Local PDF in cmux

Resolve the parent and PDF child using the commands above. If the child record does
not include its locator, read that attachment with
`scholar-workflow zotero get <attachment-key>`. Use its live `links.enclosure.href`,
not an assumed `Zotero/storage/<key>` filename. Accept only a `file:` URI with an
empty or `localhost` authority, decode its path and verify that the local file exists.
A missing or non-local locator is unavailable: do not fetch a cloud attachment or
open a different similarly named file. Shared storage/annotation rules remain in
`${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`.

In the intended cmux workspace's own terminal, the shortest operation is:

```sh
cmux open "<resolved-local-path>"
```

`<resolved-local-path>` is a placeholder, not a persistent object identity. For a
programmatic call, pass it as one argument; do not interpolate provider text into
a shell command. Use the installed CLI's `open --help` to confirm capabilities.
If `cmux` is absent from PATH, use the verified application-bundled CLI executable.

The current terminal supplies the default workspace/surface. For a requested
override, obtain current handles with `cmux identify --json` (current location) or
`cmux list-workspaces --json`, then open with a currently resolved target:

```sh
cmux open "<resolved-local-path>" --workspace <workspace-handle> --focus true
```

`--pane <pane-handle>` or `--surface <surface-handle>` may select the requested pane;
handles belong to the current cmux instance and are not portable knowledge IDs.
When child-only control rejects an external agent CLI, keep that restriction.
Hand the command to the user in the target workspace, or use an authorized native
interface and a new empty terminal. Do not inject commands into an existing user
terminal, forge cmux environment context, read control credentials, or loosen settings.
Missing application, unsupported `open`, stale destination and control rejection
are distinct failures; do not silently fall back to another application or workspace.

### Other readers and completion

Use the stable Zotero reader URI for a requested Zotero open. For registered Vault
Markdown/Canvas, the public `knowledge reader/open` interfaces resolve the containing
Obsidian Vault; their contract is in
`${CLAUDE_PLUGIN_ROOT}/references/knowledge-registration.md`. ZotFlow PDF opening
requires its separately verified local-storage reader capability; a raw local PDF
open must not be described as ZotFlow Library Reader or annotation synchronization.

Report the resource, chosen reader/location, and observed result. A successful launch
means accepted, not displayed; report displayed only after observing the correct file
in that reader. Without that observation, keep display verification pending. Reading
convenience, link clicking and editing remain explicit human assessment where relevant.
cmux previews the original local PDF, not Zotero database annotations or a synchronized
Zotero reader. Preserve source bytes and ownership; no copy, import or writeback occurs.
