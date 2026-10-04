# Explicit Single-Paper Ownership

Use for an already-ingested Zotero paper that has no Knowledge owner yet, inside
an explicitly registered writable Source/Field. This operation creates a new paper
companion note and its inventory/navigation declaration, not an analysis, migration,
PDF copy or new Zotero item. Check installed command support before using it.

```bash
scholar-workflow knowledge paper-plan \
  --source-id SOURCE_UUID --field-id FIELD_UUID \
  --item-key PAPER_KEY --attachment-key PDF_KEY \
  --segment stable-paper-segment --language en
```

The zero-write plan verifies the item, imported attachment membership and current
local PDF bytes through the Zotero Local API. It binds the selected roots, registry,
Field/provider revisions, readable note and navigation to a confirmation digest.
`--format json` returns the separate machine plan. Review the actual target and
note, then repeat the same selection with `knowledge register-paper`, adding
`--approved-digest HEX_DIGEST`. Confirm interactively, or use `--yes` only for the
already reviewed digest. The target is Field-local
`resources/papers/<segment>/Paper.md`; a root Field `.` needs no invented parent.

An existing folder is not adopted or overwritten. Existing resources, navigation,
notes and provider receipts remain intact; one Zotero item cannot acquire a second
resource identity. The allocated resource ID and paper-folder mapping are explicit,
not inferred from a filename. Library/PDF metadata remain authoritative in Zotero.

## Recovery and handoff

Registration coordinates the companion note, Field navigation and existing provider
with a persistent journal and conditional publication. It is a recoverable logical
transaction, not a filesystem-wide atomic write. After interruption, repeat the
exact approved request; publication continues only while each member is its recorded
before or after value. A concurrent human edit, root rebind, revoked capability or
changed source refuses recovery and retains the journal for explicit review.
Do not delete the journal, forge an owner or use an ordinary editor to force completion.

The registration result reports owner/resource identity, current snapshot/catalog
revisions and its registration receipt. It is **not** an analysis commit receipt or
verified backup. Pass that explicit resource and current revisions to the existing
`analysis commit-bundle` request, retaining its batch, three-file CAS, conformance
and source/reader checks. Apply only the returned explicit KnowledgeChangeSet through
the existing provider apply interface. Analysis, Canvas and sidecar stay beside the
companion note. Format and scientific/human assessment remain separate gates.

Existing legacy content and v4 joint migrations keep their independently reviewed
transaction interfaces. This new-folder registration does not adopt old analysis
packages or bypass Source first-registration review.
