# Identity Policy (shared)

How a resource is normalized, identified, and matched. Used by find-resource
(discovery dedup) and ingest-resource (Zotero upsert dedup).

## Identifier normalization

- **arXiv**: `2401.01234`, `...v1`, `...v2` all map to the same paper. Store the
  base ID without the version suffix.
- **DOI**: lowercase; strip `doi:` and `https://doi.org/` prefixes.
- **Title**: Unicode NFC + lowercase + collapse whitespace for fuzzy matching.

## Metadata source priority

Use only to verify identity — never to download PDFs (see `source-policy.md`).

1. DOI (highest confidence)
2. arXiv API
3. Crossref / OpenAlex
4. Semantic Scholar
5. User-provided (tag the source)

## Dedup key priority

Match in this order:

1. DOI
2. arXiv base ID
3. Normalized title + first author + year

Different arXiv versions of one paper are the same identity — they never create
separate resources or multiple Zotero items.
