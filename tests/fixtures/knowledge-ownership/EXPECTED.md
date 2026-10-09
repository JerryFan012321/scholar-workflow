# Knowledge ownership: independent expected results

Prepared by hand before the implementation and contract tests. These expectations
come from the ownership and read-only CLI contract, not from generated resolver
output. All Sources, Fields, providers, projects, and bytes are synthetic and
created only under pytest's temporary directory when execution is authorized.
This preparation does not authorize test execution or any real library access.

## Fixed synthetic identities and relationships

| Object | Identity | Owning primary | Source-relative path |
|---|---|---|---|
| Paper resource | `paper:synthetic:ownership` | itself | `research/resources/papers/ownership/Paper.md` |
| Paper analysis | `analysis:paper:synthetic:ownership` | paper resource | `research/resources/papers/ownership/Analysis.md` |
| Analysis Canvas | `analysis:paper:synthetic:ownership:canvas` | paper resource | `research/resources/papers/ownership/Analysis.canvas` |
| Reusable core note | `core:synthetic:ownership` | itself | `research/Overview.md` |
| Analysis sidecar | `analysis:paper:synthetic:ownership:sidecar` | paper resource | `research/resources/papers/ownership/analysis.baseline.json` |

Source A and its Field use fixed valid UUIDs distinct from Source B and its Field.
The Field title is human-readable. Project A and Project B have different project
UUIDs and may both reference the same three external Knowledge object identities.
Neither project becomes their owner. Reader URIs are presentation locators only.
For a root Field with `relative_root: .`, the paper, analysis, and Canvas paths
start at `resources/papers/ownership/`; the core note and Field home are
`Overview.md`. There is no artificial `research/` directory in that input. Its
binding still identifies the actual Source root.

## Expected observable outcomes

