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

## Explicit child registration

Use `project register-child --project-root PARENT --child-root CHILD
--archive-segment SEGMENT` for a zero-write preview of two explicitly accessible
declarations; `--json` supplies the proposed parent and both actual-byte SHA-256
baselines. The child must already name this parent's UUID. The parent may contain
other children; preserve them. Archive segments map UUIDs, not server locations.

To apply the selected registration, repeat the same roots and segment with `--apply
--expected-parent-sha256 HASH --expected-child-sha256 HASH` from that preview. Only
the parent's management declaration is replaced. The child, human documents,
archives and host inventory are not edited. Same registration is unchanged; role,
segment, parent or primary conflicts require an explicit migration, not overwrite.
No SSH access, child discovery, source checkout or experiment collection occurs.
An accessible declaration does not prove its remote deployment or Git permissions.

The writer checks byte baselines, uses a nonblocking cooperative file lock, stages
one bounded file, rechecks roots/declarations and replaces that single file. Busy or
stale requests require a fresh preview (exit 5); unsafe writes refuse (exit 7).
A replacement with unconfirmed durability reports partial completion (exit 6):
read the actual declaration before retrying. Keep external declaration editors
paused during apply. Detected changes refuse; this is not a cross-machine transaction
or a guarantee against an uncooperative edit after the final check. A crash may leave
an unused staging file, not a second authoritative declaration. No silent cleanup of
unrelated files or automatic recovery/backup claim is permitted.

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

### Single-Run collection preflight

`experiment collection-plan --project-root PARENT --child-root CHILD --run-id RUN`
checks one already-registered child's selected Run. `--json` includes parent/child
byte baselines, the child source commit, recipe hash, every recorded Attempt state,
all file hashes/sizes/modes, empty directories and the proposed destination
`experiments/<registered-child-segment>/<run-id>`. It reads neither Git HEAD nor
other Runs, invokes no tools, and performs no writes or actual reception.

Required entry/config/environment/dataset snapshots must already live inside the
selected Run, match their checksums and reproduce its recipe hash. Attempt identities,
Target snapshots, output-inventory hashes, lifecycle fields and local artifact
identities/checksums are checked. Invalid/missing/conflicting evidence stops the
preview, not a successful partial transfer. Actual execution fields, if recorded,
must agree with the frozen recipe; no command or remote path is followed.
Status is still a declared observation, not independently verified execution.

The file mapping keeps raw execution records unchanged. Remote report.md/notes.md
map to execution-report.md/execution-notes.md; parent report.md/notes.md remain
reserved for local analysis. A filename collision refuses, never overwrites or
silently chooses a name. Snapshot locators stay relative to their original child
Run and require this explicit mapping in a future collected-record reader.

This bounded preflight rejects more than 128 MiB of selected file bytes or a record
larger than 1 MiB; it does not silently drop files or limit the number of Attempts.
Large datasets/checkpoints belong remotely with explicit manifests. Symlinks,
special files/permissions, unsafe paths, duplicate YAML fields and detected changes
refuse. Running/planned Attempts are included and marked mutable; a preview is not
an immutable snapshot. Repeated source reads detect changes during inspection,
not every possible later external edit. No destination conflict/write authorization,
receiver, lifecycle update or recovery has been certified by this preflight.

### First reception and identical replay

`experiment receive-run --project-root PARENT --child-root CHILD --run-id RUN
--expected-parent-sha256 HASH --expected-child-sha256 HASH
--expected-evidence-sha256 HASH` consumes all three hashes from collection-plan.
This is an explicit write request, not a side effect of preview or registration.
The selected child root must be safely accessible; no SSH connection/download,
daily-development clone or automatic host inventory is created.

First reception creates `experiments/<child-segment>/<run-id>/` from a private
staging directory. Files are read back and hash/mode checked before a native
exclusive directory publication; there is no ordinary overwrite-rename fallback.
An existing empty directory also refuses. Safe file modes and required empty
directories are retained. The local Run records keep original child-relative
snapshot paths; use the receipt mapping, not a guessed parent-root interpretation.

The machine-only `.collection.json` uses schema 1 from
`contracts/experiment-collection.schema.json`: parent/child/Run identity, child
source commit, recipe/evidence hashes, source-to-local file mapping, hashes/sizes/
modes, required directories and `execution_verification: records_only`. It is not
another scientific recipe, source checkout or verified backup. Source report/notes
use the mapped execution names; local report/notes and other analysis remain
independent and are never written by this receiver.

