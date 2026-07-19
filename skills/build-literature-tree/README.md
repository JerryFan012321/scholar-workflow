# build-literature-tree

Build evidence-based literature lineage graphs for a research topic: timelines,
method evolution, follow-up relationships, and contribution maps.

Every non-citation edge (`follow-up`, `method-extension`, `representation-shift`,
`benchmark-successor`, `contradicts`) must carry evidence, a confidence score, and
a review status. A citation alone never proves method inheritance or a breakthrough,
and milestones are never auto-flagged without evidence.

Persists a normalized `literature-graph.json` (source of truth) and renders
Mermaid / draw.io / HTML views. Graph data requires user approval before writing.

See [SKILL.md](./SKILL.md) for the full procedure and constraints.
