"""Host-neutral submission and opening commands for recommendation candidates."""
from __future__ import annotations

from functools import wraps
import html
import json
from pathlib import Path
import sys
import webbrowser

import click

from scholar_workflow.research.cli import ResearchCommandError, _spec, root
from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations import lifecycle


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
@click.pass_obj
@guarded
def submit(context, input_path):
    """Submit candidates; preserve producer provenance and human decisions."""
    # Input syntax is checked before opening or initializing a state store.
    record = _read_input(input_path)
    payload = _store(context).submit(record)
    _json(payload)
    states = {entry["status"] for entry in payload.get("receipts", [])}
    failures = states & {"conflict", "invalid", "failed"}
    if failures:
        code = 6 if states & {"accepted", "duplicate"} else (5 if "conflict" in failures else 2)
        click.get_current_context().exit(code)


@recommendations.command(name="list")
@click.option("--query", default="")
@click.option("--kind", type=click.Choice(["paper", "project", "blog"]))
@click.option("--tag")
@click.option("--producer-id")
@click.option("--decision", type=click.Choice(["unread", "saved", "selected", "ignored"]))
@click.option("--since", help="Published on or after this ISO date, YYYY-MM-DD.")
@click.option("--limit", type=click.IntRange(1, 100), default=40)
@click.option("--offset", type=click.IntRange(min=0), default=0)
@click.option("--format", "fmt", type=click.Choice(["json", "md"]), default="md")
@click.pass_obj
@guarded
def candidates(context, query, kind, tag, producer_id, decision, since, limit, offset, fmt):
    """List shared candidates, with producer and topic matched on the same recommendation."""
    payload = _store(context).list_candidates(query=query, kind=kind, tag=tag,
        producer_id=producer_id, decision=decision, since=since, limit=limit, offset=offset)
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
@click.pass_obj
@guarded
def start(context):
    """Start or reuse this profile's identified local recommendation service."""
    lifecycle.start(context["state_dir"], context["profile"])
    _json(lifecycle.status(context["state_dir"], context["profile"]))


@recommendations.command(name="open")
@click.option("--no-browser", is_flag=True, help="Print the private session URL instead of opening it.")
@click.pass_obj
@guarded
def open_page(context, no_browser):
    """Start the installed page and open it in the system browser."""
    record = lifecycle.start(context["state_dir"], context["profile"])
    url = f"http://127.0.0.1:{record['port']}/#token={record['token']}"
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


@recommendations.command(name="serve", hidden=True)
@click.pass_obj
@guarded
def serve(context):
    """Run the private owned child process; credentials arrive through stdin."""
    lifecycle.serve(context["state_dir"], context["profile"], _read_input("-"))


if __name__ == "__main__":
    recommendations()
