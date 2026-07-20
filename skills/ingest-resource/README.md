# ingest-resource

Import papers and archive technical documents into the local library. Two phases:

- **Plan (dry-run)** — `scholar-workflow plan <inputs...>` classifies each resource,
  normalizes identifiers, dedups against the state store and Zotero, and emits a
  structured plan (create / skip / conflict per resource). Never writes externally.
  Present it to the user and wait for in-conversation approval — there is no plan file.
- **Execute** — after the user approves, `scholar-workflow apply <inputs...>` downloads
  paper PDFs from arXiv only, verifies them, and writes through `ZoteroWriteAdapter`.
  Technical documents are copied into the Vault with source/hash metadata.

Paper PDFs go only to `papers_root`; technical documents only to the Vault. Fails
closed if the Zotero Bridge is unavailable.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
