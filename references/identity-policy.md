# Identity Policy (shared)

How a resource is normalized, identified, and matched. Used by find-resource and
ingest-resource.

## Identifier normalization

- **DOI**: lowercase; strip `doi:` and `https://doi.org/` prefixes. Primary dedup key.
- **Title + authors**: Unicode NFC + lowercase + collapse whitespace. Secondary dedup
  key when no DOI is available.
- **arXiv**: version suffixes map to the same base id. It is a download-source label,
  not canonical identity; one work may have arXiv, conference, and publisher identifiers.

## `resource_id` vs library identity

`make_resource_id` prefers arXiv, then DOI, because it is an offline naming key for
local files and state. It never decides create/skip. Library identity is DOI, then
title+authors, verified live through the Zotero Local API.

## Metadata source priority

Metadata for an existing item is authoritative from the Zotero Local API. For a new
item, fetch metadata from an authoritative web source — arXiv abs, CVF, DBLP, or the
publisher — and never parse it from the PDF. Prefer a published venue over an arXiv
"preprint" label. Leave unavailable secondary fields empty rather than fabricating.

## Existence check

Before every create, query the local library and confirm fields:

1. DOI present → `scholar-workflow zotero search "<doi>" --fulltext`, then compare
   normalized DOI values.
2. No DOI → `scholar-workflow zotero search "<title>"`, then compare normalized title
   and ordered creators.
3. When a candidate needs fuller inspection, run
   `scholar-workflow zotero get <item-key> --children`.

`scholar-workflow zotero ingest` repeats the exact check immediately before its write,
so a skill-layer candidate list cannot bypass the final guard.

Outcomes:

- One confirmed match → **exact**; reuse it and do not create.
- Multiple exact matches → **conflict**; exit 5 and surface keys for human adjudication.
- No exact match → **none**; safe to create.
- An obvious same work with a different version/identity → surface it for a human choice;
  never auto-skip or merge.

Different arXiv versions share one base id and never create separate items.

## Fuzzy and topic recall

The Local API provides quick search, including indexed full text, but no native semantic
or vector endpoint. Use `scholar-workflow zotero search "<topic>" --fulltext` to recall
candidates and expose the title, abstract, or relevant-text signals supporting each result.
This project stores no embedding index. Any ordering states its explicit basis. Fuzzy
similarity is only a candidate signal; the exact identity check above controls writes.
