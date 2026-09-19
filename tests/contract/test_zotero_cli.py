"""Contract tests for the host-neutral Zotero Local API CLI."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from scholar_workflow.adapters.zotero_local import (
    Authorization,
    ServerInfo,
    ZoteroLocalError,
    ZoteroLocalUnavailable,
)
from scholar_workflow.cli import main
from scholar_workflow.workflows.zotero import ZoteroIdentityConflict, ZoteroPartialCompletion


class FakeAdapter:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def probe(self):
        return ServerInfo("server-secret", "3", "42")

    def authorize(self):
        return Authorization("must-not-be-printed", True)

    def search_items(self, query, *, qmode, limit):
        return [{"key": "ITEM1", "data": {"title": query, "qmode": qmode, "limit": limit}}]

    def get_item(self, item_key):
        return {"key": item_key}

    def get_children(self, item_key):
        return [{"key": "ATT1", "parentItem": item_key}]

    def get_fulltext(self, attachment_key):
        return {"content": f"text for {attachment_key}"}

    def get_collections(self, *, limit):
        return [{"key": "C1", "limit": limit}]

    def get_collection_items(self, collection_key, *, limit):
        return [{"key": "ITEM1", "collection": collection_key, "limit": limit}]

    def update_item(self, item_key, changes, *, version=None):
        self.update = (item_key, changes, version)


def invoke(monkeypatch, args):
    monkeypatch.setattr("scholar_workflow.cli._zotero_adapter", lambda: FakeAdapter())
    return CliRunner().invoke(main, args)


def test_probe_does_not_expose_server_id(monkeypatch):
    result = invoke(monkeypatch, ["zotero", "probe"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True, "api_version": "3", "schema_version": "42"}
    assert "server-secret" not in result.output


def test_authorize_never_prints_key(monkeypatch):
    result = invoke(monkeypatch, ["zotero", "authorize"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"authorized": True, "remembered": True}
    assert "must-not-be-printed" not in result.output


def test_search_and_read_commands_are_json(monkeypatch):
    search = invoke(monkeypatch, ["zotero", "search", "world model", "--fulltext"])
    assert search.exit_code == 0
    assert json.loads(search.output)["items"][0]["key"] == "ITEM1"
    item = invoke(monkeypatch, ["zotero", "get", "ITEM1", "--children"])
    assert json.loads(item.output)["children"][0]["key"] == "ATT1"
    fulltext = invoke(monkeypatch, ["zotero", "fulltext", "ATT1"])
    assert json.loads(fulltext.output)["content"] == "text for ATT1"
    collection = invoke(monkeypatch, ["zotero", "collection-items", "C1"])
    assert json.loads(collection.output)["items"][0]["collection"] == "C1"
    assert json.loads(collection.output)["items"][0]["limit"] is None


def test_ingest_accepts_json_file(monkeypatch, tmp_path: Path):
    payload = tmp_path / "ingest.json"
    payload.write_text(
        json.dumps({"metadata": {"itemType": "journalArticle", "title": "Paper"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("scholar_workflow.cli._zotero_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(
        "scholar_workflow.workflows.zotero.ingest_item",
        lambda *args, **kwargs: {"status": "created", "item_key": "NEW1"},
    )
    result = CliRunner().invoke(main, ["zotero", "ingest", "--input", str(payload)])
    assert result.exit_code == 0
    assert json.loads(result.output)["item_key"] == "NEW1"


def test_update_requires_version_and_rejects_protected_fields(monkeypatch, tmp_path: Path):
    payload = tmp_path / "update.json"
    payload.write_text(json.dumps({"changes": {"title": "Fixed"}, "version": 7}))
    result = invoke(monkeypatch, ["zotero", "update", "ITEM1", "--input", str(payload)])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"updated": True, "item_key": "ITEM1"}

    payload.write_text(json.dumps({"changes": {"collections": []}, "version": 7}))
    rejected = invoke(monkeypatch, ["zotero", "update", "ITEM1", "--input", str(payload)])
    assert rejected.exit_code == 2
    assert "protected fields" in rejected.output


def test_identity_conflict_maps_to_exit_5(monkeypatch, tmp_path: Path):
    payload = tmp_path / "ingest.json"
    payload.write_text(
        json.dumps({"metadata": {"itemType": "journalArticle", "title": "Paper"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("scholar_workflow.cli._zotero_adapter", lambda: FakeAdapter())

    def conflict(*args, **kwargs):
        raise ZoteroIdentityConflict("multiple exact Zotero matches: A, B")

    monkeypatch.setattr("scholar_workflow.workflows.zotero.ingest_item", conflict)
    result = CliRunner().invoke(main, ["zotero", "ingest", "--input", str(payload)])
    assert result.exit_code == 5
    assert "A, B" in result.output


def test_partial_attachment_maps_to_exit_6_with_resume_instruction(monkeypatch, tmp_path: Path):
    payload = tmp_path / "ingest.json"
    payload.write_text(
        json.dumps({"metadata": {"itemType": "journalArticle", "title": "Paper"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("scholar_workflow.cli._zotero_adapter", lambda: FakeAdapter())

    def partial(*args, **kwargs):
        raise ZoteroPartialCompletion("ITEM1", "ATT1")

    monkeypatch.setattr("scholar_workflow.workflows.zotero.ingest_item", partial)
    result = CliRunner().invoke(main, ["zotero", "ingest", "--input", str(payload)])
    assert result.exit_code == 6
    assert "ITEM1" in result.output
    assert "ATT1" in result.output
    assert "rerun the same ingest payload" in result.output


def test_zotero_failures_use_dependency_and_external_service_codes(monkeypatch):
    class FailingAdapter(FakeAdapter):
        error = ZoteroLocalUnavailable("not running")

        def __enter__(self):
            raise self.error

    adapter = FailingAdapter()
    monkeypatch.setattr("scholar_workflow.cli._zotero_adapter", lambda: adapter)
    unavailable = CliRunner().invoke(main, ["zotero", "probe"])
    assert unavailable.exit_code == 3

    adapter.error = ZoteroLocalError("HTTP 500")
    rejected = CliRunner().invoke(main, ["zotero", "probe"])
    assert rejected.exit_code == 8
