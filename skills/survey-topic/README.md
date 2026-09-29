# survey-topic

The front door for an open-ended "research X" request. It identifies the requested
scope and deliverable, then routes the work to the skill that owns that deliverable.

## What it does

A broad research ask may need a scope choice before it can be routed. Only missing
choices that change the deliverable need confirmation:

- **Depth** — which leg of field-vision you want: the *technical-evolution* view (milestones,
  how the technique evolved) or the *key-problem* view (what's solved, what's open, what's
  hot); and your stance — testing a hypothesis (read a few closely) vs. cold-start mapping
  (gather wide, then build a tree)
- **Breadth** — one problem / one direction / a whole field
- **Time window** — classics / recent / ongoing tracking

When topic context is needed to choose the route, a read-only web reconnaissance may
inform it. That reconnaissance enters no library and leaves no file.

The chosen product belongs to `recommend-papers`, `find-resource`, `ingest-resource`,
`build-literature-tree`, or `analyze-paper`. The router reports that product and its
location rather than imposing a fixed research method.

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
