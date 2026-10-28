# Vault connections and explorer environments

Use one product implementation with separate personal and test runtime contexts.
Connections use the existing host folder/Source registry, not a second knowledge
database. A read-only connection does not create a paper identity.

## Runtime environment

Personal mode is the default for `knowledge explore --root SELECTED_FOLDER`. It
permits multiple explicitly selected safe Vaults or subfolders. The selected root
owns the exploration file; connected folders retain their original documents.

For isolated development or installed acceptance, explicitly select test mode:

```sh
scholar-workflow knowledge explore --root /chosen/test/vault \
  --environment test --state-root /chosen/test/state --test-root /chosen/test/vault
```

Test mode requires separate state and allowed roots. It refuses personal state,
foreign enabled registry folders, symlink traversal and out-of-scope roots. Missing
test state is an empty test inventory, never personal-state fallback. Requests
recheck the boundary. Browser requests cannot switch environments or state paths.
Test sessions disable ambient Zotero enrichment, native reader resolution and
native asset launches. Explicitly opening the explorer's own browser UI remains
available. This does not sandbox an independently launched
agent or editor at OS level.

The header shows mode, selected folder and actual package version. Each server
has an independent token and lifetime; a different port alone is not isolation.
Test startup does not stop a personal service.

## Connect and inspect

1. Choose **Add Vault/folder**. The system picker returns a folder to the server;
   the browser receives only a short-lived candidate ID.
2. Review the bounded inspection and three independent readiness layers below.
   Partial inspection requires a smaller selection for detailed preparation.
3. **Preview necessary adjustments** rechecks the candidate and lists relative
   files, proposed operations and reasons; it does not apply a content migration.
4. **Connect read-only** confirms that candidate and the exact registry revision.
   Changed content, expired candidates and identity/CAS conflicts need a fresh
   selection. Read back the completed connection.
5. Open a connected folder to read inspected Markdown. Hidden settings, symbolic
   links, executable content and out-of-scope paths are excluded.

A new folder-only connection writes a read capability into the existing registry.
It creates no portable manifest, provider, analysis or owner. A valid portable
Source can attach read-only while preserving IDs and Fields; a missing historical
provider remains a diagnostic. Existing capabilities are not silently changed.

| Layer | Evidence required | Capability |
|---|---|---|
| Safe reading | Explicit selection and safe readable files | Read documents despite local format imperfections |
| Paper references | Source/Field, existing unique owner and declared assets | Reference complete paper units |
| Managed updates | Selected conformance, writer, baseline and transaction checks | Prepare a separate reviewed analysis/migration update |

Do not certify formats that inspection has not evaluated. Missing plugins, old
links or sidecars affect their corresponding capabilities, not safe reading.
Unknown Markdown remains a document, not a paper-shaped graph node.

Previews distinguish host connection metadata, portable registration preparation
and optional content review. Old links require identity-confirmed targets; never
guess replacements. Prose, five-branch editable Canvas, sidecars, figures and
accepted layouts stay unchanged. Actual content modifications continue through
the existing registration/analysis workflows and their CAS/recovery contracts.

## HTTP contract

All calls retain session authentication and same-origin checks:

- `GET /api/environment`: mode, selected folder name, version and native capability.
- `GET /api/vaults`: current environment connections.
- `POST /api/vaults/choose` with `{}`: system picker and inspection.
- `POST /api/vaults/preview` with `{candidate_id}`: zero-write adjustments preview.
- `POST /api/vaults/connect` with `{candidate_id, expected_revision}`: reviewed
  read-only host connection; browser absolute paths are refused.
- `GET /api/vaults/{connection_id}/documents`: inspected Markdown navigation.
- `POST /api/vaults/document-preview` with `{connection_id, relative_path}`:
  bounded plain-text reading, without embedded execution.

Connection operations preserve research drafts, selections and exploration
revisions. They do not auto-save research edits or insert pages into paper units.
