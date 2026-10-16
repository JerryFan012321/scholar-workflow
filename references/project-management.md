# Research Parent and Execution Subprojects

Shared result contract for research projects managed by Scholar Workflow. Use it
when initializing a research parent/execution child, organizing the parent entry,
or reviewing collected child experiments. It does not prescribe how an agent thinks
or turn a management request into permission to deploy, develop, or run experiments.

## Ownership and required result

| Object | Owner and required boundary |
|---|---|
| Local research parent | Stable project identity, explicit materials, internal PROJECT, one detailed plan, project knowledge/literature, agent guidance/skills, collected experiment archives, local analysis and result/recovery state |
| Remote execution child | Its own identity and parent association, source Git, canonical configs, environment definitions, tools/tests, datasets, experiment recipes and observed execution records |
| Reusable paper unit | Its existing Zotero/Knowledge owner; the parent keeps explicit entries, not another copy of the general analysis |
| Execution placement | Existing private server inventory and credential-free Target declarations; no second server/credential registry |
| Local code recovery copy | Recoverable code history and necessary nonsecret recovery information, not a development working tree or proof of verified backup |

The parent remains a complete research project, not a result inbox. Preserve its
knowledge, decisions, lightweight literature division of work, rules and selected
materials when source development moves remotely. PROJECT remains internal and
VS Code-oriented; README remains the external presentation. Keep one detailed plan
authority in PROJECT, an explicitly selected SCHEDULE, or the existing plan.
Project-specific guidance lives in canonical AGENTS with thin host entry points;
project skills are not automatic conversation-memory synchronization.

Use the owning format contracts: [project-entry.md](project-entry.md) for the
six-section PROJECT, [experiment-review.md](experiment-review.md) for conditions/
results in one comparison table and complete selected history, and
[project-context.md](project-context.md) for supported material references.
Existing paper Markdown/Canvas/evidence formats remain unchanged. Do not replace
these outputs with a file-tree dump, generic status dashboard or machine metadata.

## Source Git and development location

- All child code changes, whether human or agent, happen remotely. Every child has
  its own remote source Git; the parent has separate local-only management Git.
  The parent does not push and has no daily-development clone of any child.
- `primary` means Primary Subproject, a role rather than the parent's identity or
  a Git branch. Only primary may push project-owned development history to GitHub.
  Other children may read/clone/fetch original upstreams but do not upload their
  own changes. Repository creation, visibility and publishing are separate actions.
- For a child executed on several servers, record its main development location.
  Concurrent work uses separate branches/working directories; experiments execute
  a fixed child commit in a separate directory that is not updated during the run.
  Remote-only development does not eliminate merge conflicts or authorize force push.
- Source/config profiles, `src/utils/dataset_toolkit/`, machine-neutral `env/`,
  and per-dataset data organization belong to the remote execution child; they
  have not been removed from the project system. Parent Git may track its readable
  management documents and lightweight archives, not large data or code-recovery packs.
  Existing tracked content/ignore rules are not changed implicitly.

## Experiment registration, collection and analysis

Every child registers all experiments, including failed and interrupted executions.
The required parent organization is
`experiments/<child-segment>/<run-id>/attempts/<attempt-id>/`, with stable parent/
child identity behind the directory segment. Qualify Run/Attempt references by
their child; matching names in different children are not the same experiment.
Different executions of the same Run have distinct Attempts. Target, GPU and
execution time do not redefine the scientific recipe.

Collected evidence includes the child source commit, entry script, captured
resolved config/environment, data identity/version, status, metrics and required
result material. Do not replace that commit with the parent's management Git HEAD
or use a mutable working config as the recorded recipe. Large datasets/outputs may
remain remote with explicit manifests; a recovery-only source policy does not
remove the per-experiment snapshots needed to explain a comparison.

Remote execution facts and local human analysis have separate ownership. Preserve
all recorded outcomes, raw evidence and local analysis when collecting updates.
The reception contract requires same-identity/same-version/same-content replay to
be idempotent and conflicts to stop without overwrite. Legitimate lifecycle updates
need the known baseline, explicit revision checks and receipts; a growing execution
file must not be called an immutable snapshot. Indexes remain rebuildable views.

Analyze and compare in the parent. Keep names, actual execution times, purpose,
shared conditions, intentional differences and corresponding results together,
using the existing review contract. Unknown, remote-only, failed and conflicted
evidence stays visible; collection does not itself prove a scientific conclusion.

## Tools, context and recovery

An agent may operate through local SSH tools or run its CLI remotely. Humans may
use VS Code Remote-SSH; cmux only chooses window placement. A skill does not require
a Hub, new worker, particular model or transfer of every agent to the server.
Remote guidance/skills and execution environment must actually be available; local
rules, plugins, authentication and session history are not automatically inherited.
Provide selected task context without copying the entire knowledge base or secrets.
Native tools and the host retain their own access/approval boundaries.

Minimal local code recovery must cover retained experiment commits and necessary
nonsecret restoration information. Identify gaps for uncommitted/untracked original
work, required LFS objects or other dependent repositories rather than claiming a
Git archive includes them. Copy/hash verification and artifact promotion do not prove
an independent backup or restore exercise; use the existing
[experiment records](../skills/init-project/references/experiment-records.md) for retention
and keep verified-backup status unavailable until that separate contract exists.

## Current capability boundary

This contract is a required target and reporting boundary, not a claim that its
automation exists. Determine the installed capability before an operation:

| Requested operation | Current interface and honest result |
|---|---|
| Parent/child initialization | The helper still creates one generic source skeleton, not two role-specific layouts. For a parent/child request, return the proposed layout and unsupported-operation reason; do not apply the generic skeleton and call it complete. Explicit legacy generic initialization retains its existing contract. |
| Child registration and parent archive reception | Existing experiment commands use flat `experiments/<run-id>`; there is no child-qualified receiver. `new-run` reads the selected root's Git HEAD, and `promote` copies selected artifacts, not all child archives. Do not invent a reception command, manually fabricate schema fields or flatten child identity to make the CLI accept it. |
| Remote code in the material inventory | Context schema 1 supports local project-file and Zotero/Obsidian resources, not SSH code references. Keep supplied remote locators as explicitly unverified human information until the supported locator contract exists; never encode them as a fake local path or unknown provider. |
| PROJECT and experiment review | Read the explicitly selected, safely accessible material and produce the existing human format. Identify remote/unavailable sources and incomplete lifecycle verification. Review does not collect, execute, edit raw records or grant access to remote roots. |
| Code recovery and verified backup | No new code-recovery service or verified-backup writer is introduced by these skill edits. Deliver requirements/gaps, not a fabricated recovery or backup receipt. |

An unsupported requested operation is incomplete, with its missing capability and
safe next action stated. A document preview is not deployment, migration, source
verification, execution, normal installation or human acceptance. Never change real
project layouts or live servers merely to demonstrate this contract.
