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
| ... | A et al. | 2024 | CVPR | [key](zotero://...) | [pdf](../31-papers/...) | [2401.01234](...) | 10.xxxx | 2024-01-15 |
<!-- scholar-workflow:end -->

Human notes below stay untouched.
```

## Required columns

Title, Authors (first author + et al.), Year, Venue, Zotero (`zotero://select/...`),
PDF (path relative to `vault_root`), arXiv, DOI, Synced (ISO date).

## Hierarchical structure

```
Domain overview.md   (sub-domain list + intro)
  └── sub-domain/
        └── Topic index.md   (managed-block paper table)
```

Update parent descriptions and sub-indexes before leaf tables. The rebuild source
is Zotero plus the state mapping — the existing table is never source of truth.
