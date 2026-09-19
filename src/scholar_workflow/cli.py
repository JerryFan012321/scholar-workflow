"""CLI entry point."""
from __future__ import annotations
import http.client
import json
import os
import re
import secrets
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import urlencode
import click

from scholar_workflow import __version__
from scholar_workflow.config import DEFAULT_HOME


class InputError(click.ClickException):
    """Bad user input — maps to exit code 2 (see AGENT.md CLI exit codes)."""
    exit_code = 2


class DependencyError(click.ClickException):
    """A required dependency isn't ready — maps to exit code 3."""
    exit_code = 3


class IdentityConflictError(click.ClickException):
    """Ambiguous exact identity — maps to exit code 5."""

    exit_code = 5


class PartialCompletionError(click.ClickException):
    """A recoverable write stopped mid-operation — maps to exit code 6."""

    exit_code = 6


class ExternalServiceError(click.ClickException):
    """A reachable external service rejected an operation — maps to exit code 8."""

    exit_code = 8


def _zotero_adapter():
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter

    return ZoteroLocalAdapter()


@contextmanager
def _open_zotero() -> Iterator[object]:
    from scholar_workflow.adapters.zotero_local import (
        ZoteroAuthorizationError,
        ZoteroLocalError,
        ZoteroLocalUnavailable,
    )

    try:
        with _zotero_adapter() as adapter:
            yield adapter
    except (ZoteroLocalUnavailable, ZoteroAuthorizationError) as exc:
        raise DependencyError(str(exc)) from None
    except ZoteroLocalError as exc:
        raise ExternalServiceError(str(exc)) from None
    except ValueError as exc:
        raise InputError(str(exc)) from None


def _load_cfg():
    """Load config for business commands, turning a missing config.yml into a clean
    exit-3 message (run `config init`) instead of a traceback."""
    from scholar_workflow.config import ConfigNotFound, load_config
    try:
        return load_config()
    except ConfigNotFound:
        raise DependencyError(
            "scholar-workflow is not configured yet. Run "
            "`scholar-workflow config init --research-vault-root PATH` first.") from None


def _state_db_path() -> Path:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    home.mkdir(parents=True, exist_ok=True)
    return home / "state.db"


def _hub_snapshot_path() -> Path:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    return home / "hub" / "catalog.json"


_HUB_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_CMUX_TIMEOUT_SECONDS = 5.0
_REQUIRED_HUB_CAPABILITY = "cmux-workspace-actions-v1"


def _validate_hub_instance(
    _ctx: click.Context,
    _param: click.Parameter,
    value: str | None,
) -> str | None:
    if value is None:
        return None
    if not _HUB_INSTANCE_RE.fullmatch(value):
        raise click.BadParameter(
            "must be a 16-128 character URL-safe opaque identifier"
        )
    return value


def _require_cmux_context() -> tuple[str, str]:
    workspace_id = os.environ.get("CMUX_WORKSPACE_ID", "")
    socket_path = os.environ.get("CMUX_SOCKET_PATH", "")
    values_are_clean = all(
        value == value.strip()
        and len(value) <= 4096
        and not any(ord(char) < 32 for char in value)
        for value in (workspace_id, socket_path)
    )
    if not workspace_id or not socket_path or not values_are_clean:
        raise DependencyError(
            "open-hub must run inside a cmux workspace with "
            "CMUX_WORKSPACE_ID and CMUX_SOCKET_PATH available"
        )
    return workspace_id, socket_path


def _probe_hub_health(port: int) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1.5)
    try:
        connection.request("GET", "/api/v1/health")
        response = connection.getresponse()
        body = response.read(4097)
    except OSError:
        raise DependencyError(
            f"Research Hub is not running at http://127.0.0.1:{port}. "
            "Start it explicitly with `scholar-workflow serve-hub`."
        ) from None
    except http.client.HTTPException as exc:
        raise ExternalServiceError(f"Research Hub health probe failed: {exc}") from None
    finally:
        connection.close()
    if response.status != 200:
        raise ExternalServiceError(
            f"Research Hub health probe returned HTTP {response.status}"
        )
    if len(body) > 4096:
        raise ExternalServiceError("Research Hub health response was unexpectedly large")
    try:
        payload = json.loads(body)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        raise ExternalServiceError("Research Hub health response was not valid JSON") from None
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise ExternalServiceError("Research Hub health response did not report status=ok")
    capabilities = payload.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or _REQUIRED_HUB_CAPABILITY not in capabilities
    ):
        raise DependencyError(
            "Research Hub is running but does not support cmux workspace actions. "
            "Restart it with the current `scholar-workflow serve-hub`."
        )


