# export-annotations

Turn the annotations you made on one paper in Zotero into a structured Obsidian note.

Pulls all highlights, notes, and your comments for a paper (read-only), strips the
Translate plugin's machine translation, and groups the remaining entries under
descriptive headings suited to the material or your requested view. Comments and
highlights remain distinguishable; source order is preserved within a group when it
carries meaning. Page numbers stay as inline `(p.N)` provenance tags. Any model-added
supplement is explicitly labeled `补充（模型）`.

Read-only. Never writes `zotero.sqlite`. If the paper already has an analysis note in
the vault, this produces a separate annotations note and cross-links the two.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
