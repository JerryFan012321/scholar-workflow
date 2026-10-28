"""Thin commands for file-backed research exploration."""
from __future__ import annotations

import json
import os
import subprocess
import webbrowser
from pathlib import Path

import click
import yaml

from scholar_workflow.workflows.exploration_assets import (
    include_resource_links as _include_resource_links,
)

from .exploration import ExplorationError, ExplorationStore, query, render_markdown, validate
from .exploration_environment import ExplorerEnvironment


class ExplorationCLIError(click.ClickException):
    def __init__(self, error):
        super().__init__(str(error))
        self.exit_code = getattr(error, "code", 2)


def _spec(path):
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Specification exceeds 2 MiB.")
        result = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise TypeError("Specification must be an object.")
        return result
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError):
        raise click.BadParameter("Cannot read a bounded YAML/JSON object.") from None


def _emit(value):
    click.echo(json.dumps(value, ensure_ascii=False, indent=2))


def environment_options(function):
    """Keep the same explicit boundary on every exploration command."""
    for option in reversed([
        click.option("--environment", type=click.Choice(["personal", "test"]),
                     default="personal", show_default=True),
        click.option("--state-root", type=click.Path(file_okay=False, path_type=Path),
                     help="Independent state directory; required in test mode."),
        click.option("--test-root", multiple=True,
                     type=click.Path(exists=True, file_okay=False, path_type=Path),
                     help="Allowed test Vault/folder; repeat for explicitly allowed roots."),
    ]):
        function = option(function)
    return function


def _environment(root, environment, state_root, test_root, *inputs):
    context = ExplorerEnvironment(environment, state_root, tuple(test_root))
    context.check_root(root)
    context.check_registry()
    if context.is_test:
        for path in inputs:
            if path is not None:
                context.check_root(path.parent)
                if path.is_symlink():
                    raise ExplorationError("Test input cannot be a symlink", 7)
    return context


def _existing_paper_references(current, proposed):
    """Generic file edits may retain known papers; new units use the provider import."""
    proposed = validate(proposed)
    known = {(work["entity_ref"]["source_id"], work["entity_ref"]["object_id"]): work
             for work in current["works"] if work["kind"] == "paper"}
    for work in proposed["works"]:
        if work["kind"] != "paper":
            continue
        identity = work["entity_ref"]["source_id"], work["entity_ref"]["object_id"]
        if identity not in known:
            raise ExplorationError(
                "New paper references require exploration-import from an existing registered "
                "paper unit; generic init/apply only edits already referenced papers."
            )
        if work["assets"] != known[identity]["assets"]:
            raise ExplorationError(
                "Paper-unit assets are read-only in generic init/apply; use exploration-import "
                "to refresh declared assets or the existing paper-asset maintenance operation."
            )
    return proposed


