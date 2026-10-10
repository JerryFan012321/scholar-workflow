# Internal Project Entry Contract

Use this contract for an explicitly requested internal `PROJECT.md`, not for the
short `project overview` inventory or a public README. This is a human document,
not another registry, synchronization service or execution interface. Shared
presentation and storage rules remain in `human-presentation.md` and
`storage-policy.md`; selected material references follow `project-context.md`.
VS Code is the primary reader: load `vscode-project-docs.md` for the required
reading, diagram and navigation surface, optional extensions and native acceptance.

## Ownership and delivery

`PROJECT.md` introduces the managed research project internally. `README.md`
remains its public-facing presentation. Internal does not imply automatically
Git-ignored: leave tracking, ignore rules and publication settings unchanged.
This does not restore the plugin repository's archived architecture PROJECT.

Use the user's selected project and materials. An existing `project-context.json`
is the authority for its explicit associations; referencing it does not authorize
changing it. A missing layout or inventory does not prevent a clearly labelled
document draft, but must not cause allocation of a project identity, initialization
or invented associations. Existing code, paper units and experiment archives keep
their ownership. Reuse their locators rather than copying their contents.

Default delivery is a conversation preview. Save or update documents only when
the request includes that file boundary. For an update, preserve human prose and
existing detailed plans, check the current bytes immediately before applying the
agreed patch, and stop on intervening changes or unresolved content conflicts.
A preview is not overwrite permission. A separately saved review candidate states
that it has not replaced the active PROJECT; rebase links for its actual location.

## Required human document

Use the project's title as H1, followed by its goal, document/verification state
and a short navigation list. Include the six sections below, translating all
structural labels consistently into the chosen language. These are output slots,
not a prescribed reading or reasoning order. An absent fact stays visible in its
slot; it does not justify a fabricated placeholder result.

The required visible order is Current state, Project plan, Experiments and results,
Code and data flow, Papers and materials, then Ownership and open questions. The
opening view must show where the project stands, what comes next and what has
been achieved before diagnostics or exhaustive file inventories.

### Current state

Explain the current milestone, achieved results, active work and blockers in
readable prose. Date the actual inspection and link supporting declarations or
records beside their claims. Separate input declarations, statically inspected
files, recorded execution outcomes and checks not performed. A record's date is
not today's verification date; an older success is not necessarily current state.
State the selected scope and any uninspected areas rather than implying a full
project audit.

### Project plan

For a new plan, maintain exactly one authority for detailed tasks: inline in
PROJECT, or in an explicitly chosen `SCHEDULE.md`. If an existing unique authority
uses another name, such as `planning/BACKLOG.md`, retain and link it; organizing
the entry does not authorize renaming or migrating that plan. If external, PROJECT
contains only a clearly derived milestone/current-work summary and a direct plan link, not a
second independently maintained detailed task list. Use existing decisions,
statuses, dependencies, owners and dates; identify unknown or undated items.

If existing plans conflict and no authority is declared, expose both entries and
the unresolved choice without merging, selecting, deleting or assigning dates.
Proposed work is labelled proposed, not a user commitment or completed task.

### Experiments and results

For every selected Run, identify the selected result Attempt, recorded outcome,
requested metric/unit when available, and direct recipe/report/artifact entries.
Show all selected Attempts with their Run, status and failure/retry/replay meaning;
retain individual entry links even when a compact table groups the history.
Missing, remote-only or conflicted artifacts remain visible.

Use `experiment-review.md` for metric evidence and comparison semantics, and the
existing experiment-record contract for lifecycle. For multiple experiments, put
its comparison overview table here, or link the detailed review with a compact
derived table of the selected results. An existing detailed review
may carry comparison conditions/history if this section links it and makes every
selected entry discoverable. Do not choose a best/latest/first result implicitly.
Same-Run retries are not independent experiments. Recorded success is not proof
of actual execution or scientific superiority. Backup pending/unverified remains
explicit; a local copy, hash or promotion is not verified backup.

### Code and data flow

Give direct entries for selected code and configuration, with each module's
responsibility, inputs/outputs or interfaces, and the evidence available for them.
Include editable, bounded module/dataflow diagrams where relationships are
supported. Mermaid in Markdown may use a capable built-in VS Code preview;
declare and verify the reader capabilities rather than assuming activation. Identify
each view's scope and keep file links alongside it rather than relying on diagram
click handlers. Use compact aligned views instead of one sprawling graph.

An inspected import/call supports a static relationship, not successful runtime
execution. Keep document-only assertions or uninspected edges explicitly
unverified, outside the established-flow graph. Missing modules/configuration
remain listed with their unavailable reason. Never add edges to make a graph
look complete. Reader rendering and navigation are separate from source checks.

### Papers and materials

List selected resources with their project relevance and direct source/material
note, analysis Markdown, editable Canvas and original-document entries where
supplied. Keep these distinct, including missing entries and unqueried readers.
Use existing qualified identities and verified reader mappings; title similarity
is not ownership. Project-specific decisions can live in project notes, while
general paper analysis stays in its owning paper unit. Do not reproduce that body
or create another owner just to assemble the entry.

### Ownership and open questions

Explain where code/configuration, experiment records/results, reusable knowledge
and the detailed plan belong. List unresolved selection, evidence, availability
and decision issues with their affected entries. Distinguish internal PROJECT
from public README and reader checks from file/record checks. Do not bury missing
evidence behind a polished completion statement.

## Links and completion

The primary file list is curated navigation, not a project-tree dump. Show the
relevance and availability of code, the single plan, result reports/figures/data
and explicitly related paper source/analysis/Canvas/originals. Group verification
inventories, full logs, captured targets and historical records under supplementary
entries when they do not directly explain current work. Keep all selected files
discoverable; names or shared directories do not establish paper ownership.

Saved project-root Markdown uses project-relative links to project files. Rebase
for another output directory. External knowledge uses its stable native reader
entry or an explicitly labelled locator awaiting mapping, not guessed cross-Source
wikilinks, copied analysis or fixed loopback URLs. An unavailable target is an
honest diagnostic, not an inert success-looking button.

Account for every selected entry and the six sections before calling the draft
structurally complete. Evidence can remain partial if its limitations are clear.
State inspected and uninspected scope, files changed and outstanding decisions.
For human assessment, give the exact candidate location, how to open it in VS Code,
which code/experiment/paper/plan links to try and what clarity/rendering to judge.
An Obsidian or browser preview does not satisfy this project-document assessment.
Until explicitly accepted, navigation and appearance remain pending human assessment;
schema validation or a printable link does not certify them.
