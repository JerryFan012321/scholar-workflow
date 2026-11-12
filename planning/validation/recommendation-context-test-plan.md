# Recommendation context development verification

Scope: source-level deterministic checks for the approved project-task context,
automatic feedback delivery and metadata-only Zotero intake. No installed-runtime,
native application or human acceptance is inferred from these checks.

## Independent inputs

- One synthetic schema-2 project with a stable UUID and existing human AGENTS.md.
- Two recommendation tasks in that project and one task in a second synthetic project.
- A paper, a blog and a project webpage with full prepared reading content; a shared
  candidate attributed to two tasks, and an unprocessed candidate.
- Explicit human decisions, score/comment changes, classification instructions,
  reversals and two consumers processing different batches.
- A fake Local API provider with existing/new items, child notes, versions,
  an unavailable state and a partial-write retry. No real HTTP provider is used.

## Procedures and expected outcomes

| Check | Expected result |
|---|---|
| Enable/register/list/guide project tasks | Stable project/task identity; human rules preserved; no background read; no role privilege |
| Human decision/evaluation over store, CLI and HTTP | Durable event and automatic task/daily JSONL projections without an agent |
| Unprocessed candidates and duplicate submissions | No fabricated feedback; existing decisions retained; single human event |
| Two tasks, two projects, stale revision | Correct recipients; no cross-project context read or silent overwrite |
| Delivery interruption, unavailable root, symlink/hardlink | Pending durable delivery; safe refusal; idempotent recovery; no escape |
| Curator batch and preference update | Only selected events acknowledged after revision-checked save; later arrivals and original history retained |
| Metadata-only intake for paper/blog/webpage | Correct types and collection; prepared Chinese content, resources and exact human opinions in one child note; no PDF/HTML/Vault writes |
| Zotero unavailable/partial write/retry | Selection and feedback stay saved; visible pending/attention status; no duplicate parent or note |
| Existing initialization and recommendation behavior | Compatible existing CLI, review and identity gates; accepted paper/Canvas outputs unchanged |
| Runtime Skill links and eval schema | All normative links ship and resolve; no development-only references or private runtime paths |

Run the smallest changed unit/contract groups first, then the recommendation and
initializer regressions. Broaden only for new failures or unresolved integration
concerns. Test fixtures and output stay in pytest temporary storage; results are
reported here after execution. No production Vault, registry, Zotero, service,
external agent, network discovery or installation is changed.

## Results

Final source verification: **641 passed**, 23.87 seconds. Five existing PyMuPDF/SWIG
deprecation warnings occurred; no failing checks remain. Runtime code and tests use
only standard-library additions and existing project dependencies.

```text
uv run --offline --no-sync --with pytest python -m pytest \
  tests/unit/test_recommendation*.py tests/contract/test_recommendation*.py \
  tests/unit/test_init_project.py tests/contract/test_init_project_profiles.py \
  tests/unit/test_evals_schema.py tests/contract/test_zotero*.py \
  tests/unit/test_zotero_ingest.py tests/unit/test_recommend_notebooklm_retirement.py \
  tests/contract/test_release_skill_boundary.py -q --tb=short
```

The existing checkout environment lacked pytest. Verification used an offline
cached dependency overlay through uv; it did not replace the installed plugin or
the existing project environment. The uv cache was initially sandbox-blocked;
scoped execution approval enabled its offline use and isolated loopback fixtures. No network provider
or native application was contacted.

The first integration run exposed legacy UI fixture/API assumptions. Preserve the
old per-item preview for legacy payloads while new payloads use configured automatic
intake; explicitly inject a disabled intake service in HTTP boundary-only fixtures.
The new UI journeys now verify configuration, selection without a second preview,
quality rejection and scoped irrelevance. Another check caught a stale returned
queue status; responses now reflect the job persisted in that transaction. A bad
synthetic Zotero key in the new paging fixture was corrected without weakening the
native key validator.

Passing cases include:

- One project with multiple equal tasks, explicit expansion, separate context versus
  feedback consumption, cross-project/profile refusal and legacy rule preservation.
- Decision/evaluation/clear/reversal events, late-attribution baselines, one event
  delivered to multiple tasks, unavailable roots and symlink/hardlink/edited-file refusal.
- Sequence/pool validation, exact-batch consumption, concurrent later arrivals,
  stale preferences and overlapping consumption; original history remains.
- Paper/Blog/webpage/report metadata, full prepared introduction, exact comments
  and classification instructions, resource URLs, and zero original-file transfers.
- Offline retry, lost-note-response recovery, later opinion updates, changed provider
  or target refusal, cancelled paused intake, and preservation of edited/unmarked notes.
- A real synthetic HTTP selection automatically generating feedback and a verified
  fake Zotero parent/note; CLI task/feedback/curator operation with no page or agent.
- Local API bounded queue pagination and legacy adapter calls; existing recommendation,
  initialization, reader, source-plugin, ranking, evaluation, lifecycle and packaging boundaries.

`skill-creator/scripts/quick_validate.py skills/manage-knowledge`: **Skill is valid!**
All local normative links in the new/affected Skill entries and canonical new
references resolve; none points into the development/planning layers. Git diff
whitespace checks pass. The historical HANDOFF original is still present byte-for-byte.

## Remaining acceptance

No source check proves the hotfix is normally installed. A real receiving-collection
write/read-back, native note appearance and human review of the new settings/actions
remain pending a separately authorized normal release/install and single-object
acceptance. No production collection, original-file store, Vault, service or plugin
installation was modified in this development batch.
