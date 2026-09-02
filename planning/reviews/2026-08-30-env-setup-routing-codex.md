# Codex code-review — env-setup routing fix (2026-08-30)

Scope: v0.21.1 (committed d56954d) + uncommitted self-review follow-ups (Step 0 two-shape
rewrite, Ledger-first rewording, README sync).

Reviewer: codex (read-only, account default). turn.completed present, 5 agent messages,
no TLS failure. **VERDICT: REVISE**, 5 findings. All verified against the files.

## Findings (verbatim, condensed)

1. **[P1] Bare `list servers` breaks the managed-service boundary.** SKILL.md:3 — `list
   servers` commonly means enumerating AWS/Kubernetes/SSH-config inventory, so the claim at
   SKILL.md:18 that `server/key` "directly names this ledger" is false and conflicts with
   the skill's own managed-service exclusion. Remove that trigger or make it `list recorded
   servers` / `list env-records servers`; keep the intentional bare `查找服务器`. Rewrite the
   boundary as an explicit project contract, not a linguistic generalization: "the bare
   query phrases listed in the description route here; action intents require an
   ownership/recorded qualifier."
2. **[P1] New routing branch lacks a negative regression case.** routing.json:165 proves
   only that `查找服务器` fires; nothing catches renewed over-routing from `list servers`.
   Add e.g. input "list servers in this Kubernetes cluster", expected_skill null,
   must_not_trigger env-setup. The Zotero-upload case guards the OLD generic-action
   boundary, not the new bare-enumeration one.
3. **[P2] Missing/empty ledger behaviorally undefined.** SKILL.md:47 calls a query terminal
   while Step 1 offers scaffolding — an executor could auto-run `env-init` or mutate.
   Specify: missing files = "ledger not initialized"; empty = "no matching records"; neither
   authorizes scaffolding or mutation unless requested. Reflect in both READMEs.
4. **[P2] Recorded env-inventory queries outside the contract.** Model records conda/CUDA/
   proxy (SKILL.md:37) but query trigger + Step 0 + constraint cover only "which
   server/key". Add a read-only branch for querying a recorded host's fields, with triggers
   like `what CUDA is recorded for server X` / `查服务器环境记录`.
5. **[P2] `Ledger-first` constraint narrower than Step 0's before-use branch.** SKILL.md:74
   frames both branches as a "which host/key" question, so a task naming an exact recorded
   host needn't satisfy it, though Step 0 requires lookup before any use. Split into two
   independent cases; apply the Zotero/managed-service/public-keyless exclusions to the
   use-intent case only.

Plus: the trigger boundary IS a project-specific routing rule (not intrinsic), but its
"noun directly names the ledger" rationale should go — it overstates the semantic boundary.

Validation: eval schema tests passed (10). Full suite could not start under the read-only
sandbox (pytest couldn't create a temp dir) — "not run", not "failed".

## Triage (reason-don't-relay)
Accepted: #1, #2, #3, #5 in full. #4 PARTIAL — the gap is real (env-inventory queries are
outside the stated contract), but the suggested narrow triggers (`what CUDA is recorded
for server X`) are REJECTED: once routing has landed in this skill, choosing which ledger
field to read is intrinsic ability (tier 1, AGENT.md) and must not be encoded. Fix by not
locking the query branch's wording to "which host/key" — no new trigger words.

Notable: #1 caught a real misjudgment on my side — I flagged bare `list servers` as
uncertain in self-review and kept it anyway. The rationale sentence I wrote was an
over-claim.

---

# Round 2 + 3 — v0.21.2 (2026-08-31)

Scope: the uncommitted 0.21.2 fix batch (the response to round 1) plus three self-review
fixes made before submitting: `must_not_trigger` schema validation, zh trigger
`服务器列表` → `已登记的服务器列表`, and hoisting the managed-inventory exclusion out of the
SKILL.md body into the `description` (the body is read only *after* routing, so a boundary
rule there cannot prevent a mis-route).

## Round 2 — VERDICT: REVISE, 2 findings

Reviewer: codex, resumed session `01a05725-5444-7e41-9f58-c3b79cb636a4`, read-only, account
default. turn.completed present, 0 turn.failed/error, 5 agent messages.

1. **[P1] The managed-inventory exclusion used the wrong axis.** SKILL.md:3 excluded only
   "someone else's managed inventory", but the retained bare trigger `which servers do I
   have` explicitly asserts the user's *own* inventory — so "which servers do I have in my
   AWS account?" / "查找我 Kubernetes 集群里的服务器" still match the positive ownership
   signal and slip past the exclusion. **The distinction is data source, not ownership.**
   Proposed wording: "NOT for inventory exposed by another system, even when that account or
   cluster belongs to the user"; keep bare `查找服务器` working, let explicit
   cloud/K8s/ssh-config context override.
2. **[P2] The new negative eval didn't exercise the triggers that remain.** routing.json's
   `env-not-managed-inventory` used `list servers in this Kubernetes cluster` — but bare
   `list servers` was deleted from the description *in this same diff*, so the case guarded a
   collision that no longer exists and could not guard the retained `find a server`,
   `which servers do I have`, `查找服务器`, `查服务器`, `有哪些服务器`.

Affirmed, not flagged: the `must_not_trigger` structural validation is appropriately scoped
for pytest's stated role; "reading never mutates" is a genuine business safety boundary, not
a tier-1 restatement. Suite: 147 passed.

## Triage (reason-don't-relay)

Both accepted in full — no false positives this round, and neither had been caught by three
self-review passes. Finding 1 is the more instructive: I had been reasoning about the
boundary in terms of *whose* servers, when what actually separates the ledger from AWS/K8s
is *which system holds the record*. The ownership framing was wrong in a way that no amount
of tightening along that same axis would have fixed.

Applied:
- SKILL.md:3 and the third Trigger-boundary bullet → "inventory exposed by another system
  (a cloud account, a Kubernetes cluster, an `~/.ssh/config` dump) … even when that account
  or cluster belongs to the user". Both READMEs carry the same clause.
- `env-not-managed-inventory` replaced by three cases hitting *retained* broad triggers
  under explicit external-system context: `-k8s` ("which servers do I have in my Kubernetes
  cluster"), `-aws` ("find a server in my AWS account"), `-k8s-zh` ("查找这个 K8s 集群里的
  服务器"). Positive `env-query-find-server` (bare `查找服务器`) untouched. 28 → 30 cases.

## Round 3 — VERDICT: APPROVED

Resubmitted with an explicit adversarial question: the P1 fix puts a positive trigger
(`which servers do I have`) and an exclusion that voids it in the *same* description, both
read by the router simultaneously with no body prose to arbitrate — did the fix merely
relocate the contradiction from body-vs-description into description-vs-description?

Codex: no actionable findings. The description is decidable because the exclusion *precedes*
the trigger list and is scoped by explicit external-system context; SKILL.md:17–25 makes the
precedence explicit in the body; routing.json now covers both sides in both languages.
Both READMEs and CHANGELOG carry the same data-source boundary. 147 tests pass.

## Standing lesson

Three consecutive patches on one skill, each fixing the previous fix, all on the trigger
layer. The recurring failure mode was not carelessness but **fixing along the wrong axis**:
0.21.0 tightened by ownership and broke bare queries; 0.21.1 loosened by phrase list and
broke the managed-service boundary; 0.21.2 first re-tightened by ownership again before
round 2 identified data source as the real axis. Before editing a trigger set, name the axis
the boundary actually runs along.
