# Independent literature-evolution preview expectations

Prepared before the fixture and implementation tests. All paper titles, contribution
claims, document paths, hashes and source locations are explicitly synthetic. They
certify neither a real paper's priority nor scientific support or reader behavior.

## Input and hand-written semantic answers

The English fixture declares exactly seven papers and eight contributions:

| Paper | Contribution | Novelty | Placement | Parent |
|---|---|---|---|---|
| Synthetic Task Seed | Task seed | 1 | main | none |
| Synthetic Representation | Representation change | 2 | main | Task seed |
| Synthetic Alternative | Alternative representation | 2 | branch | Representation change |
| Synthetic Module | Local module | 3 | local | Representation change |
| Synthetic Refinement | Pipeline refinement | 4 | local | Representation change |
| Synthetic Mixed Contribution | Local module introduction | 3 | local | Representation change |
| Synthetic Mixed Contribution | Local module adaptation | 3 and 4 | local | Alternative representation |
| Synthetic Unclassified Resource | Pending contribution | none | pending | none |

Each paper appears once in the paper ledger, even when it has two contributions.
The seventh paper remains visible and is not silently assigned novelty type 4.
Main/branch membership is explicit: eligibility does not force every type-1/2
contribution into the main line. The class-3/4 contributions stay local.

Two explicit scientific relations remain in prose, independently of structural parents:

- Task seed to Representation change is an `extends` relation with Change, Reason,
  Benefit, Cost and Conditions, each carrying a labeled evidence basis and PDF source.
- Alternative representation to Representation change is a reverse `comparison`,
  not a reversed parent or an asserted inheritance edge; its Cost is explicitly
  `not_reported`, with no invented evidence or zero-cost conclusion.

The parent graph alone is acyclic. Comparison/alternative relations may cross
branches or point backwards; they must never be converted into structural parents.
The graph preview draws parent membership only. It is not the final evolution figure.

## Validation

- Root fields are exactly schema_version, topic, corpus_scope, language, synthetic,
  papers, contributions and relations. Schema version is integer 1; languages en/zh.
- Paper IDs and contribution/relation IDs are lowercase portable slugs. Paper IDs
  and qualified (source_id, object_id) pairs are unique. Source UUIDs are canonical;
  object IDs are nonwhitespace stable identities. Paths are safe relative Markdown
  declarations, not trusted roots or an existence check.
- Novelty types are strict integers 1..4, without duplicates; [3,4] is legal.
  An empty novelty list requires pending placement. Pending means placement is not
  settled: it may retain known novelty types and evidence, but its parent is null.
  Main/branch require a nonempty subset of [1,2], classification evidence and a reported basis. Local requires a
  nonempty novelty list and a parent; branch also requires a parent. Main may be
  root or have a main parent. Parent targets exist, are not pending, and have no cycle.
- All nonpending classifications use author_statement, experimental_result or
  analysis_inference and have evidence. Statement basis also permits not_reported
  and unverified. The first three require evidence; not_reported requires an empty
  evidence list and is an explicit input assertion, never an automatic conclusion
  from missing evidence. Unverified may have zero or more evidence entries and must
  render as unverified, not as not_reported.
- PDF evidence references a known paper, personal/group library, canonical positive
  numeric library ID, valid eight-character Zotero key, sha256 hash, strict
  nonnegative integer page index and a nonblank section.
- Relation IDs are unique, endpoints exist and differ, and kind is exactly extends,
  alternative, component or comparison. All five tradeoff statements are required.
- Unknown fields refuse at every nesting level. Unknown paper/parent/relation/evidence
  references, invalid IDs, unsafe paths and malformed or unsupported evidence refuse.
- Normalization is deterministic, does not mutate input or invent categories,
  relations, sources, papers or parent assignments. Rendering validates first.

## Human preview

- No H1. The declared topic, bounded corpus and synthetic status are readable.
- Papers, Contributions and Relations appear, with all seven paper names and all
  eight contribution names. Relations show all five tradeoff meanings and evidence
  basis. Chinese structure/state labels are consistently Chinese; English labels
  consistently English. Semantic synonyms are allowed: these are content checks,
  not approval of final wording, column order, colors, spacing or editable carrier.
- IDs, UUIDs and hashes do not flood the human body. Notes show their names and
  relative declared paths, explicitly not checked. No cross-Source ambiguous
  wikilink is generated and no note is read, copied, registered or adopted.
- PDF page indexes become one-based URI pages. Fixture personal evidence at index
  2 links to zotero://open-pdf/library/items/BCDE3456?page=3. Group evidence at index
  4 links to zotero://open-pdf/groups/456/items/CDEF4567?page=5. These are clickable
  declarations, not probed or verified source/reader results. No loopback URL.
- A Mermaid preview is top-to-bottom and represents only the parent graph; prose
  retains scientific relations without pretending the graph includes every relation.
- Special Markdown, HTML, wikilink and Mermaid characters in titles are escaped;
  they cannot inject executable links, HTML, embeds or graph edges.

## CLI and scope

`literature-preview --input FILE|- --format md|json` is a pure local preview.
Both input modes and formats work without config, registry, Zotero, external apps,
network or process execution. JSON preserves normalized machine identities; Markdown
has the human content above. The fixture and isolated CLI filesystem remain unchanged.
Invalid syntax/semantics produces nonzero failure and no partial success preview.

This phase is development-only and uninstalled. Real classification, source support,
Obsidian rendering, layout beauty and final editable carrier remain unverified.
