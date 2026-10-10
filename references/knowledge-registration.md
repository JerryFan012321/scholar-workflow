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

For a genuinely new Source, the plan explicitly includes
`inventory_initialization: new-empty-provider`. The reviewed digest binds this action.
Confirmation initializes a bound empty provider, publishes the portable Field manifest,
then publishes the host registration. Existing Markdown is not adopted as paper owners.
Adding a Field to an existing Source preserves its provider; it is not empty initialization.

First-Source creation uses a persistent host-local journal and per-member CAS. After
interruption, repeat the original `register` command and digest, not an unrelated fresh
plan: recovery first reads its frozen Source/Field IDs and before/after members. Changed
prose, roots, registry or published members refuse continuation and retain the journal.
The journal checksum never authorizes members outside the reviewed scope. This is a
recoverable logical transaction, not a filesystem-wide atomic write or a verified backup.
Exact completed replay is byte-idempotent only while these creation members remain
unchanged; later legitimate changes require their own operation, not replay of creation.

## Existing portable Source on a new host

Use `registration-plan ABSOLUTE_FOLDER --existing-source`, review **all existing
portable Fields**, then `register ABSOLUTE_FOLDER --existing-source --approved-digest
HEX_DIGEST`. This is an explicit host attachment, not multi-Field initialization.
The original source/field UUIDs, manifest bytes and documents stay unchanged.
This attachment never initializes a missing provider. An absent historical inventory
is unknown, not empty; restore its explicit inventory before new paper enrollment.

## Portable Field references

The portable Field manifest accepts two explicit versions. Schema 1 keeps its
original fields and serialization; even an explicit empty `references` field is
invalid in version 1. Schema 2 additionally permits each Field's `references`:

```yaml
references:
  - reference_id: ref:method-comparison
    target:
      source_id: abcdefab-cdef-4abc-8def-abcdefabcdef
      object_id: paper:zotero:123:JKLM2345
    purpose: Compare the existing method without copying its paper package.
```

This example shows the shape, not a real resource. Each record has exactly these
three fields. The reference ID is a lowercase portable ID of 2–128 characters;
the target is a canonical Source UUID and stable object ID, not a path or URL.
Purpose is required clean text of 1–2000 characters. A Field permits at most 512
references, with unique reference IDs and qualified target pairs. Other Fields
may select the same target. Paper units use their existing resource ID; explicitly
selected analyses/Canvas use their declared supporting/artifact ID.

References express relevance, never another owner or file-access grant. They do
not enter local Markdown navigation, copy bodies, move packages, synchronize
stores, or cascade deletion. Real owner, owning Field and relative paths continue
to come from the existing provider. Source reproduction retains reference metadata
and its manifest bytes, but does not export externally referenced bodies or PDFs.
Attaching the reproduced Source does not prove its external targets are available.
Existing append/migration paths preserve the manifest version and references;
legacy Field overrides cannot use navigation changes to remove or replace them.

`scholar-workflow knowledge list --language en` displays the selected purposes
without inspecting providers or claiming their targets are verified. Use
`scholar-workflow knowledge list --resolve-references --language en` (or `zh`,
or `--format json`) for an explicit read-only provider check. It distinguishes
resolved, not found, conflict and incomplete ownership, current file availability,
and an unverified reader. An unreadable/disabled/unregistered target or Source
mismatch remains visible. Qualifying a target by Source never hides duplicate
owners elsewhere in the registered Source set. Neither command launches a reader.
Listing also retains the existing bounded owner-header checks for local navigation;
reference resolution itself reads declarations and file metadata, not paper bodies.

### Add or remove one reference

The development implementation provides `knowledge reference-plan` and
`knowledge reference`; it is not yet in the normally installed 0.42.0 package.
Select the referencing Source/Field and an explicit existing object; never infer
ownership from a title or a similarly named file.

```sh
scholar-workflow knowledge reference-plan --source-id SOURCE_UUID --field-id FIELD_UUID \
  --operation add --reference-id ref:method-comparison --target-source-id OWNER_SOURCE_UUID \
  --object-id OBJECT_ID --purpose 'Compare the method without copying its paper package.'
scholar-workflow knowledge reference --source-id SOURCE_UUID --field-id FIELD_UUID \
  --operation add --reference-id ref:method-comparison --target-source-id OWNER_SOURCE_UUID \
  --object-id OBJECT_ID --purpose 'Compare the method without copying its paper package.' \
  --approved-digest HEX_DIGEST
```

The zero-write plan displays the Field, selected local reference name, exact action, purpose, resolved relative
file and confirmation digest. Use `--language zh` for Chinese or `--format json`
for machine identities/read-set diagnostics. Apply repeats the exact selection
with its current 64-hex digest and an interactive confirmation; `--yes` skips only
that prompt after the exact plan has been reviewed.

Adding requires a globally unique declared owner across registered Sources,
matching target Source and available target/primary files. A disabled, missing,
conflicted or changing declaration refuses addition. An identical existing record
is unchanged; a different record with the same ID, or the same target under a new
ID, refuses replacement. The first addition upgrades schema 1 to 2.

To remove, preview and confirm `--operation remove --reference-id REFERENCE_ID`
with the same referencing Source/Field. Do not pass target or purpose arguments.
Only that exact local selection is removed. Target registration, providers and
readers are not consulted, so offline references can still be cleaned up. Other
references, owners and all content remain unchanged; schema 2 never downgrades.

Only the referencing `fields.yml` changes; unrelated Fields, navigation and YAML
comments remain. Host coordination locks are not a second inventory. Approval
binds registry/declaration bytes and inode identities, registered directories and
selected file metadata. Apply rechecks under registry → sorted provider (add only)
→ selected Vault locks, then publishes one complete manifest using bounded,
nonblocking CAS reads. This is not a filesystem-wide transaction against arbitrary
external writers and does not freeze target content after confirmation.

Unlike multi-file Source creation, this single-file change has no recovery journal.
If durability or publication cannot be confirmed, exit 6 reports an uncertain
outcome, not success or “nothing written.” Inspect a fresh plan; do not roll back
or reuse an old digest. A fresh identical-add plan reports unchanged and its
confirmation checks current durability. Stale/unsafe approvals refuse with exit 7.
Save plans outside Source roots. Neither completion nor a direct manifest edit
proves reader behavior, scientific support, installed or human acceptance.

## Refusals and completion

Legacy/managed paper analysis, analysis sidecars, old fixed-port Hub links or unsafe
paths block simple **new Field** registration. These require separately reviewed
joint content/identity migration, not filename changes or a forced manifest. Source
attachment preserves already-established portable ownership; it cannot certify the
old content's format or provenance. Conflicts, symlinks, nonregular/oversized text,
stale digests and an uncertain durable registry commit are not successful registration.

Completion means the selected manifest and host mapping are published, and `list`
resolves their navigation. A genuinely new Source also has its explicitly bound empty
provider; existing Source attachment/Field append does not recreate one. It does not certify
paper source fidelity, Canvas visual quality, canonical paper provider enrollment or
human acceptance. No Zotero, Notion, Codex, Git or other service is written or launched.
