"""Unit tests for deterministic Zotero identity checks and ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholar_workflow.workflows.zotero import (
    ZoteroIdentityConflict,
    ZoteroPartialCompletion,
    ingest_item,
)


class FakeAdapter:
    def __init__(
        self,
        search_results=None,
        import_error: Exception | None = None,
        children=None,
    ):
        self.search_results = search_results or []
        self.import_error = import_error
        self.children = children or []
        self.created = None

    def search_items(self, query, *, qmode, limit):
        self.search = (query, qmode, limit)
        return self.search_results

    def ensure_write_authorization(self, *, require_remembered=False):
        self.preflight = require_remembered

    def get_children(self, item_key):
        self.children_parent = item_key
        return self.children

    def get_item_template(self, item_type):
        self.template_type = item_type
        return {"itemType": item_type, "title": "", "tags": []}

    def create_item(self, metadata):
        self.created = metadata
        return "NEW1"

    def update_item(self, item_key, changes, *, version):
        self.updated = (item_key, changes, version)

    def import_file(self, parent_key, path):
        self.imported = (parent_key, path)
        if self.import_error:
            raise self.import_error
        return {"attachment_key": "ATT1", "uploaded": True}

    def upload_file(self, attachment_key, path):
        self.uploaded = (attachment_key, path)
        return {"attachment_key": attachment_key, "uploaded": True}


def item(key, *, title="Paper", doi="", creator="Doe", collections=None, version=None):
    return {
        "key": key,
        "version": version,
        "data": {
            "title": title,
            "DOI": doi,
            "creators": [{"creatorType": "author", "lastName": creator, "firstName": "A"}],
            "collections": collections or [],
        },
    }


def metadata(*, title="Paper", doi="", creator="Doe"):
    return {
        "itemType": "journalArticle",
        "title": title,
        "DOI": doi,
        "creators": [{"creatorType": "author", "lastName": creator, "firstName": "A"}],
    }


def attachment(key="ATT1", *, md5=None, link_mode="imported_file"):
    return {
        "key": key,
        "data": {
            "itemType": "attachment",
            "linkMode": link_mode,
            "contentType": "application/pdf",
            "filename": "paper.pdf",
            "md5": md5,
        },
    }


def test_existing_doi_is_reused_without_write():
    adapter = FakeAdapter([item("ITEM1", doi="10.1/example")])
    result = ingest_item(adapter, metadata=metadata(doi="https://doi.org/10.1/EXAMPLE"))
    assert result == {"status": "existing", "item_key": "ITEM1"}
    assert adapter.created is None
    assert adapter.search[1] == "everything"
    assert adapter.search[2] is None


def test_title_and_creators_are_fallback_identity():
    adapter = FakeAdapter([item("ITEM1", title="  PAPER ", creator="Doe")])
    result = ingest_item(adapter, metadata=metadata(title="Paper", creator="Doe"))
    assert result["status"] == "existing"


def test_null_doi_falls_back_to_title_identity():
    adapter = FakeAdapter([item("ITEM1")])
    target = metadata()
    target["DOI"] = None
    result = ingest_item(adapter, metadata=target)
    assert result["status"] == "existing"
    assert adapter.search[0] == "Paper"


def test_existing_item_can_be_added_to_another_collection():
    adapter = FakeAdapter([item("ITEM1", collections=["C1"], version=7)])
    result = ingest_item(adapter, metadata=metadata(), collection_keys=["C1", "C2"])
    assert result == {"status": "existing_updated", "item_key": "ITEM1"}
    assert adapter.updated == ("ITEM1", {"collections": ["C1", "C2"]}, 7)


def test_existing_item_without_pdf_receives_requested_attachment(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter([item("ITEM1")])

    result = ingest_item(adapter, metadata=metadata(), pdf_path=pdf)

    assert adapter.preflight is True
    assert adapter.imported == ("ITEM1", pdf)
    assert result == {
        "status": "existing_updated",
        "item_key": "ITEM1",
        "attachment_key": "ATT1",
        "uploaded": True,
    }


def test_existing_complete_pdf_is_reused_without_duplicate(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter(
        [item("ITEM1")],
        children=[attachment("ATT2", md5="abc123")],
    )

    result = ingest_item(adapter, metadata=metadata(), pdf_path=pdf)

    assert not hasattr(adapter, "imported")
    assert result == {
        "status": "existing",
        "item_key": "ITEM1",
        "attachment_key": "ATT2",
        "uploaded": False,
    }


def test_existing_incomplete_attachment_is_resumed(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter([item("ITEM1")], children=[attachment("ATT2")])

    result = ingest_item(adapter, metadata=metadata(), pdf_path=pdf)

    assert adapter.uploaded == ("ATT2", pdf)
    assert not hasattr(adapter, "imported")
    assert result == {
        "status": "existing_updated",
        "item_key": "ITEM1",
        "attachment_key": "ATT2",
        "uploaded": True,
    }


def test_multiple_incomplete_attachments_stop_for_adjudication(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter(
        [item("ITEM1")],
        children=[attachment("ATT1"), attachment("ATT2")],
    )

    with pytest.raises(ZoteroIdentityConflict, match="ATT1, ATT2"):
        ingest_item(adapter, metadata=metadata(), pdf_path=pdf)

    assert not hasattr(adapter, "uploaded")
    assert not hasattr(adapter, "imported")


def test_non_author_creators_do_not_change_fallback_identity():
    candidate = item("ITEM1")
    candidate["data"]["creators"].append(
        {"creatorType": "editor", "lastName": "Editor", "firstName": "E"}
    )
    adapter = FakeAdapter([candidate])

    result = ingest_item(adapter, metadata=metadata())

    assert result["status"] == "existing"


def test_multiple_exact_matches_are_conflict():
    adapter = FakeAdapter([item("A"), item("B")])
    with pytest.raises(ZoteroIdentityConflict, match="A, B"):
        ingest_item(adapter, metadata=metadata())


def test_new_item_gets_collections_and_attachment(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter()
    result = ingest_item(
        adapter,
        metadata=metadata(),
        collection_keys=["C1", "C2"],
        pdf_path=pdf,
    )
    assert adapter.preflight is True
    assert adapter.created["tags"] == []
    assert adapter.created["relations"] == {}
    assert adapter.created["collections"] == ["C1", "C2"]
    assert result == {
        "status": "created",
        "item_key": "NEW1",
        "attachment_key": "ATT1",
        "uploaded": True,
    }


def test_invalid_pdf_is_rejected_before_search_or_write(tmp_path: Path):
    not_pdf = tmp_path / "paper.pdf"
    not_pdf.write_bytes(b"not a PDF")
    adapter = FakeAdapter()

    with pytest.raises(ValueError, match="valid PDF"):
        ingest_item(adapter, metadata=metadata(), pdf_path=not_pdf)

    assert not hasattr(adapter, "search")
    assert adapter.created is None


def test_attachment_failure_reports_recoverable_item_key(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    adapter = FakeAdapter(import_error=RuntimeError("upload failed"))
    with pytest.raises(ZoteroPartialCompletion, match="NEW1"):
        ingest_item(adapter, metadata=metadata(), pdf_path=pdf)
