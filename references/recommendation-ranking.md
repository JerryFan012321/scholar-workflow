# Shared recommendation context and external reordering

Use this contract when maintaining cross-session recommendation context or returning
an order for the existing local candidate pool. The external agent/harness supplies
judgment and its own model, tools and schedule. Scholar Workflow stores inputs and
results; it does not run a model, choose weights, or start a maintenance worker.

## Owned information

- Per-recommendation `recommendation_reason` is optional, attributed to the submitting
  producer/run. Multiple agents' reasons coexist. Keep it out of the author's abstract
  and the Reading Report. Older submissions without it retain their existing identity.
- A person's scores/comments and selection decisions remain human feedback. Known
  evaluation revisions are retained; no missing historical judgments are fabricated.
  An agent's interpretation belongs in its own rationale or shared notes.
- Source-specific requirements remain under each source, with immutable versions.
- Shared context is free text for current interests and judgments that should survive
  an agent change. It starts empty and supports human/agent attribution and revision
  checks. Do not copy candidate content, metrics or requirements into another registry.
- Rankings contain existing candidate IDs, order, explanations and input digest;
  candidates, documents and raw metrics keep their existing authoritative records.

## CLI handoff

Use the same `--profile personal|test` and state root as the recommendation page.
These operations are local and do not call a provider or model:

```text
scholar-research recommendations --profile personal context show
scholar-research recommendations --profile personal context snapshot
scholar-research recommendations --profile personal context save --input context.json
scholar-research recommendations --profile personal ranking submit --input ranking.json
scholar-research recommendations --profile personal ranking history
scholar-research recommendations --profile personal list --sort agent --format json
```

`context show` returns maintained text, editor/revision, candidate count and current
ranking status. `context snapshot` additionally assembles live candidates, all
attributed reasons, user evaluations and known history, decisions, raw metrics with
observation sources/times, and requirement versions. It includes `context_digest`
and the prior ranking, allowing another agent to continue without an old chat.
The digest is stable for unchanged input and includes the pool identity; exporting
from another profile or a moved state directory requires a new snapshot.

Save shared notes with the revision just read:

```json
{
  "content": "User-approved interests and ongoing judgments, if any.",
  "expected_revision": 0,
  "updated_by": {"kind": "agent", "name": "research-curator"}
}
```

The limit is 16000 characters; an empty string clears the maintained text. Edits
are versioned and conflict instead of overwriting another editor. Keep credentials
out. Saving context changes the next snapshot digest, so export after the desired
context update when preparing a ranking against it.

Submit the chosen complete order:

```json
{
  "schema_version": 1,
  "producer": {"producer_id": "research-curator", "name": "Research curator"},
  "run_id": "a-unique-maintenance-run",
  "expected_revision": 0,
  "context_digest": "<64-character digest from the current snapshot>",
  "rationale": "Explain the priorities and evidence used for this ordering.",
  "items": [
    {"candidate_id": "<existing candidate ID>", "reason": "Explain this item's relevance and position."}
  ]
}
```

List every current candidate exactly once. `expected_revision` is the ranking
revision, separate from the context, candidate and evaluation revisions. Data and
feedback are evidence for judgment, not mandatory factors or a fixed formula.
Keep different platform counts and conditions distinguishable; unknown data is
not zero. Explain claims using the recorded reasons, user judgments and available
observations, and identify unavailable evidence rather than inventing it.

The application rejects missing/duplicate/unknown IDs, changed input or a stale
ranking revision. Exact retries of the same producer/run and payload return the
saved receipt, even after inputs change; changing that payload under the same run
is a conflict. Use a new run for a newly computed order. Submitted rankings retain
their explanations and attribution in history without overwriting human feedback.

## Page behavior

Reading content comes first. The homepage stays compact; full reading content and
links precede reasons, popularity, personal evaluation and intake controls in the
detail drawer. Ranking explanations are optional expandable content after reading.

The gear opens settings: recommendation sources and their requirements, intake
history, and shared recommendation context. Human context edits use the same store
and conflict rules as the CLI. The homepage contains reading/filtering/sorting only.
The context editor disables an unchanged save, reports new edits as unsaved, and
keeps the draft on failure. View latest opens a comparison instead of replacing
dirty text; adopting a new revision is explicit. Cancel discards only after a
confirmation when there are changes. Same-origin session drafts are scoped by
profile and pool, with no promise of recovery after a dynamic-port change.

“Recommendation order” uses a current external ranking while preserving all filters.
Changes to candidate content, human feedback, metric observations or saved
requirements mark it stale; the page explicitly falls back to publication date
until a fresh ranking arrives. No candidate is hidden or removed by reordering.
Refresh the page/list to see externally submitted changes. An external maintenance
schedule is configured in its harness, not by saving context in this application.
