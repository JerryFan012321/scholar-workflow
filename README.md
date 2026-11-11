# scholar-workflow

A Claude Code and Codex plugin for project-centered research material. It connects a project's
code, related papers, knowledge notes, experiments and results while keeping authoritative content
in its existing tools. It maintains readable Markdown/Canvas analyses, literature trees, safe
ingestion and reproducible project records. Obsidian, Zotero, Notion, cmux and external Codex keep
their native reading, editing and execution interfaces.

Current product direction: retain research Skills, accepted file formats
and thin native-tool adapters; retire the old Hub website and freeze independent explorer product work. Knowledge
is managed as complete paper/blog/document asset units with explicit context. Their
management, analysis, viewing and editing are separate operations. See
[asset units](references/asset-units.md) and [project Skills](references/project-skills.md).
Multidimensional viewing/editing remains under discussion; existing records are retained.
Version 0.51.0 adds the first-phase recommendation page and shared agent intake.

The follow-up recovery fix separates a same-directory device-number recovery from
acknowledging an additive Canvas editor save. It preserves all file bytes and reports
the remaining acknowledgement; export stays strict until that separate step completes.


[中文文档](./README.zh-CN.md)

## Recommendation page — first phase (0.51.0)

Independent agents submit papers, project homepages and blogs to one versioned
JSON/CLI entry. The compact page provides topic/task/type filters, original/project
links and attributed raw platform values; expanding an item shows its complete
abstract translation and supporting links. Popularity is
shown as data without a combined score or evaluation. Host tools own scheduling.

```bash
scholar-research recommendations schema
scholar-research recommendations submit --input recommendations.json
scholar-research recommendations open
scholar-research recommendations status
scholar-research recommendations stop
```

The personal pool begins empty. Ask an agent to use the `recommend-papers` Skill;
it knows the shared submission entry. Use `recommendations --profile test` for an
independent test pool. Exported reviewed selections go to `ingest-resource`; export
does not ingest. The 0.52.0 candidate also supports explicitly confirmed Zotero
bibliography writes, described below. See the
[intake contract](references/recommendation-intake.md). This is a bounded recommendation/review page. Existing knowledge units, native
readers and agent runtimes keep their own interfaces and authority.

## Architecture

The host LLM handles understanding, classification, ranking, and recommendation; a
deterministic CLI (`src/scholar_workflow/`) performs testable file and Zotero operations.
Its Zotero adapter connects only to Zotero 10+'s loopback Local API; other outbound access
is scoped and declared — `apply` fetches PDFs from arXiv, and the separate
`bin/notion-project.py` / `bin/recommend-papers.py` reach their own declared services.
The optional `scholar-research` entry checks explicitly registered public research
channels; local `scholar-workflow research` operations do not fetch websites.
**Zotero is the authoritative library** — metadata, existence checks, indexed full text,
and additive writes use the official Local API. Topic recall combines Local API full-text
quicksearch with host-model ranking; no MCP server or local vector database is required.
Destructive actions still require your approval. **Obsidian** holds knowledge notes and
derived indexes; **Notion** holds an optional cross-device projection.

Research tracking shipped in 0.48.0, with one installed RSS-source functional check.
Other channel types, human assessment and the selected-resource archive handoff
retain their separate acceptance requirements.

### Content and project ownership

Multidimensional records remain available through
[explore-knowledge](skills/explore-knowledge/README.md). The viewing/editing design
is open; do not launch the old web application as the default workflow. Existing
`.scholar-workflow/exploration.yml`, extensible dimensions, conditional records,
evidence and saved queries remain intact. Explicit CLI query/export operations
remain available; export writes readable navigation to stdout only and does not
change paper units. See the [data contract](references/knowledge-exploration.md).

The unpublished0.50.0 candidate adds complete registered paper, Blog and technical
document references. `knowledge list --asset-units --source-id SOURCE --field-id FIELD --language en`
lists their members and availability; `--paper-units` stays paper-only. New references
use registered import. Unqualified legacy rows remain readable and unverified,
not silently adopted. The installed0.49.0 does not have this option.

