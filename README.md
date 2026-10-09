# scholar-workflow

A Claude Code and Codex plugin for project-centered research material. It connects a project's
code, related papers, knowledge notes, experiments and results while keeping authoritative content
in its existing tools. It maintains readable Markdown/Canvas analyses, literature trees, safe
ingestion and reproducible project records. Obsidian, Zotero, Notion, cmux and external Codex keep
their native reading, editing and execution interfaces.

[中文文档](./README.zh-CN.md)

## Architecture

The host LLM handles understanding, classification, ranking, and recommendation; a
deterministic CLI (`src/scholar_workflow/`) performs testable file and Zotero operations.
Its Zotero adapter connects only to Zotero 10+'s loopback Local API; other outbound access
is scoped and declared — `apply` fetches PDFs from arXiv, and the separate
`bin/notion-project.py` / `bin/recommend-papers.py` reach their own declared services.
**Zotero is the authoritative library** — metadata, existence checks, indexed full text,
and additive writes use the official Local API. Topic recall combines Local API full-text
quicksearch with host-model ranking; no MCP server or local vector database is required.
Destructive actions still require your approval. **Obsidian** holds knowledge notes and
derived indexes; **Notion** holds an optional cross-device projection.

### Content and project ownership

- **Knowledge System** keeps readable Markdown as the primary knowledge artifact. Papers,
  technical documents, and blog posts are atomic resources; analyses, Canvas overviews, and
  attachments are explicitly owned supporting artifacts. New whole-paper analyses follow the
  reference-image Abstract / Introduction / Method / Limitation tree, with evidence beside each
  claim or point; the older five-role tree remains readable for historical artifacts.
- **Project System** keeps a stable `project_id`, host-neutral source/config profiles, and
  separate Run, Attempt, Target, artifact-promotion, and backup records. A promoted artifact
  is not called a verified backup without an independently checked copy.
- **Project material context** is a separate, optional `project-context.json`: code, papers,
  knowledge notes and experiment results are explicitly referenced with their relevance to the
  project. It does not copy content, synchronize stores, execute tools or require the Hub.

Project references leave source ownership unchanged. An explicitly requested document copy is
different: it receives destination identity and evolves independently. Neither operation creates
hidden synchronization, source overwrite or cascading deletion.

### Project overview (0.31.0 hotfix; human acceptance pending)

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

### Legacy research Hub (compatibility only)

The frontend and embedded Codex control plane are no longer the product direction. The commands
below remain documented for existing installations; they are not prerequisites for project
integration or native cmux/Codex use. This refactor has not stopped any installed service/worker.
The legacy opening command is:

```bash
scholar-workflow open-hub
```

`open-hub` verifies the installed build, starts or safely restarts Scholar Workflow's managed
loopback service, discovers its dynamic port, and opens the Hub. It never needs a source checkout,
`CODE_REPO_ROOT`, a fixed port, nonce, or lease. Run it inside cmux to remember that workspace as
the page's default open location; outside cmux, reading and authorized file operations still work,
while cmux-only actions ask you to choose a destination.
The HTTP service runs independently of cmux. Inside cmux, `open-hub` also starts a small,
unfocused terminal router for window actions; closing that workspace must not stop Hub reading.
One managed Hub currently routes to one active cmux instance at a time (multiple workspaces within
that instance are supported). Opening it from a different cmux instance replaces the window route,
not file permissions; earlier pages remain readable and must choose a live destination to launch.

Service controls are explicit and idempotent:

```bash
scholar-workflow hub start
scholar-workflow hub status
scholar-workflow hub restart
scholar-workflow hub doctor
scholar-workflow hub stop
```

`status` reports the real executable, installed package version and code build, protocol, PID, dynamic port,
generation, start time, and log. `stop` affects only a process whose discovery record and live
identity handshake prove that Scholar Workflow owns it; an unknown listener is never terminated.
`hub doctor` verifies the managed process, build and private runtime files; `hub-doctor --json`
shows detailed provider and capability diagnostics. A slow provider or cmux router cannot invalidate
the lifecycle identity check. Plugin manifest versions are checked separately during release
validation. After any manual `hub restart`, run `open-hub` again: the old page points at the old
dynamic port. Run it inside cmux if window actions need a default destination.

The page is organized as `Libraries → Papers / Fields`, plus peer `Projects` and `Tools` entries.
There is no global “workspace bound/read-only” mode. Capabilities such as Vault writes, project
document writes, cmux launches, Codex tasks, ZotFlow annotations, and Zotero Local API are reported
independently. A closed cmux workspace disables only launches routed to it.

