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
| landscape or technical/challenge map | `find-resource` → `build-literature-tree` |
| close reading of selected papers | `ingest-resource` → `analyze-paper` |
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
