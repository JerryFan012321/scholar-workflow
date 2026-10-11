# Independent expected results: synthetic field library

This file is the oracle prepared before execution. It must not be supplied to the artifact generator. No test has been run by preparing it.

## Scope and disclaimer

- The only visible test destination is one new field under the independent `test` Vault: `领域库结构验收/长文检索`.
- Five invented paper identities, document fragments, and reading stubs are fixtures, not real scientific papers, completed `analyze-paper` results, or validation of scientific support.
- Do not search, download, write Zotero, register a formal Field, execute scientific experiments, change formal Vaults, or mass-copy exemplar papers.
- Release/package/install acceptance, source SHA, installed version, and rollback proof are separate responsibilities. Source-tree execution does not prove an installed skill works.

## Expected files and ownership

The visible field includes:

```text
01-论文列表.md
02-文献树.md
02-文献树.canvas
03-技术路线树.md
03-技术路线树.canvas
04-挑战洞见树.md
04-挑战洞见树.canvas
fixture.md
resources/papers/alpha/{Paper.md,阅读记录.md}
resources/papers/beta/{Paper.md,阅读记录.md}
resources/papers/gamma/{Paper.md,阅读记录.md}
resources/papers/delta/{Paper.md,阅读记录.md}
resources/papers/epsilon/{Paper.md,阅读记录.md}
```

Braces above abbreviate the two literal files, not a filename. Do not generate faux full-paper analyses, per-paper analysis Canvases, PDFs, or attachment screenshots. Any optional generated machine record must stay out of the human prose and must not create a second owner.

Each paper has exactly one owner directory. A paper appearing in more than one view or question retains the same owner and source links.

## Complete paper list and evidence state

The full list has exactly these five identities, regardless of representative diagram selection:

| Identity | Name | Novelty class | Supplied coverage | PDF status |
| --- | --- | --- | --- | --- |
| alpha | 样本甲 | 1 | Complete synthetic fragment, not actual paper full text | Not provided |
| beta | 样本乙 | 2 | Complete synthetic fragment, not actual paper full text | Not provided |
| gamma | 样本丙 | 2 | Complete synthetic fragment, not actual paper full text | Not provided |
| delta | 样本丁 | 3 | Abstract only | Missing |
| epsilon | 样本戊 | 4 | Unknown; record only | Missing |

The list shows paper materials, year/publication state, research clue, source availability, and available reading record. Publication venues and DOI/arXiv/Zotero identities are not supplied: display synthetic/unprovided status, not invented venues. The list and tree roots clearly say this is a structure test. Unknown content remains visibly unknown; no default-success badge or blank omission.

## Distinct view contracts

### 02 literature

- Horizontal spine has `alpha` then `beta`, both milestone cards.
- `gamma` is a major pipeline branch from `beta`; `epsilon` is a local follow-up/grouping under `gamma`.
- The diagram selects four papers: alpha, beta, gamma, epsilon. Delta remains in 01 and 03/04 and is not silently deleted.
- Each of the four paper cards has a short explanation underneath and a valid explanation/source link.
- Novelty 1/2 only on spine or major branch; novelty 3/4 may not be promoted to those slots. Epsilon class 4 stays local. Delta class 3 would also have to stay local if later selected.
- The gamma relation is explicitly an alternative route, not verified implementation inheritance. The epsilon edge is explicitly display grouping, not a claim that it directly builds on gamma.
- Preserve the distinction between the representative tree and the exhaustive list. No minimum paper quota is invented.

### 03 technical

- Semantic topology is exactly root → route → one paper per leaf.
- Three routes: two-stage/paragraph location has alpha and beta; parallel has gamma; filter has delta and epsilon.
- All five identities appear once. There are nine semantic nodes (one root, three route nodes, five paper leaves), excluding layout-only junctions.
- Each paper leaf names only one paper, contains its concise prepared summary and evidence limitation, and links to its single Paper owner, reading record, and document source.
- Route grouping does not establish paper inheritance or a proven integrated pipeline.

### 04 challenge

- Semantic topology is exactly root → problem → solution → one paper per leaf.
- Two problems and two solution nodes: evidence location has alpha, beta, gamma; candidate overload has beta, delta, epsilon.
- There are six paper occurrences but five distinct paper owners. Beta appears under both problems; distinct Canvas node IDs are required, both linking to `resources/papers/beta`.
- There are eleven semantic nodes (one root, two problem nodes, two solution nodes, six paper occurrences), excluding layout-only junctions.
- Solution nodes include actual prepared conditions and limitations, not abstract empty boxes. Terminal nodes are papers, not “前提/实现/论文与取舍” grouped labels.
- Claiming unknown epsilon method or delta full-text detail is a failure.

## Sources and links

- All document evidence resolves to existing `fixture.md` blocks or existing reading-record blocks. There are no synthetic Zotero/ZotFlow/PDF locators.
- Visible links use the common Vault-relative root `领域库结构验收/长文检索`.
- Every referenced note and anchor exists after copying `materials/`. Do not use filesystem absolute paths, source-checkout paths, loopback URLs, or private host IDs.
- Do not label a document-fragment link “PDF page”, pretend the stubs are full analyses, or fabricate an unavailable analysis-Canvas button.
- Markdown table wikilink pipes are escaped; normal prose and Canvas links use the normal unescaped alias syntax.

## Geometry and style

- 02 retains horizontal literature-spine structure; 03 and 04 are center-out diagrams, not timeline copies.
- Text nodes remain editable JSON Canvas text, not one raster image or a web embed.
- Connections are horizontal/vertical right-angle paths, no arrows, no curves/rounded square bends, no diagonal spans.
- Nodes are aligned by role; connectors do not cross unrelated connectors or cover another node. Hidden junction helpers are not semantic content or artificial paper leaves.
- Connector length is short subject to alignment, no crossings, and legible text. Geometry must not be sacrificed to hardcoded node counts or widths.
- Node height fits rendered text with at least approximately one spare line of click space; no cropped text or links.
- White background, readable fonts and independent role styling require the shipped style assets plus Advanced Canvas configuration. A passing JSON parser does not prove those assets are enabled in Obsidian.
- Do not rewrite unrelated Vault CSS/appearance or disable preexisting plugins to obtain the look.

## Preservation and completion boundaries

- Record pre-test bytes/hashes of copied materials and any preexisting neighboring files. Materials remain byte-identical; tests must not update sources to match outputs.
- The new directory may be regenerated in place under local Git, but no sibling test copies, formal topic packages, or other Vault contents are changed. Existing test work is not deleted.
- Automated verification covers file inventory, identity coverage, topology, references/anchors, source-status conservation, geometry and byte protection.
- Human review is still required for native Obsidian appearance, text legibility/click room, and navigation experience. State exact files to open, clicks to try, expected visible effects, and keep this gate pending until the user explicitly confirms.
- Do not present fixture completion as scientific verification, full-paper analysis acceptance, formal Field migration, or installed-plugin validation unless the corresponding distinct evidence was actually collected.
