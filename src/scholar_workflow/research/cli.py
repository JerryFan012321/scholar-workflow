"""Local research registration and event dispositions; no outbound acquisition."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import click

from scholar_workflow.config import DEFAULT_HOME
from scholar_workflow.research import (
    ResearchError,
    mark_event,
    read_sources,
    read_updates,
    register_source,
)
from scholar_workflow.research.presentation import sources_markdown, updates_markdown


class ResearchCommandError(click.ClickException):
    """A sanitized core failure with a stable product exit code."""

    def __init__(self, error: ResearchError):
        super().__init__(str(error))
        self.exit_code = error.exit_code


def root() -> Path:
    return Path(os.environ.get("SCHOLAR_WORKFLOW_HOME", DEFAULT_HOME))


def _emit(payload: dict, fmt: str, language: str, *, sources: bool = False) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2) if fmt == "json" else
               (sources_markdown if sources else updates_markdown)(payload, language=language))


def _spec(path: Path) -> dict:
    limit, descriptor = 64 * 1024, None
    try:
        absolute = Path(os.path.abspath(path))
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        directory = os.open(absolute.anchor, flags | os.O_DIRECTORY)
        try:
            for part in absolute.parts[1:-1]:
                child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(absolute.name, flags | os.O_NONBLOCK, dir_fd=directory)
        finally:
            os.close(directory)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > limit:
            raise ResearchError("Research specification must be a regular file of at most 64 KiB.", 7)
        content = os.read(descriptor, limit + 1)
        if len(content) > limit:
            raise ResearchError("Research specification exceeds 64 KiB.", 7)
    except OSError:
        raise ResearchError("Research specification is unavailable or its path is unsafe.", 7) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate key")
            result[key] = value
        return result

    try:
        record = json.loads(content.decode("utf-8"), object_pairs_hook=unique)
        if not isinstance(record, dict):
            raise TypeError("Expected object")
        return record
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise ResearchError("Research specification must be UTF-8 JSON with unique object keys.", 2) from None


@click.group()
def research() -> None:
    """Manage research sources and observed updates locally; use scholar-research to check online."""


@research.group(name="sources")
def sources() -> None:
    """Register explicitly selected public research channels without fetching them."""


@sources.command(name="list")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["zh", "en"]), default="zh")
def sources_list(fmt: str, language: str) -> None:
    try:
        payload = read_sources(root())
        _emit(payload, fmt, language, sources=True)
        if payload["status"] == "invalid":
            click.get_current_context().exit(7)
    except ResearchError as exc:
        raise ResearchCommandError(exc) from None


@sources.command(name="register")
@click.option("--spec", type=click.Path(path_type=Path), required=True)
@click.option("--expected-revision", help="Current revision for an existing channel change.")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["zh", "en"]), default="zh")
def sources_register(spec: Path, expected_revision: str | None, fmt: str, language: str) -> None:
    try:
        payload = register_source(root(), _spec(spec), expected_revision=expected_revision)
        current = read_sources(root())
        if current["status"] != "available" or payload["channel"] not in current["channels"]:
            raise ResearchError("Research registration was written but could not be confirmed; read it before retrying.", 6)
        payload = {**payload, "revision": current["revision"], "channels": current["channels"]}
        _emit(payload, fmt, language, sources=True)
    except ResearchError as exc:
        raise ResearchCommandError(exc) from None


@research.command(name="updates")
@click.option("--disposition", type=click.Choice(["unread", "read", "selected", "ignored"]))
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["zh", "en"]), default="zh")
def updates(disposition: str | None, fmt: str, language: str) -> None:
    try:
        payload = read_updates(root())
        if disposition:
            payload = dict(payload, events=[event for event in payload["events"]
                                           if event["disposition"] == disposition])
        _emit(payload, fmt, language)
        if payload["status"] == "invalid":
            click.get_current_context().exit(7)
    except ResearchError as exc:
        raise ResearchCommandError(exc) from None


@research.command(name="mark")
@click.argument("event_id")
@click.option("--disposition", type=click.Choice(["unread", "read", "selected", "ignored"]), required=True)
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
@click.option("--language", type=click.Choice(["zh", "en"]), default="zh")
def mark(event_id: str, disposition: str, fmt: str, language: str) -> None:
    try:
        payload = mark_event(root(), event_id, disposition)
        current = read_updates(root())
        if current["status"] == "invalid" or payload["event"] not in current["events"]:
            raise ResearchError("Research selection was written but could not be confirmed; read it before retrying.", 6)
        if fmt == "json":
            _emit(payload, fmt, language)
        else:
            from scholar_workflow.research.presentation import label
            click.echo(("已记录处理选择：" if language == "zh" else "Recorded disposition: ") +
                       label(disposition, language == "zh"))
    except ResearchError as exc:
        raise ResearchCommandError(exc) from None