Same-content replay verifies the receipt and every owned file/directory and
reconfirms directory synchronization, then returns unchanged. Extra local analysis
files are preserved. Changed source versions or altered local execution evidence
refuse; lifecycle updates are not implemented by overwriting the directory.
Legacy flat validation/index/Run commands refuse a research parent rather than
silently reporting zero child Runs or writing a flat index. Target registration
remains available in the parent. Use the qualified collected reader/index below.

Busy/stale/existing/conflicted reception reports exit 5; filesystem safety failures
refuse with exit 7, unavailable exclusive publication with exit 3. A published archive
whose filesystem synchronization is unconfirmed reports partial completion (exit 6).
Read back before retrying; repeated failed synchronization remains partial. Ordinary
failure before publication cleans only this operation's unchanged staging directory,
not an existing Run. Hard crashes may leave hidden reception staging; its automatic
cleanup is not implemented. Update/recovery journals below do not silently adopt it.
Empty namespace directories may remain after a failed first reception. Do not edit
declarations or owned archive files while applying. Native publication was exercised
on macOS; other platform/filesystem support must be verified independently.

### Local collected index and original evidence

`experiment collected --project-root PARENT [--child-project-id UUID] [--language en|zh]`
prints a read-only Markdown navigation table. `--json` returns the same scoped
projection with qualified identities and source-to-local references. Save Markdown
at the parent root only when requested; links are relative to that root. No index
file, human report, receipt, config or source record is changed. No server, source
child, host config, tool process or Hub is needed after reception.

Read only registered child namespaces. An optional selector must be registered;
do not scan or adopt other folders. Not received, empty, unavailable, invalid and
staging/unrecognized entries remain visible. One invalid Run does not hide other
valid children/Runs. `status: complete` means the selected read scope was inspected,
not that every child has executed, all archives have arrived, or the project is done.
Returned scope and per-child states preserve that distinction; partial data is not
silently turned into an empty successful experiment library.

The reader checks receipt identity/schema/ownership mapping/inventory hash, owned
file hashes/sizes/modes, required directories and original child recipe/Attempt/
Target/artifact consistency using the same evidence validator as collection-plan.
It re-observes receipts, owned files, declarations and locations to detect changes,
without claiming a global filesystem snapshot. Extra local analysis is not rewritten
or treated as remote-owned evidence. A verified archive means observed local
integrity and record consistency, not scientific correctness or independent execution.

Markdown keeps captured dataset/version/split, seed and config/environment links
beside each Attempt's recorded status, exit code, time and selected result-file
entries. Missing times are not inferred from mtimes. Purposes are linked to source
reports and marked not extracted; metrics are linked only from declared artifacts,
remain unreviewed, and remote-only evidence is not a local score. The table is a
navigation index, not the full comparison format. For an actual review, use
experiment-review.md: inspect the selected configuration values/differences, purpose,
metric meaning/unit/protocol and figures before making comparison claims. The
reader never chooses a best/latest Attempt, invents values or creates charts.

### Lifecycle update preview

`experiment update-plan --project-root PARENT --child-root CHILD --run-id RUN [--json]`
compares one valid collected Run with the explicitly selected incoming version.
It performs no writes, locks, staging, application or recovery. The preview supplies
parent/child declaration byte hashes, the actual local receipt byte hash, old/new
evidence hashes, exact file additions/replacements, new directories, Attempt
transitions, artifact transitions and the proposed receipt. These are bounded
operation records, not a replacement scientific recipe or general provenance store.

Keep the same Run recipe, source commit and creation facts; a different recipe is
a new Run. A frozen recipe cannot revert to draft. Previously collected files,
directories, Attempts and artifacts cannot disappear through a lifecycle update.
Running Attempts cannot return to planned; completed Attempt facts cannot be
silently rewritten. Existing Target snapshots and recorded start observations
stay frozen. New Attempts can arrive in any already-valid state: an intermittent
collector need not have observed every intermediate state.

Existing artifact facts remain stable. A manifest-only artifact may acquire a
validated local copy if its identity, role, source Attempt, remote origin and
unverified-backup state remain unchanged; this is not verified backup. Other
artifact corrections require an explicit new artifact or separately approved
correction, not an undocumented overwrite.

New execution files cannot claim an existing unowned local file, even if names
or bytes match. Local report.md/notes.md and other unowned analysis remain outside
the write set. A new empty directory is still a changed version, not unchanged.
Different hashes of mutable execution files are listed explicitly. Detected local,
source, declaration or location changes refuse; a preview is not an atomic snapshot
or authorization to bypass final revalidation.

`.collection-update.json` is reserved for the explicit update/recovery
transaction below. Its presence blocks verified reading and identical reception with
a pending-update state/exit 6, even when the old receipt still matches. A marker is
not proof of a live worker or permission to delete, finish or roll back anything.
Never import this local transaction metadata as remote execution evidence.