def _resolve_cmux_executable() -> Path:
    """Reuse the launcher's canonical config/PATH/app-bundle resolution order."""
    from scholar_workflow.hub.actions import CmuxLauncher

    return CmuxLauncher(start_if_needed=False)._resolve_executable()


def _cmux_child_env(workspace_id: str, socket_path: str) -> dict[str, str]:
    allowed = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["CMUX_WORKSPACE_ID"] = workspace_id
    env["CMUX_SOCKET_PATH"] = socket_path
    return env


def _cmux_codex_working_directory() -> Path | None:
    """Enable Hub Codex only for a server launched from a real cmux terminal."""
    if not os.environ.get("CMUX_WORKSPACE_ID") or not os.environ.get("CMUX_SOCKET_PATH"):
        return None
    working_directory = Path.cwd().resolve()
    if working_directory == Path(working_directory.anchor) or not working_directory.is_dir():
        return None
    return working_directory


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Scholar Workflow — scholarly resource management CLI."""


@main.command()
@click.option("--json", "as_json", is_flag=True)
def doctor(as_json: bool) -> None:
    """Check runtime paths and report Zotero Local API availability as advisory."""
    from scholar_workflow.config import ConfigNotFound, config_path, load_config
    from scholar_workflow.doctor import run_doctor

    try:
        cfg = load_config()
    except ConfigNotFound:
        detail = (f"no config.yml at {config_path()} — run "
                  f"`scholar-workflow config init --research-vault-root PATH`")
        report = {"ok": False, "configured": False,
                  "checks": [{"name": "config", "ok": False, "detail": detail}]}
        if as_json:
            click.echo(json.dumps(report, ensure_ascii=False))
        else:
            click.echo(f"[FAIL] config: {detail}")
        raise SystemExit(3)

    report = run_doctor(cfg)
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False))
    else:
        for c in report["checks"]:
            click.echo(f"[{'ok' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
        for a in report.get("advisories", []):
            scope = a.get("scope", "?")
            click.echo(
                f"[{'ok' if a['ok'] else 'warn'}] {a['name']} ({scope}): {a['detail']}"
            )
    if not report["ok"]:
        raise SystemExit(3)  # dependency not running (see AGENT.md exit codes)


@main.group()
def zotero() -> None:
    """Read and write Zotero through its loopback-only Local API."""


@zotero.command(name="probe")
def zotero_probe_cmd() -> None:
    """Check that Zotero's Local API is enabled and reachable."""
    with _open_zotero() as adapter:
        server = adapter.probe()
    click.echo(
        json.dumps(
            {
                "ok": True,
                "api_version": server.api_version,
                "schema_version": server.schema_version,
            },
            ensure_ascii=False,
        )
    )


@zotero.command(name="authorize")
def zotero_authorize_cmd() -> None:
    """Ask Zotero for write access and save remembered access in Keychain."""
    with _open_zotero() as adapter:
        authorization = adapter.authorize()
    click.echo(
        json.dumps(
            {"authorized": True, "remembered": authorization.remember},
            ensure_ascii=False,
        )
    )


@zotero.command(name="search")
@click.argument("query")
@click.option("--fulltext", is_flag=True, help="Search all indexed fields and full text.")
@click.option("--limit", type=click.IntRange(1, 100), default=50, show_default=True)
def zotero_search_cmd(query: str, fulltext: bool, limit: int) -> None:
    """Quick-search the local Zotero library."""
    qmode = "everything" if fulltext else "titleCreatorYear"
    with _open_zotero() as adapter:
        items = adapter.search_items(query, qmode=qmode, limit=limit)
    click.echo(json.dumps({"items": items}, ensure_ascii=False))


