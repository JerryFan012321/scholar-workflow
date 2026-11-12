"""Host-neutral submission and opening commands for recommendation candidates."""
from __future__ import annotations

import html
import json
import sys
import webbrowser
from functools import wraps
from pathlib import Path

import click

from scholar_workflow.research.cli import ResearchCommandError, _spec, root
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import lifecycle
from scholar_workflow.research.recommendations.refresh import refresh_candidate_metrics


def guarded(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ResearchError as exc:
            raise ResearchCommandError(exc) from None
        except OSError:
            raise ResearchCommandError(ResearchError("Recommendation state is unavailable.", 7)) from None
    return wrapped


def _read_input(input_path: str) -> dict:
    if input_path != "-":
        return _spec(Path(input_path), limit=2 * 1024 * 1024)
    raw = sys.stdin.read(2 * 1024 * 1024 + 1)
    if len(raw.encode("utf-8")) > 2 * 1024 * 1024:
        raise ResearchError("Recommendation submission exceeds the input limit.", 2)

    def unique(pairs):
        record = {}
        for key, value in pairs:
            if key in record:
                raise ValueError()
            record[key] = value
        return record

    try:
        payload = json.loads(raw, object_pairs_hook=unique,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        if not isinstance(payload, dict):
            raise ValueError()
        return payload
    except (ValueError, UnicodeError, RecursionError):
        raise ResearchError("Expected UTF-8 JSON with unique keys and finite numbers.", 2) from None


def _json(payload: dict) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def _store(context):
    from scholar_workflow.research.recommendations.store import RecommendationStore
    return RecommendationStore(context["state_dir"])


@click.group()
@click.option("--profile", type=click.Choice(["personal", "test"]), default="personal",
              show_default=True, help="Separate personal candidates from test fixtures.")
@click.pass_context
def recommendations(ctx, profile):
    """Submit papers, project pages and blogs, or open the recommendation page."""
    ctx.ensure_object(dict)
    ctx.obj.update(profile=profile, state_dir=root() / "recommendations" / profile)


@recommendations.command(name="schema")
@guarded
def schema():
    """Print the installed versioned JSON submission contract without creating state."""
    from scholar_workflow.research.recommendations.store import load_submission_schema
    _json(load_submission_schema())


@recommendations.command(name="submit")
@click.option("--input", "input_path", required=True, help="Submission JSON file, or - for stdin.")
@click.option("--refresh-metrics", is_flag=True, help="Explicitly fetch public GitHub/Hugging Face counts for accepted candidates.")
@click.pass_obj
@guarded
def submit(context, input_path, refresh_metrics):
    """Submit candidates; preserve producer provenance and human decisions."""
    # Input syntax is checked before opening or initializing a state store.
    record = _read_input(input_path)
    store = _store(context)
    payload = store.submit(record)
    if refresh_metrics:
        refreshes = []
        identifiers = dict.fromkeys(item["candidate_id"] for item in payload["receipts"]
                                    if item["status"] in {"accepted", "duplicate"})
        for identifier in identifiers:
            try:
                row = refresh_candidate_metrics(store, identifier)
                refreshes.append({"candidate_id": identifier, **row["metric_refresh"]})
            except ResearchError as exc:
                refreshes.append({"candidate_id": identifier, "status": "failed", "exit_code": exc.exit_code})
        payload["metric_refreshes"] = refreshes
    _json(payload)
    states = {entry["status"] for entry in payload.get("receipts", [])}
    failures = states & {"conflict", "invalid", "failed"}
    if failures:
        code = 6 if states & {"accepted", "duplicate"} else (5 if "conflict" in failures else 2)
        click.get_current_context().exit(code)


@recommendations.command(name="revise-content")
@click.option("--input", "input_path", required=True, help="Content correction JSON file, or - for stdin.")
@click.pass_obj
@guarded
def revise_content(context, input_path):
    """Correct an existing reading body without submitting another recommendation."""
    payload = _read_input(input_path)
    if set(payload) != {"candidate_id", "expected_revision", "changes", "updated_by"}:
        raise ResearchError("Content correction needs candidate_id, expected_revision, changes and updated_by.")
    _json(_store(context).revise_content(**payload))


@recommendations.command(name="content-history")
@click.option("--candidate-id", required=True)
@click.pass_obj
@guarded
def content_history(context, candidate_id):
    """Read attributed before/after content corrections from the selected pool."""
    _json(_store(context).content_revision_history(candidate_id))


@recommendations.command(name="list")
@click.option("--query", default="")
@click.option("--kind", type=click.Choice(["paper", "project", "blog"]))
@click.option("--tag")
@click.option("--producer-id")
@click.option("--decision", type=click.Choice(["unread", "saved", "selected", "ignored"]))
@click.option("--since", help="Published on or after this ISO date, YYYY-MM-DD.")
@click.option("--sort", type=click.Choice(["newest", "oldest", "published", "agent"]), default="newest")
@click.option("--limit", type=click.IntRange(1, 100), default=40)
@click.option("--offset", type=click.IntRange(min=0), default=0)
@click.option("--format", "fmt", type=click.Choice(["json", "md"]), default="md")
@click.pass_obj
@guarded
def candidates(context, query, kind, tag, producer_id, decision, since, sort, limit, offset, fmt):
    """List shared candidates, with producer and topic matched on the same recommendation."""
    payload = _store(context).list_candidates(query=query, kind=kind, tag=tag,
        producer_id=producer_id, decision=decision, since=since, sort=sort, limit=limit, offset=offset)
    if fmt == "json":
        _json(payload)
        return
    click.echo(f"推荐候选：{payload['total']} 项" + ("（测试环境）" if context["profile"] == "test" else ""))
    for item in payload["items"]:
        resource = item["resource"]
        title = html.escape(resource["title"]).replace("[", "\\[").replace("]", "\\]")
        click.echo(f"\n- [{title}]({resource['url']})")
        if item.get("tags"):
            click.echo("  领域：" + "、".join(item["tags"]))
    if not payload["items"]:
        click.echo("当前没有匹配项。agent可通过 recommendations submit 提交候选。")


@recommendations.group(name="context")
def context_commands():
    """Read or maintain shared context for external recommendation agents."""


def _ranking(context):
    from scholar_workflow.research.recommendations.ranking import RecommendationRanking
    return RecommendationRanking(_store(context))


@context_commands.command(name="show")
@click.pass_obj
@guarded
def context_show(context):
    """Show maintained notes and the current external ranking status."""
    _json(_ranking(context).context())


@context_commands.command(name="snapshot")
@click.pass_obj
@guarded
def context_snapshot(context):
    """Export live candidates, reasons, feedback, metrics and requirements with a digest."""
    _json(_ranking(context).snapshot())


@context_commands.command(name="save")
@click.option("--input", "input_path", required=True)
@click.pass_obj
@guarded
def context_save(context, input_path):
    """Save shared notes with their expected revision and human/agent attribution."""
    payload = _read_input(input_path)
    if set(payload) != {"content", "expected_revision", "updated_by"}:
        raise ResearchError("Shared context needs content, expected_revision and updated_by.")
    _json(_ranking(context).save_context(**payload))


@recommendations.group(name="ranking")
def ranking_commands():
    """Accept and inspect explicit ordering computed by an external agent."""


@ranking_commands.command(name="submit")
@click.option("--input", "input_path", required=True)
@click.pass_obj
@guarded
def ranking_submit(context, input_path):
    """Save a complete ordered candidate list, bound to its input snapshot and revision."""
    _json(_ranking(context).submit(_read_input(input_path)))


@ranking_commands.command(name="history")
@click.pass_obj
@guarded
def ranking_history(context):
    """Read recorded external rankings without invoking a model or provider."""
    _json(_ranking(context).history())


@recommendations.command(name="refresh-metrics")
@click.option("--candidate-id", multiple=True, required=True, help="Existing candidate ID; repeat for selected candidates.")
@click.pass_obj
@guarded
def refresh_metrics(context, candidate_id):
    """Read public counts for explicitly selected candidates without resubmitting them."""
    store = _store(context)
    results = []
    for identifier in dict.fromkeys(candidate_id):
        try:
            row = refresh_candidate_metrics(store, identifier)
            checks = row["metric_refresh"]["checks"]
            result = "complete" if checks and all(item["status"] == "ok" for item in checks) else "partial" if checks else "no_targets"
            results.append({"candidate_id": identifier, "status": result, "metrics": row["metrics"], "checks": checks})
        except ResearchError as exc:
            results.append({"candidate_id": identifier, "status": "failed", "exit_code": exc.exit_code})
    _json({"profile": context["profile"], "results": results})
    if any(item["status"] in {"failed", "partial"} for item in results):
        click.get_current_context().exit(6)


@recommendations.command(name="handoff")
@click.pass_obj
@guarded
def handoff(context):
    """Export selected, abstract-reviewed candidates for ingest-resource; never ingest here."""
    _json({**_store(context).prepare_handoff(), "profile": context["profile"]})


@recommendations.command(name="status")
@click.pass_obj
@guarded
def status(context):
    """Show the identified profile service; do not print browser authentication."""
    _json(lifecycle.status(context["state_dir"], context["profile"]))


@recommendations.command(name="start")
@click.option("--port", type=click.IntRange(1024, 65535), help="Save a different stable local port.")
@click.pass_obj
@guarded
def start(context, port):
    """Start or reuse this profile's identified local recommendation service."""
    lifecycle.start(context["state_dir"], context["profile"], port=port)
    _json(lifecycle.status(context["state_dir"], context["profile"]))


@recommendations.command(name="open")
@click.option("--no-browser", is_flag=True, help="Print the plain local URL instead of opening it.")
@click.pass_obj
@guarded
def open_page(context, no_browser):
    """Start the installed page and open it in the system browser."""
    record = lifecycle.start(context["state_dir"], context["profile"])
    url = f"http://127.0.0.1:{record['port']}/"
    if no_browser:
        click.echo(url)
    elif webbrowser.open(url):
        click.echo("已打开推荐页面。" + ("当前为测试环境。" if context["profile"] == "test" else ""))
    else:
        click.echo("浏览器未能自动打开。请在本机打开：\n" + url)


@recommendations.command(name="stop")
@click.pass_obj
@guarded
def stop(context):
    """Stop only this profile's identified service; preserve all candidates."""
    _json(lifecycle.stop(context["state_dir"], context["profile"]))


@recommendations.command(name="restart")
@click.pass_obj
@guarded
def restart(context):
    """Restart this pool at its saved address, preserving candidates."""
    lifecycle.stop(context["state_dir"], context["profile"])
    lifecycle.start(context["state_dir"], context["profile"])
    _json(lifecycle.status(context["state_dir"], context["profile"]))


@recommendations.command(name="serve-managed", hidden=True)
@click.pass_obj
@guarded
def serve_managed(context):
    """Run in launchd; generate credentials in memory, never in its plist."""
    import secrets

    lifecycle.serve(context["state_dir"], context["profile"], {
        "generation": secrets.token_urlsafe(24), "token": secrets.token_urlsafe(32)})


@recommendations.command(name="serve", hidden=True)
@click.pass_obj
@guarded
def serve(context):
    """Run the private owned child process; credentials arrive through stdin."""
    lifecycle.serve(context["state_dir"], context["profile"], _read_input("-"))


@recommendations.group(name="requirements")
def requirement_commands():
    """Edit shared free-text recommendation requirements, preserving every version."""


@requirement_commands.command(name="list")
@click.option("--source-id", help="List only requirements explicitly assigned to this registered source.")
@click.pass_obj
@guarded
def requirements_list(context, source_id):
    _json(_store(context).list_requirements(source_id=source_id))


@requirement_commands.command(name="show")
@click.argument("requirement_id")
@click.option("--revision", type=click.IntRange(min=1))
@click.pass_obj
@guarded
def requirements_show(context, requirement_id, revision):
    _json(_store(context).get_requirement(requirement_id, revision))


@requirement_commands.command(name="save")
@click.option("--input", "input_path", required=True,
              help="JSON with requirement_id,title,content,enabled,expected_revision,updated_by; optional source_id; or - for stdin.")
@click.pass_obj
@guarded
def requirements_save(context, input_path):
    payload = _read_input(input_path)
    expected = {"requirement_id", "title", "content", "enabled", "expected_revision", "updated_by"}
    if not expected <= set(payload) <= expected | {"source_id"}:
        raise ResearchError("A requirement save needs its identity, text, enabled state, revision and declared editing source.")
    _json(_store(context).save_requirement(**payload))


@recommendations.group(name="tags")
def tag_commands():
    """Read or edit candidate tags without changing original recommendations."""


@tag_commands.command(name="set")
@click.option("--input", "input_path", required=True, help="JSON with candidate_id,expected_revision,tags; or - for stdin.")
@click.pass_obj
@guarded
def tags_set(context, input_path):
    payload = _read_input(input_path)
    if set(payload) != {"candidate_id", "expected_revision", "tags"}:
        raise ResearchError("Tag edits need a candidate, current revision and tags.")
    _json(_store(context).edit_tags(**payload))


@tag_commands.command(name="reset")
@click.argument("candidate_id")
@click.option("--expected-revision", type=click.IntRange(min=0), required=True)
@click.pass_obj
@guarded
def tags_reset(context, candidate_id, expected_revision):
    _json(_store(context).edit_tags(candidate_id, expected_revision, reset=True))


@recommendations.group(name="sources")
def source_commands():
    """Discover reusable source connections; native tools remain owned by the agent harness."""


def _catalog(context):
    from scholar_workflow.research.recommendations.source_catalog import SourceCatalog
    return SourceCatalog(_store(context))


@source_commands.command(name="list")
@click.pass_obj
@guarded
def sources_list(context):
    _json(_catalog(context).list_sources())


@source_commands.command(name="show")
@click.argument("source_id")
@click.pass_obj
@guarded
def sources_show(context, source_id):
    _json(_catalog(context).get_source(source_id))


@source_commands.command(name="register")
@click.option("--input", "input_path", required=True, help="Non-secret source descriptor JSON file or - for stdin.")
@click.option("--expected-revision", type=click.IntRange(min=0), required=True)
@click.pass_obj
@guarded
def sources_register(context, input_path, expected_revision):
    _json(_catalog(context).register(_read_input(input_path), expected_revision))


@source_commands.command(name="import")
@click.option("--input", "input_path", required=True, help="Versioned non-secret source plugin JSON file or - for stdin.")
@click.option("--expected-revision", type=click.IntRange(min=0), required=True)
@click.pass_obj
@guarded
def sources_import(context, input_path, expected_revision):
    _json(_catalog(context).import_plugin(_read_input(input_path), expected_revision))


@source_commands.command(name="export")
@click.argument("source_id")
@click.pass_obj
@guarded
def sources_export(context, source_id):
    """Export the portable source definition, excluding local account/context state."""
    _json(_catalog(context).export_plugin(source_id))


@source_commands.command(name="guide")
@click.argument("source_id")
@click.pass_obj
@guarded
def sources_guide(context, source_id):
    """Describe source operations, current requirements and cross-agent context."""
    _json(_catalog(context).guide(source_id, profile=context["profile"]))


@source_commands.command(name="enable")
@click.argument("source_id")
@click.option("--expected-revision", type=click.IntRange(min=0), required=True)
@click.pass_obj
@guarded
def sources_enable(context, source_id, expected_revision):
    _json(_catalog(context).set_enabled(source_id, True, expected_revision))


@source_commands.command(name="disable")
@click.argument("source_id")
@click.option("--expected-revision", type=click.IntRange(min=0), required=True)
@click.pass_obj
@guarded
def sources_disable(context, source_id, expected_revision):
    _json(_catalog(context).set_enabled(source_id, False, expected_revision))


@source_commands.command(name="context")
@click.argument("source_id")
@click.option("--input", "input_path", help="Update {expected_revision,topics,notes}; omit to read.")
@click.pass_obj
@guarded
def sources_context(context, source_id, input_path):
    _catalog(context).get_source(source_id)
    if input_path:
        payload = _read_input(input_path)
        if set(payload) != {"expected_revision", "topics", "notes"}:
            raise ResearchError("Source context update needs revision, topics and notes.")
        _json(_store(context).update_source_context(source_id, **payload))
    else:
        _json(_store(context).source_context(source_id))


@source_commands.command(name="record-operation")
@click.option("--input", "input_path", required=True, help="Explicit external-agent observation, not a remote tool invocation.")
@click.pass_obj
@guarded
def sources_record(context, input_path):
    payload = _read_input(input_path)
    _catalog(context).get_source(payload.get("source_id"))
    _json(_store(context).record_source_operation(payload))


@source_commands.command(name="history")
@click.option("--source-id")
@click.pass_obj
@guarded
def sources_history(context, source_id):
    if source_id:
        _catalog(context).get_source(source_id)
    _json(_store(context).source_history(source_id))


@recommendations.group(name="ingestion")
def ingestion_commands():
    """Preview and explicitly execute reviewed Zotero bibliography ingestion."""


def _ingestion(context):
    from scholar_workflow.research.recommendations.ingestion import IngestionService
    return IngestionService(_store(context), context["profile"])


@ingestion_commands.command(name="targets")
@click.pass_obj
@guarded
def ingestion_targets(context):
    _json(_ingestion(context).targets())


@ingestion_commands.command(name="plan")
@click.option("--candidate-id", required=True)
@click.option("--expected-revision", type=click.IntRange(min=1), required=True)
@click.option("--collection-key", required=True)
@click.pass_obj
@guarded
def ingestion_plan(context, candidate_id, expected_revision, collection_key):
    _json(_ingestion(context).plan(candidate_id, expected_revision, collection_key))


@ingestion_commands.command(name="execute")
@click.option("--plan-id", required=True)
@click.option("--confirmed", is_flag=True, required=True)
@click.option("--retry", is_flag=True, help="Explicitly retry a needs-attention operation after inspecting the provider.")
@click.pass_obj
@guarded
def ingestion_execute(context, plan_id, confirmed, retry):
    result = _ingestion(context).execute(plan_id, confirmed, retry=retry)
    _json(result)
    if result.get("status") != "completed":
        click.get_current_context().exit(result.get("exit_code", 6))


@ingestion_commands.command(name="history")
@click.pass_obj
@guarded
def ingestion_history(context):
    _json({"items": _ingestion(context).history()})


if __name__ == "__main__":
    recommendations()
