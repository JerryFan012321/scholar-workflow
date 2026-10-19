# organize-project

Prepare or update an internal PROJECT.md from selected project materials. README.md
remains the public presentation. No Hub or new registry is needed.

For a local research parent with remote execution children, follow the shared
[project-management contract](../../references/project-management.md). Preserve its
full knowledge, plan, guidance and analysis surface; show selected child-qualified
results and honest remote code availability. This document task does not deploy
children or add SSH references to the current material-inventory schema.
A report-only project remains missing its local experiment archive. The shared
contract defines the collection handoff and explicit required-Run check; a complete
PROJECT document does not certify that experiment delivery is complete.

## Use

Ask: "Prepare an internal PROJECT.md preview for this project, using these code
modules, paper units and experiment records; keep the detailed plan in SCHEDULE.md."
Give the project root and selected materials, or the existing project-context
inventory. Identify result Attempts if more than one is recorded for a Run. Omit an
external schedule when the detailed plan should live only in PROJECT.

The result starts with current state, the unique plan and experiment results,
followed by code/dataflow, papers/materials and ownership/open questions. Primary
links explain their relevance; verification details remain supplementary. Missing
evidence and untested reader links stay visible. Module diagrams are editable and
source-supported; retries are not independent experiments.
Keep the accepted project architecture and module/dataflow views, without adding
folder/file trees. A small selected prototype is not a complete project skeleton.

The papers/materials section includes a compact literature division-of-work table
and a short synthesis for this project's approach and related work. Existing paper
units supply the detail; this is not another field library or a reanalysis task.
The exact format and optional detailed-note boundary are in the document contract.

VS Code is the primary reader for PROJECT, its plan and project reports. Use its
capable built-in Markdown/Mermaid preview; optional extensions and native checks are
described in [the reader contract](../../references/vscode-project-docs.md).
An Obsidian preview is not a substitute for VS Code assessment.

Default output is a conversation preview. Explicitly request a destination to
save a candidate, or a bounded update to an existing document. Human content and
unresolved plan conflicts are preserved. This does not run code, initialize a
project, copy analyses, edit raw archives or publish anything.

For an experiment-only comparison use `review-experiments`; for a new skeleton
use `init-project`. The short `project overview` CLI remains an inventory view,
not the rich PROJECT renderer.

See [the document contract](../../references/project-entry.md). Available from
0.43.0; native VS Code navigation/appearance assessment remains separate from
installation and contract checks.
