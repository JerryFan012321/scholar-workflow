# Notion Schema

Two databases, relation-linked. **Papers DB** holds one row per Zotero paper; **Related
Docs DB** holds one row per companion document (reading note / direction note /
supplementary), each pointing back to its paper. This mirrors the Obsidian layout: a
paper index row (INV1) plus its related-materials hub (INV20).

## Papers DB — machine-managed fields (sync may write)

| Field | Type | Note |
|---|---|---|
| Resource ID | Text | idempotent upsert key = Zotero identity (DOI / title+authors) |
| Name | Title | paper title |
| Type | Select | Paper / TechnicalDocument / Dataset / Project |
| Category | Select | knowledge category (leaf collection) |
| Project | Relation | owning project page |
| Status | Select | reading / research / project status |
| Zotero Item Key | Text | jump link |
| Web Source | URL | **PDF link for Notion = arXiv abs / DOI / origin site.** Resolves from any device/browser — unlike a loopback Local URL, which Notion's server can't unfurl and other machines can't reach |
| Local URL | URL | optional; `http://127.0.0.1:23128/open/...` — host-Mac only, leave empty for Notion |
| Sync Revision | Text | content hash for incremental updates |
| Last Synced | Date | last machine update |

## Related Docs DB — machine-managed fields (sync may write)

| Field | Type | Note |
|---|---|---|
| Doc ID | Text | idempotent upsert key = vault-relative path (stable, unique, doubles as backlink target) |
| Name | Title | document name |
| Doc Type | Select | reading-note / direction-note / supplementary |
| Paper | Relation | → Papers DB row this document belongs to. This phase: exactly one paper (paperless direction notes deferred) |
| Summary | Text | **one-paragraph abstract only** — the full body stays in Obsidian, never projected here |
| Vault Link | URL | `obsidian://` (or link-service) backlink to the source note |
| Sync Revision | Text | content hash for incremental updates |
| Last Synced | Date | last machine update |

## Note body: summary + backlink, not full text

A related document's **full body is NOT projected into Notion.** Notion is the simplified,
cross-device *frontend*; Obsidian + Zotero remain the backend and sole edit entry. The
Related Docs row carries only a one-paragraph `Summary` and a `Vault Link` back to the
Obsidian note. This keeps Notion light, avoids duplicating local content, and upholds
`Upload no files` (INV5/NG6) trivially — there is no body to upload.

## Sync direction

**One-way: local → Notion.** Local (Obsidian notes / Zotero annotations) is the source of
truth; the machine only pushes. Notion is a derived projection — edits made in Notion do
not flow back, and machine fields are overwritten on the next push if the source changed.
This preserves the single-source-of-truth architecture (G2, G5).

## Orchestration (upsert order)

1. Upsert the **paper** into Papers DB by `Resource ID` → capture its `page_id`.
2. For each related document, upsert into Related Docs DB by `Doc ID`, setting the
   `Paper` relation to the paper's `page_id` from step 1.

The relation must point at a real page id, so the paper upsert always precedes its
documents. `upsert_page(..., key_property="Doc ID")` selects the Related-Docs key.

## Hierarchy (mirror the Zotero collection tree)

Preserve the knowledge-base hierarchy in Notion via `Category` (leaf collection) +
`Project` relation (owning project page) + parent-page nesting that mirrors the collection
tree — the same tree `project-tree` mirrors into Obsidian folders.

## Human fields (sync must never touch)

Priority and any page content the human adds. Machine writes are confined to the fields
tabled above; everything else on either page is left alone.

## Upsert rules

- Papers DB: upsert by `Resource ID`. Related Docs DB: upsert by `Doc ID`.
- Never create pages by title.
- Write only the machine-managed fields listed above.
- Skip the update when `Sync Revision` is unchanged.
- Upload no files — no body is projected; only a Summary + backlink.