### Apply and recover a selected update

Check the normally installed CLI's version and `experiment --help` first. An older
installation without these commands cannot update archives; source tests do not
make a capability available in that installation.

Use `experiment update-run --project-root PARENT --child-root CHILD --run-id RUN`
with all four values from the current update-plan JSON:

| Flag | Preview field |
|---|---|
| `--expected-parent-sha256` | `parent_sha256` |
| `--expected-child-sha256` | `child_sha256` |
| `--expected-new-evidence-sha256` | `new_evidence_sha256` |
| `--expected-local-receipt-sha256` | `local_receipt_sha256` |

Pause external editors/synchronizers for the declarations and owned execution
files during apply/recovery. A nonblocking cooperative parent lock serializes
these writers, not uncooperative tools. The operation prepares and checks exact
before/after payloads in `.scholar-workflow/collection-transactions/tx-*/`, rechecks
the preview and ownership, persists a digest-bound pending marker, then installs
only the listed owned changes with the receipt last. Local analysis is untouched.
This is a recoverable multi-file operation, not filesystem-wide atomicity or remote
synchronization. No experiment, Git command or tool process is executed.

If interrupted, do not delete the marker or overwrite files manually. Run
`experiment recovery-plan --project-root PARENT --child-project-id UUID --run-id RUN
--json`. This is read-only and needs only the local registered archive and recovery
material, not the source child/server. It checks the journal, both complete versions,
recipe/lifecycle rules and current ownership before presenting each action as
before, after or absent, with a `revision_sha256`.

Choose explicitly, then run `experiment recover-update --project-root PARENT
--child-project-id UUID --run-id RUN --direction commit|rollback
--expected-revision HASH` using that current revision. Commit finishes the candidate;
rollback restores the previous version. A changed preview refuses with exit 5.
Unknown local edits, even identical bytes in a new unowned inode, are not adopted or
deleted. Recovery preflights the entire action set before writing and is itself
interruptible/retryable with a new preview. Temporary links are only reused/removed
when their bytes and recorded inode belong to this transaction.

Success verifies the selected version before removing its pending marker.
Interrupted writes or unconfirmed synchronization report exit 6; inspect again
before retrying. If the marker is already gone after a late synchronization failure,
inspect collected integrity and use a fresh update-plan/update-run; unchanged replay
also reconfirms directory synchronization, rather than claiming durable success from
matching bytes alone. Missing/malformed markers or unknown journals are conflicts,
not permission to infer completion or reconstruct receipts.

Recovery packages are retained, including bytes of newly added files removed from
the Run during rollback. Newly created empty directories may remain; unknown content
is never recursively deleted. Incomplete pre-activation packages are reported at
their explicit path, not activated or automatically cleaned. These materials are
local, inode-bound recovery records, not portable source backups or verified backup.
Do not manually edit owned files or recovery payloads during a pending operation.
New research-parent scaffolds ignore this recovery-package directory in management
Git. Existing ignore files are not rewritten; inspect their policy explicitly before
staging management changes, and never add recovery payloads as normal project records.

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

### Selected local Git recovery material

Check the installed `project --help` before use. These commands require Git and
an explicitly supplied **local, self-contained SHA-1 Git bundle**, not a remote
URL, working checkout or automatic SSH download. Creating/transferring that bundle
from a live child is a separate authorized operation through native tools.

```bash
scholar-workflow project code-recovery-plan --project-root /path/to/parent \
  --child-project-id CHILD_UUID --bundle-file /path/to/selected.bundle --json
scholar-workflow project retain-code --project-root /path/to/parent \
  --child-project-id CHILD_UUID --bundle-file /path/to/selected.bundle \
  --expected-plan-sha256 PLAN_SHA256 --json
```

The preview requires a registered child and valid, nonpending local archives for
that selected child. Every collected Run's recorded child source commit is required;
the parent Git HEAD is never consulted. Repeat `--commit FULL_LOWERCASE_SHA1` on
both commands for any additional selected commits. If no Run exists, select at
least one commit explicitly; do not infer one from a branch or management repository.

