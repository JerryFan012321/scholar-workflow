"""CLI entry point."""
from __future__ import annotations
import click


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
@click.argument("input_path")
def resolve(input_path: str) -> None:
    """Normalize and look up a single resource identifier."""
    raise NotImplementedError


@main.command("plan")
@click.argument("input_path")
def plan_import(input_path: str) -> None:
    """Generate an import action plan (dry-run, never writes)."""
    raise NotImplementedError


@main.command()
@click.argument("plan_id")
def apply(plan_id: str) -> None:
    """Execute an approved action plan."""
    raise NotImplementedError


@main.command()
@click.argument("job_id")
def resume(job_id: str) -> None:
    """Resume a partially completed job."""
    raise NotImplementedError


@main.command()
@click.argument("identifier")
def locate(identifier: str) -> None:
    """Locate a resource and return its local path."""
    raise NotImplementedError


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
