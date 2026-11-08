# Knowledge asset units

## Unit and authority

A paper, blog article or other selected knowledge document is managed as one
asset unit with its source and explicitly associated context. The existing
resource identity is its unit identity; do not introduce another generic asset
database or derive identity from a title, directory or viewer URL.

For a paper, reuse the qualified Zotero library/item identity and declared
Knowledge owner. Zotero owns the bibliography, original attachment and formal
annotations. The owning Knowledge resource declares its companion, analysis,
Canvas, notes, source excerpts and supplementary assets. For a selected webpage,
reuse the existing document registration and source-snapshot identity. Optional
or unfinished members stay explicitly absent/pending; registering a unit does
not prove that its analysis is complete.

Upper-level topics, project inventories, lists, comparisons and relationships
reference whole units. An analysis, Canvas, figure, annotation or quotation is a
member or evidence locator, not a new peer knowledge unit. A direct link to a
member remains useful for reading or editing and does not create another owner.
Shared context uses explicit references; it is not copied into multiple primary
units or attached merely because filenames or tags resemble each other.

Source/Field manifests organize containers and ownership; host registries locate
them on this machine. Neither is the minimum knowledge object. Preserve current
IDs, package paths, declarations and accepted Markdown/Canvas formats. A change
to this policy does not authorize moving or re-registering existing material.

## Separate operations

| Operation | Responsibility | Observable completion |
|---|---|---|
| Manage | Register a unit, resolve its owner/members, reference it from topics/projects, or explicitly change its placement | Exact identity/scope and a receipt; missing members and conflicts remain visible |
| Analyze | Produce or revise the selected unit's explanatory analysis and supporting evidence | Its versioned prose/Canvas/sidecar contracts and source checks pass; scientific and human judgments remain distinct |
| View | Open a unit or selected member in the native reader/editor, with stable source locations | Dispatch is reported separately from observed reader behavior; ownership and content are unchanged |
| Edit | Change explicitly selected content through its owning writer and appropriate conflict checks | Ordinary document edits or managed paired updates preserve identity and unrelated members; edit success does not imply scientific approval |

A management request does not silently analyze a unit. A viewing request does
not register, move or rewrite it. Managed analysis updates keep their paired
validation, CAS and recovery rules; arbitrary single-file editing cannot bypass
them. The external editor owns its actual editing session. No operation requires
a Hub, browser token, workspace binding or Scholar-controlled agent worker.

## Lists and monitoring are separate

Lab/company/researcher watchlists and publication channels are maintained in
their own documents or databases. Existing recommendation and research-channel
stores remain authoritative. A monitored site, discovered update or selected
candidate is not automatically an archived knowledge unit. Explicit ingestion
creates or reuses the appropriate unit; tracking retains a reference to it where
supported, not a second copy of its identity, body or analysis.

Multidimensional records and human assessments are retained. Their viewing and
editing design remains open; this unit boundary does not select a new interface
or change the existing exploration schema.

Use `paper-registration.md`, `document-registration.md` and
`knowledge-registration.md` for the actual supported writes. This contract
does not claim that all asset types already have a unified CLI.

## Supported outer references

The current registered atomic kinds are `paper`, `blog_post` and
`technical_document`. The common Field asset projection retains that exact
`resource_kind`; exploration maps them to `paper`, `webpage` and `report`,
respectively. It imports the qualified owner and every declared member rather
than inventing a paper identity for a Blog. Existing paper-only navigation stays
paper-only. New ownership still uses the actual supported registration operation;
an unsupported book/other registration is a capability gap, not a free-card mode.
`knowledge list --asset-units --source-id SOURCE --field-id FIELD --language en`
lists the selected Field's complete units without analyzing or changing them;
`--format json` exposes exact identities and member states. The historical
`--paper-units` selection still lists only papers and cannot be combined with it.

New outer references use the registered import. Generic edits preserve the
identity, kind and members of every qualified unit, while human positioning and
condition-specific assessments remain editable. A refresh with members absent
from the current provider inventory requires explicit reconciliation; it does
not silently certify old arbitrary members or delete historical evidence.

Old unqualified non-paper rows remain readable in place and are explicitly
unverified. Managed writes cannot create more such rows or edit those rows and
their related records/edges as if ownership had been established. Unchanged
legacy rows can remain alongside edits to other registered units; removing an
entire outer reference never deletes its source files. Registration/adoption is
separate and never inferred from a matching title or a newly filled identity field.
