# Source Policy (shared)

Canonical rule for where content and metadata may come from. Applies to
find-resource, ingest-resource, and any agent that touches acquisition.

## Paper PDFs

- **The only automatic source is arXiv.**
- Other sources (Crossref, OpenAlex, Semantic Scholar, publisher pages, CVF, DBLP)
  are for metadata verification and identity resolution only — never for PDF download.
- Never bypass paywalls, captchas, logins, or access controls.

## arXiv version handling

- `2401.01234`, `...v1`, `...v2` are the same paper. Store the base id.
- Fetch the latest version on download; create exactly one Zotero item.

Normalization, dedup keys, and metadata source priority are in `identity-policy.md`.

## Metadata acquisition

- For items already in Zotero, metadata is authoritative from zotero-mcp.
- For new items, read metadata from an authoritative web source (arXiv abs page, CVF,
  DBLP, publisher) — never parsed from the PDF. Prefer the published venue over the
  arXiv "preprint" label when both exist.
- Web fetch for metadata/identity is read-only and needs no approval.

## No arXiv PDF

Record metadata and candidate status, tag `no_arxiv_pdf`, and let the user decide.
Never fetch full text from another source.
