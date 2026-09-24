"""Contract tests for the host-neutral Zotero Local API CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from click.testing import CliRunner

from scholar_workflow.adapters.zotero_local import (
    Authorization,
    ServerInfo,
    ZoteroAttachmentLocator,
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
        if item_key == "ABCD2345":
            return {"key": item_key, "data": {"title": "Selected Paper"}}
        return {"key": item_key}

    def get_children(self, item_key):
        if item_key == "ABCD2345":
            return [
                {
                    "key": "EFGH6789",
                    "data": {
                        "itemType": "attachment",
                        "contentType": "application/pdf",
                        "filename": "paper.pdf",
                    },
                }
            ]
        return [{"key": "ATT1", "parentItem": item_key}]

    def resolve_attachment_locator(self, attachment_key):
        return ZoteroAttachmentLocator(
            attachment_key=attachment_key,
            library_id="1",
            content_hash="sha256:" + "a" * 64,
            path=Path("/not-read.pdf"),
            filename="paper.pdf",
        )

    def get_annotations(self, attachment_key):
        return [
            {
                "key": "JKLM2345",
                "data": {
                    "annotationType": "highlight",
                    "annotationText": "quoted text",
                    "annotationComment": "my comment",
                    "annotationPageLabel": "7",
                    "annotationPosition": '{"pageIndex": 6}',
                    "annotationSortIndex": "00001",
                },
            }
        ]

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


def test_annotations_command_emits_local_api_projection(monkeypatch):
    result = invoke(
        monkeypatch,
        ["zotero", "annotations", "--item", "ABCD2345", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["item_key"] == "ABCD2345"
    assert payload["attachment_key"] == "EFGH6789"
    assert payload["annotations"][0]["comment"] == "my comment"
    assert payload["annotations"][0]["source_link"].startswith("zotero://open-pdf/")


def test_snapshot_annotations_creates_independent_pdf_and_receipt(monkeypatch, tmp_path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=200)
    document.save(source)
    document.close()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    class SnapshotAdapter(FakeAdapter):
        def resolve_attachment_locator(self, attachment_key):
            return ZoteroAttachmentLocator(
                attachment_key=attachment_key,
                library_id="1",
                content_hash=f"sha256:{source_hash}",
                path=source,
                filename=source.name,
            )

        def get_annotations(self, attachment_key):
            return [
                {
                    "key": "JKLM2345",
                    "data": {
                        "annotationType": "highlight",
                        "annotationText": "quoted text",
                        "annotationComment": "my comment",
                        "annotationPosition": json.dumps(
                            {"pageIndex": 0, "rects": [[20, 20, 120, 40]]}
                        ),
                        "annotationSortIndex": "00001",
                    },
                }
            ]

    monkeypatch.setattr(
        "scholar_workflow.cli._zotero_adapter",
        lambda: SnapshotAdapter(),
    )
    output = tmp_path / "annotated.pdf"

    result = CliRunner().invoke(
        main,
        [
            "zotero",
            "snapshot-annotations",
            "EFGH6789",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["snapshot"] == str(output)
    assert payload["annotation_count"] == 1
    assert payload["imported_back"] is False
    assert output.is_file()
    assert output.with_suffix(".pdf.snapshot.json").is_file()


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