To add a research field:

1. Open **Fields → 选择 Vault / 目录** (Select Vault/Folder).
2. Choose an Obsidian Vault or a subdirectory in the system picker. The browser never receives its
   absolute path.
3. Review the zero-write preview: proposed Fields, home page, navigation order, collisions,
   template rewrites, ignored files, unmapped prose, and link changes.
4. For an ordinary new Field, confirm only the one you want to initialize. If the preview reports
   legacy analysis or Hub links, its browser confirmation is disabled; use the operator transaction
   below so registration and migration stay together. One Source may contain multiple Fields, and
   each Field defines its own navigation labels.

If the selected Vault already has a portable Field manifest but is not registered on this host,
the preview instead offers **Register existing Source**. It shows all existing Fields and IDs;
confirmation registers the Source locally without editing that manifest or its documents.

The legacy `research_vault_root` is only offered as a migration candidate. It is not the one
required knowledge root. Field pages show manifest navigation and selected Markdown together,
without a document landing page.

Paper cards act directly. The primary action opens the locally available PDF in **Zotero**;
secondary actions can open ZotFlow when its desktop local-storage mode is verified, read in the
selected cmux workspace, use the system PDF reader, show the analysis, or open the annotation note.
The cmux PDF surface is a local read-only preview, not an embedded Zotero reader or an annotation
sync client. Source links in new analysis drafts can target a verified Zotero PDF page or existing
annotation in the separate Zotero app; exact-text selection is not implied by a page link.
If the local PDF is missing or has changed, opening fails closed instead of requesting a cloud PDF.
Zotero remains the annotation authority. Only ZotFlow may hold a
Zotero Web API key, in Obsidian SecretStorage; Scholar Workflow reads annotations through the Local
API and never requests that key. The legacy `/hub/item` and `/open/paper/...` routes remain only for
one-cycle compatibility and are not emitted by the normal UI.

Expand **Related files** on a paper card for explicitly related companion notes, analysis Markdown,
Canvas, annotation/reading notes, ZotFlow Source Notes and Zotero child attachments. Rows show
source and availability; Markdown offers a Hub body preview and Obsidian opening, while Canvas
edits in Obsidian. Missing declared files retain diagnostics; names never establish paper ownership.
The ZotFlow action targets the registered Vault's Library Reader. The cmux action opens the original
PDF in the selected workspace browser, without Zotero database annotations. Each launch can override
its destination; native Obsidian/Zotero windows do not belong to a cmux workspace.

To use ZotFlow without cloud PDF downloads on desktop, go to Obsidian Settings → ZotFlow → General
→ Source Notes → Library Source Note, enable **Use Zotero Storage Directory**, and set **Zotero
Storage Path** to the absolute path of Zotero's `storage` directory (not its parent; do not use `~`).
Imported attachments then read the existing local file. A missing local file is an error, not a
reason to download it. ZotFlow's metadata/annotation Web API sync is separate from PDF file sync;
keeping the former enabled does not require Zotero cloud PDF storage. Hub disables its ZotFlow
action until it can verify this local-only mode without reading ZotFlow's secret settings.

