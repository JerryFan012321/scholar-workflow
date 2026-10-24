# track-research

Follow selected public blogs, lab/company research pages, releases and model lists.
This is source observation, not automatic ingestion or a new research desktop.

Use `scholar-workflow research sources list` to see existing channels. Register a
selected channel from a small JSON spec with `research sources register --spec
channel.json`; exact fields are in the [shared contract](../../references/research-tracking.md).

Run `scholar-research check` once to establish a baseline, then repeat to discover
new or changed items. `--channel ID` limits the run; `--initial-mode report` requests
the visible first-window items instead of a silent baseline. Read retained events
with `scholar-workflow research updates`. Use JSON to obtain event IDs for marking
`read`, `selected` or `ignored`. Selected is not archived.

The installed package provides both commands. Source tests do not prove product
installation, native rendering, scientific support or fresh-dialog reproduction.
No scheduler, credentials, model downloads or automatic Zotero/Vault writes.
