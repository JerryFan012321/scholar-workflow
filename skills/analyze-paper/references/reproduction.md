# Reproducible Paper Analysis Package

Use only when the user requests an exemplar or reproducible/replayable package.
The required five-branch output and evidence contract remain owned by the analysis
template and selected version. This reference adds operational inputs and receipts,
not a prescribed research or reasoning sequence.

## Required companion material

Place the selected paper's readable analysis, editable Canvas and machine sidecar
together with a non-secret CLI request and a short replay note. The request records
the actual versioned IR, profile, language, source spans and chosen capacity. The
replay note records the installed plugin/CLI version, input and source hashes,
expected file names, invoked public command, actual conformance result and outstanding
source/visual checks. Keep machine details outside the analysis prose.

PDFs remain in Zotero; do not redistribute private attachments, keys, complete
application settings or host environment dumps. Host-local Vault IDs and roots are
reader/location projections, not portable identities. Resolve and verify them in
the destination environment before replay; changing those values requires fresh
input hashes and a new batch identity, not reuse of a previous success receipt.

## Installed replay entry

Inspect the explicitly selected Vault or subfolder with
`scholar-workflow knowledge preview ABSOLUTE_FOLDER --language zh` (or `en`).
Use `--format json` for the separate machine preview. This installed entry needs
neither Hub nor a workspace and writes no manifest, registry or document. It lists
candidate/existing Fields, navigation, unmapped prose, external writers and conflicts.
The printed new candidate identities are provisional; no process-local confirmation
token is exported. A preview does not register a Source, create a homepage, approve
an existing-document transaction or certify paper content. Registration/commit still
uses its independently reviewed boundary.

Check an already displayed package without generating or committing it:

```bash
scholar-workflow analysis check-bundle /absolute/paper-folder \
  --markdown 'Paper Analysis.md' --canvas 'Paper Tree.canvas' \
  --sidecar 'analysis.baseline.json' --require-ir 5 --language en
```

Use the actual three filenames; the Markdown filename must match the sidecar's
`note_stem` for its Canvas backlinks to resolve. `--format json` provides the separate
byte-hash and finding record. Exit 0 means conformance and baseline consistency;
exit 7 reports a nonconformant pair and exit 2 rejects invalid/unsafe input. No
registry, batch database, Hub, external reader or network is consulted. Safe editor
metadata does not cause false drift; an edited baseline is not silently re-trusted.
The check does not establish PDF/source truth, live links, human visual acceptance
or canonical ownership. It checks exactly one explicit package, not an entire Vault.

Use `scholar-workflow analysis batch-run --request INPUT --state-db DB --stage-root STAGE`
with exactly one selected paper if the exemplar is single-paper. See `analysis-batch.md`
for identity, failure cleanup and one-repair semantics. Choose a new explicit batch ID
and staging location for an independent replay; the same completed ID is an idempotent
lookup, not proof that the model regenerated or reran the analysis.

This command stages fixed names such as `analysis.md` and `analysis.canvas`. A staged
Canvas's Markdown backlinks use the request's `note_stem`, so staging files are not
automatically a navigable Vault presentation. An explicitly requested noncanonical
review copy must preserve the renderer's bytes, give its Markdown that exact filename
stem in the selected folder, and label the package as a candidate. Never manually
change Canvas links/layout to bypass conformance or call that copy a canonical write.
Formal storage still requires the public paired commit receipt and registered owner.

To revise an existing exemplar, use `analysis stage-update` with exact existing hashes
and a new update request as described in `analysis-batch.md`. Save its returned complete
commit request with the replay records. Do not regenerate a new layout or hand-patch
the displayed Canvas to bypass the existing-pair preservation check.

For a paper without a Knowledge owner, first use the shared
`paper-registration.md` contract's installed `knowledge paper-plan/register-paper`
entry in the selected Source/Field. Registration and analysis commit receipts have
different purposes. A successful new-folder registration does not adopt a displayed
old package, certify its content, or replace the paired commit and provider apply.

After the provider owns the complete pair, the public `knowledge canvas-plan/register-canvas`
interface in the shared `canvas-registration.md` contract declares its existing Canvas identity
in `.scholar-workflow/artifacts.yml`. Use it for this portable exemplar rather than manually
inventing an owner or injecting private fields into Canvas. This declaration alone is not full
cross-host provider restoration or proof that reader links work at a new destination.

## Completion evidence

Show the actual installed version, input identity/hash, per-paper batch result and
output paths. Check that every source span belongs to the selected attachment and
its exact version; quotation presence and scientific support are separate judgments.
Keep source gaps visible. Verify editable JSON nodes, complete required slots, geometry,
reader links and exact Markdown backlinks using their owning contracts.

When human assessment is required, state it in the conversation: which Canvas/note
to open in Obsidian, which source links to click, and what constitutes readability,
alignment, non-crossing, editability and correct PDF-page placement. Automated
conformance does not certify visual quality or source truth. Mark these checks pending
until the user explicitly confirms them. A reproducible package is not a new authority,
a verified backup or permission to operate on other papers or Vaults.