@zotero.command(name="get")
@click.argument("item_key")
@click.option("--children", is_flag=True, help="Include child notes and attachments.")
def zotero_get_cmd(item_key: str, children: bool) -> None:
    """Read one Zotero item by key."""
    with _open_zotero() as adapter:
        payload: dict[str, object] = {"item": adapter.get_item(item_key)}
        if children:
            payload["children"] = adapter.get_children(item_key)
    click.echo(json.dumps(payload, ensure_ascii=False))


@zotero.command(name="fulltext")
@click.argument("attachment_key")
def zotero_fulltext_cmd(attachment_key: str) -> None:
    """Read Zotero's indexed full text for one attachment."""
    with _open_zotero() as adapter:
        payload = adapter.get_fulltext(attachment_key)
    click.echo(json.dumps(payload, ensure_ascii=False))


@zotero.command(name="collections")
@click.option("--limit", type=click.IntRange(min=1), help="Optional result cap.")
def zotero_collections_cmd(limit: int | None) -> None:
    """List local Zotero collections."""
    with _open_zotero() as adapter:
        collections = adapter.get_collections(limit=limit)
    click.echo(json.dumps({"collections": collections}, ensure_ascii=False))


@zotero.command(name="collection-items")
@click.argument("collection_key")
@click.option("--limit", type=click.IntRange(min=1), help="Optional result cap.")
def zotero_collection_items_cmd(collection_key: str, limit: int | None) -> None:
    """List top-level items in one Zotero collection."""
    with _open_zotero() as adapter:
        items = adapter.get_collection_items(collection_key, limit=limit)
    click.echo(json.dumps({"items": items}, ensure_ascii=False))


@zotero.command(name="update")
@click.argument("item_key")
@click.option(
    "--input",
    "input_file",
    type=click.File("r"),
    default="-",
    help="JSON with non-empty changes and the current item version; default stdin.",
)
def zotero_update_cmd(item_key: str, input_file) -> None:
    """Patch metadata using optimistic concurrency."""
    protected = {"itemType", "key", "version", "library", "links", "meta", "collections"}
    try:
        payload = json.load(input_file)
        changes = payload["changes"]
        version = payload["version"]
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must be a non-empty object")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError("version must be an integer from `zotero get`")
        forbidden = sorted(protected.intersection(changes))
        if forbidden:
            raise ValueError(f"protected fields cannot be patched: {', '.join(forbidden)}")
        empty_values = (None, "", [], {})
        if any(value in empty_values for value in changes.values()):
            raise ValueError("empty replacement values are not supported")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid Zotero update input: {exc}") from None
    with _open_zotero() as adapter:
        adapter.update_item(item_key, changes, version=version)
    click.echo(json.dumps({"updated": True, "item_key": item_key}, ensure_ascii=False))


@zotero.command(name="ingest")
@click.option(
    "--input",
    "input_file",
    type=click.File("r"),
    default="-",
    help="JSON with metadata, optional collection_keys, and optional pdf_path; default stdin.",
)
def zotero_ingest_cmd(input_file) -> None:
    """Deduplicate, create, and optionally attach a PDF to a Zotero item."""
    from scholar_workflow.workflows.zotero import (
        ZoteroIdentityConflict,
        ZoteroPartialCompletion,
        ingest_item,
    )

    try:
        payload = json.load(input_file)
        metadata = payload["metadata"]
        collection_keys = payload.get("collection_keys") or []
        pdf_path = Path(payload["pdf_path"]).expanduser() if payload.get("pdf_path") else None
        if not isinstance(metadata, dict) or not isinstance(collection_keys, list):
            raise ValueError("metadata must be an object and collection_keys must be a list")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InputError(f"invalid Zotero ingest input: {exc}") from None
    try:
        with _open_zotero() as adapter:
            result = ingest_item(
                adapter,
                metadata=metadata,
                collection_keys=collection_keys,
                pdf_path=pdf_path,
            )
    except ZoteroIdentityConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    except ZoteroPartialCompletion as exc:
        raise PartialCompletionError(str(exc)) from None
    except ValueError as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False))


@main.group()
def config() -> None:
    """Inspect and edit config.yml (non-secret settings; secrets stay in env vars)."""


