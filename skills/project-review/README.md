# project-review

A read-only strategic snapshot of a whole project. Long stretches of focused work
narrow your attention to the file in front of you; this skill steps back, reads the
project's own strategy documents, and reports where the project stands and what still
needs closing.

## What it does

- **Discovers** the project's strategy docs — config-first (a committed
  `.project-review.md`), auto-discovery as fallback (principles, goals, roadmap,
  progress, change history, test coverage).
- **Reads the project's own principles.** If the repo root declares review principles
  (an `AGENT.md` / `CLAUDE.md`), those govern the judgment. It hardcodes no project's
  filenames — it adapts to whatever a project provides.
- **Reports five dimensions** — alignment, roadmap status, bottlenecks & open ends,
  coverage gap, next steps — skipping any dimension it has no data for.

## How to use it

Ask for a project review in natural language, or type `/project-review`:

- *"give me a project review"*
- *"where is this project at?"*
- *"审视一下现在的整体进展"*

Output goes to the terminal. Nothing is modified, and no file is written unless you
explicitly ask to save one.

## Pinning the document set

To make every run precise and noise-free, commit a `.project-review.md` at the repo
root listing your strategy docs. The first auto-discovered run prints a suggested one
you can copy. See `references/discovery.md` for the format and the auto-discovery
fallback table.

## What it is not

- Not code or PR review — for a diff-level second opinion, use `code-review`.
- Not a data-consistency audit across external systems.
- Not a report generator — it produces perspective for you, not documents.
