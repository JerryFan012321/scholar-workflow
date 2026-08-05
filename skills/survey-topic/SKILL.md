---
name: survey-topic
description: Scope an open-ended research request, then route it through the other skills. Grills breadth and depth first, proposes an ordered research plan, and delegates each step — it produces no persistent research artifact of its own, though it may run one throwaway breadth-recon sweep to scope the field. Triggers 'survey a topic', 'research this area', 'get me up to speed on', 'what's the state of', 'help me understand the field', '调研', '了解一下这个方向', '入门这个领域', '这个方向的现状', '帮我梳理这个领域'. Not a targeted paper lookup (find-resource), a daily feed (recommend-papers), or tree-building on its own (build-literature-tree).
---

# survey-topic

The entry point for a broad "research X" request. A bare model, told "survey world
models", starts summarizing before it knows how wide or deep to go. This skill fixes
that: it **scopes** the request with a short grill, then **routes** the scoped request
through the skills that already exist. It is a conductor, not a performer — it delegates
all acquisition, dedup, and tree-building, and writes nothing itself. The one read it may
do for itself is a quick throwaway sweep to scope the request (see Grill).

## Depth → skill map (the external prescription)

Each depth answer selects a downstream skill. This ladder is repo-specific — which skill
serves which research sub-goal is the one thing worth encoding here.

| Depth the user wants | Route to |
|---|---|
| stay current / see what's new | `recommend-papers` |
| onboard / map the landscape | `find-resource` (gather) → `build-literature-tree` |
| structure systematically | `build-literature-tree` (owns its own gates) |
| read the key few closely | `ingest-resource` → `analyze-paper` |
| track an author/lab over time | `recommend-papers` watchlist sub-mode |

## Grill — converge on scope with the user

Scope is something you **reach agreement on with the user, step by step** — not a plan you
hand down. Offer your reading of what they want (with a sensible default), let them correct
it, and converge. Keep it a short back-and-forth: don't interrogate axis by axis, and don't
fix the plan unilaterally. The grill is done the moment the user agrees to a concrete
"first X, then Y".

You are scoping the request's depth (程度) and breadth (范围). Organize the depth question
around the two legs of field-vision a researcher actually decides along, which map onto
the table above:

- **Depth — field-vision**: a *technical-evolution* view (what the milestones are, how the
  technique evolved) or a *key-problem* view (the field's goal, what's solved, what's still
  open, what's hot now). The first leans on the novelty tree; the second on the live paper
  front.
- **Depth — stance**: arriving with a hypothesis/question to test (go narrow — read a few
  papers closely) vs. cold-starting to map the terrain (go wide — gather, then build a tree).
- **Breadth** — one specific problem / one direction / a whole field. Sets seed count and,
  if a tree follows, how wide it spreads.
- **Time window** — founding classics / recent progress / ongoing tracking.

**Cold-start orientation.** Arriving cold, you often can't fix depth/breadth blind. A quick
**breadth-recon sweep** first — reading broadly, *including non-arXiv sources* (models with
no paper, benchmark/project pages, lab blogs) — surfaces the landscape's shape so you can
scope against it. It is throwaway: it feeds the grill, enters no library, leaves no file.

If the topic word is polysemous (e.g. "world model" splits along function vs. domain), name
the cut-axis and confirm it before scoping breadth. Once the user lands on "structure
systematically", hand off to `build-literature-tree` and let it run its own gates — don't
re-lock resolution or boundary here (that's the tree's job; INV22).

## Steps

1. **Recognize the research intent** and name the topic back. This skill is the coarse
   front door; anything already carrying a specific verb (find / import / draw a tree /
   recommend) routes straight to that skill, skipping this one.
2. **Grill to an agreed plan.** Work depth + breadth + time window (above) into an ordered
   plan — which skills, in what order, on what scope — and **converge on it with the user**:
   propose, let them correct, confirm. Don't start delegating until they've agreed to it.
3. **Delegate, in order.** Hand each step to its skill, carrying the agreed scope as input:
   seed count, time window, which collection/topic to gather. One seeding move worth naming
   when mapping a landscape: start from a milestone/seed paper and **mine its introduction
   and related-work section** for same-direction references (citation snowball — fix a
   milestone paper, then trace the papers before and after it) — feed those to
   `find-resource`, then on to `build-literature-tree`.
4. **Report where each product landed** — candidate list, ingested items, tree notes,
   analysis notes — each owned by the skill that made it. This skill leaves no artifact.

## Constraints
- **Scope before route, by agreement.** The grill's output is a scoped plan the user has
  agreed to — converge on it together, then delegate. This skill is the reason a broad
  request gets scoped with the user instead of answered off the cuff.
- **Delegate the mechanics.** Existence check, arXiv-only download, metadata, tree
  rendering, skim — each lives in its owning skill and runs under that skill's
  constraints. This skill calls them; it does not re-implement or override them.
- **The tree stays independent (INV22).** A "draw a tree" request reaches
  `build-literature-tree` directly; this skill is only one upstream caller. When it
  routes there, it hands off scope and lets the tree run its own gates.
- **Leave no artifact.** The plan lives in the conversation. Every file/library product
  is written by the delegated skill, in its own home — this skill adds no new file type
  and no new state.
- **Orientation reads; acquisition is delegated.** The cold-start sweep is read-only and
  throwaway — it feeds the grill, enters no library, leaves no file. What gets acquired,
  from which source, and where it lands is owned by `source-policy` and `ingest-resource`;
  this skill neither restates nor overrides it.
- **Additive, plan-first (security-policy).** Any writes happen inside a delegated skill
  under the standing approval model; destructive actions still gate there, per item.

## References

Load on demand.

- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md` — arXiv-only acquisition (applies once routing reaches ingest)
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md` — additive-write + plan-first boundary the delegated skills obey
