# check-consistency

Audit cross-system consistency across Zotero, Obsidian indexes, and
Notion projections. Detects inbox-orphan PDFs (under `paper_inbox` only — never a
reverse-scan of Zotero's own `storage/`), dead Zotero keys, stale index rows,
broken attachment-key links, legacy fixed-port links, and duplicate Resource IDs.

Read-only throughout: it reports drift with a severity tag and a suggested remedy,
but never fixes or deletes anything. Remedies run in the corresponding Agent after
user confirmation.

Interactive output is a readable Markdown report: scope and conclusion, findings with
evidence and suggested remedies, then coverage gaps. An unavailable provider is not a
clean result. Structured JSON remains available on request, including JSON-only machine
calls; no report file is created unless requested.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
