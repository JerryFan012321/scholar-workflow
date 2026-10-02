---
name: survey-topic
description: Route an open-ended research topic to the appropriate research skills after confirming the desired scope and artifact. Use for 'survey this topic', 'research this area', 'get me up to speed', '调研', '了解这个领域'. Not for an explicit paper lookup, literature tree, daily feed, import, or single-paper analysis.
---

# survey-topic

Thin router for broad research requests. It creates no persistent artifact.

## Route map

| Requested outcome | Route |
|---|---|
| current papers | `recommend-papers` |
| candidate list or known-paper lookup | `find-resource` |
| landscape or technical/challenge map | `build-literature-tree`; use `find-resource` only when the requested corpus is missing |
| close reading of selected papers | `analyze-paper` for already-ingested papers; use `ingest-resource` only when selected papers need an authorized import |
| author/lab tracking | `recommend-papers` watchlist |

## Observable result and routing boundary

- The resolved request states its topic boundary, time window, desired artifact, and
  breadth or close-reading scope insofar as these change the route. Ask only for missing
  route-changing inputs; an explicitly named artifact or action routes directly.
- Return the selected owning skill(s) and the location/status of each resulting product.
  This router creates no persistent file and does not perform the delegated skill's work.
- If the route truly depends on unfamiliar topic context, a throwaway web reconnaissance
  may inform the choice; it remains read-only and produces no library or Vault content.
- Sequence delegated skills only when one product is a required input to another.
  Reuse supplied or already resolved inputs. A route to a deliverable is not permission
  to discover a broader corpus, import papers, initialize a Field, or rerun an existing analysis.

## Constraints

- Delegated skills own identity checks, acquisition, storage, rendering, and write gates;
  this router never reimplements or overrides them.
- An explicit tree request goes directly to `build-literature-tree` (INV22).
- Reconnaissance is read-only. Acquisition begins only in `ingest-resource` and follows
  the shared source and security policies.

## References

The visible routing result follows `${CLAUDE_PLUGIN_ROOT}/references/human-presentation.md`.
Load only when a delegated step reaches acquisition or a write.

- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