@config.command(name="init")
@click.option("--research-vault-root", "vault", required=True,
              help="Absolute path to the Obsidian research vault (required).")
@click.argument("extras", nargs=-1)
def config_init(vault: str, extras: tuple[str, ...]) -> None:
    """Create config.yml with the required vault + any KEY=VALUE extras (dotted keys ok).

    Writes only version + the values you name — never a full dump of defaults. Idempotent:
    an identical re-init is a no-op; a differing existing file is refused (edit with
    `config set`)."""
    from scholar_workflow.config import ConfigError, init_config

    extra: dict[str, str] = {}
    for pair in extras:
        if "=" not in pair:
            raise InputError(f"extras must be KEY=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        extra[k.strip()] = v.strip()
    try:
        path = init_config(vault, extra)
    except ConfigError as e:
        raise InputError(str(e)) from None
    except Exception as e:  # pydantic ValidationError -> clean exit 2
        raise InputError(str(e)) from None
    click.echo(json.dumps({"config": str(path)}, ensure_ascii=False))


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set one dotted KEY (e.g. notion.enabled) to VALUE, preserving comments."""
    from scholar_workflow.config import ConfigError, ConfigNotFound, set_config_value

    try:
        coerced = set_config_value(key, value)
    except ConfigNotFound:
        raise InputError(
            "no config.yml yet — run "
            "`scholar-workflow config init --research-vault-root PATH` first.") from None
    except ConfigError as e:
        raise InputError(str(e)) from None
    except Exception as e:  # pydantic ValidationError -> clean exit 2
        raise InputError(str(e)) from None
    click.echo(json.dumps({key: coerced}, ensure_ascii=False, default=str))


@config.command(name="show")
@click.option("--raw", is_flag=True, help="Print the raw config.yml text as stored.")
def config_show(raw: bool) -> None:
    """Print the effective validated config (JSON), or --raw for the file as written."""
    from scholar_workflow.config import config_path

    if raw:
        p = config_path()
        if not p.exists():
            raise DependencyError(f"no config.yml at {p} — run `config init` first.")
        click.echo(p.read_text())
        return
    cfg = _load_cfg()
    click.echo(cfg.model_dump_json(indent=2))


@config.command(name="get")
@click.argument("key")
def config_get(key: str) -> None:
    """Print the effective validated value of one dotted KEY."""
    cfg = _load_cfg()
    node: object = cfg
    for part in key.split("."):
        if not hasattr(node, part):
            raise InputError(f"Unknown config key: {key!r}")
        node = getattr(node, part)
    click.echo(json.dumps(node, ensure_ascii=False, default=str))


@config.command(name="path")
def config_path_cmd() -> None:
    """Print config.yml's path (whether or not it exists yet)."""
    from scholar_workflow.config import config_path
    click.echo(str(config_path()))


@main.command()
@click.argument("query", required=False)
def discover(query: str | None) -> None:
    """Quick-search the local library; broader discovery stays in find-resource."""
    if not query:
        raise InputError("a discovery query is required")
    with _open_zotero() as adapter:
        items = adapter.search_items(query, qmode="everything", limit=50)
    click.echo(json.dumps({"items": items}, ensure_ascii=False))


@main.command()
@click.argument("inputs", nargs=-1, required=True)
def apply(inputs: tuple[str, ...]) -> None:
    """Download paper PDFs to the inbox.

    Resolve inputs into a deterministic download plan and download each arXiv PDF to
    `paper_inbox`. Run a Local API identity check before this command, then pass the
    downloaded path to `zotero ingest`. This command itself never writes to Zotero."""
    from scholar_workflow.resolver import resolve_many
    from scholar_workflow.state import StateStore
    from scholar_workflow.planning import generate_plan
    from scholar_workflow.workflows.paper import run_paper_import

    resources = resolve_many(list(inputs))
    if not resources:
        raise InputError("no resolvable inputs")
    config = _load_cfg()
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

    Input (assembled from Zotero Local API data): {"index": "<rel path>", "heading":
    "<h1>", "entries": [{title, authors, year, venue, zotero_key, attachment_key,
    arxiv, doi, synced}, ...]}. Content outside the managed markers is preserved;
    re-running the same input is idempotent (GOALS INV4/INV18)."""
    from pathlib import Path
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.projection import project_obsidian

    payload = json.load(input_file)
    entries = payload.get("entries", [])
    cfg = _load_cfg()
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

    Input (assembled from Zotero Local API data): {"root": "<vault-rel base dir>", "tree":
    {name, collection_key, papers:[...], children:[...]}}. Each node -> one file at
    <parent>/<name>.md; a node's block holds a MOC wikilink list (child collections)
    plus a 10-column paper table (direct papers). Content outside markers is preserved;
    re-running the same input is idempotent (INV4/INV18)."""
    from pathlib import Path
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.hierarchy import plan_tree, project_tree

    payload = json.load(input_file)
    tree = payload.get("tree")
    if not tree or not tree.get("name"):
        raise InputError("input must contain a non-empty 'tree' with a 'name'")
    root = payload.get("root") or "31-paper"
    cfg = _load_cfg()
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
              help="JSON with {root, filename, doc, paperlist_only?}; default stdin. doc conforms to literature-tree.schema.json.")
