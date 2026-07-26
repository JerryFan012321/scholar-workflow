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
    """Check runtime dependencies (config paths). Zotero-mcp reachability is a
    skill-layer check (the CLI subprocess cannot reach MCP tools)."""
    from scholar_workflow.config import load_config
    from scholar_workflow.doctor import run_doctor

    report = run_doctor(load_config())
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False))
    else:
        for c in report["checks"]:
            click.echo(f"[{'ok' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
    if not report["ok"]:
        raise SystemExit(3)  # dependency not running (see AGENT.md exit codes)


@main.command()
@click.argument("query")
def discover(query: str) -> None:
    """Search and resolve paper identifiers."""
    raise NotImplementedError


@main.command()
@click.argument("inputs", nargs=-1, required=True)
def apply(inputs: tuple[str, ...]) -> None:
    """Download approved paper PDFs to the inbox.

    Resolve inputs into a deterministic all-`create` plan (no existence check) and
    download each arXiv PDF to `paper_inbox`. Dedup and existence are decided by the
    host LLM via zotero-mcp before this runs; call only after the user approves the
    import in-conversation. Never writes to Zotero — import into Zotero is done by
    the host LLM via zotero-mcp's approved write tools."""
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
        plan = approve_plan(generate_plan(resources))
        results = run_paper_import(plan, resources, config, store)
    finally:
        store.close()
    click.echo(json.dumps({"plan_id": plan.plan_id, "results": results},
                          ensure_ascii=False))


@main.command(name="project-obsidian")
@click.option("--input", "input_file", type=click.File("r"), default="-",
              help="JSON file with {index, heading, entries}; default stdin.")
def project_obsidian_cmd(input_file) -> None:
    """Write a managed-block index into the vault from Zotero-sourced JSON.

    Input (from the host LLM via zotero-mcp): {"index": "<rel path>", "heading":
    "<h1>", "entries": [{title, authors, year, venue, zotero_key, attachment_key,
    arxiv, doi, synced}, ...]}. Content outside the managed markers is preserved;
    re-running the same input is idempotent (GOALS INV4/INV18)."""
    from pathlib import Path
    from scholar_workflow.config import load_config
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.projection import project_obsidian

    payload = json.load(input_file)
    entries = payload.get("entries", [])
    cfg = load_config()
    index = payload.get("index") or "31-paper/index.md"
    heading = payload.get("heading") or "Papers"
    adapter = ObsidianAdapter(Path(cfg.vault_root),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    n = project_obsidian(entries, index, heading, adapter, cfg.link_service.port)
    click.echo(json.dumps({"index": index, "rows": n}, ensure_ascii=False))


@main.command(name="project-tree")
@click.option("--input", "input_file", type=click.File("r"), default="-",
              help="JSON with {root, tree}; default stdin.")
@click.option("--dry-run", is_flag=True,
              help="Print the files that would be written (path/heading/body) as JSON; write nothing.")
def project_tree_cmd(input_file, dry_run: bool) -> None:
    """Mirror a Zotero collection tree as a folder of managed-block notes (option C).

    Input (from the host LLM via zotero-mcp): {"root": "<vault-rel base dir>", "tree":
    {name, collection_key, papers:[...], children:[...]}}. Each node -> one file at
    <parent>/<name>.md; a node's block holds a MOC wikilink list (child collections)
    plus a 10-column paper table (direct papers). Content outside markers is preserved;
    re-running the same input is idempotent (INV4/INV18)."""
    from pathlib import Path
    from scholar_workflow.config import load_config
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.hierarchy import plan_tree, project_tree

    payload = json.load(input_file)
    tree = payload.get("tree")
    if not tree or not tree.get("name"):
        raise InputError("input must contain a non-empty 'tree' with a 'name'")
    root = payload.get("root") or "31-paper"
    cfg = load_config()
    if dry_run:
        plan = plan_tree(tree, root, cfg.link_service.port)
        click.echo(json.dumps(
            {"root": root, "dry_run": True, "files": len(plan),
             "papers": sum(p["papers"] for p in plan), "plan": plan},
            ensure_ascii=False, indent=2))
        return
    adapter = ObsidianAdapter(Path(cfg.vault_root),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    stats = project_tree(tree, root, adapter, cfg.link_service.port)
    click.echo(json.dumps({"root": root, **stats}, ensure_ascii=False))


@main.command(name="serve-links")
def serve_links() -> None:
    """Run the loopback PDF link service (foreground, blocks until Ctrl-C).

    Serves GET /open/paper/<attachment-key> as an inline PDF from the Zotero
    storage folder, so projection links open in a local browser (GOALS INV17).
    Read-only filesystem access; never reaches MCP."""
    import threading as _t
    from scholar_workflow.config import load_config
    from scholar_workflow.adapters.local_links import start_link_server

    cfg = load_config()
    server = start_link_server(cfg.link_service.port, cfg.link_service.storage_root)
    host, port = server.server_address
    click.echo(f"link-service on http://{host}:{port}  (storage: "
               f"{cfg.link_service.storage_root})  Ctrl-C to stop")
    try:
        _t.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


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
@click.option("--scope", multiple=True)
def audit(scope: tuple[str, ...]) -> None:
    """Check cross-system consistency and report drift."""
    raise NotImplementedError


@main.command()
@click.argument("job_id", required=False)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "md", "csv"]))
@click.option("--active", is_flag=True)
@click.option("--handoff", is_flag=True, help="Emit an AgentHandoff snapshot of active jobs (PreCompact).")
def report(job_id: str | None, fmt: str, active: bool, handoff: bool) -> None:
    """Retrieve a job report, or list active jobs with --active (read-only)."""
    from scholar_workflow.state import StateStore

    store = StateStore(_state_db_path())
    try:
        rows = store.active_jobs() if (active or handoff) else None
        if rows is None:
            if not job_id:
                raise InputError("provide a job_id or --active")
            job = store.get(job_id)
            if job is None:
                raise InputError(f"unknown job: {job_id}")
            rows = [job]
    finally:
        store.close()

    if handoff:
        click.echo(json.dumps(_handoff_snapshot(rows), ensure_ascii=False))
    else:
        click.echo(_format_rows(rows, fmt))


def _handoff_snapshot(rows: list[dict]) -> dict:
    """Build an AgentHandoff (contracts/handoff.schema.json) from active jobs."""
    from datetime import datetime, timezone
    return {
        "job_id": rows[0]["job_id"] if rows else "00000000-0000-0000-0000-000000000000",
        "plan_id": rows[0].get("plan_id") if rows else None,
        "from_agent": "precompact",
        "to_agent": "precompact",
        "last_success_state": rows[0]["state"] if rows else "received",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifacts": {"resource_ids": [r["resource_id"] for r in rows]},
    }


def _format_rows(rows: list[dict], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(rows, ensure_ascii=False, indent=2)
    cols = ["job_id", "resource_id", "state", "updated_at"]
    if fmt == "csv":
        lines = [",".join(cols)]
        lines += [",".join(str(r.get(c, "")) for c in cols) for r in rows]
        return "\n".join(lines)
    # md
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    return "\n".join(lines)
