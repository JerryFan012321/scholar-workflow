# Identity Policy (shared)

How a resource is normalized, identified, and matched. Used by find-resource
(discovery + recall) and ingest-resource (existence check before create).

## Identifier normalization

- **DOI**: lowercase; strip `doi:` and `https://doi.org/` prefixes. Primary dedup key.
- **Title + authors**: Unicode NFC + lowercase + collapse whitespace. Secondary dedup
  key when no DOI is available.
- **arXiv**: `2401.01234`, `...v1`, `...v2` all map to the same paper. arXiv id is a
  **download-source label**, not a canonical identity — a paper's identity is its DOI
  or title+authors, since the same work may carry an arXiv id, a conference DOI, and a
  publisher DOI at once.

## Metadata source priority

Metadata (title / authors / year / venue) is authoritative from **zotero-mcp** for
items already in the library. For new items, fetch metadata from an authoritative web
source (arXiv abs page, CVF/DBLP/publisher) — never parse it out of the PDF. When a
published version exists, its venue overrides the arXiv "preprint" label.

1. zotero-mcp query (authoritative metadata + existence for library items)
2. DOI / arXiv identifier confirmation
3. Authoritative web source for new items (arXiv abs, CVF, DBLP, publisher)
4. User-provided (tag the source)

If a secondary field (volume, pages) cannot be found from an authoritative source,
state that honestly and leave it empty — never fabricate, and never hammer an
unreachable site to fill a non-essential field.

## Existence check — two-step, via zotero-mcp

`write_item` is pure create with no dedup, so an existence check MUST run before every
create. Zotero's own dedup is detect-then-manual-merge, not a write-time block. The
check is orchestrated by the host LLM at the skill layer (the CLI cannot reach
zotero-mcp), in two steps:

1. **Recall** — `search_library` (and/or `semantic_search`) by DOI, then by
   title+authors.
2. **Confirm** — `get_item_details` on each recalled key, comparing DOI / title /
   authors to the target. A recall hit is a candidate, not a decision; the field-level
   read-back confirms it.

Outcomes:

- One confirmed match → **exact** (already in the library; do not re-create).
- Multiple items with the same identity → **conflict**: stop and surface the item keys
  for human adjudication. Never auto-merge (NG3).
- No confirmed match → **none** (safe to create).

Different arXiv versions of one paper share the same base id and resolve to the same
identity — they never create separate items.

## Reading items back — itemType caveat

`itemType` reads back as an empty string through zotero-mcp for **every** item; this
is a read-layer artifact, not a corrupted record. Do not diagnose a record as dirty
from an empty `itemType`, and do not try to set it via `write_metadata` (it is
rejected as not a valid data field). Judge record health by the substantive fields
(title, creators, DOI, attachments on disk).

## Semantic recall — fuzzy, host-LLM

Fuzzy/semantic matching is delegated to zotero-mcp's `semantic_search`; this project
builds no embeddings or vector index of its own (INV14). A semantic hit is only a
candidate — confirm identity with the two-step check above before treating it as the
same paper. Confirming or merging identity stays with the human.
