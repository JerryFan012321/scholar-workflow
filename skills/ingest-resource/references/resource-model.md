# Resource Model

## Object boundary

A technical PDF such as an official manual is a `technical_document`, not a paper
merely because its file format is PDF. It does not enter the Zotero paper flow.
An explicitly selected official webpage/blog is likewise not a full technical paper.
It may have a real Zotero `webpage` / `blogPost` bibliographic item while its
authorized original-text snapshot belongs to a registered Source/Field.
If the object's intended kind or owner remains ambiguous, report the ambiguity before writing.

## Storage target

| Kind | Target dir | Zotero item? |
|---|---|---|
| `paper` | `paper_inbox` (then ingested via Local API) | Yes — create + import via Local API |
| `technical_document` | Explicitly selected, registered Obsidian Source/Field | No (optional bib entry) |
| Selected official webpage/blog | Field-local `resources/<stable-segment>/Source.md` through document registration | Yes — `webpage` / `blogPost` bibliography; no fabricated PDF |
| `snapshot` | Explicitly selected, registered Obsidian Source/Field | No |
| `drawio` / `image` | Source-relative attachment path for the selected Field and owning note | No |
| `dataset` | Metadata only in phase 1 | No |

Resolve the selected Source through its trusted `folder_id` and the Field through
`.scholar-workflow/fields.yml`; do not derive a destination from the legacy
`research_vault_root` or a fixed category tree. If multiple Fields fit, ask for the
target. If no Field is registered or initialized, show the zero-write preview and
obtain confirmation before initialization. Do not silently migrate existing files.
Which root is authoritative for each object is the shared `storage-policy.md`.

For the selected webpage branch, load the shared `document-registration.md` contract.
Its plan/register receipt allocates the atomic resource and binds the original URL,
retrieval time, block-anchored snapshot and content hash. A downloaded HTML file,
an ordinary note or a Zotero bibliographic entry alone does not establish that owner.
Keep the snapshot separate from the analysis pair; undisclosed methods/results
remain undisclosed rather than being filled from a related paper or model version.
