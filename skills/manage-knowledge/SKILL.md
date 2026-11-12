---
name: manage-knowledge
description: Begin knowledge management from a selected Zotero receiving collection, inspect received metadata and human instructions, and organize the next authorized asset-unit operation. Use for 'organize received knowledge', 'process my knowledge inbox', '整理待整理条目', '处理知识收件箱'. Not recommendation discovery, a full paper import, an explicitly requested single-paper analysis or a literature-tree-only request.
---

# manage-knowledge

Before reading the receiving queue, follow [Zotero intake](../../references/zotero-intake.md).
Read the configured queue with `scholar-research recommendations --profile personal
intake entries --limit 50`, using the user's actual pool. This returns Zotero items
and child notes through Local API without fetching originals or reading project background.

Preserve the complete [asset-unit boundary](../../references/asset-units.md). Report
each selected item's Zotero identity, the person's exact instructions, available
sources/assets, the requested management action and missing prerequisites. A
metadata receipt alone is not a completed knowledge unit or analysis.

For the selected next operation, load only the owning installed Skill:
[ingest-resource](../ingest-resource/SKILL.md) for original acquisition/registration,
[analyze-paper](../analyze-paper/SKILL.md) for an analysis pair,
[export-annotations](../export-annotations/SKILL.md) for formal annotations,
[build-literature-tree](../build-literature-tree/SKILL.md) for topic organization,
or [organize-project](../organize-project/SKILL.md) for project presentation. Their accepted output formats and
write boundaries remain required. Unspecified ownership or conflicting identities
are explicit gaps; preserve existing human files and atomic units.

Expand project background only for an authorized task that needs it, through the
[project-task context entry](../../references/recommendation-context.md). Central
management does not read all project contexts by default. The external harness owns
execution and scheduling; this Skill does not create a worker, model or dashboard.

Reading the queue never authorizes deleting items/memberships or replacing notes.
Report metadata reception, original acquisition, registration, analysis and human
assessment separately. Keep original files out of the recommendation intake operation.
