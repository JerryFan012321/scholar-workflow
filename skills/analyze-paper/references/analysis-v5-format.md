# Five-branch Analysis v5 Interface

The human output template is owned by `analysis-output-template.md`. This reference
defines its explicit machine interface, not a reading or reasoning procedure.
Evidence states, source/quote verification, reader identity and paired storage
protection retain `analysis-format.md` and the shared source/storage policies.

## Identity and scope

- New analyses use this explicit v5 interface. Check installed runtime support;
  a specification or source checkout is not proof that the installed tool supports it.
- `schema_version: 5`, `profile.framework: reference_tree_v5`, explicit `language: en|zh`.
- `profile.markdown_quotes: true`. Supported author claims/inferences include a
  short original-language excerpt and a verified source span; only Markdown renders
  the excerpt. Structural projection cannot prove that the source contains it.
- `whole` roles normalize to Abstract, Introduction, Method, Experiments, Limitation.
  A branch can have no supported facts; preserve its structure without inventing them.
- `focused` names the selected branches and supplies their complete replacement.
  Ordinary updates cannot convert v4 to v5, change its framework or silently switch
  reader. Unselected branches and human content retain paired conflict protection.
- Schema: `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-ir.schema.json`; baseline:
  `${CLAUDE_PLUGIN_ROOT}/contracts/analysis-baseline.schema.json`.

## Outline paths and independent points

Each claim has a stable `claim_id`, role and unique `outline_path`. `<slug>` is a
lowercase alphanumeric/hyphen identifier, not an absolute path or a display title.
Each supplied point has its own stable `point_id`, text, evidence and block anchor.
Repeated challenges/contributions/modules have separate claims and parents.
Point text and Canvas summaries are prose, not additional framework headings or
machine claim comments. Literal non-heading hash-prefixed text remains prose.

| Claim outline path | Permitted point IDs |
|---|---|
| `abstract/task` | none |
| `abstract/previous_methods/<slug>` | `challenge-<positive integer>` |
| `abstract/insight` | `motivation`, `advantage` |
| `abstract/contributions/<slug>` | `summary`, `advantage` |
| `abstract/experiment` | none |
| `abstract/experiment/<slug>` | `finding-<positive integer>` |
| `introduction/task_application` | none |
| `introduction/previous_methods/<slug>` | `previous-method`, `limitation`, `technical-reason` |
| `introduction/our_pipeline/insight` | none |
| `introduction/our_pipeline/contributions/<slug>` | `purpose`, `how`, `advantage` |
| `introduction/demos_application` | none |
| `method/overview` | `task-io`, `steps` |
| `method/modules/<slug>` | `motivation`, `method`, `why-it-works`, `technical-advantage` |
| `experiments/comparison/<slug>` | `finding-<positive integer>` |
| `experiments/ablation/<slug>` | `components`, `design-choices` |
| `limitation/explanation` | none |
| `limitation/explanation/<slug>` | `reason-<positive integer>` |

Counts follow the paper, not the example's number of instances. Missing fixed
subslots render as empty labels, never fabricated availability records. All process
steps stay together in `method/overview`'s `steps` point; Method modules do not add
corresponding-challenge/contribution axes. Different modules never share a point node.

## Structural containers are not facts

Use `container: true` only for a grouping claim with no parent statement. It requires
`body: ""`, no Canvas summary, `evidence.kind: not_applicable`, a structural explanation,
no evidence anchor and no source spans. Its canonical template label is rendered;
its arbitrary `title` or detail is not shown as an unsupported fact. It has no claim
block anchor or own source entry. Its points remain independently attributable records.
Non-container claims require a nonblank body and their own evidence/backlink.

Claims/points use faithful concise summaries when their body exceeds 180 characters.
Their visible title, summary and inline source labels remain bounded by the checked
schema. Concision cannot remove a material qualification or add unsupported facts.

## Observable rendering and conformance

- Every record has its own text node, inline evidence and exact Markdown-block
  backlink. A grouped `/details` replacement does not meet this template.
- Labels follow the declared language. Labels occupy their own first line; statement,
  evidence and links remain independently readable. Quotes immediately follow their
  corresponding Markdown statement; no private comments or detached Evidence section.
- All five main branches share a trunk. Same-depth nodes align on the left;
  subtrees occupy non-overlapping vertical bands. Both edge ends have no arrow,
  `fromSide: right`, `toSide: left`, `styleAttributes.pathfindingMethod: square`.
- Apply the alignment, crossing and visible-node occlusion rules in
  `analysis-output-template.md` to the actual candidate, including preserved manual
  layout and extra graph items that interact with managed content. Absence of
  rectangle overlaps alone is not enough.
- Text boxes fit measured visible text plus approximately one click line. The current
  version preserves limits of 40 actual independent records, 96 total managed nodes,
  420 px maximum node height and 2:1 maximum overall aspect ratio. Container labels
  do not count as facts but do count toward total nodes. Failure reports the actual
  conflict; it never hides records, merges slots, shrinks fonts or silently raises limits.
- A renderer may return a noncanonical candidate for review. Baseline creation,
  batch success and canonical writes require a passing conformance report. A file
  existing is not proof of success. Source fidelity and human visual assessment are
  separate, explicitly reported checks.

## Reader, ownership and old artifacts

Verified ZotFlow projections require the registered Vault ID and local PDF mode.
Their Obsidian Library Reader links are projections of stable source spans, not PDF
identities or proof of annotation synchronization. Unverified reader configuration
cannot become a new canonical pair; do not hand-edit one file's links.

New Markdown, Canvas and sidecar stay together in the mapped Field paper folder.
Canonical writes keep source registration, provider owner, full snapshot CAS, safe
relative paths, symlink protection and journal/conditional recovery checks. Old v4
bytes and identities are not silently re-trusted, moved or regenerated. User-created
nodes/edges and safe style/layout remain distinct from managed content; conflicts
return a proposal without overwriting either artifact.

The legacy joint-placement, provider-bootstrap and Field legacy-cutover interfaces
accept v4 only. This v5 analysis interface does not authorize those migration routes
to accept v5, initialize a Field, or relocate existing content. An ordinary paired
analysis commit is not a migration or bootstrap transaction.
