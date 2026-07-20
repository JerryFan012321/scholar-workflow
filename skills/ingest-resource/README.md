# ingest-resource

Import papers and archive technical documents into the local library. Two phases:

- **Plan (dry-run)** — `scholar-workflow plan <inputs...>` classifies each resource,
  normalizes identifiers, dedups against the state store and Zotero, and emits a
  structured plan (create / skip / conflict per resource). Never writes externally.
  Present it to the user and wait for in-conversation approval — there is no plan file.
- **Execute** — after the user approves, `scholar-workflow apply <inputs...>` downloads
  paper PDFs from arXiv only into `paper_inbox` and verifies them. Zotero has no local
  write API, so import is manual. Technical documents are copied into the Vault with
  source/hash metadata.

Downloaded PDFs go only to `paper_inbox`; technical documents only to the Vault.
Metadata is read from the Zotero Local API; the plugin never writes to Zotero.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