Verification uses an isolated empty bare repository: bundle verification rejects
incremental prerequisites, unbundle loads objects without checkout, and full strict
fsck checks the advertised objects and required commits. Each required identity must
be a commit, not a tag resolving to one. This follows the
[Git bundle](https://git-scm.com/docs/git-bundle) and
[Git fsck](https://git-scm.com/docs/git-fsck) object checks; it does not authenticate
the recorded child against a live remote repository. The report explicitly says
`origin_verification: declared_child_commits_only`.

The preview changes no parent/source files. Its digest binds bundle bytes, parent
declaration and the selected local archive observation. Retention repeats these
checks under the cooperative parent lock and refuses a stale digest. Pause external
declaration/archive editors during retention; this is not a cross-machine snapshot.
Git uses no inherited Git configuration, hooks, object locations, credentials or
transport, never checks out or executes the stored code, and kills its process group
on a 30-second command timeout. Input is bounded to 256 MiB, Git stdout to 8 MiB and
one coverage record to 1 MiB; excessive inputs fail, not truncate. These are not a
complete CPU/memory/disk sandbox for hostile compressed objects.

Retain only under `backups/code/<child-uuid>/<bundle-sha256>/`:

- `source.bundle`: the exact selected bytes, mode 0600;
- `material.json`: immutable child/parent/bundle facts, mode 0600;
- `coverage/<plan-sha256>.json`: the exact preview assessment, mode 0600.

Machine records use `contracts/code-recovery.schema.json`; do not present hashes as
human project prose. One child/content hash has one bundle; an additional assessment
adds only a small coverage file. The saved preview remains `planned_not_retained`
because it records the pre-write assessment, not a new live receipt. The operation
separately reports retained, coverage_added or unchanged with relative file links.
Identical retry validates bytes/modes and reconfirms synchronization. Unknown existing
material or coverage is never overwritten; symlink destinations refuse.

Standard canonical LFS pointers and submodule gitlinks at the **selected commits**
are listed as missing payloads. This is not an audit of every historical tree or
extended/noncanonical LFS pointer. Uncommitted/untracked work, other external
dependencies and secret content are not checked. Review those gaps separately; no
secret scanning, payload transfer or code restoration is implied. Recovery material
always remains `backup_state: not-verified`.

Missing Git reports exit 3; stale or conflicting material reports exit 5. An
interrupted write or uncertain synchronization reports exit 6 with the material or
private staging location. Do not delete it or call it complete. Re-run preview and
the identical retention only if the final material validates; incomplete private
stages/coverage files are retained for inspection, not automatically adopted or
cleaned. Existing ignore files are unchanged: ensure recovery payloads are excluded
before staging management Git. No commit, push, remote command or verified-backup
writer is part of either command.

## Current capability boundary

This contract is a required target and reporting boundary, not a claim that its
automation exists. Determine the installed capability before an operation:

| Requested operation | Current interface and honest result |
|---|---|
| Parent/child initialization | The helper supports explicit research-parent/execution-child scaffolds in new empty roots, with separate management declarations and independent Git. See the init-project skeleton manifest for flags and required outputs. Existing nonempty generic projects are not converted. A scaffold does not register a child with its parent, deploy remotely, populate research facts or receive archives; report those remaining gaps. Legacy generic initialization remains compatible. |
| Child registration | `project register-child` previews and byte-CAS appends one already-declared child to an explicitly selected parent. It does not locate/contact a server or change its child declaration. Validate mutual declarations separately; no live synchronization is created. |
| Parent archive reception and index | collection-plan previews one Run; receive-run supports first reception/identical replay; collected reads the qualified local index. update-plan/update-run provide four-baseline version changes; recovery-plan/recover-update explicitly commit or roll back a pending local journal. Check actual installed help before use. Pending markers block verified reading/replay, not prove a live process. Legacy flat commands still refuse parents; Target registration remains available. No SSH reception, automatic orphan cleanup, history correction or fabricated receipt is implied. |
| Remote code in the material inventory | Additive context schema 1 `execution-code` identifies a registered child, safe relative code path and optional commit. `project remote-code-plan` combines one explicitly selected existing SSH Target and server ledger without connecting or writing. Target selection does not verify the remote child, path, commit, SSH alias or access. No fake local path, arbitrary URI, native open or implicit host binding; see project-context.md. Check installed help before use. |
| PROJECT and experiment review | Read the explicitly selected, safely accessible material and produce the existing human format. Identify remote/unavailable sources and incomplete lifecycle verification. Review does not collect, execute, edit raw records or grant access to remote roots. |
| Code recovery and verified backup | `project code-recovery-plan` checks one supplied local self-contained bundle against selected child Run commits; `project retain-code` explicitly retains it with a current digest and immutable per-plan coverage. Check installed help first. No remote bundle creation/transfer, child origin authentication, LFS/submodule payload recovery, uncommitted-work capture, daily clone or verified-backup claim. |

An unsupported requested operation is incomplete, with its missing capability and
safe next action stated. A document preview is not deployment, migration, source
verification, execution, normal installation or human acceptance. Never change real
project layouts or live servers merely to demonstrate this contract.