| Case | Independent expectation |
|---|---|
| Single paper owner | `resolved`; exactly one location and one primary owner candidate in Source A |
| Analysis of that paper | `resolved`; its own analysis path and the paper's owner ID/path |
| Canvas of that paper | `resolved`; its own Canvas path and the same paper owner ID/path |
| Reusable core note | `resolved`; its own ID/path is the primary owner |
| Root Field paper, analysis, Canvas, and core note | Four separate cases resolve the declared object at its real Source-relative path; root Field identity and primary ownership are preserved |
| Sidecar declared only in snapshot artifacts | `resolved`; falls back to its explicit paper owner and sidecar path without inventing a supporting-document declaration |
| Missing artifact-only sidecar | Identity remains resolved; sidecar file state is `missing`; primary remains available |
| Symlink artifact-only sidecar | Identity remains resolved; sidecar file state is `unsafe`; no sidecar content is read |
| Artifact-only sidecar with primary in two Sources | `conflict`; both primary candidates are shown even if the sidecar exists only in Source A |
| Same owner used by two projects | Both projects return the same Knowledge locations; no content copy or extra identity |
| No matching identity | `not_found`; no location or owner candidate; reader remains `unverified` |
| Non-Obsidian and project-file entries | Omitted from the Knowledge resolution mapping |
| Missing target leaf | Identity remains resolved; target file state is `missing`; reader remains `unverified` |
| Target leaf symlink | Identity remains resolved; target file state is `unsafe`; symlink is not followed |
| Target ancestor symlink | Identity remains resolved; target file state is `unsafe`; symlink is not followed |
| Missing primary owner leaf | Target location can remain available; owner candidate reports `missing`; Markdown explicitly shows the missing primary owner beside the target state |
| Primary owner symlink | Owner candidate reports `unsafe`; external bytes are not followed; Markdown explicitly shows the unsafe primary owner beside the target state |
| Same primary in two Sources | `conflict`; both formal primary candidates remain visible |
| Only Source A has the requested analysis, but its primary exists in A and B | `conflict`; selecting the only analysis location does not select a unique owner |
| Only Source A has the requested Canvas, but its primary exists in A and B | `conflict`; both primary owner candidates remain visible |
| Missing provider snapshot | `incomplete`; nonempty issue identifying the affected Source; no synthesized provider |
| Invalid provider JSON | `incomplete`; nonempty issue identifying the affected Source; bytes unchanged |
| Duplicate provider JSON keys | `incomplete`; ambiguous JSON is not accepted using last-key-wins |
| Provider bound to another Source root | `incomplete`; foreign binding cannot establish ownership |
| Disabled registered Source | `incomplete`; disabled Source does not authorize its provider or files |
| Field manifest names a different Source | `incomplete`; wrong Source identity cannot establish ownership |
| Duplicate registry JSON keys | Input error or an explicit incomplete resolution; never a resolved owner |
| Registry path crosses an intermediate symlink | `incomplete`; a readable target behind the symlink does not establish registry authority |
| Registered Source root crosses an intermediate symlink | `incomplete`; a matching provider binding to the resolved target does not authorize the symlink chain |
| Provider path crosses an intermediate symlink | `incomplete`; the provider target is not followed or accepted |
| Field YAML contains an alias | `incomplete`; a syntactically valid alias must not establish Field authority |
| Field YAML contains a duplicate key | `incomplete`; last-key-wins must not establish Field authority |
| Registry is atomically replaced while its declaration is read | `incomplete`; same replacement bytes do not excuse a changed file identity |
| Field manifest is atomically replaced while its declaration is read | `incomplete`; no previously read ownership location becomes a complete result |
| Provider snapshot is atomically replaced while its declaration is read | `incomplete`; replacement is detected without creating any state |
| Analysis leaf is a directory or FIFO | Two cases retain declared identity but report file state `unsafe`; no body read or blocking FIFO open |
| Primary owner leaf is a directory or FIFO | Two cases keep the analysis file state available but report primary owner file state `unsafe`; no body read or blocking FIFO open |
| Registry is a directory or FIFO | Two cases return incomplete ownership; no declaration content read or blocking FIFO open |
| Field declaration is a directory or FIFO | Two cases return incomplete ownership for the affected Source; no declaration content read or blocking FIFO open |
| Provider declaration is a directory or FIFO | Two cases return incomplete ownership for the affected Source; no declaration content read or blocking FIFO open |
| Resolver zero writes | All temporary files, symlinks, directories, and bytes remain identical after resolving |
| Default project overview | Does not access the Knowledge registry or resolver; old JSON remains unchanged and Markdown equals the independently hand-written `DEFAULT-OVERVIEW.md` golden |
| Explicit CLI resolution JSON | Adds `knowledge_ownership`; preserves each entry's ref and existing `unverified` state |
| Explicit Chinese Markdown | Shows ownership, target file state, and unverified reader together for the entry; hides machine IDs and absolute roots |
| Registry option without resolution option | Input error, no resolver/registry access, no writes |
| Explicit resolution with unavailable registry | Input error, no new registry or state files |

Issue codes are required nonempty structured diagnostics, but exact spelling is
not prescribed here because it is not part of the agreed public API. A location
reports `source_id`, `field_id`, `field_title`, `object_id`, `owner_id`,
`relative_path`, `owner_path`, and `file_state`. Ownership resolution never
certifies reader availability, scientific correctness, source authenticity, or
formal annotations. No fixture content is exported into a real Vault or registry.

The Knowledge read guard allows only the selected registry, the registered
Sources' exact `fields.yml` files, and their exact provider snapshot declarations.
The CLI additionally allows its project layout, active context, and explicitly
selected candidate context JSON. Other JSON/YAML is not a declaration: in
particular, `analysis.baseline.json` is inspected only for file metadata, never
read as content. All other content reads, external tools, and production writes
are forbidden. Metadata opens of FIFO leaves must be nonblocking.
A race fixture alone may replace one declaration with identical
bytes to model an independent concurrent writer; after inspection, all paths and
bytes must still match the pre-call fixture inventory. The resolver itself has no
write exception. Owner missing/unsafe Markdown cases must distinguish the primary
owner's state from an available analysis file and an unverified reader.
