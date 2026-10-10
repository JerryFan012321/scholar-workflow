# organize-project

Prepare or update an internal PROJECT.md from selected project materials. README.md
remains the public presentation. No Hub or new registry is needed.

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
