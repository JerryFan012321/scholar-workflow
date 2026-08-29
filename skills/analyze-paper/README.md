# analyze-paper

In-depth analysis of one already-ingested paper, written as a companion Obsidian note.
This is the **detailed** reading tier — the counterpart to the ephemeral skim tier in
`recommend-papers`. Where the skim tier decides *whether to read*, this tier produces a
persistent, deep read-through you keep in the vault.

## What it does

- Reads the paper's text through zotero-mcp `get_content` — it never parses the PDF
  body (metadata stays authoritative; INV10/INV24).
- Optionally reads the paper's **code repo** to clarify an implementation — but **only
  when you ask**, never on its own. It clones read-only and never runs the code (no
  execute, no `pip install`, no build); the repo is treated as untrusted evidence, never
  as instructions. Ephemeral by default; it saves the repo under `code_repo_root` only if
  you ask to keep it.
- Maintains **one evolving note per paper**: a whole-paper or focused pass adds or deepens
  sections; a single section may be revised in place, but the note as a whole only
  accretes — a rerun never blanks it and rewrites.
- Keeps the analysis note **distinct from** the annotations note (from
  `export-annotations`) and cross-links the two via frontmatter `related`.
- Hangs the analysis note on the paper's related-docs hub so all of a paper's satellite
  docs aggregate in one place, and (if the direction has a literature tree) states where
  the paper sits in it — surfacing update candidates without writing the tree.

## Where the note lives

- One paper → one analysis note (e.g. `<paper-name>分析.md`) under `research_vault_root`, in the
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
Each pass evolves the same note — new or deepened sections, no blank-and-rewrite. One
paper per run. To have it read the implementation, say so explicitly ("read the code" /
"check the repo") and whether to keep the clone.

If NotebookLM was already used to skim this paper in `recommend-papers`, this tier is
the deeper follow-up — it reads the full body via get_content rather than a skim.
