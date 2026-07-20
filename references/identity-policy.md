# Identity Policy (shared)

How a resource is normalized, identified, and matched. Used by find-resource
(discovery + recall) and ingest-resource (existence check before download).

## Identifier normalization

- **arXiv**: `2401.01234`, `...v1`, `...v2` all map to the same paper. Store the
  base ID without the version suffix.
- **DOI**: lowercase; strip `doi:` and `https://doi.org/` prefixes.
- **Title**: Unicode NFC + lowercase + collapse whitespace — feeds the resource_id
  fingerprint and the catalog projection, not a CLI fuzzy matcher.

## Metadata source priority

Metadata (title / authors / year) is authoritative from the **Zotero Local API**,
not parsed from arXiv. Other sources only help confirm an identifier — never to
download PDFs (see `source-policy.md`).

1. Zotero Local API (authoritative metadata + existence)
2. DOI / arXiv identifier confirmation
3. Crossref / OpenAlex / Semantic Scholar (identifier lookup only)
4. User-provided (tag the source)

## Existence check — exact, deterministic

Existence is decided by querying the **Zotero Local API** (the authority), not the
local cache. Match by identifier in this order:

1. DOI
2. arXiv base ID

- One matching item → **exact** (already in the library; skip).
- Multiple items carrying the same identifier → **conflict**: stop and surface the
  item keys for human adjudication. Never auto-merge (NG3).
- No match → **none** (safe to create).
- **Fail-closed**: if the Local API is unreachable, raise a dependency error
  (exit code 3). Never fall back to "none" — that would misjudge an existing paper
  as new and create a duplicate (INV12).

Different arXiv versions of one paper share the same base ID, so they resolve to the
same identity and never create separate resources or multiple Zotero items.

## Semantic recall — fuzzy, host-LLM

Fuzzy/semantic matching is **not** a CLI operation and produces no decision. The
host LLM reads the catalog projection (`scholar-workflow catalog` — title + abstract
per item) and judges similarity directly (INV14: no embeddings, no vector index).
A fuzzy hit is only a candidate; confirming or merging identity stays with the human.
