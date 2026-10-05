"""CLI entry point."""
from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import stat
import subprocess
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
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


class SafetyRefusalError(click.ClickException):
    """A filesystem or authorization boundary rejected the operation."""

    exit_code = 7


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
            "`scholar-workflow config init` first.") from None


def _require_legacy_vault(cfg) -> Path:
    """Resolve the pre-v3 singleton only for commands that still require it."""
    root = cfg.research_vault_root
    if root is None:
        raise DependencyError(
            "This legacy projection command requires `research_vault_root`. "
            "Set the migration candidate with `scholar-workflow config set "
            "research_vault_root PATH`; v3 Hub Fields use registered Sources instead."
        )
    path = Path(root)
    if not path.is_dir():
        raise DependencyError(
            f"Configured research_vault_root is not an accessible directory: {path}"
        )
    return path


def _state_db_path() -> Path:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    home.mkdir(parents=True, exist_ok=True)
    return home / "state.db"


def _hub_snapshot_path() -> Path:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    return home / "hub" / "catalog.json"


def _analysis_state_paths() -> tuple[Path, Path]:
    home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)) / "analysis"
    return home / "analysis.db", home / "stage"


_HUB_INSTANCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_CMUX_TIMEOUT_SECONDS = 5.0


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


def _optional_cmux_context() -> tuple[str, str] | None:
    """Return a clean cmux destination context, or None outside cmux.

    A partial or malformed environment is not accepted as a destination, but it
    also does not make the Hub globally unusable.
    """
    workspace_id = os.environ.get("CMUX_WORKSPACE_ID", "")
    socket_path = os.environ.get("CMUX_SOCKET_PATH", "")
    if not workspace_id and not socket_path:
        return None
    values = (workspace_id, socket_path)
    values_are_clean = all(
        value
        and value == value.strip()
        and len(value) <= 4096
        and not any(ord(char) < 32 for char in value)
        for value in values
    )
    if not values_are_clean:
        return None
    return workspace_id, socket_path


def _destination_capability_advertised(payload: dict[str, object] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    capabilities = payload.get("capabilities")
    names = {
        "cmux-destinations-v1",
        "cmux-destination-v1",
        "destination-routing-v1",
    }
    if isinstance(capabilities, list):
        return bool(names.intersection(str(item) for item in capabilities))
    if isinstance(capabilities, dict):
        return any(
            bool(capabilities.get(name))
            for name in names
        )
    return False


def _register_default_destination(
    port: int,
    instance_token: str,
    workspace_id: str,
) -> bool:
    """Register cmux only as this browser session's default opening place.

    The CLI first obtains the normal loopback session token.  The workspace ID
    never enters the Hub URL and this call grants no filesystem capability.
    """
    from scholar_workflow.hub.lifecycle import probe_health

    health = probe_health(port)
    origin = f"http://127.0.0.1:{port}"
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request("GET", "/api/v1/session")
        response = connection.getresponse()
        session_body = response.read(65537)
        session_status = response.status
    except (OSError, http.client.HTTPException) as exc:
        raise ExternalServiceError(
            f"Could not obtain Hub browser session: {exc}"
        ) from None
    finally:
        connection.close()
    if session_status != 200 or len(session_body) > 65536:
        raise ExternalServiceError(
            f"Hub browser session request returned HTTP {session_status}"
        )
    try:
        session_payload = json.loads(session_body)
        csrf_token = session_payload["csrf_token"]
    except (TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise ExternalServiceError("Hub browser session response was invalid") from None
    if not isinstance(csrf_token, str) or not csrf_token:
        raise ExternalServiceError("Hub browser session token was missing")

    encoded = json.dumps({"workspace_id": workspace_id}).encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    try:
        connection.request(
            "POST",
            "/api/v3/destinations/default",
            body=encoded,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(encoded)),
                "Origin": origin,
                "X-Scholar-Hub-Token": csrf_token,
                "X-Scholar-Hub-Instance": instance_token,
            },
        )
        response = connection.getresponse()
        body = response.read(65537)
        status_code = response.status
    except (OSError, http.client.HTTPException) as exc:
        raise ExternalServiceError(
            f"Could not register the cmux destination: {exc}"
        ) from None
    finally:
        connection.close()
    if status_code == 200:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ExternalServiceError(
                "Hub destination response was not valid JSON"
            ) from None
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise ExternalServiceError("Hub rejected the default cmux destination")
        return True
    if status_code in {404, 405, 501} and not _destination_capability_advertised(health):
        return False
    detail = body.decode("utf-8", errors="replace").strip()[:500]
    raise ExternalServiceError(
        f"Hub destination registration returned HTTP {status_code}"
        f"{f': {detail}' if detail else ''}"
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


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Project context, readable knowledge, and reproducible research records."""


@main.group(name="project")
def project_commands() -> None:
    """Organize explicit project material without a Hub or tool execution."""


@project_commands.command(name="context-template")
@click.option(
    "--project-root", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--language", type=click.Choice(["en", "zh"]), default="en", show_default=True)
def project_context_template(project_root: Path, language: str) -> None:
    """Print an editable template; do not create or modify project files."""
    from scholar_workflow.project.layout import load_project_layout

    try:
        layout = load_project_layout(project_root)
    except ValueError as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps({
        "schema_version": 1,
        "project_id": layout.project_id,
        "title": project_root.name,
        "summary": "说明研究目标与方法。" if language == "zh" else "Describe the research goal and approach.",
        "language": language,
        "entries": [],
    }, ensure_ascii=False, indent=2))


@project_commands.command(name="validate-context")
@click.option(
    "--project-root", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def project_validate_context(project_root: Path) -> None:
    """Validate one explicit context inventory, not external source availability."""
    from scholar_workflow.project.context import load_project_context

    try:
        context = load_project_context(project_root)
    except ValueError as exc:
        raise InputError(str(exc)) from None
    if context.language == "zh":
        click.echo(
            f"项目资料清单有效：明确声明了 {len(context.entries)} 项。"
            "尚未核验资料可用性或科学内容。"
        )
    else:
        click.echo(
            f"Valid project context: {len(context.entries)} explicitly declared items. "
            "Source availability and scientific content have not been verified."
        )


@project_commands.command(name="overview")
@click.option(
    "--project-root", required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable references and status.")
@click.option("--language", type=click.Choice(["en", "zh"]), help="Override presentation language without changing files.")
def project_overview(project_root: Path, as_json: bool, language: str | None) -> None:
    """Read declared code, papers, notes and results; print Markdown by default."""
    from scholar_workflow.project.context import build_project_overview, render_project_overview

    try:
        overview = build_project_overview(project_root)
    except ValueError as exc:
        raise InputError(str(exc)) from None
    if language is not None:
        overview = overview.model_copy(update={"language": language})
    if as_json:
        click.echo(json.dumps(overview.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        click.echo(render_project_overview(overview), nl=False)


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


@zotero.command(name="annotations")
@click.argument("query", required=False)
@click.option("--item", "item_key", help="Zotero item key; skips title search.")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw projection as JSON.")
def zotero_annotations_cmd(
    query: str | None,
    item_key: str | None,
    as_json: bool,
) -> None:
    """Read one paper's Zotero-owned annotations through the Local API."""
    from scholar_workflow.workflows.annotations import (
        AnnotationAmbiguous,
        AnnotationExportError,
        extract_annotation_export,
        to_markdown,
    )

    if query is None and item_key is None:
        raise InputError("provide a title fragment or --item ITEM_KEY")
    try:
        with _open_zotero() as adapter:
            payload = extract_annotation_export(
                adapter,
                query=query,
                item_key=item_key,
            )
    except AnnotationAmbiguous as exc:
        raise IdentityConflictError(str(exc)) from None
    except (AnnotationExportError, ValueError) as exc:
        raise InputError(str(exc)) from None
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    click.echo(
        f"item={payload['item_key']} attachment={payload['attachment_key']} "
        f"total={payload['count']}"
    )
    rendered = to_markdown(payload["annotations"])
    if rendered:
        click.echo(rendered)


@zotero.command(name="snapshot-annotations")
@click.argument("attachment_key")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="New PDF path. The Zotero attachment is never overwritten or re-imported.",
)
def zotero_snapshot_annotations_cmd(attachment_key: str, output: Path) -> None:
    """Create an independent, hash-bound PDF copy with supported annotations."""
    from scholar_workflow.hub.pdf_snapshot import (
        AnnotationSnapshotError,
        AnnotationSnapshotService,
        UnsupportedAnnotationSnapshot,
    )
    from scholar_workflow.hub.zotflow import load_annotation_ir

    destination = output.expanduser().absolute()
    try:
        with _open_zotero() as adapter:
            locator = adapter.resolve_attachment_locator(attachment_key)
            annotations = load_annotation_ir(adapter, attachment_key)
            receipt = AnnotationSnapshotService().generate(
                locator.path,
                destination,
                annotations,
            )
    except UnsupportedAnnotationSnapshot as exc:
        raise SafetyRefusalError(str(exc)) from None
    except AnnotationSnapshotError as exc:
        raise InputError(str(exc)) from None
    click.echo(
        json.dumps(
            {
                "snapshot": str(receipt.snapshot_path),
                "metadata": str(receipt.metadata_path),
                "source_pdf_hash": receipt.source_pdf_hash,
                "annotation_set_hash": receipt.annotation_set_hash,
                "output_hash": receipt.output_hash,
                "annotation_count": receipt.annotation_count,
                "imported_back": False,
            },
            ensure_ascii=False,
        )
    )


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
            raise TypeError("version must be an integer from `zotero get`")
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
            raise TypeError("metadata must be an object and collection_keys must be a list")
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
@click.option(
    "--research-vault-root",
    "vault",
    required=False,
    help="Optional legacy Vault migration candidate; v3 Sources are registered in Hub.",
)
@click.argument("extras", nargs=-1)
def config_init(vault: str | None, extras: tuple[str, ...]) -> None:
    """Create config.yml with optional legacy Vault and KEY=VALUE extras.

    Writes only version + the values you name — never a full dump of defaults. Idempotent:
    an identical re-init is a no-op; a differing existing file is refused (edit with
    `config set`)."""
    from pydantic import ValidationError

    from scholar_workflow.config import ConfigError, init_config

    extra: dict[str, str] = {}
    for pair in extras:
        if "=" not in pair:
            raise InputError(f"extras must be KEY=VALUE, got {pair!r}")
        k, v = pair.split("=", 1)
        extra[k.strip()] = v.strip()
    try:
        path = init_config(vault, extra)
    except (ConfigError, ValidationError) as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps({"config": str(path)}, ensure_ascii=False))