For non-paper updates, use [track-research](skills/track-research/README.md):
`research sources list/register` manages selected blogs, institutional pages,
release repositories and model lists; `scholar-research check` observes them once;
`research updates/mark` reviews retained events. The first success establishes a
baseline, failures remain visible, and selection does not automatically ingest.
No Hub, scheduled service, source checkout or model-weight download is required.
See [source and update contract](references/research-tracking.md). Publication and
installed acceptance of the current development batch remain separate.

- **Knowledge System** keeps readable Markdown as the primary knowledge artifact. Papers,
  technical documents, and blog posts are atomic resources; analyses, Canvas overviews, and
  attachments are explicitly owned supporting artifacts. New whole-paper analyses follow the
  reference-image Abstract / Introduction / Method / Experiments / Limitation tree, with evidence
  beside each claim or point; historical artifacts retain their own versioned formats.
- **Project System** keeps a stable `project_id`, host-neutral source/config profiles, and
  separate Run, Attempt, Target, artifact-promotion, and backup records. A promoted artifact
  is not called a verified backup without an independently checked copy.
- **Project material context** is a separate, optional `project-context.json`: code, papers,
  knowledge notes and experiment results are explicitly referenced with their relevance to the
  project. It does not copy content, synchronize stores, execute tools or require the Hub.

Project references leave source ownership unchanged. An explicitly requested document copy is
different: it receives destination identity and evolves independently. Neither operation creates
hidden synchronization, source overwrite or cascading deletion.

An explicitly selected official webpage can also have a real Zotero bibliography
and an archived, block-addressable `Source.md`. `knowledge document-plan` and
`knowledge register-document` register one new owner without a PDF; the ordinary
v5 analysis pair remains beside it. Missing technical disclosure is not filled
from another paper. See [webpage registration and use](references/document-registration.md).

From 0.43.0, schema-2 Fields can retain qualified references to existing
knowledge objects and their purpose. `knowledge list --resolve-references` optionally shows
declared ownership and file diagnostics without opening readers or creating copies. Schema 1
keeps its original shape. `knowledge reference-plan/reference` previews and
confirms one addition/removal without changing its target. Human navigation acceptance
remains separate from the installed command contracts.
See [knowledge registration](references/knowledge-registration.md).

