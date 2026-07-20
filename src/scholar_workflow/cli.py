"""CLI entry point."""
from __future__ import annotations
import json
import os
from pathlib import Path
import click

from scholar_workflow.config import DEFAULT_HOME


class InputError(click.ClickException):
    """Bad user input — maps to exit code 2 (see AGENT.md CLI exit codes)."""
    exit_code = 2


def _state_db_path() -> Path:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    home.mkdir(parents=True, exist_ok=True)
    return home / "state.db"


@click.group()
@click.version_option()
def main() -> None:
    """Scholar Workflow — scholarly resource management CLI."""


@main.command()
@click.option("--json", "as_json", is_flag=True)
def doctor(as_json: bool) -> None:
    """Check runtime dependencies (Zotero, Obsidian, Bridge)."""
    raise NotImplementedError


@main.command()
@click.argument("query")
def discover(query: str) -> None:
    """Search and resolve paper identifiers."""
    raise NotImplementedError


@main.command()
@click.argument("identifier")
def resolve(identifier: str) -> None:
    """Normalize a single identifier and report its existence (read-only)."""
    from scholar_workflow.resolver import resolve_one
    from scholar_workflow.state import StateStore
    from scholar_workflow.dedup import check_existence

    if not identifier.strip():
        raise InputError("empty identifier")
    res = resolve_one(identifier)
    store = StateStore(_state_db_path())
    try:
        existence = check_existence(res, store)
    finally:
        store.close()
    click.echo(json.dumps({
        "resource": res.model_dump(mode="json"),
        "existence": {"match": existence.match.value,
                      "resource_id": existence.resource_id,
                      "zotero_item_key": existence.zotero_item_key,
                      "candidates": existence.candidates},
    }, ensure_ascii=False))


@main.command("plan")
@click.argument("inputs", nargs=-1, required=True)
def plan_import(inputs: tuple[str, ...]) -> None:
    """Generate an import action plan (dry-run, never writes)."""
    from scholar_workflow.resolver import resolve_many
    from scholar_workflow.state import StateStore
    from scholar_workflow.planning import generate_plan

    resources = resolve_many(list(inputs))
    if not resources:
        raise InputError("no resolvable inputs")
    store = StateStore(_state_db_path())
    try:
        plan = generate_plan(resources, state=store)
    finally:
        store.close()
    click.echo(plan.model_dump_json(indent=2))


@main.command()
@click.argument("inputs", nargs=-1, required=True)
def apply(inputs: tuple[str, ...]) -> None:
    """Execute an import: resolve, dedup, then write Zotero. Call only after the
    user has approved the plan in-conversation — this command performs the writes."""
    from scholar_workflow.resolver import resolve_many
    from scholar_workflow.state import StateStore
    from scholar_workflow.planning import generate_plan
    from scholar_workflow.approvals import approve_plan
    from scholar_workflow.workflows.paper import run_paper_import
    from scholar_workflow.config import load_config

    resources = resolve_many(list(inputs))
    if not resources:
        raise InputError("no resolvable inputs")
    config = load_config()
    store = StateStore(_state_db_path())
    try:
        plan = approve_plan(generate_plan(resources, state=store))
        results = run_paper_import(plan, resources, config, store)
    finally:
        store.close()
    click.echo(json.dumps({"plan_id": plan.plan_id, "results": results},
                          ensure_ascii=False))


@main.command()
@click.argument("job_id")
def resume(job_id: str) -> None:
    """Report a job's persisted state so it can be resumed (read-only)."""
    from scholar_workflow.state import StateStore

    store = StateStore(_state_db_path())
    try:
        job = store.get(job_id)
    finally:
        store.close()
    if job is None:
        raise InputError(f"unknown job: {job_id}")
    click.echo(json.dumps(job, ensure_ascii=False))


@main.command()
@click.argument("identifier")
def locate(identifier: str) -> None:
    """Check whether a resource already exists (read-only, exact + fuzzy recall)."""
    from scholar_workflow.resolver import resolve_one
    from scholar_workflow.state import StateStore
    from scholar_workflow.dedup import check_existence, Match

    if not identifier.strip():
        raise InputError("empty identifier")
    store = StateStore(_state_db_path())
    try:
        result = check_existence(resolve_one(identifier), store)
        click.echo(json.dumps({
            "match": result.match.value,
            "resource_id": result.resource_id,
            "zotero_item_key": result.zotero_item_key,
            "candidates": result.candidates,
        }, ensure_ascii=False))
    finally:
        store.close()


@main.command()
@click.option("--scope", multiple=True)
def audit(scope: tuple[str, ...]) -> None:
    """Check cross-system consistency and report drift."""
    raise NotImplementedError


@main.command()
@click.argument("job_id")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "md", "csv"]))
@click.option("--active", is_flag=True)
@click.option("--handoff", is_flag=True)
def report(job_id: str | None, fmt: str, active: bool, handoff: bool) -> None:
    """Retrieve job report."""
    raise NotImplementedError
