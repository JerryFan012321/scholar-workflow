# Synthetic project acceptance input

This directory is one explicit synthetic project, not a real project migration.
`project-context.json` declares seven items: five existing local locators, one
unqueried synthetic external paper, and one intentionally missing local file.
No reader URI is present, so reviewing this fixture cannot open an application.

`EXPECTED-OVERVIEW.md` is the manually prepared expected output, **not an executed
renderer result or a passed test**. It is saved at the fixture root so its project
file links can be reviewed there. The fixture source is not to be executed. The
experiment/report files make no real Run, result, or backup claim.

After approval, tests copy this one fixture to an isolated temporary project and
compare actual CLI output with the expected text. No real Vault, Zotero library,
cmux workspace, Hub process, or external Codex task participates.