For a selected Field's existing paper packages, `knowledge list
--paper-units --source-id SOURCE_UUID --field-id FIELD_UUID` groups information,
analysis, Canvas and note entries with direct safe Obsidian links and honest
unavailable states. It does not replace the fixed ledger, copy content or write
files. Available from 0.43.0; see [paper-unit navigation](skills/build-literature-tree/references/field-paper-units.md).

From 0.44.0, ask `build-literature-tree` to organize a selected topic into a complete
01 paper list, a 02 literature timeline, 03 radial technical routes and 04 radial
challenges/solutions. The installed skill includes the pure layout helper and scoped
CSS assets; exact native styling requires Advanced Canvas and the two enabled snippets.
From 0.44.2, timeline titles stay short-name/year links and radial paper leaves stay
one method sentence plus navigation; detailed evidence stays in prose, not repeated cards.
See [setup and output format](skills/build-literature-tree/references/field-library-format.md).
Existing paper owners and current single-paper analysis formats remain unchanged.
Native appearance and each new topic's human assessment remain separate gates.

From 0.44.3, the Field-library format uses the user's Canonical Knowledge Vault as its
sole blueprint: required elements must be present, absent elements are omitted by
default, and subsequent directory, prose and visual formats must match. New paper
packages use `resources/<segment>/`; existing declared owners stay in place.
Scientific detail and figure/table/evidence counts follow the actual papers, not
the exemplar's content volume.
Normal installation, native display and each topic's human assessment are separate
from source validation; see the same format contract.

The 0.43.0 `literature-preview --input evolution.json --format md|json`
also previews contribution-level novelty, placement and evidence-linked technical
tradeoffs without reading or writing source material. The final editable evolution
figure and human appearance acceptance remain pending.
See [the evolution preview contract](skills/build-literature-tree/references/evolution-preview.md).

The 0.43.0 `review-experiments` skill turns selected Run/Attempt/Artifact
records into a readable, source-linked comparison without running experiments or
adding a result database. Ask to compare explicit Runs, result Attempts and metrics;
failures, replays and missing evidence remain visible. See
[experiment review](skills/review-experiments/README.md).

The 0.43.0 `organize-project` skill prepares a rich internal PROJECT.md:
current state, source-supported module diagrams, direct code/experiment/paper links,
and one detailed plan in PROJECT or SCHEDULE. README remains public-facing. It is
separate from initialization and the short inventory overview. See
[internal project entry](skills/organize-project/README.md).

### Project material and collected experiment views

The source candidate adds an editable YAML/JSON `--selection-file` for readable
metrics, configuration, reports and figures, while model payloads remain at the
source. Original Run/Attempt/artifact records stay unchanged; reception, reading,
updates and recovery use the same selection. Explicitly deferred required evidence
remains incomplete. Installed 0.49.0 does not expose this option; check installed
help before use. Remote export/SSH pulling is not provided by this interface.
See [result selection and delivery](references/experiment-result-selection.md).

For collected child experiments, use a normally installed version whose
`scholar-workflow experiment --help` exposes `collected`:

```bash
scholar-workflow experiment collected --project-root /path/to/parent --language en
scholar-workflow experiment collected --project-root /path/to/parent --child-project-id CHILD_UUID --json
```

This prints a local, read-only navigation index, without contacting child servers.
Configuration/conditions and recorded outcomes share each row; missing or invalid
archives remain visible. Save Markdown at the parent root only when requested so
its relative links resolve. It does not evaluate metric meaning or rank results.
See the [management contract](references/project-management.md) for preview,
registration, first reception, four-baseline updates and explicit local commit/rollback
recovery. These commands require a normally installed version that exposes them;
source development or a passing test is not installation evidence.

For remote child code, the additive `execution-code` inventory reference retains
child identity and relative code location without a local source clone.
`project remote-code-plan` previews an explicitly selected existing Target/server
declaration; it does not connect, verify remote Git or launch an editor. Check the
installed command's help and the [context contract](references/project-context.md).

Minimal local source retention uses `project code-recovery-plan` followed explicitly
by `project retain-code` with the returned plan digest. It checks a supplied local
self-contained Git bundle against the selected child's collected Run commits, then
saves one bundle plus small coverage records, not a development checkout. It does
not fetch from servers, capture uncommitted work or certify backup; see the
[recovery procedure and gaps](references/project-management.md#selected-local-git-recovery-material).
Confirm these commands exist in the normally installed version before use.

For an initialized project, print an editable inventory template, select the actual material,
and explicitly save it as `project-context.json` in that project. Template generation does not
write files or invent related papers:

```bash
scholar-workflow project context-template --project-root /path/to/project --language en
scholar-workflow project validate-context --project-root /path/to/project
scholar-workflow project overview --project-root /path/to/project
scholar-workflow project overview --project-root /path/to/project --json
scholar-workflow project overview --project-root /path/to/project --context-file project-context-candidate.json
```

The default overview is Markdown on stdout. Save it beside the project root inventory only when
you want a document; relative links are rooted there. It reports missing/unsafe local references,
does not follow symlinks, and leaves external resources unverified until checked in their owning
application. It does not need plugin configuration, a running service or workspace registration.
See [Project context contract](references/project-context.md) for fields and native reader links.
The optional candidate selector is a read-only, explicitly unapplied preview of one root-level
JSON declaration. It does not replace the active inventory or approve an overwrite.

From 0.42.0, `project overview --resolve-knowledge` checks selected Knowledge IDs against
registered declarations and reports ownership, file availability, and unverified
readers separately. It does not move content or add synchronization; default output
stays unchanged. After normal installation, verify `scholar-workflow --version` and
`project overview --help` before using the new option. Synthetic validation is complete;
installed-product and human navigation acceptance remain separate.

### Inspect a knowledge folder without Hub (0.34.0)

Run `scholar-workflow knowledge preview /absolute/selected/folder --language en`.
It reports candidate/existing Fields, complete navigation, unmapped Markdown,
external writers and conflicts. Add `--format json` for machine output. This is
a zero-write preview, not registration or acceptance; it creates no homepage and
does not start a service. Existing Source/Field registration and canonical analysis
commits remain separate reviewed operations.

### Open a registered note or Canvas in Obsidian (0.37.0)

Get its `source_id` from `scholar-workflow knowledge list --format json`, then run:

```bash
scholar-workflow knowledge reader SOURCE_ID
scholar-workflow knowledge open SOURCE_ID 'relative/note.md'
scholar-workflow knowledge open SOURCE_ID 'relative/tree.canvas'
```

A selected Source subfolder uses its containing Obsidian Vault only as the native
open destination; file permissions remain inside the Source. No Hub/workspace or
Obsidian CLI is needed. An accepted request is not visual acceptance or canonical
paper enrollment. PDF/ZotFlow capability checks remain independent.

### Register one knowledge Field without Hub (0.36.0)

From 0.39.0, export portable ownership with
`knowledge reproduction-plan` and restore a copied, explicitly attached Source with
`knowledge restore-plan/restore`. See [replay contract](references/knowledge-reproduction.md)
for exact inputs, non-overwrite boundaries and outstanding reader/source/human checks.

For a device-number change at the **same registered path and inode**, 0.41.4 provides
`knowledge rebind-plan --source-id SOURCE_ID --format json`, then
`knowledge rebind --source-id SOURCE_ID --approved-digest HEX` after review. It changes
only the host binding and derived snapshot revision, never content or ownership.
Different directories and stale inputs refuse; see the same replay contract for recovery.

After `knowledge preview`, choose exactly one candidate relative root. Run
`scholar-workflow knowledge registration-plan /absolute/selected/folder --field-root .`,
review its navigation and digest, then `knowledge register /absolute/selected/folder
--field-root . --approved-digest HEX_DIGEST`. Confirm locally; `knowledge list` shows
registered navigation. Changes invalidate confirmation; managed/legacy analysis
still requires joint migration review. Existing portable Sources use the separate
`--existing-source` mode, preserving all IDs and manifest bytes. No homepage or
paper rewrite. See [registration contract](references/knowledge-registration.md).

### Check an existing paper package (0.35.0)

The single-paper enrollment interface (0.38.0+) is documented in
[Paper registration](references/paper-registration.md): `knowledge paper-plan`
and `knowledge register-paper` use an existing registered Source/Field, live Zotero
identity, a new companion folder and digest-bound conditional recovery. This is
not adoption of old packages or scientific acceptance; verify installed support.
From 0.43.0, registration checks canonical paper ownership across explicitly registered
Sources and refuses missing inventories. New Source registration initializes its empty
provider explicitly; old Source attachment never guesses one. See the linked contracts
for conditional recovery.

```bash
scholar-workflow analysis check-bundle /absolute/paper-folder \
  --markdown 'Paper Analysis.md' --canvas 'Paper Tree.canvas' \
  --sidecar 'analysis.baseline.json' --require-ir 5 --language en
