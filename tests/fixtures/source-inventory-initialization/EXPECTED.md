# New Source inventory initialization: independent expectations

Prepared before implementation. These are hand-written product expectations, not
observations of the current implementation. This file and the companion tests have
not been executed. The new composition entry point does not exist yet; an import or
assertion failure is an expected feature RED, never a passing product result.

## Inputs and fixed boundaries

- Each new Source is a pytest directory containing only an existing `README.md` and
  `Reading.md`. The original Markdown bytes are recorded before each operation.
- One synthetic host state contains the existing `hub/sources.json` registry and
  its existing `knowledge-providers/<source-id>/knowledge-provider.snapshot.json`
  locations. No real Vault, Zotero library, installed product or network is used.
- The first requested Field has relative root `.`. Source/Field UUIDs are generated
  by the implementation but must be frozen by the prepared creation journal.
- Public `knowledge registration-plan/register` retain their names. A genuinely new
  Source plan explicitly includes `inventory_initialization: new-empty-provider`.
  The confirmation digest binds this action as well as the existing reviewed scope.
- The dedicated callable is
  `workflows.register_source.register_source(service, root, field_root,
  existing_source, approved_digest, fault_inject=None)` and returns `FieldManifest`,
  preserving the existing registration return shape. It is imported inside the
  tests, so the missing feature does not prevent unrelated test collection.
- An empty provider has the selected root path/device/inode binding and empty
  resource/artifact/relation/projection inventories. It does not adopt Markdown
  bodies, create paper owners, or change existing readable files.
- A Source-creation journal is host-local recovery state, not a second owner store.
  Tests identify its one JSON record without imposing a new directory layout.

## Cases and exact expected results

| Case | Input / action | Expected result |
|---|---|---|
| P1 | Plan the same new root twice | Same approved digest; explicit new-empty-provider action; no Source/state writes |
| P2 | Confirm using the normal public CLI | Registered manifest plus an actual bound empty provider; both original Markdown files unchanged |
| P3 | Remove the initialization action from the reviewed plan before hashing | The reduced digest cannot authorize creation; no Source/state writes |
| E1 | Initialize two new empty Sources in one registry | Both have independent empty providers; neither prevents the other's creation |
| E2 | Register different fake Local API papers in these Sources | Exactly one correct owner per Source; original Markdown unchanged |
| E3 | Try the same library `123` + item `ABCD2345` in the other Source | Conflict; no duplicate paper directory, navigation or provider change |
| E4 | A selected historical Source has a manifest/registry but no provider | Refuse; absence is not treated as empty; no new paper owner or provider |
| E5 | An external historical Source is missing its provider | Refuse the otherwise-valid selected Source paper plan; no writes |
| A1 | Attach an existing portable Source into a new host state | Preserve its UUIDs/manifest; no new-empty-provider action and no provider initialization |
| R1 | Interrupt immediately after `provider-created` | Empty provider exists; manifest and registry have not been published; prose unchanged |
| R2 | Interrupt immediately after `manifest-published` | Provider and manifest exist; registry not yet published; prose unchanged |
| R3 | Interrupt immediately after `registry-published` | All three members exist; journal remains prepared until verification/commit |
| R4 | Retry each interrupted request using its original digest | Resume the original journal before ordinary preview; preserve the frozen Source/Field UUIDs; one provider and one Source entry; exact completed replay is byte-idempotent |
| C1 | Append even whitespace to the prepared provider | Refuse recovery; preserve the changed provider and all other current bytes |
| C2 | Append a human comment to the published manifest | Refuse recovery; preserve the changed manifest and all other current bytes |
| C3 | Disable the just-published Source in the registry | Refuse recovery; preserve the changed registry and all other current bytes |
| C4 | Edit existing `README.md` after interruption | Refuse recovery; preserve the human text and all other current bytes |
| C5 | Damage the prepared journal JSON | Refuse recovery; retain its damaged bytes and every current member |
| C6 | Change the root locator inside a valid prepared journal | Refuse recovery; no publication into the substituted root; retain current bytes |
| L1 | Remove a provider after Source creation has committed, then retry creation | Refuse; the committed journal is not permission to recreate an empty snapshot |

## Inspection and pass conditions

Assertions inspect the produced JSON/YAML and filesystem bytes directly. They do
not call the production provider validator, renderer, hash helper or lock machinery
as their expected-result oracle. Local paper metadata and locator bytes come only
from a small in-memory fake; the fake PDF is not a real paper or a claimed readable
PDF. The tests do not evaluate scientific content, Obsidian display, runtime
installation or backup.

Each test uses its own `tmp_path`. A deliberate test interruption raises
`RuntimeError` at one fixed named phase. Expected refusal is `FieldRegistryError`
(or the existing CLI safety-refusal exit); no test swallows an unexpected success.
Conflicting human/declaration bytes must remain unchanged on refusal. Input and
scope changes require revisiting these expectations before test execution.

## Recovery safety supplement, prepared before the corresponding fix

- Interrupt after the prepared journal is durable but before any member is
  published. Change only its serialized `fields_after`, `registry_after`, or
  `provider_after`, then recompute the ordinary fingerprint. The original plan
  digest is unchanged. Recovery must reject a different Field declaration, an
  extra unapproved folder, or a provider bound to a different root; no member may
  be published and all current bytes must be retained. A checksum is not approval.
- Replace the registry parent directory after its lock is acquired but before the
  workflow receives the directory descriptor. Refuse before creating a journal or
  provider; the path must identify the same inode as the locked descriptor. Also
  refuse replacement after the first publication checkpoint without writing into
  the new parent. Existing `KnowledgeApplySafetyError` from the provider boundary
  is also a valid refusal for the latter case, not an expected publication success.
- Interrupt after a member's durable write but before its progress checkpoint.
  Retrying with the original digest must safely recognize the exact after bytes,
  preserve the frozen IDs, and complete once, without inferring a lost provider is
  empty. This uses injected writes only in the synthetic state directory.
- A provider safety refusal surfaced by the public registration command must be
  reported as exit 7, not an uncaught exception. Inject the existing provider's
  safety error before writes; retain all Source/state bytes.
