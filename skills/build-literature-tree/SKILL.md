---
name: build-literature-tree
description: Build an Obsidian literature tree and flat paper ledger for a research topic. Supports technical trees (task → pipeline → optional module → paper) and challenge trees (challenge → insight → paper). Use for 'literature tree', 'novelty tree', 'paper lineage', '文献树', '文献脉络', '技术路线树', '挑战洞见树', '画出发展脉络'.
---

# build-literature-tree

## Output contract

- **Technical tree:** `task → pipeline/representation → module (optional) → paper`.
- **Challenge tree:** `challenge → insight → paper`.
- Internal nodes are concepts; paper leaves reference `resource_id`.
- `novelty_anchor` stores the first paper proposing a task, pipeline, module, or
  insight. A paper that only improves an existing module is an ordinary paper leaf and
  has no anchor field.
- One document contains one tree. Technical and challenge trees are separate notes that
  may share papers and always use the same topic-local flat ledger.

## Vault format

Inside `<topic>/`:

- `01-Paperlist.md` — fixed flat metadata ledger;
- `02-<topic>文献树.md`, `03-<topic>挑战洞见树.md`, ... — one numbered tree/view per
  note, in creation order;
- `paper_assets/<year>-<first-author-surname>-<title>.md` — companion note per paper,
  including `# 相关文献树` back-links to every tree section that contains it.

A tree note has no H1. It contains an inline Mermaid overview followed by concept
sections: task/challenge `##`, pipeline/insight `###`, module `####`, with each
node's anchor, optional summary, and paper subset. The ledger and trees cross-link.

## Steps

1. Resolve the topic folder, tree view, paper set, time window, and requested resolution.
   Ask only for unspecified choices that materially change the output.
2. Collect papers from a Zotero collection
   (`scholar-workflow zotero collection-items`), an existing paper index, or the user's
   list. Zotero/authoritative sources supply metadata. For a large set, NotebookLM may
   be used as a read substrate; otherwise use Zotero indexed full text. The resulting
   concept placement and anchors go into the schema below.
3. Assemble a document conforming to
   `contracts/literature-tree.schema.json`. Keep unplaced papers in the ledger with
   `classified: false`.
4. Preview and render:
   - ledger: pipe
     `{"root":"<topic>","paperlist_only":true,"doc":{...}}` to
     `scholar-workflow project-literature-tree`;
   - tree: pipe
     `{"root":"<topic>","filename":"02-<topic>文献树.md","doc":{...}}` to the same
     command, using `03-`, `04-`, ... for additional views.
   Use `--dry-run` before each write.
5. Create/update the paper companion notes and their tree back-links without replacing
   unrelated human content.

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

## References

- `${CLAUDE_PLUGIN_ROOT}/references/storage-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
