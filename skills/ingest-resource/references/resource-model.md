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
| `paper` | `paper_inbox` (then ingested via zotero-mcp) | Yes — create + import via zotero-mcp |
| `technical_document` | `research_vault_root/32-documents/<category>` | No (optional bib entry) |
| `snapshot` | `research_vault_root/32-documents/snapshots/` | No |
| `drawio` / `image` | `research_vault_root/<project dir>` | No |
| `dataset` | Metadata only in phase 1 | No |

Which root is authoritative for each object is the shared `storage-policy.md`.
On classification conflict, stop and report — never guess.
