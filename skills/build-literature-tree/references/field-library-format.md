# Field Library v2 — Canonical Knowledge Vault

This is the portable final-output contract of the user's sole **Canonical Knowledge
Vault (模范知识库)** blueprint. Earlier live Vaults and generated test outputs are
not competing templates. Required format elements must be present; extra structural
elements absent from the blueprint are omitted by default. Later outputs must match
this structure, content placement and visual treatment, not merely resemble it.

The blueprint governs presentation, not substantive content or a quota. Its directory
roles, view types, heading/column roles, link treatment and visual conventions are
reusable; its facts, arguments, explanation depth, images, tables, evidence and number
of papers, routes, challenges or examples are not. Select and explain material from
the actual corpus and analysis scope. Include the figures/tables that support the
current explanation; never match a sample's image count, pad with irrelevant material
or omit necessary evidence to fit its content volume. The existing single-paper
analysis contract determines required framework slots and supported image types,
not a fixed amount of scientific content.

Every structural addition needs a concrete research-reading/navigation purpose and an
explicit user request or a demonstrated correctness/safety need. Report such exceptions;
do not silently add homepages, taxonomies, summary dossiers, status panels or process
commentary. Necessary evidence, conditions and limitations are not clutter. This contract
constrains operations and output, never internal reasoning. Paper counts, topics,
scientific verdicts, personal paths, Vault IDs and attachment keys are not template data.

## 1. Files, ownership and navigation

A new Chinese-language topic uses the following fixed slots; English output uses the
corresponding English names in parentheses. Existing explicitly chosen names are
preserved during updates; do not silently rename, recreate a deleted note or add a
second list. Do not renumber one view into another.

| Slot | File | Responsibility |
|---|---|---|
| 01 | `01-论文列表.md` (`01-Paperlist.md`) | Complete flat corpus and readable topic entry |
| 02 | `02-文献树.canvas`, with the selected explanation variant (`02-Literature Tree`) | Timeline / literature context, not a radial map |
| 03 | `03-技术路线树.canvas` + `03-技术路线树.md` (`03-Technical Routes`) | Center-out goal → approach → individual paper |
| 04 | `04-挑战洞见树.canvas` + `04-挑战洞见树.md` (`04-Challenges and Insights`) | Center-out goal → problem → solution → individual paper |

The parent domain has one `README.md`: a short introduction and a topic table with
`方向 / 收录 / 入口 / 主要问题` (`Topic / Papers / Entries / Research question`).
Reuse an existing overview; provide it when creating an entire new domain. Do not add
a second homepage or a topic-level README. A request concerning one existing topic
does not authorize rewriting its parent domain. Each view's Markdown starts with its
readable title and the blueprint's direct navigation: 01 links the domain and each
view's selected entry (02 may be its paired Markdown rather than its Canvas); a paired
02 links the domain, list and its graph. 03/04 link their own graph, the list and the
related view entries in the selected blueprint variant; not every variant links
every graph. Preserve that variant rather than force full cross-linking. Link each
entry once, not in a repeated navigation paragraph.
Paper companions link back to the list/domain; do not force every page to link
every view or add unrelated shortcuts.
The blueprint has two valid 02 explanation variants: a paired `02-文献树.md`, or
direct links into existing paper analyses/details without that extra note. Declare
the selected variant for a new topic and retain its complete explanations and
navigation. Do not add an empty 02 note for filename symmetry, or remove/recreate an
existing one without instruction and preservation of its content and links.

01 contains its title, direct navigation, a short scope, an honest reading-status
callout when needed, and the table. Do not append mandatory how-to, comparison,
coverage-ledger or workflow sections; place detailed research discussion in the
corresponding view or paper. The list includes every selected paper, even if absent from a representative diagram,
unclassified, missing its local PDF or only read at abstract level. Fixed columns:

| 中文 | English |
|---|---|
| 论文资料 | Paper materials |
| 年份与发表 | Year and publication |
| 研究线索 | Research focus |
| 原 PDF · ZotFlow | Original PDF · ZotFlow |
| 分析与图示 | Analysis and diagrams |

The publication cell normally contains year and venue, not a full bibliography or
complete first-preprint date. Distinguish preprint and publication years when relevant;
keep full dates in the paper record. Do not display conference/journal as a complex public type taxonomy. Metadata comes
from Zotero/authoritative records, not body-text guesses. Scope and reading status are
short prose/callouts; audit logs, hashes and machine comments are not table content.
Escape wikilink alias pipes inside Markdown tables.

