# Contribution and Evolution Preview

Use this result interface when the requested literature view distinguishes technical
progress from concept membership. It is a zero-write preview, separate from the legacy
technical/challenge tree projector. The preview does not select a final editable carrier
or certify source support, paper priority, reader behavior or visual acceptance.

## Input and invocation

Provide a document conforming to `contracts/literature-evolution.schema.json`:
integer `schema_version: 1`, `topic`, bounded `corpus_scope`, `language` (`en`/`zh`),
explicit `synthetic`, and `papers`, `contributions`, `relations` arrays.

```bash
scholar-workflow literature-preview --input evolution.json --format md
scholar-workflow literature-preview --input evolution.json --format json
```

The command validates before emitting output. It requires no Hub, configuration,
registered workspace or service. It does not resolve the registry, read notes/PDFs,
write a Vault, allocate paper folders, open readers or modify the original paper units.
Unknown fields and unresolved identifiers are input errors, never silently omitted.

## Identity and contribution fields

Each paper appears once, with a local `paper_id`, stable qualified `source_id` +
`object_id`, display `title`, and declared Source-relative `note_path`. Paths are not
identity, existence proofs, file authorization or a cross-Vault reader mapping.
Repeated contributions reuse that paper entry; references never create another owner.

Each contribution has `contribution_id`, `paper_id`, `title`, `novelty_types`,
`placement`, explicit `parent_id` (or null), and a `classification` statement.

| Novelty type | Meaning | Eligible placement |
|---|---|---|
| 1 | Seminal work for a milestone task | Main, major branch or local |
| 2 | Seminal work for a novel pipeline/representation | Main, major branch or local |
| 3 | Seminal work for a novel module | Local only |
| 4 | Module augmentation improving an existing pipeline | Local only |

Types describe contributions, not quality. A contribution may have overlapping types,
including 3 and 4. Only a nonempty subset of 1/2 is eligible for `main`/`branch`;
eligibility does not require placement there. An unresolved type stays empty with
`placement: pending`; do not default it to type 4. A known classification may also
remain pending while its placement is unresolved. Pending has no parent. Nonpending classifications
require a source-supported basis within the declared corpus, not an unbounded global
first-paper claim. A branch/local contribution needs a parent; a main parent, if any,
is main. The structural parent graph has no cycles or pending parents.

## Scientific relation fields

Each relation has its own `relation_id`, existing `from_id`/`to_id` contributions,
`kind` (`extends`, `alternative`, `component`, `comparison`), and five statements:
`change`, `reason`, `benefit`, `cost`, `conditions`. All five remain visible.

Every statement contains `text`, `basis` and `evidence`. Basis is
`author_statement`, `experimental_result`, `analysis_inference`, `not_reported` or
`unverified`. The first three carry evidence; `not_reported` carries none and is the
input author's explicit, still-unverified assertion about the source. `unverified`
means not yet extracted/checked and may retain candidate pointers. Neither is a
supported nonpending classification. Missing cost is not zero cost; missing conditions do not establish
comparability. Author statements, observations and analyst inference remain distinct.

An evidence pointer contains `paper_id`, `library_type` (`personal`/`group`), positive
canonical `library_id`, Zotero `attachment_key`, `content_hash` (`sha256:…`), zero-based
physical `page_index`, and human `section`. The preview derives a stable Zotero native
page URL; it promises a physical page, not sentence selection or a ZotFlow mapping.
It does not verify attachment ownership, hash, page existence or scientific support.
Actual source verification remains necessary before treating a real relation as accepted.

## Visible result and completion boundary

The preview has no H1 and uses the selected language for structural labels and states.
It shows the bounded corpus, synthetic status, the complete paper ledger, every
contribution and the five statements of every scientific relation, with inline sources.
Declared note paths and source pointers are explicitly unverified; no ambiguous
cross-Source wikilinks are fabricated. Machine identities and hashes remain in JSON.

The compact top-to-bottom Mermaid overview contains only contribution titles/types
and explicit parent membership, using straight orthogonal, arrowless connections.
It does not convert chronology, membership, comparison or alternatives into inheritance.
Scientific relations remain complete in the adjacent prose even when not drawn in this
placement-only overview. This preview is not the final no-crossing evolution diagram.
Final editable carrier, compact appearance and real scientific content require their
own acceptance; renderer/schema success does not satisfy those judgments.
