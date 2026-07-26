# Obsidian Index Format

## Managed block

The machine-maintained table lives inside a managed block. Content outside the
markers must never be modified.

```markdown
# <Topic> Paper Index

Human notes above stay untouched.

<!-- scholar-workflow:start -->
| Title | Authors | Year | Venue | Zotero | PDF | arXiv | DOI | Synced |
|---|---|---:|---|---|---|---|---|---|
| ... | A One; B Two | 2024 | CVPR | [open](zotero://select/items/@8USWVHLD) | [PDF](http://127.0.0.1:23128/open/paper/S6LZUS6S) | [2401.01234](https://arxiv.org/abs/2401.01234) | 10.xxxx | 2024-01-15 |
<!-- scholar-workflow:end -->

Human notes below stay untouched.
```

## Required columns

Title, Authors (`; `-joined), Year, Venue, Zotero (`zotero://select/items/@<item-key>`),
PDF (link-service URL `http://127.0.0.1:<port>/open/paper/<attachment-key>` — never a
relative or absolute file path), arXiv (`[id](https://arxiv.org/abs/id)`), DOI, Synced
(ISO date, taken from the input row, not `now()` — keeps re-projection idempotent).

## Hierarchical structure

```
Domain overview.md   (sub-domain list + intro)
  └── sub-domain/
        └── Topic index.md   (managed-block paper table)
```

Update parent descriptions and sub-indexes before leaf tables. The rebuild source
is Zotero plus the state mapping — the existing table is never source of truth.