Keep the human topic folder to these reading entries and its paper materials.
Layout inputs, test plans, checks, screenshots and release receipts belong to a
separate development/test area, not extra children of the topic or table rows.
State common reading coverage once in 01; other views link to it. Item-specific
missing sources remain visible in 01 and the paper companion. Do not repeat API
checks, ownership disclaimers or the same missing-analysis sentence on every card.
An unavailable analysis stays unavailable; compact presentation must not invent it.

One reusable paper unit keeps its declared owner and folder. New units use
`resources/<stable-segment>/` under the owning Field through paper-registration;
existing `resources/papers/<segment>/`, `paper_assets/` and declared note names remain valid.
The companion (existing `Paper.md` or declared equivalent), analysis, editable
paper-analysis Canvas, sidecar, notes and evidence assets remain together as owned;
PDFs/formal annotations stay in Zotero. A view referencing an external owner does not
copy or relocate the unit. This layout tool cannot allocate paper identity/ownership.

A companion `Paper.md` uses the full paper title, links back to the list/domain, then
`原文和项目`, `分析与笔记`, `最相关工作`, `书目信息`
(`Original and project`, `Analysis and notes`, `Related work`, `Bibliography`).
Only link real available resources; a genuine missing source/analysis is stated briefly,
not replaced by a fake button, empty file or an alternative analysis format. Related
work is not automatically a nearest predecessor. Existing declared names remain valid.
The analysis Markdown and editable paper Canvas belong beside `Paper.md`; actual
images and replay metadata stay in that paper's `attachments/`, never a new Field-level
asset category. Do not create empty attachment directories or extra paper front pages.
Missing material remains
diagnosed. Do not rewrite old paper analysis just to organize its Field. Current
`analyze-paper` requirements — full five-role tree, folded contextual quotations,
direct-evidence emphasis, inline sources, source regions and selected figures — remain
in force for new analyses. Older exemplar analyses are not a competing standard.

## 2. 02 Literature tree: timeline and context

- An aligned horizontal spine progresses left to right through selected milestones.
  Important pipeline/representation entries branch downward; local modules/follow-ups
  grow to their right on compact shared vertical trunks. Do not use a central radial root.
- Only supported novelty types 1 (seminal milestone task) and 2 (seminal pipeline or
  representation) are eligible for the spine/major branches. Type 3 (seminal module)
  and 4 (module improvements to an existing pipeline) remain local. Unknown novelty
  stays pending in the complete list; never promote a paper to fill a layout slot.
  Types, bounded priority and evidence semantics are owned by `evolution-preview.md`.
- The title card contains only a linked short name and year, for example
  `[[papers/example/Paper|Short Name · 2024 ↗]]`, without a heading, full date,
  venue, extra source buttons or a bibliography block. Full metadata stays in 01
  and the paper companion. A long name may wrap; never truncate its identity.
- Every paper has an immediately adjacent one-to-two-sentence explanation beneath
  it: what changes, why it matters, and a material condition/cost/unknown, with a
  compact detail/source entry. Do not add a repeated completion-status paragraph.
  The readable detail preserves change, reason, benefit, cost and conditions with
  same-point evidence. Missing cost does not mean zero cost.
- Chronology, membership and citation are not direct inheritance. A visible legend
  explains whether connections are documented extensions or family/context grouping;
  alternative/comparison relations must not masquerade as succession or superiority.
- The Canvas itself includes a readable title and a compact visible legend. Include
  a section/relation label only where it explains the selected connections, as in
  the blueprint; these are not additional paper nodes or a new classification layer.
- Use compact blue-accent milestone cards, green-accent pipeline cards, lightweight
  warm-colored local links, muted explanation text and sharp right-angle arrowless
  connections. The bundled `scholar-literature-tree.css` defines the selected treatment.
  Short title cards default to 300px width; long names may require 320–350px or more
  only when needed for legibility, never extra metadata. Explanation blocks use the
  same compact column or the blueprint's 320–360px range. Height follows actual text
  plus click space; the sample's 58px height is not permission to clip a new title.
- The selected explanation entry (paired 02 or existing paper details) names the diagram subset and all omitted/pending papers, explains
  each selected work and the relations with inline source/detail links, and retains
  the full corpus through 01. No minimum paper count is imposed.

## 3. 03 Technical routes

The center states the research goal. First-level branches name concrete approaches,
not contribution scores or chronology; the outside ends each contain one paper.
A repeated paper may appear under several approaches using distinct visual node IDs
and the same qualified paper identity/owner.

