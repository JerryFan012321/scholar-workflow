# Resource Model

## Kind classification

| Kind | How to recognize |
|---|---|
| `paper` | Has DOI / arXiv ID, or is clearly scholarly (abstract, authors, venue) |
| `technical_document` | Technical report, official doc, tutorial, spec, whitepaper |
| `snapshot` | Web page snapshot (HTML / MHTML / PDF of a page) |
| `drawio` | draw.io / diagrams.net file |
| `image` | Image, screenshot, figure |
| `dataset` | Dataset file or descriptor |

A technical PDF (e.g. CUDA docs, an official manual) is a `technical_document`
even though it is a PDF — it never enters the paper flow.

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
On classification conflict, stop and report — never guess.
