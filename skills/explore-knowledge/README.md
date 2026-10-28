# explore-knowledge

Use **Add Vault/folder** for system selection, independent reading/reference/update
checks, an adjustments preview and explicit read-only host connection. Existing
paper units keep their contents and format. See the shared
[connection/environment contract](../../references/vault-connections.md).

Explore research works through editable dimensions, conditions, results and
evidence-linked relations. This layer references existing paper units without
changing their prose, Canvas, images or sidecars.

Use **Reference paper units** to select a registered Field and whole paper units.
All declared assets are referenced together; this does not create a new paper,
copy its package or save automatically. Multiple conditional records still refer
to the same unit. Paper asset membership stays read-only in the explorer; maintain
the owned package through its existing workflow. Validation failures keep the
form and previous unsaved draft intact.

```sh
scholar-workflow knowledge explore --root /path/to/selected/folder
```

The local interface uses a dynamic loopback port and opens in cmux when available,
otherwise in a normal browser. Keep the terminal running; Ctrl-C stops it. Use
`--no-open` to receive the session URL without opening a window.

State lives in `.scholar-workflow/exploration.yml`. Query and Markdown export are
read-only. Explicit initialization and revision-checked saves write only that
manifest. Adding a dimension changes the definition rather than a fixed UI enum.
Conditions and results stay together, and filters cannot join unrelated records
merely because they belong to the same work.

Select a paper, then choose **Preview** on its declared Markdown asset. Original
excerpt headings keep their source action visible; expand them to read the full
quotation and direct-evidence emphasis. Declared local figures appear beside
their captions. Unsupported or missing images retain a diagnosis; remote images
are not loaded automatically. The preview is read-only, and **Open in native
application** remains available for supported assets such as editable Canvas.

The readable export provides work positioning, the complete declared asset list,
conditions/results and relations for use in Obsidian. It prints to stdout; saving
an additional navigation document is an explicit separate file operation.

See the [runtime contract](../../references/knowledge-exploration.md) for exact
commands, schema, opening behavior and current limits. Development checks do not
prove normal installation, native-tool opening or human usability.
