# find-resource

Search for and locate scholarly resources. Two modes:

- **Discovery** — normalize identifiers (DOI / arXiv ID / title), check the local
  library and Zotero for existing copies, and (with explicit authorization) query
  Crossref / OpenAlex / Semantic Scholar. Returns a candidate list with match
  rationale and arXiv PDF availability.
- **Locate** — resolve an existing paper or document to its local path and
  local-link service URL, without copying files.

Read-only. Never downloads PDFs from non-arXiv sources and never writes files.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
