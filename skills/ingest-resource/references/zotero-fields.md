# Zotero Field Mapping

## Paper item (journalArticle / conferencePaper / preprint)

| Zotero field | Source | Note |
|---|---|---|
| `title` | metadata | required |
| `creators` | metadata | author list |
| `DOI` | identifier | if present |
| `url` | arXiv / DOI URL | prefer arXiv |
| `date` | year | YYYY |
| `publicationTitle` | venue | journal |
| `conferenceName` | venue | conference |
| `abstractNote` | metadata | abstract |
| `extra` | arXiv ID | `arXiv: 2401.01234` |
| `collections` | user-confirmed | Collection key list |

## Attachment (linked_file)

| Field | Value |
|---|---|
| `linkMode` | `linked_file` |
| `path` | canonical absolute PDF path (finalized by Bridge / ZotMoov) |
| `contentType` | `application/pdf` |
| `title` | `{arxiv_id}.pdf` or `{first_author}_{year}_{short_title}.pdf` |

## Dedup

Dedup key priority and arXiv version handling are in the shared
`references/identity-policy.md`. Upsert against the existing item; never create a
duplicate.
