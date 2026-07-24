# export-annotations

Turn the annotations you made on one paper in Zotero into a structured Obsidian note.

Pulls all highlights, notes, and your comments for a paper (read-only), strips the
Translate plugin's machine translation, and reorganizes them along argument logic —
your comments as the backbone, highlighted text as supporting evidence. Page numbers
stay as inline `(p.N)` tags, never as the ordering key.

Read-only. Never writes `zotero.sqlite`. If the paper already has an analysis note in
the vault, this produces a separate annotations note and cross-links the two.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