A paper leaf starts with a level-two linked short title (`## [[owner|Short Name]]`), one specific sentence explaining
its method, and a compact navigation row for available analysis / paper Canvas /
original source. Conditions, costs, components and detailed limitations belong to
the branch or paired prose, not an additional repeated leaf paragraph. Common
unavailable-analysis states are stated in 01 and linked from the view; an item-specific
gap remains diagnosed in its linked companion/list entry rather than a false button.
Never end a branch in an aggregate list
instead of individual paper leaves. Same-route placement does not assert inheritance.
Approach/problem cards link to their corresponding prose section with `展开说明`
(`Details`); do not add another duplicate explanation page.

The paired Markdown has: navigation; how to read and evidence/reading coverage;
a concise table “想解决什么 / 大致怎么做 / 论文”
(“Problem / Approach / Papers”); one section per route describing the approach,
requirements and limitations; each paper's material/analysis/Canvas/source entries,
specific method, major components and limits or unknowns; and comparison conditions.
Actual author results and analyst judgments remain distinguishable.
Do not repeat the same condition/limitation within one paragraph, copy the whole
coverage notice into every view, or restate each paper in a second relation dossier.
Explain each relation once and link to the existing paper detail for its evidence.
Use the blueprint's ordinary labels: `怎么读`, `按问题找论文`, then the approach
sections with `需要什么？` / `还要注意什么？`; each paper has its navigation row and
`怎么做` / `主要部分` / `限制或待确认`. End with `怎么比较这些方案` when comparison
needs explanation. Do not invent a new public vocabulary or turn these fields into
separate status dashboards.

## 4. 04 Challenges and insights

Use the same center-out visual treatment as 03, with an extra semantic level:
goal → concrete problem → solution → individual paper. One problem may have several
solutions and each solution several papers; a paper may address several problems.
“Inference” or “insight” does not mean a new experiment has succeeded.

The paired Markdown explains each problem and solution in ordinary language:
“问题在哪里？ / 怎么解决？ / 需要什么？ / 具体怎么做？ /
改善了什么，还要注意什么？” (problem / solution / requirements / implementation /
benefit and limitations). Include actual steps only when supported; preserve numbers
and evidence from existing source-backed analyses, rather than replacing detail with
a generic slogan. Each paper has the same four navigation entries as 03. Finish with
comparable conditions; grouping alone does not make the methods an integrated system.
Its paper leaves use the same compact content contract as 03; this view's additional
problem/solution level is not permission to expand each paper into a second analysis.
Put requirements and cautions in the solution node and the corresponding prose;
paper leaves remain the same concise title/method/navigation as 03.
Solutions use the blueprint's white detail-card treatment, while the problem level
uses branch cards. This styling does not turn a solution into a paper leaf.

## 5. Layout helper — installed, pure and domain-independent

The skill bundles `scripts/layout_canvas.py` and two CSS assets. Resolve them relative
to the **loaded installed skill directory**, not a source checkout, personal cache
version, project root or Python wheel location. It needs only Python 3.11+ stdlib.

Feed prepared Markdown and structural roles on stdin; stdout is the complete editable
JSON Canvas. For example, with the actual loaded skill directory in `SKILL_DIR`:

```bash
python3 "$SKILL_DIR/scripts/layout_canvas.py" < prepared-layout.json
```

The host saves stdout only after checking it in the user's selected folder. There is
no file-write flag, network access, automatic ownership/registration, classification,
source resolution, app launch or scientific verification.

Input version 1:

- Common: integer `schema_version: 1`, `view: literature | technical | challenge`.
- 03/04: `root: {id, text}`, `branches: [{id, text, children: [...]}]`.
  03 has root/approach/paper depth; 04 has root/problem/solution/paper depth.
- 02: `spine: [{id, text, description, role, children: [...]}]`.
  Spine role is `milestone`, its children `pipeline`, further children `local`.
  Every selected paper entry has a nonempty description beneath its title.
  Current full-view output also supplies prepared `title` and `legend` Markdown
  together, rendered as separate borderless header/legend nodes outside the graph.
  A spine entry may provide `section_label` where the selected relations need one;
  it uses the blueprint's small muted label treatment above that section.
  Older unframed inputs remain accepted as a graph-only compatibility interface,
  not proof of a complete current literature-tree delivery.
