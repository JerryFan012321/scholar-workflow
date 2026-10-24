"""Installed, explicitly invoked public-source checker; never a background service."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import click

from scholar_workflow import __version__
from scholar_workflow.adapters.research_sources import fetch_channel
from scholar_workflow.research import (
    ResearchError,
    apply_observation,
    check_lock,
    read_sources,
    read_updates,
)
from scholar_workflow.research.cli import ResearchCommandError, root
from scholar_workflow.research.presentation import updates_markdown


def run_check(root: Path, channel_ids: list[str] | None = None, *, initial_mode="baseline",
              client=None, checked_at: str | None = None) -> dict:
    inventory = read_sources(root)
    if inventory["status"] == "invalid":
        raise ResearchError("Research sources are invalid or unsafe; no request was made.", 7)
    channels = inventory["channels"]
    selected = set(channel_ids or [])
    if selected - {channel["channel_id"] for channel in channels}:
        raise ResearchError("A selected research channel is not registered.", 2)
    current = read_updates(root)
    if current["status"] == "invalid":
        raise ResearchError("Research observations are invalid or unsafe; no request was made.", 7)
    if not channels:
        return {**current, "check_results": []}
    with check_lock(root):
        return _check_registered(root, channels, selected, current, initial_mode, client, checked_at)


def _check_registered(root, channels, selected, current, initial_mode, client, checked_at):
    previous = {channel["channel_id"]: channel for channel in current["channels"]}
    results, events = [], []
    for channel in channels:
        identifier = channel["channel_id"]
        if selected and identifier not in selected:
            continue
        if not channel["enabled"]:
            results.append({"channel_id": identifier, "status": "disabled", "events": []})
            continue
        # Timestamp before the request lets the state layer reject late stale observations.
        observed_at = checked_at or datetime.now(UTC).isoformat()
        observation = fetch_channel(channel, previous=previous.get(identifier), client=client)
        outcome = apply_observation(root, channel, observation, observed_at, initial_mode=initial_mode)
        results.append(outcome)
        events.extend(outcome.get("events", []))
    current = read_updates(root)
    return {**current,
            "status": "partial" if any(row["status"] == "failed" for row in results)
            else current["status"],
            "check_results": results, "events": events,
            "scope": "selected-channel-observed-window; not full publisher history"}


@click.group()
@click.version_option(__version__, prog_name="scholar-research")
def main() -> None:
    """Check explicitly registered public research sources; no automatic ingestion."""


@main.command(name="check")
@click.option("--channel", "channel_ids", multiple=True, help="Registered channel ID; repeat to select.")
@click.option("--initial-mode", type=click.Choice(["baseline", "report"]), default="baseline",
              help="First successful check: baseline only, or report the currently visible items.")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["zh", "en"]), default="zh")
def check(channel_ids: tuple[str], initial_mode: str, fmt: str, language: str) -> None:
    """Fetch enabled channels once, isolate failures and retain incremental observations."""
    try:
        payload = run_check(root(), list(channel_ids), initial_mode=initial_mode)
    except ResearchError as exc:
        raise ResearchCommandError(exc) from None
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2) if fmt == "json" else
               updates_markdown(payload, language=language))
    if payload["status"] == "partial":
        click.get_current_context().exit(6)
