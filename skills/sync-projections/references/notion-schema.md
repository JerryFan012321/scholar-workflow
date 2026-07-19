# Notion Schema

## Machine-managed fields (sync may write)

| Field | Type | Note |
|---|---|---|
| Resource ID | Text | idempotent upsert key |
| Name | Title | title or document name |
| Type | Select | Paper / TechnicalDocument / Dataset / Project |
| Category | Select | knowledge category |
| Project | Relation | owning project page |
| Status | Select | reading / research / project status |
| Zotero Item Key | Text | jump link |
| Local URL | URL | `http://127.0.0.1:23128/open/...` |
| Web Source | URL | arXiv / DOI / origin site |
| Sync Revision | Text | content hash for incremental updates |
| Last Synced | Date | last machine update |

## Human fields (sync must never touch)

Summary, Notes, Priority, and the content of any related pages.

## Upsert rules

- Upsert by Resource ID; never create pages by title.
- Write only machine-managed fields.
- Skip the update when `Sync Revision` is unchanged.
- Upload no files.