@click.command("exploration-init")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@click.option("--spec", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@environment_options
def exploration_init(root, spec, environment, state_root, test_root):
    """Create only the outer exploration manifest, leaving paper units untouched."""
    try:
        _environment(root, environment, state_root, test_root, spec)
        store = ExplorationStore(root)
        current = store.load()
        if current["revision"] is not None:
            raise ExplorationError("Exploration already exists; use exploration-apply.", 5)
        proposed = _existing_paper_references(
            current["data"], _spec(spec) if spec else current["data"],
        )
        _emit(store.save(proposed, expected_revision=None))
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None


@click.command("exploration-apply")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@click.option("--spec", required=True,
              type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--expected-revision", required=True)
@environment_options
def exploration_apply(root, spec, expected_revision, environment, state_root, test_root):
    """Save a validated manifest only against its exact current revision."""
    try:
        _environment(root, environment, state_root, test_root, spec)
        store = ExplorationStore(root)
        proposed = _existing_paper_references(store.load()["data"], _spec(spec))
        _emit(store.save(proposed, expected_revision=expected_revision))
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None


@click.command("exploration-query")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@click.option("--selection", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@environment_options
def exploration_query(root, selection, environment, state_root, test_root):
    """Read and query joint research records without initializing files."""
    try:
        _environment(root, environment, state_root, test_root, selection)
        _emit(query(ExplorationStore(root).load()["data"], _spec(selection) if selection else {}))
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None


@click.command("exploration-export")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@environment_options
def exploration_export(root, environment, state_root, test_root):
    """Print readable Obsidian navigation; never replace paper files."""
    try:
        _environment(root, environment, state_root, test_root)
        click.echo(render_markdown(root, ExplorationStore(root).load()["data"]))
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None


@click.command("exploration-import")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@click.option("--source-id", required=True)
@click.option("--field-id", required=True)
@click.option("--apply", "apply_changes", is_flag=True,
              help="Save references only; without this flag, print a zero-write preview.")
@click.option("--expected-revision", help="Current exploration revision, or 'absent'.")
@environment_options
def exploration_import(root, source_id, field_id, apply_changes, expected_revision,
                       environment, state_root, test_root):
    """Reference the registered Field's declared paper assets without rewriting them."""
    from scholar_workflow.knowledge.exploration_import import import_paper_units
    from scholar_workflow.knowledge.fields import FieldRegistryError, KnowledgeSourceRegistry
    from scholar_workflow.workflows.field_paper_units import field_paper_units

    if apply_changes and expected_revision is None:
        raise click.UsageError("--apply requires --expected-revision (or 'absent').")
    try:
        context = _environment(root, environment, state_root, test_root)
        path = context.registry_path
        registry = KnowledgeSourceRegistry(path)
        before = registry.revision()
        registrations = registry.load_document()
        options = {"resolve_reader": False} if context.is_test else {}
        if context.is_test:
            options["root_validator"] = context.check_root
        payload = field_paper_units(path, source_id=source_id, field_id=field_id,
                                    include_resource_links=True, **options)
        if not context.is_test:
            payload = _include_resource_links(payload)
        if before != registry.revision():
            raise ExplorationError("Source registration changed; reload the selection.", 5)
        folders = {folder.folder_id: folder.root for folder in registrations.folders
                   if folder.enabled and "read" in folder.capabilities}
        source_roots = {source.source_id: folders[source.folder_id]
                        for source in registrations.sources
                        if source.enabled and "read" in source.capabilities
                        and source.folder_id in folders}
        store = ExplorationStore(root)
        current = store.load()
        proposed = import_paper_units(root, current["data"], payload, source_roots=source_roots)
        if apply_changes:
            _emit(store.save(proposed, expected_revision=None if expected_revision == "absent"
                             else expected_revision))
        else:
            _emit({"expected_revision": current["revision"] or "absent", "data": proposed,
                   "source_status": payload.get("status"), "written": False})
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None
    except (FieldRegistryError, OSError, ValueError):
        raise click.ClickException("Registered paper assets could not be resolved safely.") from None


def open_explorer(url):
    """Use cmux only as the browser destination, with a normal-browser fallback."""
    if os.environ.get("CMUX_WORKSPACE_ID"):
        try:
            result = subprocess.run(["cmux", "browser", "open", url], shell=False,
                                    capture_output=True, timeout=10, check=False)
            if result.returncode == 0:
                return "cmux"
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "browser" if webbrowser.open(url) else "manual"


@click.command("explore")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False,
                                                     path_type=Path))
@click.option("--port", type=click.IntRange(0, 65535), default=0, show_default=True)
@click.option("--no-open", is_flag=True, help="Print the session URL without opening a browser.")
@click.option("--source-id", help="Read existing registered paper packages without saving an exploration.")
@click.option("--field-id", help="Field of the explicitly selected Source; requires --source-id.")
@environment_options
def explore(root, port, no_open, source_id, field_id, environment, state_root, test_root):
    """Open editable dimensions, evidence relations and asset navigation locally.

    The service runs visibly in this terminal; Ctrl-C stops it.
    """
    from scholar_workflow.adapters.knowledge_explorer import make_server

    if bool(source_id) != bool(field_id):
        raise click.UsageError("Read-only browsing requires both --source-id and --field-id.")
    try:
        context = _environment(root, environment, state_root, test_root)
        # Refuse a malformed existing manifest before opening a window.
        ExplorationStore(root).load()
        reading = None
        if source_id:
            from scholar_workflow.workflows.exploration_references import (
                ExplorationReferenceService,
                RegisteredReadingStore,
            )
            service = ExplorationReferenceService(context.registry_path,
                resolve_reader=not context.is_test, enrich_resources=not context.is_test,
                root_validator=context.check_root if context.is_test else None)
            reading = RegisteredReadingStore(root, source_id, field_id, service=service)
            reading.load()
        server, token = make_server(root, port=port, reading_store=reading, environment=context)
        url = f"http://127.0.0.1:{server.server_address[1]}/#token={token}"
        click.echo(f"Knowledge Explorer: {url}")
        click.echo(f"Environment: {context.mode}; folder: {root.name}")
        click.echo("Stop: Ctrl-C. The session token expires when this process stops.")
        if not no_open:
            click.echo(f"Open destination: {open_explorer(url)}")
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        click.echo("Knowledge Explorer stopped.")
    except ExplorationError as exc:
        raise ExplorationCLIError(exc) from None
    except OSError:
        raise click.ClickException("Could not start the local explorer.") from None


def register_commands(group):
    for command in (explore, exploration_init, exploration_apply, exploration_import,
                    exploration_query, exploration_export):
        group.add_command(command)
