"""Approval gate: plan signing and verification."""
from __future__ import annotations
from datetime import datetime
from scholar_workflow.models import ActionPlan
from scholar_workflow.planning import validate_plan


def approve_plan(plan: ActionPlan) -> ActionPlan:
    """Mark plan as approved. Call only after user confirmation."""
    plan.approved_at = datetime.utcnow()
    return plan


def assert_executable(plan: ActionPlan, resources: list) -> None:
    """Raise if plan cannot be executed. Called at start of every apply()."""
    errors = validate_plan(plan, resources)
    if errors:
        raise PermissionError(
            "Plan cannot be executed:\n" + "\n".join(f"  - {e}" for e in errors)
        )