@click.option("--dry-run", is_flag=True,
              help="Print the files that would be written (path/heading/body) as JSON; write nothing.")
def project_literature_tree_cmd(input_file, dry_run: bool) -> None:
    """Render a novelty tree (里程碑任务 → pipeline → 论文) as a single managed-block note,
    or the flat 01-Paperlist.md ledger.

    Input (assembled by the host LLM per contracts/literature-tree.schema.json):
      {"root": "<topic folder, vault-rel>", "filename": "02-<topic>文献树.md",
       "doc": {paper_list:[...], tree:{name, kind, ...}}}
    `root` defaults to the doc's `topic` (the topic folder name), else '35-literature-tree'.
    One tree = one note: an inline Mermaid overview + nested task(##)/pipeline(###) sections,
    each with its novelty anchor, optional 内容简介, and a 论文列表 subpaperlist. Pass
    "paperlist_only": true to (re)write 01-Paperlist.md (the flat 全集 ledger) instead;
    `filename` then defaults to 01-Paperlist.md. Content outside markers is preserved;
    re-running the same input is idempotent (INV4/INV18/INV22)."""
    from pathlib import Path
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.novelty_tree import (
        plan_novelty_tree, project_novelty_tree, plan_paperlist, project_paperlist,
    )

    payload = json.load(input_file)
    doc = payload.get("doc")
    if not doc or not (doc.get("tree") or {}).get("name"):
        raise InputError("input must contain a 'doc' with a non-empty 'tree.name'")
    paperlist_only = bool(payload.get("paperlist_only"))
    root = payload.get("root") or doc.get("topic") or "35-literature-tree"
    cfg = _load_cfg()
    port = cfg.link_service.port

    if paperlist_only:
        fname = payload.get("filename") or "01-Paperlist.md"
        planner = lambda: plan_paperlist(doc, root, port, fname)
        applier = lambda ad: project_paperlist(doc, root, ad, port, fname)
    else:
        fname = payload.get("filename")
        if not fname:
            raise InputError("a tree render needs 'filename' (e.g. '02-<topic>文献树.md')")
        planner = lambda: plan_novelty_tree(doc, root, port, fname)
        applier = lambda ad: project_novelty_tree(doc, root, ad, port, fname)

    if dry_run:
        plan = planner()
        click.echo(json.dumps(
            {"root": root, "filename": fname, "dry_run": True, "files": len(plan),
             "papers": sum(p["papers"] for p in plan), "plan": plan},
            ensure_ascii=False, indent=2))
        return
    adapter = ObsidianAdapter(Path(cfg.research_vault_root),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    stats = applier(adapter)
    from scholar_workflow.hub.catalog import CatalogSnapshotStore
    from scholar_workflow.hub.links import LinkedCatalogProvider, ProjectionLinkStore
    from scholar_workflow.workflows.hub_projection import (
        build_topic_catalog_patch,
        merge_catalog_patch,
    )

    store = CatalogSnapshotStore(_hub_snapshot_path())
    patch = build_topic_catalog_patch(
        doc,
        root,
        port,
        fname,
        paperlist_only=paperlist_only,
    )
    catalog = merge_catalog_patch(store.load(), patch)
    store.save(catalog)
    click.echo(json.dumps(
        {"root": root, "filename": fname, **stats, "hub_revision": catalog.revision},
        ensure_ascii=False,
    ))


@main.command(name="serve-links")
def serve_links() -> None:
    """Compatibility name for the unified local Hub service."""
    _serve_hub_foreground()


@main.command(name="serve-hub")
def serve_hub() -> None:
    """Run the local research Hub (foreground, blocks until Ctrl-C)."""
    _serve_hub_foreground()


@main.command(name="open-hub")
@click.option(
    "--instance",
    callback=_validate_hub_instance,
    help="Optional URL-safe opaque id for this Hub browser instance.",
)
def open_hub(instance: str | None) -> None:
    """Open the running research Hub in the current cmux workspace."""
    from scholar_workflow.hub.actions import CmuxUnavailable

    workspace_id, socket_path = _require_cmux_context()
    cfg = _load_cfg()
    port = cfg.link_service.port
    instance_id = instance or f"hub_{secrets.token_urlsafe(18)}"
    url = f"http://127.0.0.1:{port}/hub/?{urlencode({'instance': instance_id})}"

    _probe_hub_health(port)
    try:
        executable = _resolve_cmux_executable()
    except CmuxUnavailable as exc:
        raise DependencyError(str(exc)) from None

    argv = [
        str(executable),
        "open",
        url,
        "--workspace",
        workspace_id,
        "--focus",
        "true",
    ]
    try:
        result = subprocess.run(
            argv,
            shell=False,
            timeout=_CMUX_TIMEOUT_SECONDS,
            env=_cmux_child_env(workspace_id, socket_path),
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExternalServiceError(
            f"cmux did not respond within {_CMUX_TIMEOUT_SECONDS:g} seconds"
        ) from None
    except OSError as exc:
        raise DependencyError(f"Could not execute cmux: {exc}") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise ExternalServiceError(
            f"cmux could not open the Hub: "
            f"{detail or f'exit status {result.returncode}'}"
        )
    click.echo("Opened Scholar Hub in the current cmux workspace.")


def _serve_hub_foreground() -> None:
    """Serve the Web Hub and legacy PDF URLs on the same loopback listener.

    Serves GET /open/paper/<attachment-key> as an inline PDF from the Zotero
    storage folder and the human-facing Hub at /hub/. Explicit Hub editor saves
    are confined to registered Vault artifacts; never reaches MCP."""
    import threading as _t
    from scholar_workflow.hub.server import start_hub_server

    cfg = _load_cfg()
    server = start_hub_server(
        port=cfg.link_service.port,
        storage_root=cfg.link_service.storage_root,
        vault_root=cfg.research_vault_root,
        codex_working_directory=_cmux_codex_working_directory(),
    )
    host, port = server.server_address
    click.echo(
        f"research-hub on http://{host}:{port}/hub/  "
        f"(storage: {cfg.link_service.storage_root})  Ctrl-C to stop"
    )
    try:
        _t.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


@main.command(name="install-service")
@click.option("--load/--no-load", default=True,
              help="Load into launchd immediately (default: load).")
def install_service(load: bool) -> None:
    """Install a macOS LaunchAgent so the Hub auto-starts at login (KeepAlive).

    Writes ~/Library/LaunchAgents/com.scholar-workflow.link-service.plist pointing at
    this executable + the compatible `serve-links` entry point, then bootstraps it.
    Idempotent: an existing agent is unloaded and replaced. macOS only."""
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
    from scholar_workflow.workflows.env_setup import scaffold

    cfg = _load_cfg()
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
    """Print a job's persisted state (read-only). Does not resume execution."""
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
@click.argument("job_id", required=False)
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "md", "csv"]))
@click.option("--active", is_flag=True)
@click.option("--handoff", is_flag=True, help="Emit a PreCompactSnapshot of active jobs (PreCompact hook).")
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
    """Build a PreCompactSnapshot (contracts/handoff.schema.json) from active jobs."""
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
