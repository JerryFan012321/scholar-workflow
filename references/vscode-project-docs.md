# VS Code Project Document Surface

VS Code is the primary reader for internal `PROJECT.md`, its authoritative project
plan and project-local experiment reports. Their conclusions, figures, module
views and project-file navigation must work there. An Obsidian preview or a
browser-generated screenshot does not establish this acceptance.

This is a presentation contract, not permission to install extensions, change
editor settings, execute document code or alter source ownership. It does not
replace the paper unit's Markdown/JSON Canvas format or its Obsidian editing surface.

## Reader and optional tools

Use one declared Markdown preview engine. VS Code 1.121 introduced built-in
Mermaid rendering, including pan/zoom, through Mermaid Markdown Features. For a
capable installation, use the built-in Markdown preview rather than requiring a
second renderer. Verify the actual version and enabled features; an extension's
installed files alone do not establish activation in the current window/profile.
See the [official release notes](https://code.visualstudio.com/updates/v1_121).

- `yzhang.markdown-all-in-one` is optional editing assistance, not a rendering
  requirement. Existing installations need no duplicate editor extension.
- `hediet.vscode-drawio` is optional for precise visual editing of project module
  diagrams. A `.drawio.svg` can hold the editable drawing and its SVG presentation
  in one project-local file, embedded using ordinary Markdown image syntax.
  The [author's documentation](https://github.com/hediet/vscode-drawio) describes
  default offline editing; do not enable online mode implicitly. This editor does
  not guarantee a crossing-free layout or edit Obsidian JSON Canvas. Its experimental
  Insiders-only inline editor is not a stable-version requirement.
- Do not require deprecated `bierner.markdown-mermaid` on a capable current VS Code.
  Markdown Preview Enhanced is an alternative engine only for a separately chosen
  need; it is not necessary for the ordinary Markdown/Mermaid/image contract.

## Portable readable result

Use standard Markdown headings, tables, image embeds and links for project-local
documents. Keep the useful conclusion/state, unique plan and results first, with
short navigation and legible figures. Do not rely on Obsidian wikilinks, callouts,
block references, live queries or external applications for the project document's
own reading/navigation functions. Paper units retain their separate native format.

Use report-relative links and images, section anchors for Markdown navigation, and
code-file links with line fragments when verified in the chosen reader. Do not
assume Markdown-file line fragments work like code navigation. Keep file links
beside diagrams; graph click handlers are not the only navigation route.
Explicit Zotero/Obsidian actions remain labelled external reader actions, not
objects embedded inside VS Code. Preserve their stable identities and ownership.

Mermaid source remains editable. Show module diagrams at a readable size in the
actual preview width; a long horizontal graph shrunk to fit is not a good default.
Use bounded supported views without dropping relationships or required content.
For exact manually controlled geometry, use the optional project-local diagram
format above only when selected; never silently convert an accepted paper Canvas.
Connection compactness follows `human-presentation.md`.

Embed supported local result SVG/PNG images with readable labels, captions and
source-data links. Preview CSS and typography are workspace-level, opt-in reader
configuration, not another document authority. The built-in preview supports local
styles through `markdown.styles`; changing settings requires its own scope. Keep
Markdown preview security at Strict: ordinary Mermaid and local images do not
justify enabling arbitrary scripts, remote rendering or document code execution.
See [VS Code's Markdown documentation](https://code.visualstudio.com/docs/languages/markdown).

## Native acceptance

Use one selected project candidate, its selected plan/report, code entry and existing
result figure. Identify the actual VS Code version, profile and preview engine;
open the folder and run **Markdown: Open Preview to the Side**. Check the full
document, rendered module diagram, result figure, section navigation and selected
code/data/report links in VS Code. Check separately labelled external actions in
their intended tools without calling them embedded functionality.

State the exact objects, operations, expected visible effects and pass criteria in
the conversation. Have the user assess legibility, visual order, navigation and
diagram compactness. Record unavailable/disabled features and untested actions
explicitly. File checks, installed packages, a successful diagram parse and another
reader's approval cannot replace actual VS Code display or human acceptance.
