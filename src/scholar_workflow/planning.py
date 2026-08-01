"""Action plan generation (always dry-run)."""
from __future__ import annotations
from scholar_workflow.models import ActionPlan, ActionItem, Resource, ResourceKind


def generate_plan(resources: list[Resource]) -> ActionPlan:
    """Build an ActionPlan from resolved resources. Never writes externally.

    Deterministic and offline: every resource becomes a `create` action. Existence
    and dedup are decided by the host LLM via zotero-mcp before this runs, so the CLI
    plan carries no Zotero-derived operation.
    """
    actions: list[ActionItem] = []
    for res in resources:
        item = ActionItem(resource_id=res.resource_id, operation="create")

        if res.kind == ResourceKind.PAPER:
            arxiv = res.identifiers.arxiv
            if arxiv:
                item.download_url = f"https://arxiv.org/pdf/{arxiv}"
            item.notion_projection = True

        if res.projections.obsidian_index:
            item.obsidian_index = res.projections.obsidian_index

        actions.append(item)

    return ActionPlan(actions=actions)
