---
name: build-literature-tree
description: Build an Obsidian literature tree and flat paper ledger for a research topic. Supports technical trees (task → pipeline → optional module → paper) and challenge trees (challenge → insight → paper). Use for 'literature tree', 'novelty tree', 'paper lineage', '文献树', '文献脉络', '技术路线树', '挑战洞见树', '画出发展脉络'.
---

# build-literature-tree

## Output contract

- **Technical tree:** `task → pipeline/representation → module (optional) → paper`.
- **Challenge tree:** `challenge → insight → paper`.
- Internal nodes are concepts; paper leaves reference `resource_id`.
- `novelty_anchor` stores the earliest supported introducing paper within the declared
  corpus for a task, pipeline, module, or insight. Leave it unresolved when that bounded
  priority claim is not supported. A paper that only improves an existing module is an
  ordinary paper leaf and has no anchor field.
- One document contains one tree. Technical and challenge trees are separate notes that
  may share papers and always use the same topic-local flat ledger.

## Vault format

Inside a registered topic Field (`<Field>/`):

- `01-Paperlist.md` — fixed flat metadata ledger;
- `02-<topic>文献树.md`, `03-<topic>挑战洞见树.md`, ... — one numbered tree/view per
  note, in creation order;
- `resources/papers/<stable-paper-segment>/论文信息.md` — new companion note per paper,
  including `# 相关文献树` back-links to every tree section that contains it. Keep its
  analysis Markdown, editable Canvas, sidecar, and other Scholar-owned paper notes in
  the same paper folder. The Zotero PDF remains in Zotero storage.

The segment is a path-safe, collision-checked folder label allocated once and recorded
with the paper's stable `resource_id` and companion-note path in the owning manifest;
it is not the paper identity. Existing `paper_assets/*.md` paths remain valid on reads
and updates. Do not move them or create a second companion note merely to apply the
new layout.

A tree note has no H1. It contains an inline Mermaid overview followed by concept
sections: task/challenge `##`, pipeline/insight `###`, module `####`, with each
node's anchor, optional summary, and paper subset. The ledger and trees cross-link.

## Steps

1. Resolve the registered topic Field, tree view, paper set, time window, and requested resolution.
   Ask only for unspecified choices that materially change the output.
2. The declared corpus comes from a Zotero collection
   (`scholar-workflow zotero collection-items`), an existing paper index, or the user's
   list. Metadata comes from Zotero or authoritative sources. The output conforms to
   `contracts/literature-tree.schema.json`; papers without supported concept placement
   remain in the ledger with `classified: false`.
3. Preview and render:
   - ledger: pipe
     `{"root":"<topic>","paperlist_only":true,"doc":{...}}` to
     `scholar-workflow project-literature-tree`;
   - tree: pipe
     `{"root":"<topic>","filename":"02-<topic>文献树.md","doc":{...}}` to the same
     command, using `03-`, `04-`, ... for additional views.
   Use `--dry-run` before each write.
4. For a new companion note, resolve or explicitly allocate its manifest-declared paper
   folder before writing. If the mapping cannot be durably declared, preview the proposed
   path and leave the paper note unwritten. Update existing companion notes at their
   declared paths, including legacy `paper_assets/*.md`, and maintain tree back-links
   without replacing unrelated human content.

## Constraints

- Preserve the topology, filename, heading, anchor, and backlink contracts above.
- `01-Paperlist.md` is per topic. A `resource_id` may appear in multiple nodes,
  trees, or topic folders; do not impose one-node/one-tree uniqueness (INV25).
- Render only Obsidian managed blocks and inline Mermaid; no PNG, draw.io, HTML, or
  Notion output in this skill.
- Metadata never comes from PDF body text. DOI remains an identity field and is not a
  rendered column.
- Writes are limited to managed blocks and new companion-note content; never overwrite
  human-authored content outside managed blocks.
- `asset_note` in the paper-list/tree payload is the declared companion-note path, not
  a filename derived from title, author, or `resource_id`. A paper's repeated appearances
  in one Field reuse that path; path collisions require explicit resolution, not overwrite.

## References

- `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`
- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
