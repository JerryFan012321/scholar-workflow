# Source & attribution

`SKILL.md`, `GLOSSARY.md`, and `agents/openai.yaml` in this folder are vendored
**verbatim** (byte-for-byte) from Matt Pocock's public skills repository:

- Repo: https://github.com/mattpocock/skills
- Path: `skills/productivity/writing-great-skills/`
- Files: `SKILL.md`, `GLOSSARY.md`, `agents/openai.yaml` (the complete folder)
- Fetched: 2026-08-02
- SHA-256 verified identical to upstream at fetch time
- License: MIT — full text in `THIRD_PARTY_LICENSES` (Copyright (c) 2026 Matt Pocock)

## Why it lives in `dev-guide/`, not `skills/`

It is a **development-time authoring reference** (`disable-model-invocation: true`) —
the vocabulary and principles for writing scholar-workflow's own skills well. It is
**not** a runtime skill for end users, so it stays out of `skills/` and is never shipped
to the `release` branch by `scripts/make-release.sh`.

## Editing policy

Do not edit `SKILL.md` / `GLOSSARY.md` / `agents/openai.yaml` in place — they are an
external verbatim copy. Record any local notes or adaptations here in `SOURCE.md` instead,
so the originals stay diffable against upstream.
