# Obsidian Index Format

## Managed block

The machine-maintained table lives inside a managed block. Content outside the
markers must never be modified.

```markdown
# <Topic> Paper Index

Human notes above stay untouched.

<!-- scholar-workflow:start -->
| Title | Authors | Year | Venue | Importance | Zotero | PDF | arXiv | Synced |
|---|---|---:|---|---|---|---|---|---|
| ... | A One; B Two | 2024 | CVPR | founding ★★★ | [open](zotero://select/items/@8USWVHLD) | [PDF](http://127.0.0.1:23128/open/paper/S6LZUS6S) | [2401.01234](https://arxiv.org/abs/2401.01234) | 2024-01-15 |
<!-- scholar-workflow:end -->

Human notes below stay untouched.
```

## Required columns

Title, Authors (`; `-joined), Year, Venue (keep it — with Year it lets a later step look
up the BibTeX citation), Importance (three-tier text `founding` / `milestone` /
`representative`, from the Zotero `prio:★★★/★★/★` tag; the renderer appends the star badge
so the cell reads e.g. `founding ★★★`; empty when untagged), Zotero
(`zotero://select/items/@<item-key>`), PDF (link-service URL
`http://127.0.0.1:<port>/open/paper/<attachment-key>` — never a relative or absolute file
path), arXiv (`[id](https://arxiv.org/abs/id)`), Synced (ISO date, taken from the
input row, not `now()` — keeps re-projection idempotent).

DOI is **not** a rendered column — it is retained only as a dedup identity field in the
data (INV1). The shared renderer (`projection.py`) dropped it from every table, so the
Zotero-mirror index and the literature-tree paper list stay column-aligned.

## Hierarchical structure (folder mirror of the Zotero collection tree)

`project-tree` mirrors the collection tree under a plain `paper/` root (no numeric
prefix). Two node shapes:

- **Hub** (has child collections) → `<parent>/<name>/index.md`, managed block holds a MOC
  wikilink list to its children. Heading = bare collection name.
- **Leaf** (papers, no children) → `<parent>/<name>.md`, managed block holds the 9-column
  paper table. Heading = `<name>相关论文`.

The nested `index.md` for hubs is deliberate: it stops a folder and its own note from
appearing as same-named siblings in the file tree. A MOC link to a hub child points at
that child's `index`; a link to a leaf child points at the file directly.

```
paper/
  科研项目/
    index.md                 <- hub MOC: - [[paper/科研项目/上汽标注/index|上汽标注]]
    上汽标注/
      index.md               <- hub MOC: - [[paper/科研项目/上汽标注/text2cad|text2cad]]
      text2cad.md            <- leaf: # text2cad相关论文 + 9-column paper table
```

The rebuild source is Zotero via zotero-mcp — the existing files are never source of
truth. The host LLM walks `get_collections(recursive)` + `get_collection_items` into the
tree JSON; the CLI owns all path computation (deterministic, MCP-free — INV18).

The `# heading` line is written only when a file is first created; re-running rewrites the
managed block but not the heading. Renames / heading-rule changes need a manual heading fix.

Preview before writing: `scholar-workflow project-tree --dry-run` prints every planned
file (path + heading + body) and touches nothing; re-run without the flag to apply.
