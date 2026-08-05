# survey-topic

The front door for an open-ended "research X" request. When you say *"survey world
models"* or *"get me up to speed on 3D reconstruction"*, this skill scopes the request
before any work starts, then routes it through the other skills.

## What it does

A broad research ask is under-specified: the same topic can mean a 10-minute skim or a
weeks-long deep dive. This skill runs a short **grill** and **converges on the scope with
you** — proposing, letting you correct, confirming — across:

- **Depth** — which leg of field-vision you want: the *technical-evolution* view (milestones,
  how the technique evolved) or the *key-problem* view (what's solved, what's open, what's
  hot); and your stance — testing a hypothesis (read a few closely) vs. cold-start mapping
  (gather wide, then build a tree)
- **Breadth** — one problem / one direction / a whole field
- **Time window** — classics / recent / ongoing tracking

Arriving cold, you often can't scope blind. The skill may first run a quick **breadth-recon
sweep** — reading broadly, including non-arXiv sources (models with no paper, benchmark or
project pages, lab blogs) — to surface the landscape's shape. That sweep is throwaway: it
feeds the scoping conversation, enters no library, and leaves no file.

Once you've agreed on a plan, it hands each step to the skill that owns it:
`recommend-papers`, `find-resource`, `ingest-resource`, `build-literature-tree`, or
`analyze-paper`. When mapping a landscape, one move it uses is the **citation snowball** —
starting from a milestone paper and mining its introduction and related-work section for
same-direction references to seed the search.

## What it does NOT do

- It produces no persistent research artifact and writes no file — every product is made
  by the skill it delegates to, in that skill's own home. The one read it may do for
  itself is the quick throwaway breadth-recon sweep above, purely to scope the request.
- It does not replace `build-literature-tree`. "Draw a tree" still goes straight there;
  this skill only routes to the tree when a survey needs one, and lets the tree run its
  own scoping.
- It is not a targeted lookup (`find-resource`) or a daily feed (`recommend-papers`) —
  those trigger directly on their own verbs.

## When it triggers

Broad, open-ended openings: *"调研…"*, *"了解一下这个方向"*, *"入门这个领域"*, *"这个方向
的现状如何"*, *"help me understand the field"*. A request that already names a specific
action skips this skill and routes to that action directly.
