---
name: project-review
description: Read-only strategic snapshot of the whole project — auto-discovers a project's own strategy docs (principles, roadmap, progress, test coverage) and reports a five-dimension picture of where it stands. Use for direction review, alignment check, milestone status, pre-meeting overview, or to regain the big picture after long focused work. Triggers 'project review', 'strategic review', 'where is the project at', 'what's the project status', '项目全景', '审视一下方向', '项目现在什么状态', '现在整体进展'. Not code or PR review (that's a diff-level review), not a data-consistency audit.
---

# project-review

A panoramic, read-only snapshot of a whole project. Long focused work narrows attention to the file in front of you; this skill steps back and reads the project's own strategy documents to answer "where does this stand, and what still needs closing?" — the perspective that slips away mid-flight.

It is deliberately **generic**: it does not know any one project's filenames. It discovers each project's own documents, reads that project's own stated principles, and judges by them. On a project whose root defines review principles (e.g. an `AGENT.md` / `CLAUDE.md`), those principles govern the read; on a project with none, it falls back to the dimensions below.

## Step 1: Load the document set

Discover what to read, in this order.

1. **Config first.** If the project declares its own review sources, read that list and stop discovering — the maintainer already said what constitutes the strategic picture. Look for, in order: `.project-review.md` at repo root, then `docs/strategy/.review-sources.md`. Each non-comment line is a path relative to root; a path ending `/` means "the 2 most-recently-modified `.md` files in that directory".

2. **Auto-discover** (only if no config). Probe these generic roles by exact path with sequential fallback — never `**/` recursive globs, which match vendored/`node_modules` noise. Take the first hit per role; skip a role if nothing matches. Exclude `node_modules/`, `.venv/`, `vendor/`, `third_party/`, `dist/`, `build/`.

   | Role | Exact paths, in priority order |
   |---|---|
   | Principles / rules | `AGENTS.md` → `AGENT.md` → `CLAUDE.md` → `CONTRIBUTING.md` |
   | Identity / positioning | `README.md` → `README.*.md` → `docs/README.md` |
   | Goals / intent | `planning/GOALS.md` → `docs/strategy/vision.md` → `VISION.md` → `GOALS.md` |
   | Roadmap / phases | `planning/*.md` → `docs/strategy/roadmap.md` → `ROADMAP.md` |
   | Progress / hand-off | `planning/HANDOFF.md` → `HANDOFF.md` → `docs/strategy/meetings/` |
   | Change history | `CHANGELOG.md` → recent `git log --oneline -20` |
   | Test / acceptance coverage | `evals/` → `tests/` (list what exists; note pass vs pending/pass ratios if a machine-readable file like `evals/*.json` states them) |

3. **Nothing found.** If neither config nor any role resolves, say so and suggest the project add a `.project-review.md` listing its strategy docs. Do not invent a picture from an empty set.

**Completion criterion:** every discovered document has been read (not skimmed by filename), and each of the five dimensions below is backed by specific documents or explicitly skipped for lack of data.

## Step 2: Five-dimension analysis

Produce a dimension only when supporting documents exist. Skipping a dimension is correct when the data is absent — speculation reads as fact and misleads worse than silence. Judge by the project's own stated principles where they exist; otherwise by the plain reading below.

1. **Alignment** — Is current work serving the stated goals/intent? Which assumptions are validated, which challenged, which untested? (Infer goals from README only if no goals doc exists; mark it inferred.)
2. **Roadmap status** — Done / in-progress / planned. Where the current phase sits in the whole arc. Any work that has drifted off the stated plan.
3. **Bottlenecks & open ends** — What is genuinely blocked vs. merely unfinished. Separate technical blockers from research/product ones. Name what is "written but never run end-to-end" distinctly from "not started".
4. **Coverage gap** — What the tests/evals actually guard vs. what is claimed done. Flag capabilities described as finished but backed only by pending/absent tests.
5. **Next steps** — Recommendations grounded in the four dimensions above, ordered urgent vs. important. Prefer one move that closes several open ends at once.

## Step 3: Output

Print to the terminal. Do not write a file unless the user explicitly asks to save one — a review skill that spawns review documents just adds noise. Follow the user's language.

```
================================================
  PROJECT REVIEW — <project-name> | <YYYY-MM-DD>
  Sources: <config | auto-discovered>
================================================

## 1. Alignment
## 2. Roadmap status
## 3. Bottlenecks & open ends
## 4. Coverage gap
## 5. Next steps
```

If the set was auto-discovered, end with a one-block suggested `.project-review.md` listing the files actually used, so the next run is pinned and noise-free.

## Constraints

- **Read-only.** Modify nothing. The value is perspective, not action — decisions stay with the user.
- **Discover, don't assume.** Never hardcode one project's filenames as required. A project supplies its own documents and its own review principles; this skill adapts to them.
- **State evidence, skip on absence.** Every claim traces to a document read this run. A dimension with no backing data is skipped, not guessed.
- **No sibling overlap.** This is whole-project direction, not diff-level review (`code-review`) and not data-consistency auditing across external systems.

## References

Load on demand.

- `references/discovery.md` — the config format and the auto-discovery fallback table in full
