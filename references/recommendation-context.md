# Project recommendation tasks and human-feedback context

Use this contract only for enabling project recommendations, registering a recurring
task, reading/maintaining that task's context, or maintaining shared curator preferences.
Source execution still follows the selected source contract. Research judgment and
scheduling belong to the external agent/harness.

## Identity and discovery

- `project_id` is the existing schema-2 `project-layout.json` identity. A copied ID at
  a different registered root is a conflict, not another project.
- `producer_id` identifies one recurring recommendation task, never a conversation,
  model, role or privileged agent. One project can register multiple tasks. Each
  execution has its own existing `run_id` and retry-safe submissions.
- Any authorized project agent can continue or edit a task using the same interfaces.
  Roles do not expand filesystem access. Cross-project access requires the actual task
  scope; switching roles does not erase a chat's already-read context.
- The pool database stores project/task registration and context locators. It does
  not import project background into shared preferences. The default task guide only
  returns locators. Use `--read-context` only for the selected authorized task.

Enable the optional component after ordinary project initialization, or explicitly
for an existing selected project:

```text
scholar-research recommendations --profile personal projects enable --project-root PROJECT
scholar-research recommendations --profile personal tasks register --input task.json
scholar-research recommendations --profile personal tasks list --project-id PROJECT_UUID
scholar-research recommendations --profile personal tasks guide PRODUCER_ID
scholar-research recommendations --profile personal tasks guide PRODUCER_ID --read-context
```

`task.json` contains exactly:

```json
{
  "project_id": "<existing canonical UUIDv4>",
  "producer_id": "world-model-evaluation",
  "title": "World-model evaluation research",
  "expected_revision": 0
}
```

Use the returned registration revision when renaming that task. A producer ID cannot
be reassigned to another project. Enablement preserves existing AGENTS.md bytes and
appends one link to `.agents/context/recommendations/CONTEXT.md`; it never generates
placeholder project Skills, scans disk, starts an agent or registers a remote host.

## Project-owned files

```text
AGENTS.md -> .agents/context/recommendations/CONTEXT.md
.agents/context/recommendations/
  component.json                 project, pool and profile binding
  CONTEXT.md                     task discovery and shared project references
  tasks/<producer_id>/
    CONTEXT.md                   this task's editable background and requirements
    feedback.jsonl               automatic derived human-feedback history
    state.json                  consumed event IDs and context revision
```

Real mutable task knowledge stays in this project, not in the generic Skill or a
central agent's memory. Initial task context is a small editable entry; fill it with
actual project requirements and references. Existing human entries are not replaced.
The component is bound to one pool/profile; use a separate synthetic project for
test. Test registration never discovers or copies the personal registry.

## Automatic feedback, without an agent

When a person saves a decision, evaluation, reversal or a processed item's tag
change, code writes its current state and a monotonically sequenced feedback event
in the same database transaction. It immediately materializes JSONL files. Failed
destinations remain in a durable outbox. The running recommendation service retries
delivery without a browser; `feedback sync` is the explicit recovery command.

An unprocessed recommendation does not become feedback. A newly registered task or
new attribution to an already-processed candidate receives a `baseline` of known
current state, not fabricated historical judgments. Its unknown human processing
time is null. A baseline is not another curator preference vote.

Each feedback record contains `schema_version`, `pool_id`, `event_id`, `sequence`,
`kind`, `candidate_id`, `title`, one primary `url`, `tags`, prepared Chinese
`summary`, `processed_at`, `observed_at`, `decision`, `disposition`, `evaluation`,
`candidate_revision`, `resource_digest` and attributed `tasks`. Evaluation retains
score/comment/revision/time and its original content digest. Tasks retain stable
project/producer identity and title. JSONL is JSON records, not an additional YAML
representation. Never hand-edit derived feedback to change a person's judgment.

`ignored` may carry `reason: quality | not_relevant | other`. `not_relevant` requires
an explicit `scope` naming the project or research direction. Legacy unqualified
ignores retain an unknown reason. A project-scoped relevance judgment does not
establish global dislike. Saved/later, selected and quality rejection retain their
separate meanings; scores do not overwrite those meanings.

```text
scholar-research recommendations --profile personal feedback status
scholar-research recommendations --profile personal feedback sync
scholar-research recommendations --profile personal feedback events --producer-id PRODUCER_ID --after 0 --limit 100
```

`events` returns `pool_id`, `items`, `next_sequence`, `has_more`. Continue a nonzero
sequence with `--pool-id` from that response; another pool is rejected. Existing `list --since` filters publication dates,
not feedback dates. Most project tasks simply read their already-delivered JSONL.
Human processing is complete before an agent reads or interprets the record.

Human-decision/evaluation interfaces represent the person's explicit instruction.
Recommending or curator agents do not manufacture human feedback, scores or review
confirmation from their own judgment. Agent interpretations retain agent attribution.

## Updating selected task context

Read the task guide with `--read-context` and its own feedback file. Maintain actual
project requirements and useful judgments; keep the person's words in feedback.
Save through `tasks save-context --input task-context.json`:

```json
{
  "producer_id": "world-model-evaluation",
  "content": "<complete revised task Markdown>",
  "expected_revision": "<context_revision returned by guide>",
  "consumed_event_ids": ["<event ID actually incorporated>"]
}
```

The file revision protects concurrent project agents and human edits. Context is
saved before consumption is advanced; interruption cannot silently acknowledge an
unwritten context. Delivery and interpretation are separate. Foreign task events
cannot be acknowledged. Report conflicts and reread instead of overwriting.

## Central curator: progressive disclosure and consumption

Shared maintained preferences reuse `recommendations context show/save`; organize
the text by the actual research domains rather than a fixed dimension enumeration.
The user-data pool owns `context/PREFERENCES.md` as its readable projection and
`context/inbox/YYYY-MM-DD.jsonl` as pending daily feedback. Unprocessed candidates
stay in the candidate pool. Project background stays in project-owned files.

```text
scholar-research recommendations --profile personal curator batch --limit 100
scholar-research recommendations --profile personal curator consume --input consumed.json
```

`batch` returns current preferences and explicit pending events without reading any
project background. It does not acknowledge them. `consumed.json` contains exactly
`batch_id`, complete revised preference `content`, `expected_revision` and
`updated_by: {"kind": "agent" | "human", "name": "..."}`. Preserve the original
human observations; agent interpretations belong in preferences or ranking reasons.

Consumption checks the preference revision, then atomically saves preferences and
acknowledges only that saved batch. Exact retries are idempotent. Newly arriving
events remain pending. Only consumed temporary daily records/files are cleaned;
the database event history and project feedback remain. Never delete a whole day
blindly. Reordering uses the existing explicit snapshot/ranking contract when that
task actually needs current candidates; it is not the default context load.

## Safety and completion

CLI enablement accepts an explicit selected root. Browser operations cannot supply
project paths or read arbitrary task background. Managed context writes reject
symlinks, hardlinks, changed identity, stale revisions and unknown edited feedback.
Report unavailable destinations and pending delivery independently of the saved
human decision. Registration does not confer server, Git or Zotero permissions.
