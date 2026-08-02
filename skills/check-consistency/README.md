# check-consistency

Audit cross-system consistency across Zotero, Obsidian indexes, and
Notion projections. Detects orphaned PDFs, dead Zotero keys, stale index rows,
broken local links, and duplicate Resource IDs.

Read-only throughout: it reports drift with a severity tag and a suggested remedy,
but never fixes or deletes anything. Remedies run in the corresponding Agent after
user confirmation.

Output is a structured JSON report, optionally with a Markdown summary.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