- IDs are stable local layout keys, not paper identity. Text is prepared Markdown
  with resolved note/source entries and honest unavailable states; the helper preserves
  it rather than inventing scientific content. A paper appearing twice has two visual
  keys but links the same owner.
- Empty branches produce a root only; empty spine produces an empty graph. Explain
  absence in the owner note/root rather than generating placeholder papers.
- Repeated routes, problems, solutions and paper leaves have no fixed count quota;
  fixed semantic levels define their roles, not the number of instances. Preserve
  every declared instance and its complete text rather than truncating to a sample.
- Malformed/unknown fields, duplicate IDs, wrong depth, oversized byte input or unsafe
  geometry fail with exit 2 and no success JSON. Tool limits are reported errors,
  never silent truncation or a universal maximum corpus size. The stdin byte-size
  and per-text safeguards are input-resource boundaries, not branch/node count quotas.

Both radial maps balance whole subtrees left/right, align peer columns, and size cards
from their actual text with at least one spare text line for clicking. Use clear 18px
body text and compact margins, not uniformly oversized or clipped cards. The timeline
uses 22px titles/19px descriptions. More content may expand height; the helper's estimate
still needs a native clipping check for actual fonts and zoom.
The blueprint's radial center, route/problem and solution columns use 340px cards;
paper leaves use 370px. Keep those widths by default and vary height with the content.
Keep the shipped white background, scoped type sizes, branch treatment and navigation
appearance; do not independently redesign a later topic. A necessary adaptation for
long text must preserve the format and be disclosed, not justified as approximate fidelity.

All connections use exact integer horizontal/vertical segments, fixed side endpoints,
no arrows, square bends, short practical gaps and shared junctions where appropriate.
Junctions are routing aids, not semantic nodes. No non-junction overlap, non-shared
crossing, text occlusion or dangling edge is acceptable. `validate_canvas` checks the
actual routed segments, not just endpoint distance. Preserve full text, sources and
the original selected topology; layout optimization cannot silently delete content.
A diagram export is optional and never replaces editable Canvas.

Native Advanced Canvas saves may add optional `metadata` containing exactly
`version` (nonblank string, at most 64 characters) and `frontmatter`
(object with string keys). Preserve valid metadata; it is editor data,
not paper/Field identity or authorization. Unknown top-level/metadata fields and
malformed types remain invalid. Geometry checks still apply after native saves.

## 6. Native appearance setup

Both CSS files in `assets/` contain only attribute-scoped styling. For the user's
chosen Vault, preview copying them to `.obsidian/snippets/`, then enable them under
Appearance → CSS snippets. Reuse identical installed snippets; a different existing
file is a conflict, not permission to overwrite it. Do not copy a whole exemplar
`.obsidian` directory or secret plugin data.

Advanced Canvas must be installed/enabled for this exact treatment. Check its actual
capabilities; do not claim standard Canvas natively implements Advanced Canvas style
attributes. Configure/verify only these relevant settings, preserving all others:

```json
{
  "edgesStylingFeatureEnabled": true,
  "defaultEdgeStyleAttributes": {"pathfindingMethod": "square"},
  "edgeStyleSquarePathRounded": false
}
```

Obsidian Settings → Community plugins and Appearance are valid manual setup routes.
Do not auto-install plugins or change other Vaults just to run the skill. Missing
prerequisites mean exact native appearance is unverified/unavailable, not a reason to
claim success with a bitmap or curved default rendering.

## 7. Acceptance and safe updates

Before saving, account for the complete corpus, view subset, qualifications, each
paper leaf and its declared links; validate JSON, geometry, paired prose and clean
human presentation. Check blueprint completeness, absence of unrequested additions,
the exact role/heading/navigation structure and native appearance independently;
filenames or geometry alone cannot establish matching format. A topic with navigation
cards but missing its required paper analyses/Canvases is a partial organization result,
not a complete exemplar reproduction. Never create placeholder analyses to pass.
Existing accepted view layout is preserved unless a re-layout is
explicitly requested. Check current bytes before applying a reviewed update and retain
recovery; do not use this new-library contract to overwrite user prose/deletions or
perform an undeclared batch migration. Keep test iterations at one Git-managed test
Vault topic rather than proliferating copies.

Report separately: (a) format/link/geometry checks, (b) installation and native reader
observations, (c) scientific support, (d) human appearance/navigation assessment.
The user must be shown the exact files, how to open/edit them, which source/detail
links to click and what remains pending. Rendering, a schema pass or accepted exemplar
structure is not automatic acceptance of every newly generated topic.
