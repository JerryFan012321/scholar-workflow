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

## Steps

1. Confirm only the missing inputs that change the route: topic boundary, time window,
   desired artifact, and whether the user wants breadth or close reading. If the request
   already names an artifact or action, route directly without another scoping round.
2. When an ambiguous topic cannot be scoped from the request, a read-only, throwaway web
   reconnaissance is allowed. It must not download, ingest, or write files.
3. Dispatch only the owning skill or skills required by the confirmed artifact. Order them
   only where one product is an input to another.
4. Report each delegated product and its location. This skill writes nothing itself.

## Constraints

- Delegated skills own identity checks, acquisition, storage, rendering, and write gates;
  this router never reimplements or overrides them.
- An explicit tree request goes directly to `build-literature-tree` (INV22).
- Reconnaissance is read-only. Acquisition begins only in `ingest-resource` and follows
  the shared source and security policies.

## References

Load only when a delegated step reaches acquisition or a write.

- `${CLAUDE_PLUGIN_ROOT}/references/source-policy.md`
- `${CLAUDE_PLUGIN_ROOT}/references/security-policy.md`
