# explore-knowledge

Explore research works through editable dimensions, conditions, results and
evidence-linked relations. This layer references existing paper units without
changing their prose, Canvas, images or sidecars.

The interaction design is pending discussion. The existing webpage is not the
recommended workflow, and invoking the skill does not open it, create another
interface or migrate data. A native replacement interface has not been delivered.

## File-backed operations

Select an existing folder and the operation you need. For read-only queries and
Markdown output, use:

```sh
scholar-workflow knowledge exploration-query --root /path/to/selected/folder --selection query.yml
scholar-workflow knowledge exploration-export --root /path/to/selected/folder
```

Omit `--selection` for the default selection. A missing manifest is an empty
in-memory model, not implicit file creation. Export prints to stdout; saving an
additional navigation document is an explicit separate file operation. Keep it
outside existing paper packages and in the chosen folder so relative links work.

State stays in `.scholar-workflow/exploration.yml`: extensible dimension definitions,
whole-unit references, joint conditions/results, evidence-linked relations and
saved views. Queries match one record before grouping by work; they cannot combine
unrelated conditions merely because they appear in the same work. Author reports,
local reproduction, independent assessments and analysis remain distinguishable.

For an explicitly selected change, `exploration-init` creates a new manifest and
`exploration-apply` saves against its current revision. `exploration-import`
previews actual registered Source/Field paper units, with a separate revision-bound
apply. Whole units bring their complete declared asset inventory; this does not
copy or reanalyse them. Generic model saves cannot add a paper identity or change
its owned assets. Direct file editing keeps the same schema and ownership rules;
reload after external changes and resolve conflicts without overwriting newer edits.

Readable output keeps positioning, conditions/results, relations and the complete
declared local/web/native asset links, including missing or unavailable diagnostics.
The original paper package remains the place to read/edit its Markdown and Canvas
with existing tools. A model query/export does not launch those tools or demonstrate
that their links were opened successfully.

Folder connection, test/personal isolation and layered readiness checks retain the
[connection/environment contract](../../references/vault-connections.md). They are
separate operations, not an implicit pre-step for every query.

## Historical webpage entry

Only when the existing interface is explicitly requested:

```sh
scholar-workflow knowledge explore --root /path/to/selected/folder
```

This retained technical entry uses a dynamic local port and may open a browser or
cmux surface. Keep its terminal running and stop it with Ctrl-C; `--no-open` reports
the session URL without opening a window. It is not a requirement for the file-backed
operations above, nor the product direction for future interaction design.

See the [runtime contract](../../references/knowledge-exploration.md) for exact
commands, schema, opening behavior and current limits. Development checks do not
prove normal installation, native-tool opening or human usability.
