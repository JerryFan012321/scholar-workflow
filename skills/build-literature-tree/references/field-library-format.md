# Field Library v1 — Three Coexisting Views

This is the current final-output contract for a selected research topic, distilled
from two accepted topic-library organizations. It constrains operations and visible
results, not research reasoning. It is domain-independent; sample paper counts,
scientific terms, classification verdicts, identities and machine paths are not defaults.

## 1. Files, ownership and navigation

A new Chinese-language topic uses the following fixed slots; English output uses the
corresponding English names in parentheses. Existing explicitly chosen names are
preserved during updates; do not silently rename, recreate a deleted note or add a
second list. Do not renumber one view into another.

| Slot | File | Responsibility |
|---|---|---|
| 01 | `01-论文列表.md` (`01-Paperlist.md`) | Complete flat corpus and readable topic entry |
| 02 | `02-文献树.canvas` + `02-文献树.md` (`02-Literature Tree`) | Timeline / literature context, not a radial map |
| 03 | `03-技术路线树.canvas` + `03-技术路线树.md` (`03-Technical Routes`) | Center-out goal → approach → individual paper |
| 04 | `04-挑战洞见树.canvas` + `04-挑战洞见树.md` (`04-Challenges and Insights`) | Center-out goal → problem → solution → individual paper |

Reuse the parent domain overview and its topic links; a new compulsory homepage is
not part of this contract. Each new Markdown starts with its readable title, direct
navigation to the list/three Canvas views and scope. 03/04 also link their paired
editable graph. The topic list and paper companions link back to these views.
02's paired note is the new-library default; when an existing 02 note was explicitly
deleted, use the selected existing analysis/detail entries for explanations instead
of restoring it without instruction.

The list includes every selected paper, even if absent from a representative diagram,
unclassified, missing its local PDF or only read at abstract level. Fixed columns:

| 中文 | English |
|---|---|
| 论文资料 | Paper materials |
| 年份与发表 | Year and publication |
| 研究线索 | Research focus |
| 原 PDF · ZotFlow | Original PDF · ZotFlow |
| 分析与图示 | Analysis and diagrams |

Do not display conference/journal as a complex public type taxonomy. Metadata comes
from Zotero/authoritative records, not body-text guesses. Scope and reading status are
short prose/callouts; audit logs, hashes and machine comments are not table content.
Escape wikilink alias pipes inside Markdown tables.

One reusable paper unit keeps its declared owner and folder. New units use
`resources/papers/<stable-segment>/` under the owning Field through paper-registration;
existing `resources/<segment>/`, `paper_assets/` and declared note names remain valid.
The companion (existing `Paper.md` or declared equivalent), analysis, editable
paper-analysis Canvas, sidecar, notes and evidence assets remain together as owned;
PDFs/formal annotations stay in Zotero. A view referencing an external owner does not
copy or relocate the unit. This layout tool cannot allocate paper identity/ownership.

A companion provides bibliography/source actions, analysis/Canvas/notes, relevant
related work and contextual links back to the list/views. Missing material remains
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
- Every paper has a title/detail link and an immediately adjacent short explanation
  beneath it: what changes, why it matters, and its important condition/cost/unknown.
  The readable detail preserves change, reason, benefit, cost and conditions with
  same-point evidence. Missing cost does not mean zero cost.
- Chronology, membership and citation are not direct inheritance. A visible legend
  explains whether connections are documented extensions or family/context grouping;
  alternative/comparison relations must not masquerade as succession or superiority.
- Use compact blue-accent milestone cards, green-accent pipeline cards, lightweight
  warm-colored local links, muted explanation text and sharp right-angle arrowless
  connections. The bundled `scholar-literature-tree.css` defines the selected treatment.
- The readable note names the diagram subset and all omitted/pending papers, explains
  each selected work and the relations with inline source/detail links, and retains
  the full corpus through 01. No minimum paper count is imposed.

## 3. 03 Technical routes

The center states the research goal. First-level branches name concrete approaches,
not contribution scores or chronology; the outside ends each contain one paper.
A repeated paper may appear under several approaches using distinct visual node IDs
and the same qualified paper identity/owner.

A paper leaf contains a linked short title, one specific sentence explaining its
method, and usable analysis / paper Canvas / original-source links, or a concise
unavailable reason for each missing entry. Never end a branch in an aggregate list
instead of individual paper leaves. Same-route placement does not assert inheritance.

The paired Markdown has: navigation; how to read and evidence/reading coverage;
a concise table “想解决什么 / 大致怎么做 / 论文”
(“Problem / Approach / Papers”); one section per route describing the approach,
requirements and limitations; each paper's material/analysis/Canvas/source entries,
specific method, major components and limits or unknowns; and comparison conditions.
Actual author results and analyst judgments remain distinguishable.

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
- IDs are stable local layout keys, not paper identity. Text is prepared Markdown
  with resolved note/source entries and honest unavailable states; the helper preserves
  it rather than inventing scientific content. A paper appearing twice has two visual
  keys but links the same owner.
- Empty branches produce a root only; empty spine produces an empty graph. Explain
  absence in the owner note/root rather than generating placeholder papers.
- Malformed/unknown fields, duplicate IDs, wrong depth, unbounded input or unsafe
  geometry fail with exit 2 and no success JSON. Tool limits are reported errors,
  never silent truncation or a universal maximum corpus size.

Both radial maps balance whole subtrees left/right, align peer columns, and size cards
from their actual text with at least one spare text line for clicking. Use clear 18px
body text and compact margins, not uniformly oversized or clipped cards. The timeline
uses 22px titles/19px descriptions. More content may expand height; the helper's estimate
still needs a native clipping check for actual fonts and zoom.

All connections use exact integer horizontal/vertical segments, fixed side endpoints,
no arrows, square bends, short practical gaps and shared junctions where appropriate.
Junctions are routing aids, not semantic nodes. No non-junction overlap, non-shared
crossing, text occlusion or dangling edge is acceptable. `validate_canvas` checks the
actual routed segments, not just endpoint distance. Preserve full text, sources and
the original selected topology; layout optimization cannot silently delete content.
A diagram export is optional and never replaces editable Canvas.

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
human presentation. Existing accepted view layout is preserved unless a re-layout is
explicitly requested. Check current bytes before applying a reviewed update and retain
recovery; do not use this new-library contract to overwrite user prose/deletions or
perform an undeclared batch migration. Keep test iterations at one Git-managed test
Vault topic rather than proliferating copies.

Report separately: (a) format/link/geometry checks, (b) installation and native reader
observations, (c) scientific support, (d) human appearance/navigation assessment.
The user must be shown the exact files, how to open/edit them, which source/detail
links to click and what remains pending. Rendering, a schema pass or accepted exemplar
structure is not automatic acceptance of every newly generated topic.
