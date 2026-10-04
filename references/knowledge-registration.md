# Independent knowledge folder registration

These commands use the existing portable `.scholar-workflow/fields.yml` and the
existing host Source registry. No Hub, cmux workspace, singleton Vault setting or
second identity store is required. A Source root may be a selected Vault subfolder;
this does not register its parent Vault or establish a PDF-reader identity.

## Native reader and document opens

Use `knowledge list --format json` to obtain the registered `source_id`.
`scholar-workflow knowledge reader SOURCE_ID --language en` resolves the unique
host-registered Obsidian Vault containing that Source (or `--format json`).
The reader Vault ID only routes native opens; the selected Source remains the
file-access boundary. Missing, duplicate or nested Vault matches fail closed.

Run `scholar-workflow knowledge open SOURCE_ID 'relative/note.md' --language en`
or pass an existing `.canvas` path to edit a Canvas in Obsidian. Paths are relative
to the Source, not its parent Vault; hidden paths, symlinks, missing files and other
types are refused. No Hub, cmux destination, Obsidian CLI or ZotFlow is required
for a native note/Canvas open. Success means the OS accepted an open request,
not that a window was observed or the document was human-approved. This command
does not establish knowledge ownership, commit an analysis or migrate content.
External edits after dispatch are controlled by the external application, not a
file lock held by this command.

For ZotFlow PDF projections, the containing Vault must separately pass the existing
audited-plugin/local-storage/attachment checks. Finding its reader ID alone never
proves that local PDF reading or annotation synchronization works.

## New single Field

1. Run `scholar-workflow knowledge preview ABSOLUTE_FOLDER --language en` (or `zh`).
   Review existing Markdown home, navigation, external writers and conflicts.
2. Choose one candidate's exact relative root, including `.` for a single subfolder.
   Run `scholar-workflow knowledge registration-plan ABSOLUTE_FOLDER --field-root RELATIVE_ROOT
   --language en`. This is zero-write; a ready plan supplies a confirmation digest.
   Machine output is available with `--format json`.
3. Review that exact scope. Run `scholar-workflow knowledge register ABSOLUTE_FOLDER
   --field-root RELATIVE_ROOT --approved-digest HEX_DIGEST --language en`. Confirm the
   local prompt. `--yes` is only for an already reviewed explicit digest, not discovery
   or blanket registration. Content, root identity, manifest or registry changes invalidate
   confirmation; review a fresh plan instead of silently accepting different bytes.
4. Run `scholar-workflow knowledge list --language en` or `--format json` to inspect
   registered Fields and their original navigation. Unavailable roots retain diagnostics.

Only the selected Field enters the manifest. No homepage, prose or Canvas is generated
or rewritten. Unselected sibling candidates are not registered. Store saved plan/results
outside the selected Source: adding them inside it changes the reviewed file set.

## Existing portable Source on a new host

Use `registration-plan ABSOLUTE_FOLDER --existing-source`, review **all existing
portable Fields**, then `register ABSOLUTE_FOLDER --existing-source --approved-digest
HEX_DIGEST`. This is an explicit host attachment, not multi-Field initialization.
The original source/field UUIDs, manifest bytes and documents stay unchanged.

## Refusals and completion

Legacy/managed paper analysis, analysis sidecars, old fixed-port Hub links or unsafe
paths block simple **new Field** registration. These require separately reviewed
joint content/identity migration, not filename changes or a forced manifest. Source
attachment preserves already-established portable ownership; it cannot certify the
old content's format or provenance. Conflicts, symlinks, nonregular/oversized text,
stale digests and an uncertain durable registry commit are not successful registration.

Completion means the selected manifest and host mapping are published using the
existing CAS/rollback rules, and `list` resolves their navigation. It does not certify
paper source fidelity, Canvas visual quality, canonical paper provider enrollment or
human acceptance. No Zotero, Notion, Codex, Git or other service is written or launched.
