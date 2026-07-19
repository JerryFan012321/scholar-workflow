# ingest-resource

Import papers and archive technical documents into the local library. Two phases:

- **Plan (dry-run)** — classify the resource, normalize identifiers, dedup against
  the state store and Zotero, recommend a Zotero Collection / Vault category, and
  emit a structured `action-plan.json`. Never writes to external systems.
- **Execute** — requires a valid, approved `plan_id`. Downloads paper PDFs from
  arXiv only, verifies them, and writes through `ZoteroWriteAdapter`. Technical
  documents are copied into the Vault with source/hash metadata.

Paper PDFs go only to `papers_root`; technical documents only to the Vault. Fails
closed if the Zotero Bridge is unavailable.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
