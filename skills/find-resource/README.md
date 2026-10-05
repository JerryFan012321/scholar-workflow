# find-resource

Search for and locate scholarly resources:

- **Discovery** — normalize identifiers (DOI / arXiv ID / title), check Zotero
  for existing copies, and read metadata from
  Crossref / OpenAlex / Semantic Scholar. Returns a candidate list with match
  rationale and arXiv PDF availability.
- **Locate** — return an existing paper's item/attachment identity and stable
  reader URI, or a registered document's Vault-relative path, without copying files.
- **Open, when requested** — use a native reader or cmux's current/chosen location.
  The [opening reference](./references/resource-location.md#requested-native-opening)
  covers live local-PDF resolution, minimal commands and explicit control failures.
  Launch acceptance is not proof of display; original PDFs do not contain Zotero's
  database annotations.

Read-only. Never downloads PDFs from non-arXiv sources and never writes files.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
