# analyze-paper

In-depth analysis of one already-ingested paper, written as a companion Obsidian note.
This is the **detailed** reading tier — the counterpart to the ephemeral skim tier in
`recommend-papers`. Where the skim tier decides *whether to read*, this tier produces a
persistent, deep read-through you keep in the vault.

## What it does

- Reads the paper's text through zotero-mcp `get_content` — it never parses the PDF
  body (metadata stays authoritative; INV10/INV24).
- Writes a whole-paper analysis, or appends a focused section (method, experiments, a
  specific section) to the same note on each partial pass.
- Keeps the analysis note **distinct from** the annotations note (from
  `export-annotations`) and cross-links the two via frontmatter `related`.
- Hangs the analysis note on the paper's related-docs hub (`<paper-name>论文相关资料.md`)
  so all of a paper's satellite docs aggregate in one place.

## Where the note lives

- One paper → one analysis note (e.g. `<paper-name>分析.md`) under `vault_root`, in the
  same folder as the paper's index row / hub.
- All analysis content sits in the **human area, outside managed blocks**, so
  re-projection / sync never overwrites it (INV4).

## Analysis vs annotations

| | analyze-paper | export-annotations |
|---|---|---|
| Content | Claude's read-through / synthesis | your highlights + comments |
| Source | get_content (paper body) | your Zotero annotations |
| Note | `<paper>分析.md` | `<paper>批注.md` |

They are separate files, cross-linked via `related` — never merged.

## Usage

Ask to "analyze this paper" (whole) or "analyze the method / this section" (focused).
Focused passes append new sections; earlier sections are preserved. One paper per run.

If NotebookLM was already used to skim this paper in `recommend-papers`, this tier is
the deeper follow-up — it reads the full body via get_content rather than a skim.
