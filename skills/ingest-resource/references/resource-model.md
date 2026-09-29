# Resource Model

## Object boundary

A technical PDF such as an official manual is a `technical_document`, not a paper
merely because its file format is PDF. It does not enter the Zotero paper flow.
If the object's intended kind or owner remains ambiguous, report the ambiguity before writing.

## Storage target

| Kind | Target dir | Zotero item? |
|---|---|---|
| `paper` | `paper_inbox` (then ingested via Local API) | Yes — create + import via Local API |
| `technical_document` | Explicitly selected, registered Obsidian Source/Field | No (optional bib entry) |
| `snapshot` | Explicitly selected, registered Obsidian Source/Field | No |
| `drawio` / `image` | Source-relative attachment path for the selected Field and owning note | No |
| `dataset` | Metadata only in phase 1 | No |

Resolve the selected Source through its trusted `folder_id` and the Field through
`.scholar-workflow/fields.yml`; do not derive a destination from the legacy
`research_vault_root` or a fixed category tree. If multiple Fields fit, ask for the
target. If no Field is registered or initialized, show the zero-write preview and
obtain confirmation before initialization. Do not silently migrate existing files.
Which root is authoritative for each object is the shared `storage-policy.md`.
