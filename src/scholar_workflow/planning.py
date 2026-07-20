"""Action plan generation (always dry-run)."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta
from scholar_workflow.models import ActionPlan, ActionItem, Resource, ResourceKind
from scholar_workflow.dedup import check_existence, decide_operation


PLAN_TTL_HOURS = 24


def _input_digest(resources: list[Resource]) -> str:
    payload = json.dumps([r.model_dump(mode="json") for r in resources], sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def generate_plan(resources: list[Resource], config_version: str = "0",
                  state=None) -> ActionPlan:
    """Build an ActionPlan from resolved resources. Never writes externally.

    When `state` is given, the deterministic existence check sets each operation
    (create / skip / conflict); a fuzzy hit becomes a conflict, never an auto-merge.
    """
    actions: list[ActionItem] = []
    for res in resources:
        item = ActionItem(resource_id=res.resource_id, operation="create")

        if state is not None:
            op, conflicts = decide_operation(check_existence(res, state))
            item.operation = op
            item.conflicts = conflicts
        elif res.zotero.item_key:
            item.operation = "update"

        if res.kind == ResourceKind.PAPER:
            arxiv = res.identifiers.arxiv
            if arxiv:
                item.download_url = f"https://arxiv.org/pdf/{arxiv}"
            item.notion_projection = True

        if res.projections.obsidian_index:
            item.obsidian_index = res.projections.obsidian_index

        actions.append(item)

    return ActionPlan(
        input_digest=_input_digest(resources),
        config_version=config_version,
        expires_at=datetime.utcnow() + timedelta(hours=PLAN_TTL_HOURS),
        actions=actions,
    )


def validate_plan(plan: ActionPlan, resources: list[Resource]) -> list[str]:
    """Return list of validation errors; empty list means plan is executable."""
    errors: list[str] = []
    if plan.is_expired():
        errors.append(f"Plan {plan.plan_id} has expired")
    if not plan.is_approved():
        errors.append(f"Plan {plan.plan_id} has not been approved")
    if plan.input_digest != _input_digest(resources):
        errors.append("Input digest mismatch — resource list changed since plan was generated")
    return errors
