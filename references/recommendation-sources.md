# Shared recommendation source catalog

The catalog records reusable non-secret source definitions for external agents.
For versioned packages, import/export, editing, enablement and the agent handoff,
load [source plugins](recommendation-source-plugins.md).
It does not fetch sources, run an agent, start a model, install a connector or
maintain another account registry. Every host/model can query the same installed
CLI and then use its own native tools. Candidates still enter the one
[recommendation intake](recommendation-intake.md) with the same schema and final
presentation requirements.

## Query and register

```text
scholar-research recommendations --profile personal sources list
scholar-research recommendations --profile personal sources show alphaxiv
scholar-research recommendations --profile personal sources register --help
```

Read the current catalog before choosing a source or registering one. Registration
uses the current whole-catalog revision; a stale revision refuses even for an
otherwise identical record. Reuse a matching source ID. An identical registration
is unchanged; updating an existing source keeps its ID. Packaged builtin definitions
cannot be shadowed. User registrations live only in the chosen recommendation pool;
the package's source_catalog.json is the sole builtin definition, not copied into
that pool as a second editable truth.

A descriptor contains:

| Field | Meaning |
|---|---|
| `source_id`, `name`, `purpose` | Stable source identity, display name and intended use |
| `status`, `enabled` | Definition availability and explicit enabled flag; planned entries stay disabled |
| `scope` | Descriptive acquisition scope, including `self_account_only` where required |
| `interfaces` | MCP/API/feed public URLs or native CLI instructions, never executable commands |
| `capabilities` | Free-form descriptions of what this source provides |
| `documentation` | Public documentation URLs |
| Optional `auth` | Method, symbolic reference and setup instructions; never actual credentials |
| Optional `plugin_version`, `agent` | Portable version and operation contract, defined by [source plugins](recommendation-source-plugins.md) |

`interfaces` supports `mcp`, `api`, `feed` and `cli`. New provider IDs and capability
labels do not require a new global platform enumeration. Network interfaces use
public HTTPS URLs without credentials or secret query parameters. CLI instructions
are descriptions, not shell commands submitted to an executor. Do not put private
absolute paths, tokens, cookies or keys in any field. Authentication belongs to
the chosen native tool or host credential store. Registration alone grants no
network access, cloud write, account authorization or executable capability.

List/show projections add `origin` (`builtin` or `registered`) and
`connection_status`. `available` means the interface is described and usable under
its prerequisites, not that an account has been authenticated. `not_checked` is
explicitly unknown. Only an actual host connection/tool request can verify access.
A planned entry has no implemented acquisition and cannot be called available.
These projection fields must not be copied into a registration payload.

## Builtin sources

- **alphaXiv:** an important popular-discovery source, using the host's native
  `alphaxiv` MCP connection. The descriptor records its official endpoint and
  documentation. Load [alphaXiv source](alphaxiv-source.md) for its modes and
  source-specific boundaries. The host owns OAuth; this catalog never implements
  another MCP/credential client or proxy. Native researcher/library operations may
  be used under the actual request and recorded locally as reported operations.
- **Hugging Face Daily Papers:** the existing configured `recommend-papers`
  aggregator already reads its public daily-paper metadata. It returns source
  candidates, not the shared submission envelope. Obtain full authoritative
  abstracts/translation before submitting; Daily Papers upvotes are not model
  likes or repository stars. This entry does not claim a new generic API executor.
- **X own account / Zhihu own account:** planned. The selected user's own reposts
  or bookmarks/collections are the intended scope. No other people's accounts,
  home timeline, automatic harvesting, account setup or payment is implemented by
  registering these descriptions. Follow the future provider's actual permissions,
  cost limits and acquisition contract before claiming integration.

A registered custom plugin supplies its own operation contract and connection hints.
The external agent reads `sources guide SOURCE_ID`, then discovers the actual native
tools and schemas. A legacy description may lack that contract; neither form grants
permission or proves a connection. The [plugin contract](recommendation-source-plugins.md)
owns those fields and lifecycle operations.

Each source entry contains an expandable recommendation-requirements list/editor;
agents query it with `recommendations requirements list --source-id SOURCE_ID`.
The [requirements contract](recommendation-requirements.md) owns source binding,
editing and versioned references. Source topics and notes below keep their separate
management role. Old unassigned requirements are not automatically assigned a source.

## Shared management and continuity

Source management context and operation records stay in the same selected pool:

```text
scholar-research recommendations --profile personal sources context alphaxiv
scholar-research recommendations --profile personal sources history --source-id alphaxiv
scholar-research recommendations --profile personal sources record-operation --help
```

Read existing context/history before changing an account or continuing another
agent's task. Context records explicit topics and notes with optimistic revision
checking. Use it for durable preferences, research interests and pending proposals;
not a copy of the remote library or undisclosed private chat memory. A proposal to
follow a researcher is not an executed follow.

After an authorized native operation, record its actual actor, source, action,
status, time, explanation and public evidence links through the shared CLI. The
operation ID is stable for retrying the same local receipt. Outcomes are
`proposed`, `reported_completed`, `reported_failed` or `unconfirmed`; the record
is marked `agent_reported`. A report does not certify remote truth or authorize
repeating an ambiguous write. Inspect current remote state when an operation may
have executed but its response was lost. Record uncertainty rather than turning
it into empty success, confirmed completion or a new implicit retry.

The external agent/harness remains responsible for orchestration and native-tool
permissions. The page displays common candidate results and source information;
it does not offer arbitrary RPC, commands, model configuration or account control.
No operation is scheduled merely by registering a source.

## Prepare and submit candidates

Domain/project recommendation agents keep their own task identity and selected
scope. alphaXiv supplies popular discovery alongside them. Record actual discovery
channels separately from producing agent and topic tags; deduplicate the verified
resource while preserving each real recommendation record. The complete asset
unit remains the smallest formal knowledge object after ingestion.

All agents use installed `recommendations schema` and `submit`, including complete
Chinese abstract translations, a clearly labeled sourced summary when no author
abstract exists, usable original/project/Blog links and actual raw measurements.
An opaque source ID or generated AI report is not bibliographic metadata or an
author's abstract. A local agent can verify missing platform objects/counts and
submit the verified links before explicit metric refresh; never guess values or
calculate a synthetic popularity score. Scientific analysis is a separate request.

Use the selected test profile and isolated state for development fixtures. Reading
or registering a catalog descriptor does not access the real source, and a
synthetic catalog test cannot prove installed/native access or human acceptance.
