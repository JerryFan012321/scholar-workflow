# Document Discovery

How `project-review` decides what to read. Config wins; auto-discovery is the fallback.

## Config format

A project pins its strategic document set by committing one of:

- `.project-review.md` (repo root), or
- `docs/strategy/.review-sources.md`

When either exists, read the files it lists and skip auto-discovery entirely — the maintainer has declared what the "strategic picture" is.

```markdown
# Project Review Sources

## Principles
- AGENT.md

## Goals
- planning/GOALS.md

## Progress
- planning/HANDOFF.md

## Roadmap (latest 2 in dir)
- planning/

## Coverage
- evals/
```

Rules:

- Lines starting with `#` are section headers, for grouping only.
- Each other line is a path relative to repo root.
- A path ending in `/` means "read the 2 most-recently-modified `.md` files in that directory" — keeps rolling notes (meetings, phase specs) fresh without listing each.
- A file path that no longer resolves is reported as a stale source, not silently dropped.

## Auto-discovery fallback

Used only when no config file exists. For each role, probe the exact paths in order and take the first that resolves. Skip a role that matches nothing. Never use `**/` recursive globs — they pull in `node_modules/`, `vendor/`, `third_party/`, `.venv/`, `dist/`, `build/` and produce noise. Exclude those directories.

| Role | Exact paths, in priority order |
|---|---|
| Principles / rules | `AGENTS.md` → `AGENT.md` → `CLAUDE.md` → `CONTRIBUTING.md` |
| Identity / positioning | `README.md` → `README.*.md` → `docs/README.md` |
| Goals / intent | `planning/GOALS.md` → `docs/strategy/vision.md` → `VISION.md` → `GOALS.md` |
| Roadmap / phases | `planning/*.md` → `docs/strategy/roadmap.md` → `ROADMAP.md` |
| Progress / hand-off | `planning/HANDOFF.md` → `HANDOFF.md` → `docs/strategy/meetings/` |
| Change history | `CHANGELOG.md` → recent `git log --oneline -20` |
| Test / acceptance coverage | `evals/` → `tests/` |

For the coverage role, when a machine-readable file (e.g. `evals/*.json`) states pass/pending status, report the ratio rather than just listing filenames — "3 of 16 outcomes pass, 13 pending" is a real coverage signal; "there is an evals folder" is not.

## First-run onboarding

When the set was auto-discovered, append a ready-to-commit `.project-review.md` at the end of the output, listing the files actually read this run. The user commits it, and every later run is pinned and noise-free.
