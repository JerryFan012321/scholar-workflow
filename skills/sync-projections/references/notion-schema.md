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
| Web Source | URL | **PDF link for Notion = arXiv abs / DOI / origin site.** Resolves from any device/browser — unlike a loopback Local URL, which Notion's server can't unfurl and other machines can't reach |
| Local URL | URL | optional; `http://127.0.0.1:23128/open/...` — host-Mac only, leave empty for Notion |
| Sync Revision | Text | content hash for incremental updates |
| Last Synced | Date | last machine update |

## Sync direction

**One-way: local → Notion.** Local (Obsidian notes / Zotero annotations) is the source of
truth; the machine only pushes. Notion is a derived projection — edits made in Notion do
not flow back, and are overwritten inside the managed region on the next push if the
source changed. This preserves the single-source-of-truth architecture (G2, G5).

## Managed note body (markdown → Notion page blocks)

A note's markdown body is rendered into **native Notion page blocks** (headings,
paragraphs, tables) inside a **managed region** on the resource page — the block analogue
of Obsidian's managed block. This is content projection, **not** a file upload, so
`Upload no files` (INV5/NG6) still holds. Rules:
- Bound the projected body with sentinel marker blocks; rewrite only between them.
- Everything outside the region — and the human fields below — is never touched.
- The region is machine-managed: re-render replaces it when `Sync Revision` changes.

## Hierarchy (mirror the Zotero collection tree)

Preserve the knowledge-base hierarchy in Notion via `Category` (leaf collection) +
`Project` relation (owning project page) + parent-page nesting that mirrors the collection
tree — the same tree `project-tree` mirrors into Obsidian folders.

## Human fields (sync must never touch)

Summary, Priority, and any page content outside the managed note-body region. (Note: the
projected note body is now machine-managed inside its region; human commentary belongs
outside it or in Summary.)

## Upsert rules

- Upsert by Resource ID; never create pages by title.
- Write only machine-managed fields + the managed note-body region.
- Skip the update when `Sync Revision` is unchanged.
- Upload no files — note body goes in as page blocks, never as an attached file.
