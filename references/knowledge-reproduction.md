# Portable Knowledge ownership reproduction

Use for an explicitly requested Source replay on another host or registered root.
Check that the installed CLI exposes `knowledge reproduction-plan`, `restore-plan`
and `restore` before using this contract; older installations do not support it.
No Hub, workspace binding, private provider initializer or inferred file owner is needed.

## Replay input and authority

`knowledge reproduction-plan --source-id SOURCE_ID --format json` exports a version-1
package (public schema: `contracts/knowledge-reproduction-package.schema.json`).
It retains Source/Field IDs, explicit resource and artifact ownership, relations,
portable navigation and hashes of every declared file. The current provider is still
the authority; the export is a frozen replay input, not another mutable knowledge root.
Host root bindings, provider receipt history and runtime diagnostics are removed.
Bodies, PDFs, credentials and application settings are not embedded or downloaded.

Every owned analysis must contain its conformant Markdown/Canvas/sidecar trio in
the same paper folder. Declared artifacts/assets must match their physical hashes.
Home/navigation paths are Field-relative; file inventory paths are Source-relative.
The explicit inventory also binds portable manifests, including absence of artifacts.yml.
Missing, unsafe, changed or incomplete members refuse export rather than producing
a misleading partial package. `--format md --language en|zh` gives a separate readable
summary; it does not provide the complete replay input.

## Restore in a new registered location

1. Save the JSON export outside the Source being checked. Explicitly copy the selected
   Source's inventory files with their relative paths and exact bytes to the chosen root.
   Do not copy the old host provider state, receipt directory or Zotero attachment storage.
   Copying unrelated files is not part of this interface and does not adopt them.
2. Attach the copied existing portable Source through
   `knowledge registration-plan /absolute/copied-root --existing-source` and
   `knowledge register /absolute/copied-root --existing-source --approved-digest HEX`.
   See `knowledge-registration.md`. This preserves original IDs/manifest bytes and
   requires an explicit destination choice; it alone does not restore the provider.
3. With Zotero running locally for a Source containing papers, inspect:

   ```bash
   scholar-workflow knowledge restore-plan --source-id SOURCE_ID \
     --package /absolute/replay-input.json --language en
   ```

   `--format json` records the complete reviewed plan. It binds package file bytes,
   current host registry, destination directory identity, complete file hashes and
   Local API paper/attachment ownership and PDF hashes. Source spans additionally
   require their current attachment hash/library and annotation membership, or a
   registered document/block within this Source. Unknown external Vault spans require
   a separate supported source mapping; this operation cannot silently adopt them.
   Legacy non-SHA256 PDF evidence hashes must be reverified through the normal paired
   analysis update before restoration. Never bypass a stale source locator.
4. Review the root, identities, read set and outstanding reader checks, then run:

   ```bash
   scholar-workflow knowledge restore --source-id SOURCE_ID \
     --package /absolute/replay-input.json --approved-digest HEX --language en
   ```

   Confirm locally. `--yes` is for an already reviewed exact digest. The operation
   creates only the missing host provider and a separate recovery journal. It never
   overwrites an existing provider or changes Markdown, Canvas, sidecars or portable
   manifests. Read-only/disabled/unregistered roots refuse restoration.
5. Retry the exact restore command after interruption; the prepared journal permits
   continuation only if authority, input and file bytes still match. The same completed
   request returns its receipt, not a new execution. Conflicts retain the journal and
   existing values for explicit recovery, without reverting concurrent edits.

## Reader and completion handoff

Saved ZotFlow Vault IDs are host-local routing values. Each restored analysis reports
`binding-matched`, `rebinding-required` or `reader-unresolved` against the destination's
non-secret Obsidian registry. Identity matching is not a plugin/local-PDF capability
probe or proof that a window opened. A mismatch does not affect folder authorization.
Rebind through a normal paired `analysis stage-update`/`commit-bundle` with fresh
base hashes and verified reader capability, never hand-edit one managed file.

The restore receipt reports `ownership-restored`, unchanged content and current source
identity checks. It deliberately leaves full reproduction, scientific support, reader
launches and human acceptance unverified. Source hash/membership checks do not grade
quotation fidelity, page interpretation or scientific entailment. Use `analysis check-bundle`
for the copied pair and native `knowledge reader/open` for explicit display; evaluate
the same output/source contracts as the original. Show the user which note/Canvas to
open, which source links to click, and what remains pending.

A replay succeeds in full only when ownership, format, external-tool links and the
required human/source assessments are all evidenced. A recovery journal/export is
not a verified backup and does not authorize copying other Sources or migrating a library.
