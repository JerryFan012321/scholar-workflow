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
@click.argument("query", required=False)
def discover(query: str | None) -> None:
    """Discovery is a skill-layer capability, not a CLI command.

    Searching / resolving identifiers needs zotero-mcp (existence, semantic recall) and
    web metadata, which the CLI subprocess cannot reach. The host LLM does this via the
    `find-resource` skill. This command only signposts that; it performs no work."""
    raise InputError(
        "discovery is not a CLI operation — the CLI cannot reach zotero-mcp. "
        "Ask in-conversation instead (e.g. 'find world model papers'); the host LLM "
        "runs it via the find-resource skill.")


@main.command()
@click.argument("inputs", nargs=-1, required=True)
def apply(inputs: tuple[str, ...]) -> None:
    """Download paper PDFs to the inbox.

    Resolve inputs into a deterministic all-`create` plan (no existence check) and
    download each arXiv PDF to `paper_inbox`. Dedup and existence are decided by the
    host LLM via zotero-mcp before this runs. Never writes to Zotero — import into
    Zotero is done by the host LLM via zotero-mcp's write tools."""
    from scholar_workflow.resolver import resolve_many
    from scholar_workflow.state import StateStore
    from scholar_workflow.planning import generate_plan
    from scholar_workflow.workflows.paper import run_paper_import
    from scholar_workflow.config import load_config

    resources = resolve_many(list(inputs))
    if not resources:
        raise InputError("no resolvable inputs")
    config = load_config()
    store = StateStore(_state_db_path())
    try:
        plan = generate_plan(resources)
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
    adapter = ObsidianAdapter(Path(cfg.research_vault_root),
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
    adapter = ObsidianAdapter(Path(cfg.research_vault_root),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    stats = project_tree(tree, root, adapter, cfg.link_service.port)
    click.echo(json.dumps({"root": root, **stats}, ensure_ascii=False))


@main.command(name="project-literature-tree")
@click.option("--input", "input_file", type=click.File("r"), default="-",
              help="JSON with {root, doc}; default stdin. doc conforms to literature-tree.schema.json.")
@click.option("--dry-run", is_flag=True,
              help="Print the files that would be written (path/heading/body) as JSON; write nothing.")
def project_literature_tree_cmd(input_file, dry_run: bool) -> None:
    """Render a novelty tree (里程碑任务 → pipeline → 论文) as managed-block notes.

    Input (assembled by the host LLM per contracts/literature-tree.schema.json): {"root":
    "<vault-rel base dir>", "doc": {paper_list:[...], tree:{name, kind, ...}}}. The topic
    root note carries an inline Mermaid overview + the flat 全集 paper list; each concept
    note carries its novelty anchor + a MOC wikilink list / paper table. Content outside
    markers is preserved; re-running the same input is idempotent (INV4/INV18/INV22)."""
    from pathlib import Path
    from scholar_workflow.config import load_config
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.novelty_tree import plan_novelty_tree, project_novelty_tree

    payload = json.load(input_file)
    doc = payload.get("doc")
    if not doc or not (doc.get("tree") or {}).get("name"):
        raise InputError("input must contain a 'doc' with a non-empty 'tree.name'")
    root = payload.get("root") or "35-literature-tree"
    cfg = load_config()
    if dry_run:
        plan = plan_novelty_tree(doc, root, cfg.link_service.port)
        click.echo(json.dumps(
            {"root": root, "dry_run": True, "files": len(plan),
             "papers": sum(p["papers"] for p in plan), "plan": plan},
            ensure_ascii=False, indent=2))
        return
    adapter = ObsidianAdapter(Path(cfg.research_vault_root),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    stats = project_novelty_tree(doc, root, adapter, cfg.link_service.port)
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


@main.command(name="install-service")
@click.option("--load/--no-load", default=True,
              help="Load into launchd immediately (default: load).")
def install_service(load: bool) -> None:
    """Install a macOS LaunchAgent so serve-links auto-starts at login (KeepAlive).

    Writes ~/Library/LaunchAgents/com.scholar-workflow.link-service.plist pointing at
    this executable + `serve-links`, then bootstraps it. Idempotent: an existing agent
    is unloaded and replaced. macOS only."""
    import subprocess
    import sys
    from scholar_workflow.workflows.service import LABEL, plist_path, render_plist

    if sys.platform != "darwin":
        raise InputError("install-service is macOS-only (launchd)")
    executable = str(Path(sys.argv[0]).resolve())
    log_dir = str(Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)))
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    home_env = os.environ.get("SCHOLAR_WORKFLOW_HOME")
    dest = plist_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_plist(executable, log_dir, home_env), encoding="utf-8")
    if load:
        subprocess.run(["launchctl", "unload", str(dest)],
                       capture_output=True, check=False)
        subprocess.run(["launchctl", "load", str(dest)], check=True)
    click.echo(json.dumps({"label": LABEL, "plist": str(dest), "loaded": load},
                          ensure_ascii=False))


@main.command(name="env-init")
@click.option("--git-init/--no-git-init", default=True,
              help="Run `git init` in the records dir if not already a repo (default: yes). Never pushes.")
def env_init(git_init: bool) -> None:
    """Scaffold the personal env-records directory (path from config `env_records_root`).

    Lays down a uniform skeleton — gitignored real records (servers.yaml / apis.yaml),
    committed templates (*.example.yaml), a setup/ tree, README and .gitignore — then
    optionally `git init` (local only, never pushed). Idempotent: existing files are
    never overwritten, so real records survive re-runs. The plugin owns no private data;
    the directory location is the only input, taken from config."""
    import subprocess
    from scholar_workflow.config import load_config
    from scholar_workflow.workflows.env_setup import scaffold

    cfg = load_config()
    result = scaffold(cfg.env_records_root)
    git_done = False
    if git_init and not (result.root / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(result.root),
                       capture_output=True, check=True)
        git_done = True
    click.echo(json.dumps(
        {"root": str(result.root), "created": result.created,
         "skipped": result.skipped, "git_init": git_done},
        ensure_ascii=False, indent=2))


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