@config.command(name="set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set one dotted KEY (e.g. notion.enabled) to VALUE, preserving comments."""
    from pydantic import ValidationError

    from scholar_workflow.config import ConfigError, ConfigNotFound, set_config_value

    try:
        coerced = set_config_value(key, value)
    except ConfigNotFound:
        raise InputError(
            "no config.yml yet — run `scholar-workflow config init` first."
        ) from None
    except (ConfigError, ValidationError) as exc:
        raise InputError(str(exc)) from None
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
    from scholar_workflow.planning import generate_plan
    from scholar_workflow.resolver import resolve_many
    from scholar_workflow.state import StateStore
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
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.projection import project_obsidian

    payload = json.load(input_file)
    entries = payload.get("entries", [])
    cfg = _load_cfg()
    index = payload.get("index") or "31-paper/index.md"
    heading = payload.get("heading") or "Papers"
    adapter = ObsidianAdapter(_require_legacy_vault(cfg),
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
    adapter = ObsidianAdapter(_require_legacy_vault(cfg),
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
    from scholar_workflow.adapters.obsidian import ObsidianAdapter
    from scholar_workflow.workflows.novelty_tree import (
        plan_novelty_tree,
        plan_paperlist,
        project_novelty_tree,
        project_paperlist,
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
    adapter = ObsidianAdapter(_require_legacy_vault(cfg),
                              cfg.obsidian.managed_block_start,
                              cfg.obsidian.managed_block_end)
    stats = applier(adapter)
    from scholar_workflow.hub.catalog import CatalogSnapshotStore
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
    """Retired fixed-listener entry point retained for an explicit diagnostic."""
    raise DependencyError(
        "`serve-links` is retired in Hub v3; use `scholar-workflow hub start` "
        "or `scholar-workflow open-hub`."
    )


@main.command(name="_hub-service", hidden=True)
@click.option("--generation", required=True)
@click.option(
    "--discovery",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option("--log", required=True, type=click.Path(dir_okay=False, path_type=Path))
def _hub_service_process(generation: str, discovery: Path, log: Path) -> None:
    """Private installed-package entry point for the detached Hub process."""
    from scholar_workflow.hub.service_process import run

    raise SystemExit(
        run(
            [
                "--generation",
                generation,
                "--discovery",
                str(discovery),
                "--log",
                str(log),
            ]
        )
    )


@main.command(name="_hub-router", hidden=True)
@click.option("--generation", required=True)
@click.option(
    "--runtime-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
)
def _hub_router_process(generation: str, runtime_root: Path) -> None:
    """Private cmux-descendant router for validated window operations."""
    from scholar_workflow.hub.cmux_router import run

    raise SystemExit(
        run(
            [
                "--generation",
                generation,
                "--runtime-root",
                str(runtime_root),
            ]
        )
    )


@main.command(name="serve-hub")
@click.option(
    "--port",
    type=click.IntRange(0, 65535),
    default=None,
    help="Override the configured port; use 0 for an ephemeral canary port.",
)
@click.option(
    "--canary",
    is_flag=True,
    help="Run a temporary headless canary; defaults to an ephemeral port.",
)
@click.option(
    "--knowledge-provider-state-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Explicit Knowledge provider snapshot root; otherwise use the configured home if present.",
)
def serve_hub(
    port: int | None,
    canary: bool,
    knowledge_provider_state_root: Path | None,
) -> None:
    """Run the local research Hub (foreground, blocks until Ctrl-C)."""
    options: dict[str, object] = {"port_override": port, "canary": canary}
    if knowledge_provider_state_root is not None:
        options["knowledge_provider_state_root"] = knowledge_provider_state_root
    _serve_hub_foreground(**options)


@main.command(name="hub-doctor")
@click.option("--port", type=click.IntRange(1, 65535), default=None)
@click.option("--json", "as_json", is_flag=True)
def hub_doctor(port: int | None, as_json: bool) -> None:
    """Compatibility alias for managed Hub diagnostics."""
    from scholar_workflow.hub.lifecycle import HubServiceManager, probe_diagnostics

    if port is None:
        status = HubServiceManager().status()
        if not status.running or status.record is None or status.health is None:
            raise DependencyError(status.detail)
        selected_port = status.record.port
    else:
        selected_port = port
    payload = probe_diagnostics(selected_port)
    if payload is None:
        raise DependencyError(
            f"No detailed Scholar Workflow Hub diagnostics at 127.0.0.1:{selected_port}"
        )
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return
    service = payload.get("service", {})
    protocol = payload.get("protocol", {})
    directory = payload.get("hub_directory", {})
    click.echo(
        f"[ok] {service.get('name')} {service.get('version')} "
        f"on 127.0.0.1:{selected_port}"
    )
    click.echo(
        f"[ok] protocol={protocol.get('version')} "
        f"HubDirectory={directory.get('schema_version')} "
        f"owner={payload.get('owner_mode')}"
    )
    providers = payload.get("provider_capabilities", {})
    if isinstance(providers, dict):
        for name in ("papers", "projects", "tools"):
            detail = providers.get(name, {})
            available = isinstance(detail, dict) and detail.get("available") is True
            click.echo(f"[{'ok' if available else 'warn'}] provider {name}")
    worker = payload.get("worker_capabilities", {})
    task_execution = isinstance(worker, dict) and worker.get("task_execution") is True
    click.echo(
        f"[{'ok' if task_execution else 'off'}] task execution "
        f"{'enabled' if task_execution else 'disabled'}"
    )


def _lifecycle_failure(exc: Exception) -> click.ClickException:
    from scholar_workflow.hub.lifecycle import HubStartError, UnsafeManagedProcess

    if isinstance(exc, UnsafeManagedProcess):
        return SafetyRefusalError(str(exc))
    if isinstance(exc, HubStartError):
        return DependencyError(str(exc))
    return ExternalServiceError(str(exc))


def _echo_managed_record(record: object) -> None:
    payload = record.as_payload()
    click.echo(
        f"[ok] {payload['service_name']} {payload['package_version']} "
        f"on 127.0.0.1:{payload['port']}"
    )
    click.echo(
        f"[ok] pid={payload['pid']} executable={payload['executable']}"
    )
    click.echo(
        f"[ok] build={payload['build_hash']} protocol={payload['protocol_version']} "
        f"generation={payload['service_generation']}"
    )
    click.echo(
        f"[ok] started={payload['started_at']} log={payload['log_path']}"
    )


def _ensure_hub_router(record: object, workspace_id: str) -> None:
    """Attach only window routing to cmux; never move the HTTP service there."""
    from scholar_workflow.hub.cmux_router import ensure_router
    from scholar_workflow.hub.lifecycle import _installed_cli_executable, runtime_root

    ensure_router(
        runtime_root=runtime_root(),
        service_generation=record.service_generation,
        workspace_id=workspace_id,
        executable=_installed_cli_executable(),
    )


@main.group(name="hub")
def hub_lifecycle() -> None:
    """Manage the installed package's host-local Hub service."""


def _hub_state_root() -> Path:
    return Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)).expanduser().resolve()


def _managed_field_hub_record():
    from scholar_workflow.hub.lifecycle import HubServiceManager

    status = HubServiceManager().status()
    if not status.running or status.record is None:
        raise DependencyError(status.detail)
    return status.record


def _field_hub_request(
    port: int,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    operator_token: str | None = None,
) -> dict[str, object]:
    """Call the proven managed listener; never put approval data in a URL."""
    if payload is not None:
        session = _field_hub_request(port, "/api/v1/session")
        csrf = session.get("csrf_token")
        if not isinstance(csrf, str) or not csrf:
            raise ExternalServiceError("Hub browser session response was invalid")
        try:
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise InputError("Field request is not strict JSON") from exc
        if len(encoded) > 8 * 1024 * 1024:
            raise InputError("Field request is too large")
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": csrf,
        }
        if operator_token is not None:
            headers["X-Scholar-Hub-Operator"] = operator_token
    else:
        encoded = None
        headers = {}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30.0)
    try:
        connection.request(
            "POST" if encoded is not None else "GET",
            path,
            body=encoded,
            headers=headers,
        )
        response = connection.getresponse()
        content = response.read(4 * 1024 * 1024 + 1)
        status_code = response.status
    except (OSError, http.client.HTTPException) as exc:
        raise ExternalServiceError(f"Managed Hub request failed: {exc}") from None
    finally:
        connection.close()
    if len(content) > 4 * 1024 * 1024:
        raise ExternalServiceError("Managed Hub response was unexpectedly large")
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = {"error": content.decode("utf-8", errors="replace")}
    if not isinstance(decoded, dict):
        raise ExternalServiceError("Managed Hub response was invalid")
    if status_code != 200:
        detail = str(decoded.get("error", f"HTTP {status_code}"))
        if "candidate expired" in detail or "plan is unknown or expired" in detail:
            detail += "; review again within 30 minutes; Hub restart invalidates plan tokens"
        if status_code == 400:
            raise InputError(detail)
        if status_code in {403, 409}:
            raise SafetyRefusalError(detail)
        if status_code == 503:
            raise DependencyError(detail)
        raise ExternalServiceError(detail)
    return decoded


def _field_operator_token(record: object) -> str:
    """Read the private local-operator credential after lifecycle identity proof."""
    from scholar_workflow.hub.field_transaction import _open_private_directory
    from scholar_workflow.hub.server import OPERATOR_CREDENTIAL_NAME

    path = Path(record.log_path).parent / OPERATOR_CREDENTIAL_NAME
    try:
        parent_fd = _open_private_directory(path.parent)
    except (OSError, ValueError) as exc:
        raise SafetyRefusalError("Field operator credential parent is unsafe") from exc
    try:
        parent = os.fstat(parent_fd)
        if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
            raise SafetyRefusalError("Field operator credential parent is not private")
        descriptor = os.open(
            path.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size > 1024
            ):
                raise SafetyRefusalError("Field operator credential is unsafe")
            content = handle.read(1025)
    except OSError as exc:
        raise SafetyRefusalError("Field operator credential is unavailable or unsafe") from exc
    finally:
        os.close(parent_fd)
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafetyRefusalError("Field operator credential is invalid") from exc
    if not isinstance(payload, dict) or set(payload) != {"service_generation", "pid", "token"}:
        raise SafetyRefusalError("Field operator credential is invalid")
    if payload["service_generation"] != record.service_generation or payload["pid"] != record.pid:
        raise SafetyRefusalError("Field operator credential belongs to a stale generation")
    token = payload["token"]
    if not isinstance(token, str) or len(token) < 32:
        raise SafetyRefusalError("Field operator credential is invalid")
    return token


def _read_legacy_field_package(handle: object) -> dict[str, object]:
    """Bound the local candidate document before sending it to the operator route."""
    try:
        encoded = handle.read(8 * 1024 * 1024 + 1)
    except OSError as exc:
        raise InputError(f"Could not read Field proposal package: {exc}") from exc
    if not isinstance(encoded, bytes) or len(encoded) > 8 * 1024 * 1024:
        raise InputError("Field proposal package must be at most 8 MiB")

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate Field proposal JSON key")
            result[key] = value
        return result

    try:
        package = json.loads(
            encoded,
            object_pairs_hook=unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("Non-finite Field proposal number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InputError(f"Invalid Field proposal package: {exc}") from exc
    if not isinstance(package, dict):
        raise InputError("Field proposal package must be a JSON object")
    return package


@hub_lifecycle.group(name="field-transaction")
def hub_field_transaction() -> None:
    """Plan one Field as a group; commit only with a local operator."""


@hub_field_transaction.command(name="plan")
@click.option("--field-root", default=None, help="Choose this relative Field root after folder selection.")
@click.option("--candidate-token", default=None, help="Use a prior Hub folder-selection candidate.")
@click.option("--field-id", default=None, help="Field ID from that exact candidate preview.")
def hub_field_transaction_plan(
    field_root: str | None,
    candidate_token: str | None,
    field_id: str | None,
) -> None:
    """Read only: inspect the full Field change set and exact approval digest."""
    record = _managed_field_hub_record()
    if (candidate_token is None) != (field_id is None):
        raise InputError("--candidate-token and --field-id must be provided together")
    if candidate_token is not None:
        if field_root is not None:
            raise InputError("--field-root cannot accompany an existing candidate")
        selected_token, selected_id = candidate_token, field_id
    else:
        selected = _field_hub_request(record.port, "/api/v3/fields/select", payload={})
        preview = selected.get("preview")
        if not isinstance(preview, dict):
            raise ExternalServiceError("Field preview response was invalid")
        rows = preview.get("fields")
        if not isinstance(rows, list):
            raise ExternalServiceError("Field preview response was invalid")
        matches = [
            row for row in rows
            if isinstance(row, dict)
            and (field_root is None or row.get("relative_root") == field_root)
        ]
        if len(matches) != 1:
            roots = [row.get("relative_root") for row in rows if isinstance(row, dict)]
            raise InputError(
                "Choose exactly one Field with --field-root; candidates: "
                + ", ".join(str(root) for root in roots)
            )
        selected_token, selected_id = preview.get("candidate_token"), matches[0].get("field_id")
        if not isinstance(selected_token, str) or not isinstance(selected_id, str):
            raise ExternalServiceError("Field preview identity was invalid")
    result = _field_hub_request(
        record.port,
        "/api/v3/field-transactions/plan",
        payload={"candidate_token": selected_token, "field_id": selected_id},
    )
    plan = result.get("plan")
    if not isinstance(plan, dict):
        raise ExternalServiceError("Field transaction plan response was invalid")
    click.echo(json.dumps({**plan, "candidate_token": selected_token}, ensure_ascii=False, sort_keys=True))


@hub_field_transaction.command(name="legacy-preview")
@click.argument("candidate_token")
@click.argument("field_id")
@click.option(
    "--package-file",
    required=True,
    type=click.File("rb"),
    help="Trusted local JSON proposal (or - for stdin); never sent by a browser.",
)
def hub_field_transaction_legacy_preview(
    candidate_token: str,
    field_id: str,
    package_file: object,
) -> None:
    """Read-only mechanical cutover review for one legacy analysis pair."""
    package = _read_legacy_field_package(package_file)
    record = _managed_field_hub_record()
    response = _field_hub_request(
        record.port,
        "/api/v3/field-transactions/legacy/preview",
        payload={"candidate_token": candidate_token, "field_id": field_id, "package": package},
        operator_token=_field_operator_token(record),
    )
    click.echo(json.dumps(response, ensure_ascii=False, sort_keys=True))


@hub_field_transaction.command(name="legacy-stage")
@click.argument("candidate_token")
@click.argument("field_id")
@click.option(
    "--package-file",
    required=True,
    type=click.File("rb"),
    help="The same trusted local JSON proposal reviewed in legacy-preview.",
)
@click.option(
    "--approved-cutover-digest",
    required=True,
    help="Exact cutover_digest from the reviewed read-only preview.",
)
@click.option(
    "--field-definition-file",
    type=click.File("rb"),
    default=None,
    help="Optional reviewed Field navigation/home override as local JSON.",
)
def hub_field_transaction_legacy_stage(
    candidate_token: str,
    field_id: str,
    package_file: object,
    approved_cutover_digest: str,
    field_definition_file: object | None,
) -> None:
    """Unavailable until Provider and Field share a recovery journal."""
    raise DependencyError(
        "Legacy analysis staging is unavailable until Provider and Field changes "
        "share one recoverable transaction journal; use legacy-preview for read-only review"
    )


@hub_field_transaction.command(name="apply")
@click.argument("plan_token")
@click.option("--approved-digest", required=True, help="Exact plan_digest from the reviewed plan.")
@click.option(
    "--external-writers-paused",
    is_flag=True,
    help="Human assertion: Obsidian and sync writers are paused; the CLI cannot detect this.",
)
def hub_field_transaction_apply(
    plan_token: str,
    approved_digest: str,
    external_writers_paused: bool,
) -> None:
    """Commit the reviewed plan in a manually arranged quiet writer window."""
    if not external_writers_paused:
        raise SafetyRefusalError("External Field writers must be paused before apply")
    if not click.confirm(
        "Confirm external editors/sync are stopped and this exact digest was reviewed?",
        default=False,
    ):
        raise SafetyRefusalError("Field transaction was not confirmed")
    record = _managed_field_hub_record()
    operator_token = _field_operator_token(record)
    response = _field_hub_request(
        record.port,
        "/api/v3/field-transactions/apply",
        payload={"plan_token": plan_token, "approved_digest": approved_digest},
        operator_token=operator_token,
    )
    result = response.get("result")
    if not isinstance(result, dict):
        raise ExternalServiceError("Field transaction apply response was invalid")
    click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@hub_field_transaction.command(name="recover")
@click.argument("source_id")
@click.argument("field_id")
@click.option("--confirm-recovery", is_flag=True, help="Confirm conditional rollback/completion.")
@click.option(
    "--external-writers-paused",
    is_flag=True,
    help="Human assertion: Obsidian and sync writers are paused; the CLI cannot detect this.",
)
def hub_field_transaction_recover(
    source_id: str,
    field_id: str,
    confirm_recovery: bool,
    external_writers_paused: bool,
) -> None:
    """Conditionally recover only this interrupted Field, preserving conflicts."""
    if not confirm_recovery:
        raise SafetyRefusalError("Explicit --confirm-recovery is required")
    if not external_writers_paused:
        raise SafetyRefusalError("External Field writers must be paused before recovery")
    if not click.confirm("Inspect the pending Field journal and conditionally recover it?", default=False):
        raise SafetyRefusalError("Field recovery was not confirmed")
    record = _managed_field_hub_record()
    operator_token = _field_operator_token(record)
    response = _field_hub_request(
        record.port,
        "/api/v3/field-transactions/recover",
        payload={
            "source_id": source_id,
            "field_id": field_id,
            "external_writers_paused": True,
        },
        operator_token=operator_token,
    )
    result = response.get("result")
    if not isinstance(result, dict):
        raise ExternalServiceError("Field recovery response was invalid")
    click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))


@hub_lifecycle.group(name="field-migration")
def hub_field_migration() -> None:
    """Preview or explicitly apply legacy-link cleanup for one registered Field."""


def _field_migration_service():
    from scholar_workflow.hub.field_migration import FieldMigrationService
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    root = _hub_state_root() / "hub"
    return FieldMigrationService(
        KnowledgeSourceRegistry(root / "sources.json"),
        state_root=root / "field-migration-private",
    )


@hub_field_migration.command(name="plan")
@click.argument("source_id")
@click.argument("field_id")
def hub_field_migration_plan(source_id: str, field_id: str) -> None:
    """Read only: show the exact Field file set, link changes, and plan digest."""
    from dataclasses import asdict

    from scholar_workflow.hub.field_migration import FieldMigrationError
    from scholar_workflow.knowledge.fields import FieldRegistryError

    try:
        plan = _field_migration_service().plan(source_id, field_id)
    except (FieldMigrationError, FieldRegistryError, OSError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    payload = asdict(plan)
    payload.pop("plan_token")
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@hub_field_migration.command(name="apply")
@click.argument("source_id")
@click.argument("field_id")
@click.option(
    "--approved-digest",
    required=True,
    help="Exact plan_digest from a reviewed, fresh read-only plan.",
)
@click.option(
    "--external-writers-paused",
    is_flag=True,
    help="Human assertion: Obsidian and sync writers are paused; the CLI cannot detect this.",
)
def hub_field_migration_apply(
    source_id: str,
    field_id: str,
    approved_digest: str,
    external_writers_paused: bool,
) -> None:
    """Re-plan and CAS-apply one approved Field in a quiet writer window."""
    from dataclasses import asdict

    from scholar_workflow.hub.field_migration import FieldMigrationError
    from scholar_workflow.knowledge.fields import FieldRegistryError

    service = _field_migration_service()
    try:
        plan = service.plan(source_id, field_id)
        if approved_digest != plan.plan_digest:
            raise FieldMigrationError("Field changed; review a fresh plan_digest")
        if plan.conflicts:
            raise FieldMigrationError("Field migration plan has unresolved conflicts")
        if not external_writers_paused:
            raise FieldMigrationError("External Field writers must be paused before apply")
        if not click.confirm(
            "Confirm external editors/sync are stopped and this exact digest was reviewed?",
            default=False,
        ):
            raise FieldMigrationError("Field migration was not confirmed")
        result = service.apply(
            plan.plan_token,
            approved_digest=approved_digest,
            external_writers_paused=True,
        )
    except (FieldMigrationError, FieldRegistryError, OSError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    payload = asdict(result)
    payload["recovery_snapshot"] = str(result.recovery_snapshot)
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@hub_field_migration.command(name="recover")
@click.argument("source_id")
@click.argument("field_id")
def hub_field_migration_recover(source_id: str, field_id: str) -> None:
    """Explicitly conditionally restore an interrupted Field migration."""
    from dataclasses import asdict

    from scholar_workflow.hub.field_migration import FieldMigrationError
    from scholar_workflow.knowledge.fields import FieldRegistryError

    try:
        result = _field_migration_service().recover(source_id, field_id)
    except (FieldMigrationError, FieldRegistryError, OSError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    payload = asdict(result)
    if result.recovery_snapshot is not None:
        payload["recovery_snapshot"] = str(result.recovery_snapshot)
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


_DEFAULT_TASK_RECIPE_ID = "general-research"
_DEFAULT_TASK_POLICY_ID = "default-safe"


def _allow_default_recipe_target(root: Path, target_id: str) -> None:
    """Extend the explicit default recipe after a trusted target is registered.

    Registering a target is already the local administrator's explicit grant for
    Codex cwd use.  Keeping the default recipe's allowlist in the same operation
    avoids a second, unrelated browser or filesystem authority.
    """
    from scholar_workflow.hub.tasks import (
        TaskContractError,
        TaskRecipeRegistry,
    )

    registry_path = root / "task-recipes.json"
    if not registry_path.is_file():
        return
    registry = TaskRecipeRegistry(registry_path)
    try:
        document = registry.load()
    except TaskContractError as exc:
        raise SafetyRefusalError(str(exc)) from None
    changed = False
    recipes = []
    for recipe in document.recipes:
        if recipe.recipe_id != _DEFAULT_TASK_RECIPE_ID:
            recipes.append(recipe)
            continue
        allowed = list(recipe.allowed_target_ids or [])
        if target_id not in allowed:
            allowed.append(target_id)
            recipe = recipe.model_copy(update={"allowed_target_ids": sorted(allowed)})
            changed = True
        recipes.append(recipe)
    if changed:
        registry.save(document.model_copy(update={"recipes": recipes}))


@hub_lifecycle.group(name="target")
def hub_target() -> None:
    """Manage trusted cwd aliases without accepting browser filesystem paths."""


@hub_target.command(name="list")
def hub_target_list() -> None:
    """List public execution-target metadata; never print registered host paths."""
    from scholar_workflow.hub.directory import ProjectRegistry
    from scholar_workflow.hub.routing import ExecutionTargetRegistry
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    root = _hub_state_root() / "hub"
    registry = ExecutionTargetRegistry(
        root / "execution-targets.json",
        project_registry=ProjectRegistry(root / "projects.json"),
        source_registry=KnowledgeSourceRegistry(root / "sources.json"),
    )
    payload = {
        "targets": [
            {
                "target_id": target.target_id,
                "kind": target.kind,
                "capabilities": target.capabilities,
            }
            for target in registry.load().targets
        ]
    }
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@hub_target.command(name="add-source")
@click.argument("source_id")
@click.option("--target-id", required=True, help="Portable alias shown in the Hub.")
def hub_target_add_source(source_id: str, target_id: str) -> None:
    """Authorize one already registered Knowledge Source as a Codex cwd target."""
    from scholar_workflow.hub.directory import ProjectRegistry
    from scholar_workflow.hub.routing import (
        ExecutionTarget,
        ExecutionTargetError,
        ExecutionTargetRegistry,
        ExecutionTargetRegistryDocument,
    )
    from scholar_workflow.knowledge.fields import (
        FieldRegistryError,
        KnowledgeSourceRegistry,
        KnowledgeSourceRegistryDocument,
    )

    root = _hub_state_root() / "hub"
    sources = KnowledgeSourceRegistry(root / "sources.json")
    try:
        source_document = sources.load_document()
        source = next(row for row in source_document.sources if row.source_id == source_id)
        folder = next(
            row for row in source_document.folders if row.folder_id == source.folder_id
        )
    except StopIteration:
        raise InputError("Unknown registered Knowledge Source") from None
    except FieldRegistryError as exc:
        raise SafetyRefusalError(str(exc)) from None
    if not source.enabled or not folder.enabled:
        raise SafetyRefusalError("Knowledge Source or its registered folder is disabled")

    target_registry = ExecutionTargetRegistry(
        root / "execution-targets.json",
        project_registry=ProjectRegistry(root / "projects.json"),
        source_registry=sources,
    )
    try:
        targets = target_registry.load()
        candidate = ExecutionTarget(
            target_id=target_id,
            kind="vault",
            registered_root_id=folder.folder_id,
            capabilities=["codex"],
        )
    except (ExecutionTargetError, ValueError) as exc:
        raise InputError(str(exc)) from None
    existing = next((row for row in targets.targets if row.target_id == target_id), None)
    if existing is not None and existing != candidate:
        raise IdentityConflictError("target_id is already registered to another root")
    if existing is None:
        # Save the unusable alias first, then grant the root capability.  A crash
        # between the two writes fails closed because target resolution still rejects it.
        target_registry.save(
            ExecutionTargetRegistryDocument(targets=[*targets.targets, candidate])
        )

    updated_folders = []
    for row in source_document.folders:
        if row.folder_id == folder.folder_id and "codex" not in row.capabilities:
            row = row.model_copy(update={"capabilities": [*row.capabilities, "codex"]})
        updated_folders.append(row)
    try:
        sources.save(
            KnowledgeSourceRegistryDocument(
                folders=updated_folders,
                sources=source_document.sources,
            )
        )
        target_registry.resolve(target_id, capability="codex")
        _allow_default_recipe_target(root, target_id)
    except (FieldRegistryError, ExecutionTargetError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(
        json.dumps(
            {
                "target_id": candidate.target_id,
                "kind": candidate.kind,
                "capabilities": candidate.capabilities,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@hub_target.command(name="add-project")
@click.argument("project_id")
@click.option("--target-id", required=True, help="Portable alias shown in the Hub.")
def hub_target_add_project(project_id: str, target_id: str) -> None:
    """Authorize one already registered Project as a Codex cwd target."""
    from scholar_workflow.hub.directory import ProjectRegistry, RegistryError
    from scholar_workflow.hub.routing import (
        ExecutionTarget,
        ExecutionTargetError,
        ExecutionTargetRegistry,
        ExecutionTargetRegistryDocument,
    )
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    root = _hub_state_root() / "hub"
    projects = ProjectRegistry(root / "projects.json")
    try:
        rows = projects.load()
        project = next(row for row in rows if row.project_id == project_id)
    except StopIteration:
        raise InputError("Unknown registered project_id") from None
    except (RegistryError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if not project.enabled:
        raise SafetyRefusalError("Registered project is disabled")

    target_registry = ExecutionTargetRegistry(
        root / "execution-targets.json",
        project_registry=projects,
        source_registry=KnowledgeSourceRegistry(root / "sources.json"),
    )
    try:
        targets = target_registry.load()
        candidate = ExecutionTarget(
            target_id=target_id,
            kind="project",
            registered_root_id=project_id,
            capabilities=["codex"],
        )
    except (ExecutionTargetError, ValueError) as exc:
        raise InputError(str(exc)) from None
    existing = next((row for row in targets.targets if row.target_id == target_id), None)
    if existing is not None and existing != candidate:
        raise IdentityConflictError("target_id is already registered to another root")
    if existing is None:
        target_registry.save(
            ExecutionTargetRegistryDocument(targets=[*targets.targets, candidate])
        )

    updated = [
        row.model_copy(update={"capabilities": [*row.capabilities, "codex"]})
        if row.project_id == project_id and "codex" not in row.capabilities
        else row
        for row in rows
    ]
    try:
        projects.save(updated)
        target_registry.resolve(target_id, capability="codex")
        _allow_default_recipe_target(root, target_id)
    except (RegistryError, ExecutionTargetError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(
        json.dumps(
            {
                "target_id": candidate.target_id,
                "kind": candidate.kind,
                "capabilities": candidate.capabilities,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@hub_lifecycle.group(name="codex")
def hub_codex() -> None:
    """Configure the server-owned Codex task recipe and inspect its capability."""


@hub_codex.command(name="configure")
@click.option(
    "--executable",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Explicit absolute Codex executable; PATH is never scanned by the Hub.",
)
@click.option(
    "--model",
    required=True,
    help="Approve a local model for server-owned profiles; task requests use profile IDs.",
)
@click.option(
    "--sandbox",
    type=click.Choice(["read-only", "workspace-write"]),
    default="workspace-write",
    show_default=True,
)
def hub_codex_configure(executable: Path, model: str, sandbox: str) -> None:
    """CLI fallback: approve an explicit installation, model and existing targets."""
    from scholar_workflow.hub.codex_setup import CodexSetupService
    from scholar_workflow.hub.directory import ProjectRegistry
    from scholar_workflow.hub.routing import ExecutionTargetRegistry
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    root = _hub_state_root() / "hub"
    projects = ProjectRegistry(root / "projects.json")
    sources = KnowledgeSourceRegistry(root / "sources.json")
    targets = ExecutionTargetRegistry(
        root / "execution-targets.json", project_registry=projects, source_registry=sources,
    )
    service = CodexSetupService(
        root, project_registry=projects, source_registry=sources, target_registry=targets,
    )
    try:
        target_ids = [row["target_id"] for row in service.public_targets()
                      if row.get("available", True)]
        result = service.register_explicit(
            executable=executable.expanduser(), model=model, sandbox=sandbox,
            target_ids=target_ids,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    # A running HTTP service owns its task-service snapshot; CLI registration is out of process.
    click.echo(json.dumps({
        "configured": result["configured"], "available": True,
        "recipe_id": _DEFAULT_TASK_RECIPE_ID, "allowed_target_ids": target_ids,
        "efforts": ["fast", "standard", "deep"], "restart_required": True,
    }, ensure_ascii=False, sort_keys=True))


@hub_codex.command(name="status")
def hub_codex_status() -> None:
    """Probe the private Codex registration without executing a task."""
    from scholar_workflow.hub.tasks import CodexCapabilityProbe, TaskRecipeRegistry
    from scholar_workflow.hub.terminal_worker import (
        TerminalWorkerError,
        TerminalWorkerState,
    )

    root = _hub_state_root() / "hub"
    state = TerminalWorkerState(root / "task-worker")
    try:
        runtime = state.current_runtime()
        capabilities = CodexCapabilityProbe(runtime.resolved_codex_executable()).probe()
        recipes = TaskRecipeRegistry(runtime.recipe_registry_path).load()
    except (
        OSError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        ValueError,
        TerminalWorkerError,
    ) as exc:
        raise DependencyError("Codex task runtime is not configured or is invalid") from exc
    click.echo(
        json.dumps(
            {
                "configured": True,
                "available": capabilities.available,
                "create": capabilities.create,
                "resume": capabilities.resume,
                "fork": capabilities.fork,
                "recipes": [recipe.recipe_id for recipe in recipes.recipes],
                "detail": capabilities.detail,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


@hub_lifecycle.command(name="start")
@click.option("--json", "as_json", is_flag=True)
def hub_start(as_json: bool) -> None:
    """Start or reuse the current managed Hub on a dynamic loopback port."""
    from scholar_workflow.hub.cmux import CmuxControlError
    from scholar_workflow.hub.lifecycle import HubLifecycleError, HubServiceManager

    try:
        record = HubServiceManager().start()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    cmux_context = _optional_cmux_context()
    if cmux_context is not None:
        try:
            _ensure_hub_router(record, cmux_context[0])
        except CmuxControlError as exc:
            raise DependencyError(f"Hub is readable, but cmux routing failed: {exc}") from None
    if as_json:
        click.echo(json.dumps(record.as_payload(), ensure_ascii=False, sort_keys=True))
    else:
        _echo_managed_record(record)


@hub_lifecycle.command(name="status")
@click.option("--json", "as_json", is_flag=True)
def hub_status(as_json: bool) -> None:
    """Show the real executable, build, PID, port, start time, and log path."""
    from scholar_workflow.hub.lifecycle import HubLifecycleError, HubServiceManager

    try:
        status = HubServiceManager().status()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    if as_json:
        click.echo(json.dumps(status.as_payload(), ensure_ascii=False, sort_keys=True))
        return
    if status.record is not None:
        _echo_managed_record(status.record)
    click.echo(f"[{'ok' if status.running else 'off'}] {status.detail}")


@hub_lifecycle.command(name="stop")
def hub_stop() -> None:
    """Stop only a health-proven managed Hub; already stopped is success."""
    from scholar_workflow.hub.cmux import CmuxControlError
    from scholar_workflow.hub.cmux_router import stop_router
    from scholar_workflow.hub.lifecycle import HubLifecycleError, HubServiceManager

    manager = HubServiceManager()
    try:
        prior = manager.status()
        stopped = manager.stop()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    if prior.record is not None:
        try:
            stop_router(manager.record_path.parent, prior.record.service_generation)
        except CmuxControlError as exc:
            raise ExternalServiceError(
                f"Managed Hub stopped, but cmux router cleanup failed: {exc}"
            ) from None
    click.echo("[ok] managed Hub stopped" if stopped else "[ok] managed Hub already stopped")


@hub_lifecycle.command(name="restart")
@click.option("--json", "as_json", is_flag=True)
def hub_restart(as_json: bool) -> None:
    """Safely replace a proven Hub; attach cmux routing when available."""
    from scholar_workflow.hub.cmux import CmuxControlError
    from scholar_workflow.hub.lifecycle import HubLifecycleError, HubServiceManager

    cmux_context = _optional_cmux_context()
    try:
        record = HubServiceManager().restart()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    if cmux_context is not None:
        try:
            _ensure_hub_router(record, cmux_context[0])
        except CmuxControlError as exc:
            raise DependencyError(f"Hub is readable, but cmux routing failed: {exc}") from None
    if as_json:
        click.echo(json.dumps(record.as_payload(), ensure_ascii=False, sort_keys=True))
    else:
        _echo_managed_record(record)


@hub_lifecycle.command(name="doctor")
@click.option("--json", "as_json", is_flag=True)
def hub_managed_doctor(as_json: bool) -> None:
    """Verify discovery permissions, installed build, and live process identity."""
    import stat as _stat

    from scholar_workflow.hub.lifecycle import (
        HUB_PROTOCOL_VERSION,
        HubLifecycleError,
        HubServiceManager,
        discovery_path,
        installed_build_hash,
    )

    try:
        status = HubServiceManager().status()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    checks: list[dict[str, object]] = []
    mode = None
    try:
        mode = _stat.S_IMODE(discovery_path().stat().st_mode)
    except FileNotFoundError:
        pass
    checks.append(
        {
            "name": "discovery-mode",
            "ok": mode == 0o600,
            "detail": "0600" if mode == 0o600 else "missing or not 0600",
        }
    )
    record = status.record
    health = status.health or {}
    health_service = health.get("service", {})
    health_process = health.get("process", {})
    health_protocol = health.get("protocol", {})
    health_build = health.get("build", {})
    checks.append(
        {
            "name": "managed-process",
            "ok": status.running,
            "detail": status.detail,
        }
    )
    checks.append(
        {
            "name": "installed-build",
            "ok": record is not None
            and record.package_version == __version__
            and record.build_hash == installed_build_hash(),
            "detail": (
                f"package={record.package_version} build={record.build_hash}"
                if record is not None
                else "no discovery record"
            ),
        }
    )
    checks.append(
        {
            "name": "health-identity",
            "ok": status.running
            and record is not None
            and isinstance(health_service, dict)
            and health_service.get("name") == "scholar-workflow-hub"
            and health_service.get("version") == record.package_version
            and isinstance(health_process, dict)
            and health_process.get("pid") == record.pid
            and health_process.get("executable") == record.executable,
            "detail": (
                f"service={health_service.get('name')} "
                f"version={health_service.get('version')} "
                f"pid={health_process.get('pid')}"
                if isinstance(health_service, dict)
                and isinstance(health_process, dict)
                else "health identity unavailable"
            ),
        }
    )
    checks.append(
        {
            "name": "protocol",
            "ok": record is not None
            and record.protocol_version == HUB_PROTOCOL_VERSION
            and isinstance(health_protocol, dict)
            and health_protocol.get("version") == HUB_PROTOCOL_VERSION,
            "detail": (
                f"discovery={record.protocol_version} health="
                f"{health_protocol.get('version')}"
                if record is not None and isinstance(health_protocol, dict)
                else "unavailable"
            ),
        }
    )
    build_version = health_build.get("version") if isinstance(health_build, dict) else None
    checks.append(
        {
            "name": "health-build",
            "ok": record is not None and build_version == record.package_version,
            "detail": f"health build version={build_version}",
        }
    )
    log_mode = None
    if record is not None:
        try:
            log_mode = _stat.S_IMODE(Path(record.log_path).stat().st_mode)
        except FileNotFoundError:
            pass
    checks.append(
        {
            "name": "private-log",
            "ok": log_mode == 0o600,
            "detail": "0600" if log_mode == 0o600 else "missing or not 0600",
        }
    )
    report: dict[str, object] = {
        "ok": all(bool(item["ok"]) for item in checks),
        "checks": checks,
        "status": status.as_payload(),
    }
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        for item in checks:
            click.echo(
                f"[{'ok' if item['ok'] else 'FAIL'}] "
                f"{item['name']}: {item['detail']}"
            )
    if not report["ok"]:
        raise SystemExit(3)


@main.command(name="open-hub")
@click.option(
    "--instance",
    callback=_validate_hub_instance,
    help="Optional URL-safe opaque id for this Hub browser instance.",
)
def open_hub(instance: str | None) -> None:
    """Start the managed Hub and open it, with cmux as an optional destination."""
    from scholar_workflow.hub.actions import CmuxUnavailable
    from scholar_workflow.hub.cmux import CmuxControlError
    from scholar_workflow.hub.lifecycle import HubLifecycleError, HubServiceManager

    manager = HubServiceManager()
    cmux_context = _optional_cmux_context()
    try:
        record = manager.ensure_running()
    except HubLifecycleError as exc:
        raise _lifecycle_failure(exc) from None
    instance_id = instance or f"hub_{secrets.token_urlsafe(18)}"

    if cmux_context is None:
        port = record.port
        url = f"http://127.0.0.1:{port}/hub/?{urlencode({'instance': instance_id})}"
        if not webbrowser.open(url, new=2):
            raise ExternalServiceError(
                "The managed Hub is running, but the system browser did not open"
            )
        click.echo(
            f"[ok] Hub opened at {url}; choose a cmux destination only for launch actions"
        )
        return

    workspace_id, socket_path = cmux_context
    port = record.port
    try:
        _ensure_hub_router(record, workspace_id)
        registered = _register_default_destination(port, instance_id, workspace_id)
    except CmuxControlError as exc:
        raise DependencyError(f"Hub is readable, but cmux routing failed: {exc}") from None
    if not registered:
        raise ExternalServiceError("Managed Hub does not support cmux destinations")
    url = f"http://127.0.0.1:{port}/hub/?{urlencode({'instance': instance_id})}"
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
    click.echo("[ok] Hub opened; current cmux workspace is the default opening place")


def _serve_hub_foreground(
    *,
    port_override: int | None = None,
    canary: bool = False,
    knowledge_provider_state_root: Path | None = None,
) -> None:
    """Serve an explicit foreground Hub, normally on an ephemeral port.

    PDF content is resolved through Zotero's live Local API locator.  The
    one-cycle legacy routes share this listener but are never stable identity.
    """
    import threading as _t

    from scholar_workflow.config import Config, ConfigNotFound, load_config
    from scholar_workflow.hub.compatibility import compatibility_vault_root
    from scholar_workflow.hub.server import start_hub_server

    try:
        cfg = load_config()
    except ConfigNotFound:
        cfg = Config()
    vault_root = compatibility_vault_root(cfg.research_vault_root)
    selected_port = 0 if port_override is None else port_override
    server = start_hub_server(
        port=selected_port,
        storage_root=cfg.link_service.storage_root,
        vault_root=vault_root,
        knowledge_provider_state_root=knowledge_provider_state_root,
        owner_mode="headless",
        require_workspace_binding=False,
    )
    host, port = server.server_address
    if canary:
        from scholar_workflow.hub.lifecycle import probe_health

        try:
            payload = probe_health(port)
            if payload is None:
                raise ExternalServiceError("Canary health endpoint is unavailable")
            if payload.get("owner_mode") != "headless":
                raise ExternalServiceError(
                    "Canary did not start in headless mode"
                )
        except Exception:
            server.shutdown()
            server.server_close()
            raise
    click.echo(
        f"research-hub on http://{host}:{port}/hub/  "
        f"(storage: {cfg.link_service.storage_root})  "
        f"{'CANARY · EPHEMERAL  ' if canary else ''}Ctrl-C to stop"
    )
    try:
        _t.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


@main.command(name="install-service")
@click.option("--load/--no-load", default=True,
              help="Load into launchd immediately (default: load).")
def install_service(load: bool) -> None:
    """Retired LaunchAgent installer; Hub v3 owns its managed process directly."""
    del load
    raise DependencyError(
        "The fixed-port LaunchAgent is retired; use `scholar-workflow hub start`."
    )


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


def _experiment_result(value: object) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    click.echo(json.dumps(value, ensure_ascii=False, indent=2))


def _experiment_error(exc: ValueError) -> InputError:
    return InputError(str(exc))


@main.group()
def analysis() -> None:
    """Render and enforce versioned paper-analysis result contracts."""


@analysis.command(name="batch-run")
@click.option(
    "--request",
    "request_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSON document conforming to analysis-batch.schema.json.",
)
@click.option(
    "--repair-request",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional second JSON request containing one targeted repaired IR per item.",
)
@click.option("--state-db", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--stage-root", type=click.Path(file_okay=False, path_type=Path))
def analysis_batch_run(
    request_path: Path,
    repair_request: Path | None,
    state_db: Path | None,
    stage_root: Path | None,
) -> None:
    """Stage and validate every paper independently before any canonical write."""
    from pydantic import ValidationError

    from scholar_workflow.analysis.batch import (
        AnalysisBatchConflict,
        AnalysisBatchRunner,
        AnalysisBatchStore,
    )
    from scholar_workflow.analysis.models import AnalysisBatchRequest

    default_db, default_stage = _analysis_state_paths()
    try:
        request = AnalysisBatchRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        repaired_documents = None
        if repair_request is not None:
            repaired = AnalysisBatchRequest.model_validate_json(
                repair_request.read_text(encoding="utf-8")
            )
            if repaired.batch_id != request.batch_id:
                raise ValueError("repair request must use the original batch_id")
            original_ids = [item.item_id for item in request.items]
            repaired_ids = [item.item_id for item in repaired.items]
            if repaired_ids != original_ids:
                raise ValueError("repair request must contain the same ordered item IDs")
            repaired_documents = {
                item.document.artifact_id: item.document for item in repaired.items
            }
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise InputError(str(exc)) from None

    store = AnalysisBatchStore(state_db or default_db)
    try:
        runner = AnalysisBatchRunner(store=store, stage_root=stage_root or default_stage)

        def repair(document, _report):
            assert repaired_documents is not None
            try:
                return repaired_documents[document.artifact_id]
            except KeyError:
                raise ValueError(
                    f"repair request has no document for {document.artifact_id}"
                ) from None

        result = runner.run(
            request,
            repair=repair if repaired_documents is not None else None,
        )
    except AnalysisBatchConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    finally:
        store.close()
    click.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if result.state != "completed":
        raise PartialCompletionError(
            "one or more analysis items failed conformance; inspect the JSON result"
        )


@analysis.command(name="acknowledge-canvas-metadata")
@click.option("--request", "request_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--vault-root", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--registered-canvas-hash", help="Explicit registered hash for an unchanged graph re-encoded by its editor.")
def analysis_acknowledge_canvas_metadata(
    request_path: Path, vault_root: Path, registered_canvas_hash: str | None,
) -> None:
    """Explicitly record an editor's metadata-only save; never rewrite the pair."""
    from scholar_workflow.analysis.apply_changes import KnowledgeApplyConflict, KnowledgeApplyError
    from scholar_workflow.analysis.commit import AnalysisCommitConflict, AnalysisCommitSafetyError
    from scholar_workflow.analysis.editor_metadata import acknowledge_canvas_metadata
    from scholar_workflow.analysis.models import AnalysisCommitRequest
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    try:
        request = AnalysisCommitRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(str(exc)) from None
    try:
        result = acknowledge_canvas_metadata(
            vault_root=vault_root, request=request,
            source_registry=KnowledgeSourceRegistry(_hub_state_root() / "hub" / "sources.json"),
            registered_canvas_hash=registered_canvas_hash,
        )
    except (AnalysisCommitConflict, KnowledgeApplyConflict) as exc:
        raise IdentityConflictError(str(exc)) from None
    except (AnalysisCommitSafetyError, KnowledgeApplyError, OSError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@analysis.command(name="stage-update")
@click.option("--request", "request_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--vault-root", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--state-db", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--stage-root", type=click.Path(file_okay=False, path_type=Path))
def analysis_stage_update(
    request_path: Path, vault_root: Path, state_db: Path | None, stage_root: Path | None,
) -> None:
    """Stage one baseline-bound update without replacing the existing pair."""
    from hashlib import sha256

    from pydantic import ValidationError

    from scholar_workflow.analysis.batch import (
        AnalysisBatchConflict,
        AnalysisBatchRunner,
        AnalysisBatchStore,
    )
    from scholar_workflow.analysis.commit import (
        AnalysisCommitConflict,
        AnalysisCommitSafetyError,
        plan_existing_analysis_update,
    )
    from scholar_workflow.analysis.models import AnalysisBatchRequest, AnalysisCommitRequest

    try:
        request = AnalysisCommitRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
        if request.zotero_item_key is None:
            raise ValueError("an update requires the explicit Zotero item key")
        plan = plan_existing_analysis_update(vault_root=vault_root, request=request)
    except AnalysisCommitConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    except AnalysisCommitSafetyError as exc:
        raise SafetyRefusalError(str(exc)) from None
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise InputError(str(exc)) from None

    merged_request = request.model_copy(update={"document": plan.document, "source_state": "validated"})
    batch = AnalysisBatchRequest.model_validate({
        "schema_version": 1, "batch_id": request.batch_id,
        "items": [{"item_id": request.item_id, "zotero_item_key": request.zotero_item_key,
                   "note_stem": request.note_stem, "document": plan.document.model_dump(mode="json")}],
    })
    context = "sha256:" + sha256(request.model_dump_json().encode()).hexdigest()
    default_db, default_stage = _analysis_state_paths()
    store = AnalysisBatchStore(state_db or default_db)
    try:
        def preserved_renderer(document, note_stem):
            if document != plan.document or note_stem != request.note_stem:
                raise ValueError("staged update identity changed")
            return plan.proposed

        runner = AnalysisBatchRunner(
            store=store, stage_root=stage_root or default_stage, renderer=preserved_renderer,
        )
        result = runner.run(batch, input_context=context)
    except AnalysisBatchConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    except (OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    finally:
        store.close()
    click.echo(json.dumps({
        "batch": result.model_dump(mode="json"),
        "commit_request": merged_request.model_dump(mode="json") if result.state == "completed" else None,
        "canonical_written": False,
    }, ensure_ascii=False, indent=2))
    if result.state != "completed":
        raise PartialCompletionError("the update did not pass paired conformance")


@analysis.command(name="audit-batches")
@click.option("--state-db", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def analysis_audit_batches(state_db: Path | None) -> None:
    """Read persisted batch state and report unfinished or retained failed stages."""
    from scholar_workflow.analysis.audit import audit_analysis_batch_store
    from scholar_workflow.analysis.batch import AnalysisBatchStore

    default_db, _default_stage = _analysis_state_paths()
    path = state_db or default_db
    if not path.is_file():
        raise DependencyError(f"analysis state database does not exist: {path}")
    store = AnalysisBatchStore(path, readonly=True)
    try:
        report = audit_analysis_batch_store(store)
    finally:
        store.close()
    click.echo(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


@analysis.command(name="check-bundle")
@click.argument("directory", type=click.Path(path_type=Path))
@click.option("--markdown", required=True, help="Exact Markdown filename in the selected directory.")
@click.option("--canvas", required=True, help="Exact Canvas filename in the selected directory.")
@click.option("--sidecar", required=True, help="Exact baseline JSON filename in the selected directory.")
@click.option("--require-ir", type=click.IntRange(1, 5), default=None)
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def analysis_check_bundle(
    directory: Path, markdown: str, canvas: str, sidecar: str,
    require_ir: int | None, fmt: str, language: str,
) -> None:
    """Read only: validate an existing explicit pair and its baseline, without Hub."""
    from scholar_workflow.analysis.package_check import check_package, package_check_markdown

    try:
        report = check_package(
            directory, markdown=markdown, canvas=canvas, sidecar=sidecar, require_ir=require_ir,
        )
    except (OSError, ValueError, TypeError) as exc:
        raise InputError(str(exc)) from None
    click.echo(
        json.dumps(report, ensure_ascii=False, indent=2)
        if fmt == "json" else package_check_markdown(report, language=language),
    )
    if report["status"] != "conformant":
        raise click.exceptions.Exit(7)


@analysis.command(name="commit-bundle")
@click.option(
    "--request",
    "request_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="JSON document conforming to analysis-commit-request.schema.json.",
)
@click.option(
    "--vault-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
)
@click.option("--state-db", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--stage-root", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--commit-state-root", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--provider-state-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Legacy v1-v3 option; IR v4/v5 resolves its provider from the registered Source.",
)
def analysis_commit_bundle(
    request_path: Path,
    vault_root: Path,
    state_db: Path | None,
    stage_root: Path | None,
    commit_state_root: Path | None,
    provider_state_root: Path | None,
) -> None:
    """CAS-commit one validated staged Markdown/Canvas/sidecar bundle."""
    from pydantic import ValidationError

    from scholar_workflow.analysis.batch import AnalysisBatchStore
    from scholar_workflow.analysis.commit import (
        AnalysisCommitConflict,
        AnalysisCommitError,
        AnalysisCommitPartialError,
        AnalysisCommitSafetyError,
        commit_analysis_bundle,
    )
    from scholar_workflow.analysis.models import (
        AnalysisBaseline,
        AnalysisCommitRequest,
        AnalysisState,
    )
    from scholar_workflow.analysis.rendering import AnalysisBundle
    from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry

    default_db, default_stage = _analysis_state_paths()
    state_home = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME)) / "analysis"
    try:
        request = AnalysisCommitRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise InputError(str(exc)) from None

    store = AnalysisBatchStore(state_db or default_db, readonly=True)
    try:
        item = store.get_item(request.batch_id, request.item_id)
        staged_zotero_item_key = store.get_zotero_item_key(
            request.batch_id,
            request.item_id,
        )
    finally:
        store.close()
    if item is None:
        raise DependencyError("analysis batch item does not exist")
    if item.state not in {AnalysisState.VALIDATED, AnalysisState.REPAIRED}:
        raise DependencyError("analysis bundle has not passed conformance")
    if item.state.value != request.source_state:
        raise IdentityConflictError("commit request source_state differs from batch state")
    if (
        request.document.schema_version in {4, 5}
        and staged_zotero_item_key != request.zotero_item_key
    ):
        raise IdentityConflictError(
            "commit request Zotero item key differs from staged batch Zotero item key"
        )
    if item.stage_path is None:
        raise DependencyError("validated analysis bundle has no staging receipt")

    configured_stage = (stage_root or default_stage).absolute()
    staged = Path(item.stage_path)
    try:
        stage_base = configured_stage.resolve(strict=True)
        if configured_stage.is_symlink():
            raise ValueError("analysis stage root cannot be a symlink")
        current = stage_base
        relative = staged.resolve(strict=True).relative_to(stage_base)
        if relative.parts != (request.batch_id, request.item_id):
            raise ValueError("staged bundle identity differs from commit request")
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("staged bundle cannot traverse a symlink")
        markdown_path = staged / "analysis.md"
        canvas_path = staged / "analysis.canvas"
        baseline_path = staged / "analysis.baseline.json"
        for path in (markdown_path, canvas_path, baseline_path):
            if path.is_symlink() or not path.is_file():
                raise ValueError("staged bundle must contain three regular files")
        canvas = json.loads(canvas_path.read_text(encoding="utf-8"))
        if not isinstance(canvas, dict):
            raise TypeError("staged Canvas root must be an object")
        bundle = AnalysisBundle(
            markdown=markdown_path.read_text(encoding="utf-8"),
            canvas=canvas,
        )
        baseline = AnalysisBaseline.model_validate_json(
            baseline_path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValidationError,
        ValueError,
    ) as exc:
        raise SafetyRefusalError(str(exc)) from None

    try:
        receipt = commit_analysis_bundle(
            vault_root=vault_root,
            state_root=commit_state_root or state_home / "commit-state",
            request=request,
            bundle=bundle,
            baseline=baseline,
            provider_state_root=provider_state_root,
            source_registry=(
                KnowledgeSourceRegistry(_hub_state_root() / "hub" / "sources.json")
                if request.document.schema_version in {4, 5}
                else None
            ),
        )
    except AnalysisCommitPartialError as exc:
        raise PartialCompletionError(str(exc)) from None
    except AnalysisCommitSafetyError as exc:
        raise SafetyRefusalError(str(exc)) from None
    except AnalysisCommitConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    except AnalysisCommitError as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2))


@analysis.command(name="apply-change-set")
@click.option(
    "--change-set",
    "change_set_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Explicit JSON change conforming to knowledge-change-set.schema.json.",
)
@click.option(
    "--provider-state-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Existing root containing the authoritative Knowledge provider snapshot.",
)
def analysis_apply_change_set(
    change_set_path: Path,
    provider_state_root: Path,
) -> None:
    """CAS-apply one explicit change to the provider manifest and catalog."""
    from pydantic import ValidationError

    from scholar_workflow.analysis.apply_changes import (
        KnowledgeApplyConflict,
        KnowledgeApplyError,
        KnowledgeApplySafetyError,
        apply_knowledge_change_set,
    )
    from scholar_workflow.analysis.models import KnowledgeChangeSet

    try:
        change_set = KnowledgeChangeSet.model_validate_json(
            change_set_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise InputError(str(exc)) from None
    try:
        receipt = apply_knowledge_change_set(
            state_root=provider_state_root,
            change_set=change_set,
        )
    except KnowledgeApplySafetyError as exc:
        raise SafetyRefusalError(str(exc)) from None
    except KnowledgeApplyConflict as exc:
        raise IdentityConflictError(str(exc)) from None
    except KnowledgeApplyError as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2))


@analysis.command(name="audit-knowledge")
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Explicit no-discovery inventory conforming to knowledge-audit-manifest.schema.json.",
)
@click.option(
    "--vault-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--catalog-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Optional explicit root for catalog_path; defaults to the Vault root.",
)
@click.option(
    "--commit-state-root",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Explicit root for analysis commit receipt paths in the audit manifest.",
)
def analysis_audit_knowledge(
    manifest_path: Path,
    vault_root: Path,
    catalog_root: Path | None,
    commit_state_root: Path | None,
) -> None:
    """Audit explicit Knowledge objects and projections without writing any source."""
    from pydantic import ValidationError

    from scholar_workflow.analysis.audit import audit_knowledge_manifest
    from scholar_workflow.analysis.models import KnowledgeAuditManifest

    try:
        manifest = KnowledgeAuditManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        report = audit_knowledge_manifest(
            vault_root,
            manifest,
            catalog_root=catalog_root,
            commit_state_root=commit_state_root,
        )
    except (OSError, UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise InputError(str(exc)) from None
    click.echo(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


@main.group()
def experiment() -> None:
    """Create and validate local-first Run, Attempt, Target, and Artifact records."""


@experiment.command(name="new-run")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--run-script", type=click.Path(path_type=Path), required=True)
@click.option("--resolved-config", type=click.Path(path_type=Path), required=True)
@click.option("--dataset-manifest", type=click.Path(path_type=Path), required=True)
@click.option("--dataset-id", required=True)
@click.option("--dataset-version", required=True)
@click.option("--dataset-split", required=True)
@click.option("--seed", type=int, required=True)
@click.option("--environment-definition", type=click.Path(path_type=Path), required=True)
def experiment_new_run(
    project_root: Path,
    run_id: str,
    run_script: Path,
    resolved_config: Path,
    dataset_manifest: Path,
    dataset_id: str,
    dataset_version: str,
    dataset_split: str,
    seed: int,
    environment_definition: Path,
) -> None:
    """Snapshot one machine-neutral recipe into a new Run."""
    from scholar_workflow.project import ExperimentError, create_run

    try:
        result = create_run(
            project_root,
            run_id=run_id,
            run_script=run_script,
            resolved_config=resolved_config,
            dataset_manifest=dataset_manifest,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_split=dataset_split,
            seed=seed,
            environment_definition=environment_definition,
        )
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="target-add")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--spec", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
def experiment_target_add(project_root: Path, spec: Path) -> None:
    """Validate and register one explicit local or SSH Target profile."""
    from scholar_workflow.project import ExperimentError, register_target

    try:
        result = register_target(project_root, spec)
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="new-attempt")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--attempt-id", required=True)
@click.option("--target-id", required=True)
def experiment_new_attempt(
    project_root: Path,
    run_id: str,
    attempt_id: str,
    target_id: str,
) -> None:
    """Create an Attempt and freeze its Run recipe."""
    from scholar_workflow.project import ExperimentError, create_attempt

    try:
        result = create_attempt(
            project_root,
            run_id=run_id,
            attempt_id=attempt_id,
            target_id=target_id,
        )
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="finalize-attempt")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--attempt-id", required=True)
@click.option(
    "--status",
    type=click.Choice(["succeeded", "failed", "interrupted"]),
    required=True,
)
@click.option("--exit-code", type=int, required=True)
@click.option(
    "--actual-json",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--output-inventory",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def experiment_finalize_attempt(
    project_root: Path,
    run_id: str,
    attempt_id: str,
    status: str,
    exit_code: int,
    actual_json: Path,
    output_inventory: Path | None,
) -> None:
    """Finalize an Attempt from an explicit observed-runtime JSON record."""
    from scholar_workflow.project import ExperimentError, finalize_attempt

    try:
        actual = json.loads(actual_json.read_text(encoding="utf-8"))
        if not isinstance(actual, dict):
            raise TypeError("actual-json must contain one JSON object")
        result = finalize_attempt(
            project_root,
            run_id=run_id,
            attempt_id=attempt_id,
            status=status,
            exit_code=exit_code,
            actual=actual,
            output_inventory=output_inventory,
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ExperimentError,
        TypeError,
        ValueError,
    ) as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="start-attempt")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--attempt-id", required=True)
def experiment_start_attempt(project_root: Path, run_id: str, attempt_id: str) -> None:
    """Record the start time of a planned Attempt without launching it."""
    from scholar_workflow.project import ExperimentError, start_attempt

    try:
        result = start_attempt(project_root, run_id=run_id, attempt_id=attempt_id)
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="validate")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
def experiment_validate(project_root: Path) -> None:
    """Validate every local Run, Attempt, Target, Artifact, and checksum."""
    from scholar_workflow.project import ExperimentError, validate_project

    try:
        result = validate_project(project_root)
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="promote")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--attempt-id", required=True)
@click.option("--source", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True)
@click.option("--destination", required=True)
@click.option(
    "--role",
    type=click.Choice(
        [
            "report", "metrics", "parameters", "point-cloud", "image", "video",
            "checkpoint", "log", "intermediate", "other",
        ]
    ),
    required=True,
)
@click.option(
    "--retention",
    type=click.Choice(["local-required", "local-selected"]),
    required=True,
)
@click.option("--remote-source")
def experiment_promote(
    project_root: Path,
    run_id: str,
    attempt_id: str,
    source: Path,
    destination: str,
    role: str,
    retention: str,
    remote_source: str | None,
) -> None:
    """Copy and checksum one selected artifact; backup remains unverified."""
    from scholar_workflow.project import ExperimentError, promote_artifact

    try:
        result = promote_artifact(
            project_root,
            run_id=run_id,
            attempt_id=attempt_id,
            source=source,
            destination=destination,
            role=role,
            retention=retention,
            remote_source=remote_source,
        )
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="record-remote")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
@click.option("--run-id", required=True)
@click.option("--attempt-id", required=True)
@click.option("--remote-source", required=True)
@click.option(
    "--role",
    type=click.Choice(
        [
            "report", "metrics", "parameters", "point-cloud", "image", "video",
            "checkpoint", "log", "intermediate", "other",
        ]
    ),
    required=True,
)
def experiment_record_remote(
    project_root: Path,
    run_id: str,
    attempt_id: str,
    remote_source: str,
    role: str,
) -> None:
    """Record a large remote artifact as manifest-only."""
    from scholar_workflow.project import ExperimentError, record_manifest_only_artifact

    try:
        result = record_manifest_only_artifact(
            project_root,
            run_id=run_id,
            attempt_id=attempt_id,
            remote_source=remote_source,
            role=role,
        )
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="index")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
def experiment_index(project_root: Path) -> None:
    """Rebuild the optional experiment index from authoritative Run bundles."""
    from scholar_workflow.project import ExperimentError, rebuild_index

    try:
        result = rebuild_index(project_root)
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


@experiment.command(name="migrate-plan")
@click.option("--project-root", type=click.Path(path_type=Path), default=".", show_default=True)
def experiment_migrate_plan(project_root: Path) -> None:
    """Inspect legacy experiment directories without writing or moving anything."""
    from scholar_workflow.project import ExperimentError
    from scholar_workflow.project.experiments import legacy_migration_plan

    try:
        result = legacy_migration_plan(project_root)
    except ExperimentError as exc:
        raise _experiment_error(exc) from None
    _experiment_result(result)


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
    from datetime import UTC, datetime

    return {
        "job_id": rows[0]["job_id"] if rows else "00000000-0000-0000-0000-000000000000",
        "plan_id": rows[0].get("plan_id") if rows else None,
        "from_agent": "precompact",
        "to_agent": "precompact",
        "last_success_state": rows[0]["state"] if rows else "received",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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


@main.group(name="knowledge")
def knowledge() -> None:
    """Preview and explicitly register knowledge folders without Hub."""


@knowledge.command(name="preview")
@click.argument("root", type=click.Path(path_type=Path))
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_preview(root: Path, fmt: str, language: str) -> None:
    """Zero-write Source/Field preview of exactly the chosen absolute folder."""
    from scholar_workflow.knowledge.fields import (
        FieldRegistryError,
        FieldService,
        KnowledgeSourceRegistry,
    )
    from scholar_workflow.knowledge.presentation import preview_markdown

    # Retain the existing registry location; do not create a second fact store.
    state_root = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    try:
        preview = FieldService(KnowledgeSourceRegistry(state_root / "hub" / "sources.json")).preview(root)
    except (FieldRegistryError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps({
            "schema_version": 1,
            "product_version": __version__,
            "status": "preview-only",
            "preview": preview.model_dump(mode="json", exclude={"candidate_token"}),
        }, ensure_ascii=False, indent=2))
    else:
        click.echo(preview_markdown(preview, language=language))


def _local_field_service():
    from scholar_workflow.knowledge.fields import FieldService, KnowledgeSourceRegistry

    state_root = Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))
    return FieldService(KnowledgeSourceRegistry(state_root / "hub" / "sources.json"))


def _paper_selection_options(command):
    for name in ("source-id", "field-id", "item-key", "attachment-key", "segment"):
        command = click.option("--" + name, required=True)(command)
    return click.option("--language", type=click.Choice(["en", "zh"]), default="en")(command)


@knowledge.command(name="paper-plan")
@_paper_selection_options
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def knowledge_paper_plan(fmt: str, **selection) -> None:
    """Zero-write, digest-bound plan for one new paper owner and navigation entry."""
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
    from scholar_workflow.knowledge.presentation import _text
    from scholar_workflow.workflows.register_paper import paper_plan

    try:
        with ZoteroLocalAdapter() as zotero:
            plan = paper_plan(_local_field_service().registry, zotero, **selection)
    except (RuntimeError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        zh = selection["language"] == "zh"
        click.echo("# 单篇论文登记方案\n" if zh else "# Paper registration plan\n")
        click.echo(_text(plan["paper"]["title"]) + "\n")
        click.echo(f"{'新增资料笔记' if zh else 'New companion note'}: {plan['owner_path']}\n")
        click.echo(plan["note"])
        click.echo("确认摘要：" if zh else "Confirmation digest:")
        click.echo(plan["approved_digest"])
        click.echo("尚未写入；登记不等于分析或科学验收。" if zh else
                   "Nothing written; registration is not analysis or scientific acceptance.")


@knowledge.command(name="register-paper")
@_paper_selection_options
@click.option("--approved-digest", required=True)
@click.option("--yes", is_flag=True)
def knowledge_register_paper(approved_digest: str, yes: bool, **selection) -> None:
    """CAS-register one reviewed paper; repeat the exact request to resume its journal."""
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
    from scholar_workflow.workflows.register_paper import register_paper

    if not yes:
        click.confirm("登记已审阅的单篇论文？" if selection["language"] == "zh" else
                      "Register the reviewed paper?", abort=True, err=True)
    try:
        with ZoteroLocalAdapter() as zotero:
            result = register_paper(_local_field_service().registry, zotero,
                                    approved_digest=approved_digest, **selection)
    except (RuntimeError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


def _canvas_selection_options(command):
    for name in ("source-id", "field-id", "artifact-id"):
        command = click.option("--" + name, required=True)(command)
    return command


@knowledge.command(name="canvas-plan")
@_canvas_selection_options
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_canvas_plan(fmt: str, language: str, **selection) -> None:
    """Zero-write portable declaration plan for one already-owned analysis Canvas."""
    from scholar_workflow.workflows.register_canvas import canvas_plan

    try:
        plan = canvas_plan(_local_field_service().registry, **selection)
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        zh = language == "zh"
        click.echo("# Canvas 便携登记方案\n" if zh else "# Portable Canvas registration plan\n")
        click.echo(plan["artifact"]["vault_path"] + "\n")
        click.echo("只更新身份清单；不改正文、图或 provider。" if zh else
                   "Only the identity manifest changes; prose, graph and provider remain unchanged.")
        click.echo("已登记，无需改变。" if zh and plan["status"] == "unchanged" else
                   "Already declared; no change needed." if plan["status"] == "unchanged" else
                   "将新增单篇声明，其他行保留。" if zh else "Append one declaration; preserve other rows.")
        click.echo(("确认摘要：\n" if zh else "Confirmation digest:\n") + plan["approved_digest"])
        click.echo("尚未写入；不证明科学支持、人工评鉴或整库跨机恢复。" if zh else
                   "Nothing written; source support, human assessment and full cross-host recovery are not proven.")


@knowledge.command(name="register-canvas")
@_canvas_selection_options
@click.option("--approved-digest", required=True)
@click.option("--yes", is_flag=True)
def knowledge_register_canvas(approved_digest: str, yes: bool, **selection) -> None:
    """CAS-register one reviewed portable Canvas identity, with conditional replay."""
    from scholar_workflow.workflows.register_canvas import register_canvas

    if not yes:
        click.confirm("Register the reviewed Canvas declaration?", abort=True, err=True)
    try:
        result = register_canvas(_local_field_service().registry,
                                 approved_digest=approved_digest, **selection)
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2))


@knowledge.command(name="reproduction-plan")
@click.option("--source-id", required=True)
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_reproduction_plan(source_id: str, fmt: str, language: str) -> None:
    """Export one explicit Source's portable ownership and file checks, without writes."""
    from scholar_workflow.workflows.knowledge_reproduction import reproduction_plan

    try:
        result = reproduction_plan(_local_field_service().registry, source_id=source_id)
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        zh = language == "zh"
        package = result["package"]
        click.echo("# 知识归属复现输入\n" if zh else "# Knowledge reproduction input\n")
        click.echo(("Source：" if zh else "Source: ") + source_id)
        click.echo(("已核文件：" if zh else "Checked files: ") + str(len(package["files"])))
        click.echo(("需重新绑定阅读器：" if zh else "Reader rebinding required: ")
                   + str(len(package["reader_rebind_required"])))
        click.echo(("输入摘要：" if zh else "Input digest: ") + result["package_digest"])
        click.echo("零写入；尚未恢复目的地或完成人工/科学验收。机器输入使用 --format json。" if zh else
                   "Nothing written; destination not restored or human/source-approved. Use --format json for replay input.")


def _reproduction_restore_options(command):
    command = click.option("--source-id", required=True)(command)
    command = click.option("--package", required=True, type=click.Path(path_type=Path))(command)
    command = click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")(command)
    return click.option("--language", type=click.Choice(["en", "zh"]), default="en")(command)


def _reproduction_restore_summary(result, fmt, language, *, committed):
    if fmt == "json":
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    zh = language == "zh"
    click.echo("# 知识归属恢复\n" if zh else "# Knowledge ownership restoration\n")
    click.echo(("Source：" if zh else "Source: ") + result["source_id"])
    click.echo(("确认摘要：" if zh else "Confirmation digest: ") + result["approved_digest"])
    if committed:
        click.echo("已恢复归属；正文、Canvas 和便携清单未修改。" if zh else
                   "Ownership restored; prose, Canvas and portable manifests unchanged.")
    else:
        click.echo(("已核文件：" if zh else "Checked files: ") + str(len(result["files"])))
        click.echo("尚未写入；只会创建缺失的主机 provider 和恢复记录。" if zh else
                   "Nothing written; creates only missing host ownership and recovery records.")
    for reader in result["readers"]:
        labels = {"binding-matched": "阅读器身份匹配", "rebinding-required": "需要重新绑定阅读器",
                  "reader-unresolved": "阅读器未登记或不明确"}
        click.echo(reader["artifact_id"] + ": " + (labels[reader["status"]] if zh else reader["status"]))
    click.echo("阅读器实际打开、科学支持和人工评鉴尚未通过；不是已验证备份或全部复现完成。" if zh else
               "Reader launches, scientific support and human review remain unverified; not a verified backup or complete reproduction.")


@knowledge.command(name="restore-plan")
@_reproduction_restore_options
def knowledge_restore_plan(source_id, package, fmt, language):
    """Preview restoring exported ownership into one explicitly attached Source."""
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
    from scholar_workflow.workflows.knowledge_reproduction import restore_plan
    try:
        with ZoteroLocalAdapter() as zotero:
            result = restore_plan(_local_field_service().registry, zotero, source_id=source_id, package=package)
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    _reproduction_restore_summary(result, fmt, language, committed=False)


@knowledge.command(name="restore")
@_reproduction_restore_options
@click.option("--approved-digest", required=True)
@click.option("--yes", is_flag=True)
def knowledge_restore(source_id, package, fmt, language, approved_digest, yes):
    """Create missing ownership from the reviewed input, or resume its exact journal."""
    from scholar_workflow.adapters.zotero_local import ZoteroLocalAdapter
    from scholar_workflow.workflows.knowledge_reproduction import restore
    if not yes:
        click.confirm("恢复已审阅的知识归属？" if language == "zh" else
                      "Restore the reviewed ownership?", abort=True, err=True)
    try:
        with ZoteroLocalAdapter() as zotero:
            result = restore(_local_field_service().registry, zotero, source_id=source_id,
                             package=package, approved_digest=approved_digest)
    except (RuntimeError, OSError, ValueError, TypeError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    _reproduction_restore_summary(result, fmt, language, committed=True)


@knowledge.command(name="registration-plan")
@click.argument("root", type=click.Path(path_type=Path))
@click.option("--field-root", help="Exactly one relative root from knowledge preview.")
@click.option("--existing-source", is_flag=True, help="Attach all existing portable Fields to this host.")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_registration_plan(root: Path, field_root: str | None,
                                existing_source: bool, fmt: str, language: str) -> None:
    """Zero-write plan for one explicit Field, or an existing portable Source."""
    from scholar_workflow.knowledge.fields import FieldRegistryError
    from scholar_workflow.knowledge.registration import plan_markdown, registration_plan

    try:
        plan = registration_plan(_local_field_service(), root,
                                 field_root=field_root, existing_source=existing_source)
    except (FieldRegistryError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps(plan.payload, ensure_ascii=False, indent=2) if fmt == "json"
               else plan_markdown(plan.payload, language=language))


@knowledge.command(name="register")
@click.argument("root", type=click.Path(path_type=Path))
@click.option("--field-root")
@click.option("--existing-source", is_flag=True)
@click.option("--approved-digest", required=True, help="Exact digest from the reviewed plan.")
@click.option("--yes", is_flag=True, help="Confirm the already reviewed digest noninteractively.")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_register(root: Path, field_root: str | None, existing_source: bool,
                       approved_digest: str, yes: bool, fmt: str, language: str) -> None:
    """Register only the reviewed scope; reject changed bytes and legacy cutovers."""
    from scholar_workflow.knowledge.fields import FieldRegistryError
    from scholar_workflow.knowledge.registration import fields_markdown, register

    if not yes:
        click.confirm("确认登记已审阅的目录？" if language == "zh" else
                      "Register the reviewed folder scope?", abort=True, err=True)
    try:
        service = _local_field_service()
        manifest = register(service, root, field_root=field_root,
                            existing_source=existing_source, approved_digest=approved_digest)
    except (FieldRegistryError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps({"schema_version": 1, "status": "registered",
                               "manifest": manifest.model_dump(mode="json")},
                              ensure_ascii=False, indent=2))
    else:
        click.echo("登记完成；没有改写正文或 Canvas。" if language == "zh" else
                   "Registered; no prose or Canvas was rewritten.")
        click.echo(fields_markdown([row for row in service.list_fields()
                                    if row["source_id"] == manifest.source_id], language=language))


@knowledge.command(name="list")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_list(fmt: str, language: str) -> None:
    """Read the single existing registry and portable navigation manifests."""
    from scholar_workflow.knowledge.fields import FieldRegistryError
    from scholar_workflow.knowledge.registration import fields_markdown

    try:
        fields = _local_field_service().list_fields()
    except (FieldRegistryError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps({"schema_version": 1, "fields": fields}, ensure_ascii=False, indent=2)
               if fmt == "json" else fields_markdown(fields, language=language))


@knowledge.command(name="reader")
@click.argument("source_id")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_reader(source_id: str, fmt: str, language: str) -> None:
    """Resolve the native reader Vault without expanding Source file permissions."""
    from scholar_workflow.workflows.knowledge_open import reader_info

    try:
        info = reader_info(_local_field_service().registry, source_id)
    except (RuntimeError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    if fmt == "json":
        click.echo(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        zh = language == "zh"
        click.echo("# Obsidian 打开位置\n" if zh else "# Obsidian reader destination\n")
        click.echo(f"{'所选目录' if zh else 'Selected folder'}: {info['source_root']}")
        click.echo(f"{'阅读器 Vault' if zh else 'Reader Vault'}: {info['reader_vault_root']}")
        click.echo("父 Vault 只提供打开位置；文件授权仍限于所选目录。" if zh else
                   "The parent Vault only routes opens; file authorization remains Source-scoped.")


@knowledge.command(name="open")
@click.argument("source_id")
@click.argument("relative_path")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["en", "zh"]), default="en")
def knowledge_open(source_id: str, relative_path: str, fmt: str, language: str) -> None:
    """Open an existing Source-relative Markdown or Canvas in Obsidian."""
    from scholar_workflow.workflows.knowledge_open import open_document

    try:
        result = open_document(_local_field_service().registry, source_id, relative_path)
    except (RuntimeError, OSError, ValueError) as exc:
        raise SafetyRefusalError(str(exc)) from None
    click.echo(json.dumps(result, ensure_ascii=False, indent=2) if fmt == "json" else
               (f"已请求 Obsidian 打开：{relative_path}；实际显示仍待人工评鉴。" if language == "zh" else
                f"Requested Obsidian open: {relative_path}; visible result awaits human assessment."))
