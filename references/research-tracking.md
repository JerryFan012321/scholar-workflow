# Research channel and update contract

## Authorities

`SCHOLAR_WORKFLOW_HOME` selects the existing private configuration/state root.
Non-paper subscriptions live only in `research-sources.yml`; observations, source
validators, known external item digests and event dispositions live only in
`research/tracking.json`. Neither is a Knowledge Source/Field, Zotero mirror or
knowledge-body store. Existing `recommend.yml` paper feeds/S2 author watchlists are
unchanged and are not automatically copied. Assets exposes a derived overview.

One selected channel is a non-secret JSON object:

```json
{
  "channel_id": "sample-lab-blog",
  "name": "Research notes",
  "publisher": "Sample Lab",
  "publisher_kind": "lab",
  "kind": "rss",
  "url": "https://example.org/feed.xml",
  "enabled": true,
  "topics": ["world models"]
}
```

This is a synthetic format example, not a live feed to subscribe to. Publisher kinds
are `researcher`, `lab`, `company`, `team`, `other`; they are administrative metadata,
not a new public classification tree. Multiple channels can describe the same
publisher. A publisher label does not certify an official account or legal rights.
IDs remain stable when descriptions change. A URL belongs to one channel, not a
new record each time its label changes. Registration validates the complete result.

## Supported acquisition

| Kind | Selected URL | Observation |
|---|---|---|
| `rss` / `atom` | Public feed URL | Finite feed entries, stable GUID/ID or canonical item URL |
| `webpage` | One explicit public research/release page | Normalized readable body change; not a crawler |
| `github_releases` | `https://github.com/OWNER/REPO` | Public releases and revisions, all API pages |
| `hf_models` | `https://huggingface.co/ORG` | Public model-repository metadata and revisions, all API pages |

Use the registered publisher's actual endpoint; resolve uncertainty before writing.
Only public HTTPS is accepted. No URL credentials or secret query parameters,
private/loopback targets, private API tokens, downloaded weights, repository clones,
page script execution or secondary full-text acquisition. The network adapter
validates redirects and bounds response sizes, requests and pagination; unsafe,
malformed or incomplete acquisition is a visible failure. A finite feed is only
the visible feed window. API/page changes do not establish model capabilities.
Actual requests resolve and pin public origin addresses, preserving original Host,
TLS hostname/certificate verification and operator-configured HTTP/HTTPS proxy
routing. Mixed public/private DNS answers refuse. Proxy endpoints are trusted
operator routing configuration, not registered research origins. Unsupported proxy
schemes fail rather than silently connecting directly. A separately injected full
MockTransport is for isolated fixtures only; arbitrary real clients cannot bypass
the pinning boundary.
Webpage observation covers normalized text, not changes confined to images,
videos or other media. RSS2/Atom UTF-8 is supported; RDF/RSS1 and JavaScript-only
pages require a different supported endpoint, not a fabricated empty success.

## Local interfaces

Before using the new commands, resolve the actual installed launchers and compare
the loaded plugin manifest version with both `scholar-workflow --version` and
`scholar-research --version`. A missing command or mismatch is an installation gap,
not an empty subscription list. Use the normal package install/update procedure
from the same published runtime revision as the plugin; do not substitute a source
checkout, `PYTHONPATH` injection or a plugin-cache wrapper. Matching version labels
are necessary but do not prove an exact build: installed acceptance also records
the approved runtime revision and actual launcher/interpreter paths. Version and
help commands do not initialize configuration or make source requests.

```sh
scholar-workflow research sources list --format json
scholar-workflow assets list --kind research
scholar-workflow research sources register --spec channel.json --format json
scholar-workflow research sources register --spec changed-channel.json --expected-revision REVISION
scholar-workflow research updates --disposition unread --language zh
scholar-workflow research mark EVENT_ID --disposition selected
```

Writes read back the actual result. An identical registration is unchanged;
changing an existing record requires its current whole-registry revision. Pause
with the same ID and `enabled: false`; do not create another ID or delete history.
Reads never initialize a missing store. Invalid/unsafe stores refuse instead of
appearing empty. Event dispositions are `unread`, `read`, `selected`, `ignored`.
Selection creates no bibliography, owner, archive or successful-reading claim.

## Network interface

```sh
scholar-research check --channel CHANNEL_ID --language zh
scholar-research check --channel CHANNEL_ID --initial-mode report --format json
```

The installed package provides `scholar-research`. The plugin also ships the thin
`bin/track-research.py check` wrapper for an interpreter with that installed package.
Do not require a source repository or inject it into `PYTHONPATH` for installed use.
No invocation silently schedules later checks or requires a running Hub.

First success defaults to `baseline`: retain the currently visible IDs/digests
without presenting them as newly published. An explicitly requested `report` emits
`discovered` items. Subsequent unseen IDs produce `new`; changed digest/version
produces `updated`. Missing entries never imply deletion. Publisher dates, observed
time, last checked time and last successful check have different meanings.

An error leaves prior successful items/checkpoint intact and remains visible next
to successful channels. A first-ever 304 cannot establish a baseline. API
pagination must complete; a limit or failed later page refuses the whole channel's
observation, not successful earlier channels. Changed configuration invalidates
cached validators. Stale configuration/results refuse without silently relabelling
the observation. Inspect JSON diagnostics for machine codes; never print credentials
or raw network exception strings.

## Human result

In one selected language, show a source/check table followed by an update table:

| Observation time | Publisher / channel | Title and original source | Change | Disposition |
|---|---|---|---|---|
| Actual check time | Registered publisher/channel | Usable original link | New / initially discovered / content changed | Unread / read / selected, not archived / ignored |

Show disabled/failed channels and last successful check; state baseline/observed
window limits and avoid claiming completeness. Human events are newest-observed
first; durable history retains its original order. Escape source text as data, with no
active HTML, machine hashes or event IDs in ordinary prose. Content changes are
pending review, not scientific-progress endorsements. Retained event lists may be
filtered by disposition; the check result lists only events emitted by that check.

An explicit request to archive an item hands its source URL/version to the existing
ingest flow, which still verifies identity, rights, chosen Knowledge destination and
current provider state. The tracking layer does not bypass those checks. Related
announcements remain distinct documents; event grouping/model-family dossiers are
not inferred by title matching or claimed as implemented by channel registration.
