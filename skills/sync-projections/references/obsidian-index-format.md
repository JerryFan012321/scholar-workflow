# Obsidian Index Format

## Managed block

The machine-maintained table lives inside a managed block. Content outside the
markers must never be modified.

```markdown
# <Topic> Paper Index

Human notes above stay untouched.

<!-- scholar-workflow:start -->
| Title | Authors | Year | Venue | Importance | Zotero | PDF | arXiv | DOI | Synced |
|---|---|---:|---|---|---|---|---|---|---|
| ... | A One; B Two | 2024 | CVPR | ★★★ | [open](zotero://select/items/@8USWVHLD) | [PDF](http://127.0.0.1:23128/open/paper/S6LZUS6S) | [2401.01234](https://arxiv.org/abs/2401.01234) | 10.xxxx | 2024-01-15 |
<!-- scholar-workflow:end -->

Human notes below stay untouched.
```

## Required columns

Title, Authors (`; `-joined), Year, Venue (keep it — with Year it lets a later step look
up the BibTeX citation), Importance (from the Zotero `prio:★★★` tag; empty when untagged),
Zotero (`zotero://select/items/@<item-key>`), PDF (link-service URL
`http://127.0.0.1:<port>/open/paper/<attachment-key>` — never a relative or absolute file
path), arXiv (`[id](https://arxiv.org/abs/id)`), DOI, Synced (ISO date, taken from the
input row, not `now()` — keeps re-projection idempotent).

## Hierarchical structure (folder mirror of the Zotero collection tree)

`project-tree` mirrors the collection tree: each node → one file at `<parent>/<name>.md`,
its children live in `<parent>/<name>/`. A node's single managed block holds a MOC
wikilink list (its child collections) followed by a 10-column paper table (papers filed
directly in that collection). Either section is omitted when empty.

```
31-paper/
  科研项目.md            <- MOC: - [[31-paper/科研项目/上汽标注|上汽标注]]
  科研项目/
    上汽标注.md          <- MOC: - [[31-paper/科研项目/上汽标注/text2cad|text2cad]]
    上汽标注/
      text2cad.md        <- paper table (10 columns)
```

The rebuild source is Zotero via zotero-mcp — the existing files are never source of
truth. The host LLM walks `get_collections(recursive)` + `get_collection_items` into the
tree JSON; the CLI owns all path computation (deterministic, MCP-free — INV18).