To open a Zotero attachment in ZotFlow's **Library Reader** manually, use Obsidian's Command
Palette (`Cmd-P`) → `ZotFlow: Open Zotero Tree View`, search the paper title, expand its item,
and double-click the PDF attachment. `ZotFlow: Search Zotero Library` is a shorter alternative:
search the title and press Enter on the attachment result. Do not open a PDF from the Vault file
explorer for a Zotero round-trip test: that is the Local Reader and its annotations stay in a
co-located `.zf.json`. In Obsidian Settings → ZotFlow → Sync, the intended library must be
`Bidirectional`; after annotating, use ZotFlow Activity Center → Sync and wait for Tasks to finish.
If the paper is absent from Tree View, run `Sync All` there first. Keep any Zotero Web API key
inside ZotFlow's own settings, never pass it to Scholar Workflow. See the
[ZotFlow reader guide](https://zotflow.peterduan.dev/reading-and-annotating/) and
[getting started guide](https://zotflow.peterduan.dev/getting-started/).

Notion and other Web tools open through registered URL recipes in a selected cmux browser surface.
CLI and Codex recipes open a terminal surface there, but cwd comes only from a registered project,
Vault, or folder target. Browser requests cannot supply URLs, commands, cwd, model, sandbox,
permissions, environment, or raw Codex configuration. Project operations still accept only a
registered `project_id` and a relative path under `docs/`; collisions and symlink escapes fail,
deletion goes to recoverable project trash, and Hub never writes Git.

To enable a task, open **Codex tasks → Configure Codex**:

1. Review detected executable versions and model choices. Detection does not save or launch a task.
2. Select permitted registered targets, or choose a working folder in the system picker and confirm
   its preview. A Field suggestion scopes cwd to that Field, not the entire Vault.
3. Confirm a model and either read-only or workspace-write policy.
4. Return to tasks. Current Project/Field or a paper's unique Field relation suggests its exact target;
   only one applicable recipe auto-selects. Ambiguity requires a choice; missing targets guide registration.
5. Pick Default/a specific model and a supported reasoning level, enter a brief up to 8 KiB, review
   the recipe/target/model/reasoning/destination summary and start. Selected identities are context
   locators, not an automatic full-paper text injection.

Choices persist on the server across port changes. Default means the confirmed local CLI model, not
desktop proprietary auto-routing. Catalog availability is not account entitlement; only a real
successful call proves access. Existing threads pin actual model/reasoning; a changed configuration
requires a new task or explicit fork, never a silent resume switch.

The CLI fallback runs on the Hub host; destination routes the terminal, target resolves cwd:

```bash
scholar-workflow hub target list
scholar-workflow hub target add-source SOURCE_ID --target-id research
# Or use an already registered project:
scholar-workflow hub target add-project PROJECT_ID --target-id project
scholar-workflow hub codex configure --executable /absolute/path/to/codex --model YOUR_MODEL --sandbox workspace-write
scholar-workflow hub codex status
scholar-workflow hub restart
```

`SOURCE_ID` is shown in the **Fields → 选择 Vault / 目录** preview; `PROJECT_ID` comes
from the project's manifest and host registration. Use the target command that matches your work.
`configure` probes the explicitly supplied executable and stores the model and sandbox as private
server policy; it does not search `$PATH`. Restart the Hub after CLI configuration; browser setup
refreshes the task entry immediately. Until configuration, a live destination, and the
worker capability check all succeed, the panel shows the specific unavailable reason. The
administrator can choose `--sandbox read-only` instead for a task that must not write files.

If ZotFlow is unavailable, check the registered Vault, plugin versions and local-storage mode; do
not enable cloud PDF fallback. Re-select a live cmux workspace after destination expiry; reading
still works. Empty task targets require registration rather than an arbitrary first choice. A
missing model catalog offers only a confirmed local model. Configuration changes wait for active
runs to finish or be explicitly cancelled.

These new entries are implemented in the development tree but await independent tests and one-paper
visible acceptance; see `planning/hub-paper-task-test-plan.md`. This does not claim installed-product validation.

To give another PDF reader a separate copy with supported Zotero annotations:

```bash
scholar-workflow zotero snapshot-annotations ATTACHMENT_KEY --output /path/to/annotated-copy.pdf
```

This creates a new PDF and hash receipt; it never overwrites the Zotero attachment or syncs edits
made to the copy back into Zotero. Unsupported annotation types fail explicitly.

For an existing research folder with legacy links or a legacy analysis pair, do not use the
browser's old **Initialize Field** confirmation first. Use the single-Field operator transaction
instead. Its read-only plan covers the portable manifest, local Source registration, old-link
rewrites, and any reviewed Markdown/Canvas/sidecar replacement together:

```bash
scholar-workflow hub field-transaction plan --field-root FIELD_RELATIVE_ROOT
# Review the returned candidate_token, field_id, plan_token, plan_digest,
# file-by-file diff, conflicts, and unresolved files before any write.
scholar-workflow hub field-transaction apply PLAN_TOKEN --approved-digest sha256:PLAN_DIGEST --external-writers-paused
```

`plan` may open the system folder picker. If you selected the Field directory itself, its relative
root is `.`. `apply` requires a second interactive confirmation and a manually arranged pause of
Obsidian/sync writers; the CLI cannot prove that they are paused. A restart or expired review token
requires a fresh plan and a fresh digest review. The private recovery snapshot is **not** a
verified backup.

When a legacy paper analysis must be normalized in that same transaction, prepare a trusted local
JSON proposal with `schema_version`, relative `markdown_path`/`canvas_path`/`sidecar_path`, the
candidate Analysis IR and rendered Markdown/Canvas bundle, and complete old-Markdown/Canvas
mapping plans. The server reads the old files itself; the package must not contain source bytes,
absolute paths, or a Web API key. Preview the mechanical gate first and resolve every finding
and paper-fact uncertainty. Legacy staging is disabled until Provider and Field changes share
one recoverable transaction journal; a preview cannot authorize a Vault write:

```bash
scholar-workflow hub field-transaction legacy-preview CANDIDATE_TOKEN FIELD_ID --package-file PROPOSAL.json
```

`legacy-preview` is read-only; `legacy-stage` exits with dependency error 3 and its HTTP endpoint
returns 503, even for a valid digest. Ordinary clean Field transactions remain available, but a
plain `plan` cannot bypass managed analysis conflicts. Mechanical conformance cannot replace human
review of scientific claims or the Canvas layout. Existing `recover` remains available for a
previously interrupted transaction and requires a manually arranged pause of Obsidian/sync writers.

The older link-only command remains for an **already registered** Field that needs no analysis or
manifest reorganization:

```bash
scholar-workflow hub field-migration plan SOURCE_ID FIELD_ID
scholar-workflow hub field-migration apply SOURCE_ID FIELD_ID --approved-digest sha256:PLAN_DIGEST --external-writers-paused
scholar-workflow hub field-migration recover SOURCE_ID FIELD_ID
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
| build-literature-tree | Build a novelty tree (task → pipeline → paper) + flat paper list |
| check-consistency | Audit cross-system consistency (read-only) |
| export-annotations | Turn a paper's Zotero annotations into a structured vault note |
| recommend-papers | Daily multi-source paper feed + NotebookLM skim → Reading Report |
| analyze-paper | Project detailed paper analysis into paired Markdown + editable Canvas |
| env-setup | Scaffold — and consult — a personal API-key / SSH-server env-records ledger |
| agent-collaboration | Coordinate bounded work bidirectionally between Claude Code, Codex, or another available agent |
| init-project | Initialize a host-neutral, Git-managed research project skeleton without custom agents or hooks |
| config-setup | Initialize, query, and update the plugin configuration |
| project-backlog | Maintain the repository's persistent work-item queue |

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
  - `notebooklm-py` + a Google login — only for the `recommend-papers` skim tier and
    NotebookLM-assisted literature-tree batch reading.
  - A Scholar Inbox account — only for that one recommendation source.
  - A target agent's CLI and existing login — only when `agent-collaboration` crosses
    host runtimes instead of using a native agent tool.

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

2. **Install the CLI** (provides the `scholar-workflow` command the skills call):
   ```bash
   pip install -e .        # from a clone
   # or: pipx install scholar-workflow
   ```
   Verify: `scholar-workflow --help`.

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
version (see [CHANGELOG.md](./CHANGELOG.md) for what changed). Refresh the marketplace or
pull the latest `release` branch, then re-run `pip install -e .`
(or `pipx upgrade scholar-workflow`) if the CLI version changed. Your `config.yml` and any
credentials live outside the repo and are unaffected by updates.

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

Each skill's own `README` (under `skills/<name>/`) documents its options and setup in
detail. Recommendation reports are ephemeral; papers you keep flow into the normal
find/ingest pipeline so nothing enters your library without the dedup check.

## Status & limitations

The plugin is in active `0.x` development. What's solid vs. still settling:

- **Live-tested on Zotero 10.0.2:** the Local API path has passed probe, search, collection
  listing, remembered write authorization, item creation, imported-PDF upload, exact DOI
  reuse, and attachment reuse. The same ingest payload returns the original item and
  attachment without re-uploading.
- **Hub v3: 0.30.0 hotfix; installed-product human acceptance is pending:** it replaces the
  v0.28.1 binding model in the development tree. cmux is only an open location; trusted
  folder/project targets authorize files and cwd. Managed lifecycle uses a dynamic port and
  self-identifying discovery rather than a fixed 23128 service or source-tree root.
- **Real data still uses per-Field gates:** the first Source is the current research-document
  Vault, the first Field is World Models, and JEPA/V-JEPA is the acceptance sample. A preview must
  be accepted before that Field changes; other Vaults and projects remain untouched.
- **ZotFlow availability is diagnosed, not repaired automatically:** incompatible versions,
  disabled local-storage mode, missing CLI proof, or absent local PDF disable only the ZotFlow
  action with a reason. Hub never upgrades Obsidian, removes another plugin, or retrieves a PDF
  from the Zotero Web API/WebDAV to repair local availability.
- **Implemented but not yet exercised on a real end-to-end run:** the `build-literature-tree`
  CLI render path (especially the fourth `module` level and the challenge-insight tree
  written to the vault), the `recommend-papers` NotebookLM skim tier, and `check-consistency`.
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