```

Supply the exact three filenames. The checker reads the displayed bytes and reports
format/geometry/backlink and baseline consistency without regenerating or registering.
Use `--format json` for hashes/findings. Source truth, live readers and visual acceptance
remain separate; exit 0/7/2 means conformant/nonconformant/invalid input respectively.

### Reproducible project/experiment example (0.33.0)

The installed init-project skill includes an optional portable example:
`python3 skills/init-project/scripts/example_project.py plan /chosen/new-project`, then
`apply /chosen/new-project`, from the installed plugin root. It prepares only a new project;
the generated bilingual README explains the separate scoped commit, explicit local execution
and new-clone replay. No Hub, source-checkout variable, external paper or system dependency
installation is required. See [reproduction contract](skills/init-project/references/reproducibility.md).
The deterministic example does not establish scientific validity or replace human assessment.

### Compatibility service without a website

The old Hub website and its bundled HTML/JavaScript/CSS are retired in current
source. `/hub/` and `/hub/assets/*` return HTTP 410. `open-hub` refuses before
starting a service, routing a terminal or opening a browser. It does not redirect
to the undecided multidimensional interface. Installed 0.49.0 keeps its old
behavior until an updated package is normally installed.

Existing catalog/health/PDF and controlled native-open compatibility APIs remain.
Their safety boundaries, existing state and lifecycle commands are retained:

```bash
scholar-workflow hub status
scholar-workflow hub doctor
scholar-workflow hub stop
```

Stop/restart only affect a process verified as Scholar-managed. This source change
does not stop installed services or delete their state. Native paper/note opening
uses the [resource-location contract](skills/find-resource/references/resource-location.md)
and independent `knowledge open` commands. No website is required.

For an explicitly selected separate PDF copy with supported Zotero annotations,
`scholar-workflow zotero snapshot-annotations ATTACHMENT_KEY --output /path/to/copy.pdf`
keeps its existing semantics: no original replacement or annotation write-back.

### Local Field transactions

Field content operations have local entries without an HTTP listener, browser token
or cmux. For a newly selected Field, review the complete JSON plan, storing it
outside the selected source:

```bash
scholar-workflow knowledge field-transaction plan --root /path/to/selected-folder --field-root . > REVIEWED.json
scholar-workflow knowledge field-transaction apply REVIEWED.json --approved-digest sha256:PLAN_DIGEST --external-writers-paused
```

Use `--source-id SOURCE_ID --field-root RELATIVE_ROOT` instead of `--root` to select
an unregistered Field within an already registered Source. The plan binds the exact
selection, proposals and bytes. Apply reconstructs and checks it in a fresh process,
then requires interactive confirmation and an explicitly arranged external-writer
pause. A stale digest refuses. The recovery snapshot is not a verified backup.
For an interrupted original journal, use `knowledge field-transaction recover
SOURCE_ID FIELD_ID --confirm-recovery --external-writers-paused`.

For read-only conservation review of a trusted legacy proposal:

```bash
scholar-workflow knowledge field-transaction legacy-preview --root /path/to/selected-folder --field-root . --package-file PROPOSAL.json
```

This does not stage old analyses. Joint legacy Provider/Field staging remains
unavailable; `legacy-stage` exits 3. Existing managed-content conflicts cannot be
bypassed by enrollment. Old `hub field-transaction` commands return a migration
notice; saved browser candidates need a fresh explicit local plan.

The older link-only command remains for an **already registered** Field that needs no analysis or
manifest reorganization:

```bash
scholar-workflow knowledge field-migration plan SOURCE_ID FIELD_ID
scholar-workflow knowledge field-migration apply SOURCE_ID FIELD_ID --approved-digest sha256:PLAN_DIGEST --external-writers-paused
scholar-workflow knowledge field-migration recover SOURCE_ID FIELD_ID
```

Its plan is read-only. Each distinct attachment key must be verified through Zotero's Local API as
an available PDF in the user library before its stable URI is approved. Missing items, group items,
non-PDF or unsupported attachments, and an unavailable Local API are explicit plan conflicts; apply
also reverifies them before any recovery snapshot or write. Apply re-scans the Field and requires the
exact approved digest; it only rewrites legacy links in Markdown/Canvas files named by that Field's
manifest. Unmapped files with remaining legacy links block the operation. It does not reorganize
paper analysis or normalize JEPA templates. Apply also requires an interactive confirmation and
the operator's explicit assertion that Obsidian and other external writers are actually paused;
the CLI cannot verify that assertion. An interrupted multi-file replacement leaves a private
journal: a new plan/apply refuses until the explicit `recover` command verifies the journal, snapshot,
and current file hashes and conditionally restores only unchanged Field files. External edits or a
damaged snapshot require manual review; recovery never overwrites them. The recovery snapshot is
not a verified backup. Do not use this compatibility path to initialize the World Models Field.

See [`references/hub-contract.md`](references/hub-contract.md) for the complete runtime contract.
Recovery snapshots created during a Field migration are not verified backups; a separate backup
medium and restore exercise remain required.
Older v1 HTTP write/upload/action routes return `410 Gone`; use the v3 Field, target, and action
flows instead of treating a compatibility response as write authority.

## Skills

| Skill | Purpose |
|---|---|
| survey-topic | Scope an open-ended "research X" request, then route it through the other skills |
| find-resource | Search for papers, verify identity, locate existing resources |
| ingest-resource | Import papers / archive technical documents |
| sync-projections | Rebuild Obsidian index tables + sync the Notion projection |
| build-literature-tree | Complete paper list + literature timeline + radial technical routes and challenges |
| check-consistency | Audit cross-system consistency (read-only) |
| export-annotations | Turn a paper's Zotero annotations into a structured vault note |
| recommend-papers | Research recommendations, shared agent intake and reviewed selection |
| track-research | Selected blogs, institutional pages, releases and model lists → incremental updates |
| explore-knowledge | Editable dimensions, joint-condition research comparisons, evidence relations and complete asset navigation |
| analyze-paper | Project detailed paper analysis into paired Markdown + editable Canvas |
| manage-assets | Query, register and reuse owned servers and knowledge libraries |
| env-setup | Scaffold — and consult — a personal API-key / SSH-server env-records ledger |
| agent-collaboration | Coordinate bounded work bidirectionally between Claude Code, Codex, or another available agent |
| init-project | Initialize a host-neutral, Git-managed research project skeleton without custom agents or hooks |
| organize-project | Internal PROJECT entry with module views, material links and a single plan (0.43.0+) |
| review-experiments | Read-only review/comparison of selected experiment archives (0.43.0+) |
| config-setup | Initialize, query, and update the plugin configuration |

## Personal research assets

Ask the agent to find your existing servers/libraries or record an owned server. It
queries saved records first rather than asking you to repeat known details.

```sh
scholar-workflow assets list --language en
scholar-workflow assets server show gpu-example --language en
scholar-workflow assets server register --spec server.json --language en
scholar-workflow assets server check --language en
```

The JSON registration spec contains non-secret metadata such as `alias`, `host`,
`user` and `port`; new password/token values are refused. Existing records are reused,
and conflicting updates require their current revision. Queries never initialize or
connect. Knowledge registration still uses the existing preview/confirmation commands;
known native Vaults, registered Sources and paper owners are distinct states. See
[asset operations](references/asset-management.md). Scholar watchlists/source settings
keep their recommendation store and are not yet providers in `assets list`.

## Requirements

- **Claude Code or Codex** (Codex CLI or the Codex app; the IDE extension does not load plugins).
- **Python ≥ 3.11** — the deterministic CLI is a Python package.
- **Git** — required when `init-project` creates or verifies a project skeleton.
- **cmux** — optional for routing Web/terminal/Codex/CLI windows to a chosen workspace. It does not
  grant file access and is not required for reading, Vault saves, or registered project-document
  operations.
- **Zotero 10+ with Local API enabled** — the authoritative library. Enable it in
  Zotero's **Settings → Advanced**. No Zotero plugin or MCP server is required. A sandboxed
  Codex run may need localhost/network permission before it can reach port 23119; retry with
  that permission before interpreting exit 3 as Zotero being offline.
- **Optional, per feature:**
  - **Obsidian + ZotFlow** — for in-Obsidian PDF annotation. Hub checks the installed app/plugin
    versions, ZotFlow's `minAppVersion`, and a narrow live proof of local-only storage mode; it
    reports incompatibility but never upgrades Obsidian. The optional Obsidian CLI is needed only
    for this ZotFlow-specific proof, not for the Zotero primary action. ZotFlow keeps its Zotero
    Web API key in Obsidian SecretStorage.
  - Notion integration token — only if you enable the Notion projection.
  - `notebooklm-py` + a Google login — only for explicitly chosen NotebookLM-assisted
    literature-tree reading; recommendations do not require it.
  - A Scholar Inbox account — only for that one recommendation source.
  - A target agent's CLI and existing login — only when `agent-collaboration` crosses
    host runtimes instead of using a native agent tool.

## Background recommendation work

External recommending agents and the curator use the shared data CLI with no browser
or HTTP service required. Their harness owns scheduling. For people, run
`scholar-research recommendations start` and open the plain URL returned by it;
`status` rediscovers that URL and `open --no-browser` prints it. Multiple local
browser/cmux windows work without URL tokens or existing browser credentials.
Closing windows does not stop the service; `stop` does not disable data CLI access.

## Installation

1. **Install the plugin in your host.**

   The release ships separate native marketplace metadata for Codex and a
   Claude-compatible marketplace entry; both install the same plugin root and version.

   Claude Code:
   ```text
   /plugin marketplace add JerryFan012321/scholar-workflow@release
   /plugin install scholar-workflow@jerry-plugins
   ```

   Codex CLI:
   ```bash
   codex plugin marketplace add JerryFan012321/scholar-workflow --ref release
   codex plugin add scholar-workflow@jerry-plugins
   ```
   Start a new Claude Code or Codex session after installation so bundled skills and hooks
   are loaded.

2. **Install the Python package** (provides both CLI commands; no source checkout required):
   ```bash
   pipx install "git+https://github.com/JerryFan012321/scholar-workflow.git@release"
   ```
   Use the same published runtime revision as the host plugin. For reproducible
   acceptance, replace `release` with the approved runtime commit from the release
   receipt. Marketplace installation alone does not install or update this package.
   Verify the resolved commands in the host environment:
   ```bash
   command -v scholar-workflow
   command -v scholar-research
   scholar-workflow --version
   scholar-research --version
   scholar-workflow research --help
   scholar-research check --help
   ```
   Both versions must match the loaded plugin manifest. Missing commands or version
   mismatches require an installation correction, not a source/cache-script fallback.
   Matching labels alone do not prove a pinned build; retain the runtime commit and
   launcher/interpreter paths for acceptance. Developers may use `pip install -e .`
   from their checkout; that is not normal installed-plugin acceptance.

3. **Create the config.** Ask in-conversation ("configure scholar-workflow") and the
   `config-setup` skill runs it for you, or do it directly:
   ```bash
   scholar-workflow config init
   # add optional settings inline as KEY=VALUE, e.g.:
   #   scholar-workflow config init notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # change one key later
   scholar-workflow config show                                       # inspect effective values
   ```
   This writes `~/.config/scholar-workflow/config.yml` (only the keys you name), validates
   it, and preserves comments on later edits. Override the location with
   `SCHOLAR_WORKFLOW_HOME` if needed. Add each Vault or folder from **Hub → Fields → 选择 Vault / 目录**;
   an old `research_vault_root` value is treated only as a migration candidate.

4. **Authorize Zotero writes.** Start Zotero, then run:
   ```bash
   scholar-workflow zotero probe
   scholar-workflow zotero authorize
   ```
   Choose **Always Allow** in Zotero for multi-step PDF imports. The key is stored in
   macOS Keychain and is never printed or written to config/git. Read commands need no key.

5. **Provide other credentials** as needed (see [Requirements](#requirements)). Tokens/cookies
   live in environment variables or each tool's own login store — **never in config or
   git**. E.g. Notion: `export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`.

## Updating

The host manifests (`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`) share one
version (see [CHANGELOG.md](./CHANGELOG.md) for what changed). Refresh the host plugin
and reinstall the package from the same published runtime revision:

```bash
pipx install --force "git+https://github.com/JerryFan012321/scholar-workflow.git@release"
```

For pinned acceptance use the approved runtime commit instead of `release`, then
repeat the command/path/version checks above in a new host session. Updating the
marketplace and updating the Python package are separate operations; neither proves
the other was updated. Your `config.yml` and credentials remain outside the repo.

## Usage

Talk to Claude Code or Codex in natural language — each skill triggers on intent. In Codex,
you can also invoke a skill explicitly with `$skill-name`, e.g.:

- *"survey the field of world models"* → survey-topic → (recommend / find / tree …)
- *"find the DreamerV3 paper and import it"* → find-resource → ingest-resource
- *"recommend today's papers on world models"* → recommend-papers
- *"analyze the method section of this paper"* → analyze-paper
- *"build a literature tree from NeRF to 3DGS"* → build-literature-tree
- *"export my annotations on this paper"* → export-annotations
- *"sync the Obsidian index and Notion"* → sync-projections
- *"have Claude Code and Codex split this migration and integrate it"* → agent-collaboration
- *"initialize this project with the standard skeleton"* → init-project
- *"prepare an internal PROJECT preview from these selected materials"* → organize-project

Each skill's own `README` (under `skills/<name>/`) documents its options and setup in
detail. Recommendation reports are ephemeral; papers you keep flow into the normal
find/ingest pipeline so nothing enters your library without the dedup check.

## Status & limitations

The plugin is in active `0.x` development. What's solid vs. still settling:

- **Live-tested on Zotero 10.0.2:** the Local API path has passed probe, search, collection
  listing, remembered write authorization, item creation, imported-PDF upload, exact DOI
  reuse, and attachment reuse. The same ingest payload returns the original item and
  attachment without re-uploading.
- **Multidimensional interaction remains undecided:** retain file-backed records
  and accepted paper packages. The old explorer is not the recommended workflow;
  source checks, normal installation and human usability remain distinct.
- **Legacy compatibility APIs remain:** the Hub website is removed; dynamic service
  identity, PDF delivery and retained native routing stay protected. Native tools retain
  their own configuration and lifecycle; cmux selects an opening location, not file permission.
- **Real data still uses per-Field gates:** explicitly select a registered Source/Field and
  review a current preview before a migration changes it. Other Vaults and projects remain untouched;
  a sample's acceptance does not approve another Field or a whole-library migration.
- **ZotFlow availability is diagnosed, not repaired automatically:** incompatible versions,
  disabled local-storage mode, missing CLI proof, or absent local PDF disable only the ZotFlow
  action with a reason. Hub never upgrades Obsidian, removes another plugin, or retrieves a PDF
  from the Zotero Web API/WebDAV to repair local availability.
- **Implemented but not yet exercised on a real end-to-end run:** the legacy
  `build-literature-tree` Mermaid CLI projection (especially the fourth `module`
  level), and `check-consistency`.
  The current Field-library profile has separate installed/native/human assessment.
- **No cross-run resume:** re-running `apply` starts a fresh job and re-downloads every item;
  it does not pick up where a prior run stopped.
- **Identity safety is enforced twice:** skills preview candidates and `zotero ingest`
  repeats the exact DOI or normalized title+creators check immediately before creation.
  Destructive Zotero commands are not exposed; future destructive actions remain gated.

## Development

The published `release` branch contains runtime files only, including native Codex and
Claude-compatible marketplace metadata and both host manifests. Development conventions,
planning docs, tests, and evals live on `main`. See its `AGENT.md` for contributor guidelines;
run tests there with `pytest tests/unit tests/contract`.

### Source catalog and direct bibliography intake (0.52.0)

External agents discover sources through the same local catalog and call available
MCP, API or tooling connections in their own harness. alphaXiv is an important
source; the plugin declares its official MCP endpoint for supported hosts. Native
connections, OAuth and API credentials remain with the harness. The recommendation
page does not present a native-tool console or manage an alphaXiv API key.

```bash
scholar-research recommendations sources list
scholar-research recommendations sources show alphaxiv
scholar-research recommendations sources context alphaxiv
scholar-research recommendations sources history --source-id alphaxiv
```

This candidate adds shared [recommendation requirements](references/recommendation-requirements.md).
Each recommendation-source entry contains an expandable requirements list/editor;
external agents use `scholar-research recommendations requirements list --source-id ID`
and the same `show/save` interface against that pool. Normal new records include
the registered source identity; historical unassigned records stay readable without
a guessed source.
Content is free text supplied by the actual task. Tasks explicitly choose a saved
version, retained in their recommendation details. Saving does not start an agent
or rewrite previous recommendations. This increment shipped in 0.52.0.


Use the [source-catalog contract](references/recommendation-sources.md) to register
another source or record management notes, researcher suggestions and external
operation results. Such records are `agent_reported`; they preserve context across
chats without proving live access or replacing a source's cloud state. All agents
retain their own producer identity and submit verified metadata, complete abstract
translations or sourced summaries through the normal recommendation entry.

The homepage stays compact. Expand an item for complete reading content, original
text, flexible attachments and provenance. Source collection and preparation do not
start agents or models from the page, and existing paper Markdown/Canvas stay intact.

After reviewing/selecting a card, choose a Zotero collection, preview and confirm
**Zotero bibliography ingestion**. Actual item/collection read-back determines
completion. PDF and Vault-unit preparation remain separate and explicitly marked
`not_requested`; a successful bibliography receipt does not complete a paper unit.
See [alphaXiv source use](references/alphaxiv-source.md) and
[recommendation intake](references/recommendation-intake.md).

## Shared writing and report delivery

`content-and-style` supplies shared explanation quality, Chinese prose and typography
through conditional references; `create-report` handles report purpose, selected
medium and human review. Existing paper/Canvas, knowledge and experiment templates
retain ownership. Recommendation synopses reuse the shared prose requirements.
They preserve complete author abstracts or summarize actual source bodies, with
brief labels and expandable Sources. `recommendations revise-content --input FILE`
corrects an existing reading body with its exact revision; `content-history` reads
its attributed changes without adding another recommendation.


## Source plugins (0.54.0)

Settings → Sources adds versioned packages with create/import/edit/export/enable
operations. External agents use `scholar-research recommendations sources guide SOURCE_ID`
for operation contracts, requirements and shared context, then discover native tools
in their own host. New sources need no core/UI enumeration. See the
[source-plugin contract](references/recommendation-source-plugins.md). This capability ships in 0.54.0; use the normal installation and update commands.
