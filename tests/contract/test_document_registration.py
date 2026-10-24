"""Synthetic Webpage ownership registration; no real Zotero, Vault or PDF.

Inputs are one registered temporary Source, a fake Local API Webpage and an
explicit UTF-8 source snapshot with unique block anchors. The expected result is
one new Source.md owner with exact bytes/hash and Field navigation. Planning is
zero-write; approved registration recovers each publication interruption and
replays without changing files. Changed sources/metadata, duplicate ownership,
unsafe paths and malformed source declarations refuse without replacing content.
These tests cover registration safety, not scientific support or native reading.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.models import KnowledgeAtomicResource
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.models import ResourceKind
from scholar_workflow.workflows.register_document import document_plan, register_document
from scholar_workflow.workflows.register_paper import paper_plan
from scholar_workflow.workflows.register_source import register_source


class LocalDocument:
    def __init__(self):
        self.title = "Synthetic official Webpage"
        self.url = "https://example.org/research/model"
        self.item_type = "webpage"
        self.version = 4

    def get_item(self, key):
        assert key == "ABCD2345"
        return {"key": key, "version": self.version,
                "library": {"id": 123, "type": "user"},
                "data": {"itemType": self.item_type, "title": self.title, "url": self.url}}


def _scope(tmp_path: Path, field_root="."):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("# Existing home\n")
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    service = FieldService(registry)
    proposal = registration_plan(service, root, field_root=".", existing_source=False)
    manifest = register_source(service, root, field_root=".", existing_source=False,
                               approved_digest=proposal.payload["approved_digest"])
    if field_root != ".":
        (root / field_root).mkdir(parents=True)
        (root / field_root / "README.md").write_text("# Existing nested home\n")
        value = manifest.model_dump(mode="json")
        value["fields"][0]["relative_root"] = field_root
        manifest = FieldManifest.model_validate(value)
        (root / ".scholar-workflow/fields.yml").write_text(yaml.safe_dump(
            manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False))
    source = tmp_path / "official-source.md"
    source.write_text("# Synthetic source\n\nThe model predicts a future state.\n^source-one\n\n"
                      "This is a synthetic statement, not a measured result.\n^source-two\n")
    selection = {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
                 "item_key": "ABCD2345", "segment": "synthetic-document", "language": "en",
                 "markdown_path": source, "source_url": "https://example.org/research/model",
                 "retrieved_at": "2026-01-02T03:04:05+00:00"}
    return root, registry, LocalDocument(), selection


def _files(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("field_root", [".", "domain/topic"])
@pytest.mark.parametrize("item_type", ["webpage", "blogPost"])
def test_document_plan_register_and_replay_preserve_exact_source(tmp_path, field_root, item_type):
    root, registry, zotero, selection = _scope(tmp_path, field_root)
    zotero.item_type = item_type
    before = _files(tmp_path)
    plan = document_plan(registry, zotero, **selection)
    assert plan == document_plan(registry, zotero, **selection)
    assert _files(tmp_path) == before
    owner_path = (Path(field_root) / "resources/synthetic-document/Source.md").as_posix()
    assert plan["owner_path"] == owner_path
    result = register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    expected = selection["markdown_path"].read_bytes()
    assert (root / owner_path).read_bytes() == expected
    snapshot = load_knowledge_provider_snapshot(
        registry.path.parent / "knowledge-providers" / selection["source_id"])
    owner = snapshot.manifest.atomic_resources[0]
    assert owner.resource_id == "document:zotero:123:ABCD2345"
    assert owner.kind == ResourceKind.BLOG_POST
    assert owner.markdown_path == owner_path
    assert owner.markdown_sha256 == "sha256:" + hashlib.sha256(expected).hexdigest()
    assert snapshot.catalog.resources[0].zotero.attachment_key is None
    assert snapshot.catalog.resources[0].identifiers.url == zotero.url
    assert FieldService._load_manifest(root).fields[0].navigation[-1].items == [
        "resources/synthetic-document/Source.md"]
    assert not result["analysis_committed"] and not result["backup_verified"]
    after = _files(tmp_path)
    assert register_document(registry, zotero, approved_digest=plan["approved_digest"],
                             **selection) == result
    assert _files(tmp_path) == after


@pytest.mark.parametrize("member", [1, 2, 3])
def test_document_registration_recovers_each_member(tmp_path, member):
    root, registry, zotero, selection = _scope(tmp_path)
    plan = document_plan(registry, zotero, **selection)

    def interrupt(point):
        if point == f"member-{member}":
            raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="synthetic"):
        register_document(registry, zotero, approved_digest=plan["approved_digest"],
                          fault_inject=interrupt, **selection)
    result = register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert result["status"] == "registered"
    assert (root / result["owner_path"]).read_bytes() == selection["markdown_path"].read_bytes()


@pytest.mark.parametrize("change", ["input", "metadata", "existing-folder", "fields"])
def test_stale_document_plan_refuses_without_publication(tmp_path, change):
    root, registry, zotero, selection = _scope(tmp_path)
    plan = document_plan(registry, zotero, **selection)
    if change == "input":
        selection["markdown_path"].write_text("Changed source.\n^source-three\n")
    elif change == "metadata":
        zotero.version += 1
    elif change == "existing-folder":
        folder = root / "resources/synthetic-document"
        folder.mkdir(parents=True)
        (folder / "human.md").write_text("Keep the human file.\n")
    else:
        fields = root / ".scholar-workflow/fields.yml"
        fields.write_text(fields.read_text() + "# changed declaration\n")
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert _files(tmp_path) == before


def test_interrupted_registration_never_overwrites_human_source(tmp_path):
    root, registry, zotero, selection = _scope(tmp_path)
    plan = document_plan(registry, zotero, **selection)

    def interrupt(point):
        if point == "member-1":
            raise RuntimeError("interrupt")

    with pytest.raises(RuntimeError):
        register_document(registry, zotero, approved_digest=plan["approved_digest"],
                          fault_inject=interrupt, **selection)
    owner = root / plan["owner_path"]
    owner.write_text("Human revision.\n^human\n")
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert _files(tmp_path) == before


@pytest.mark.parametrize(("field", "value"), [
    ("source_url", "http://example.org/research/model"),
    ("source_url", "https://example.org/different"),
    ("source_url", "https://user:secret@example.org/research/model"),
    ("retrieved_at", "2026-01-02T03:04:05"),
    ("retrieved_at", "not-a-time"),
    ("segment", "../escape"),
])
def test_invalid_document_selection_refuses_before_writes(tmp_path, field, value):
    _, registry, zotero, selection = _scope(tmp_path)
    selection[field] = value
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        document_plan(registry, zotero, **selection)
    assert _files(tmp_path) == before


@pytest.mark.parametrize("content", [
    b"No anchors.\n", b"A.\n^same\n\nB.\n^same\n", b"\xff\xfe",
    b"```text\n^not-a-real-block\n```\n", b"A. ^inline-only\n",
])
def test_source_requires_utf8_and_unique_real_blocks(tmp_path, content):
    _, registry, zotero, selection = _scope(tmp_path)
    selection["markdown_path"].write_bytes(content)
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError):
        document_plan(registry, zotero, **selection)
    assert _files(tmp_path) == before


def test_symlink_source_refuses(tmp_path):
    _, registry, zotero, selection = _scope(tmp_path)
    link = tmp_path / "linked-source.md"
    link.symlink_to(selection["markdown_path"])
    selection["markdown_path"] = link
    with pytest.raises(FieldRegistryError):
        document_plan(registry, zotero, **selection)


def test_duplicate_document_in_another_registered_source_refuses(tmp_path):
    _, registry, zotero, selection = _scope(tmp_path)
    plan = document_plan(registry, zotero, **selection)
    register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    other = tmp_path / "other-source"
    other.mkdir()
    (other / "README.md").write_text("# Another registered home\n")
    service = FieldService(registry)
    proposal = registration_plan(service, other, field_root=".", existing_source=False)
    manifest = register_source(service, other, field_root=".", existing_source=False,
                               approved_digest=proposal.payload["approved_digest"])
    selected = dict(selection, source_id=manifest.source_id,
                    field_id=manifest.fields[0].field_id, segment="another-name")
    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError, match="owner|ownership|registered"):
        document_plan(registry, zotero, **selected)
    assert _files(tmp_path) == before


def test_document_owner_cannot_be_registered_again_as_a_paper_with_an_attachment(tmp_path):
    _, registry, zotero, selection = _scope(tmp_path)
    plan = document_plan(registry, zotero, **selection)
    register_document(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    pdf = tmp_path / "synthetic-attachment.pdf"
    pdf.write_bytes(b"%PDF-1.7 synthetic Local API attachment fixture\n")

    class AttachedDocument(LocalDocument):
        def get_item(self, key):
            if key == "EFGH2345":
                return {"key": key, "library": {"id": 123, "type": "user"},
                        "data": {"itemType": "attachment", "parentItem": "ABCD2345",
                                 "contentType": "application/pdf", "linkMode": "imported_file"}}
            return super().get_item(key)

        def resolve_attachment_locator(self, key):
            return SimpleNamespace(path=pdf, attachment_key=key, library_id="123")

    before = _files(tmp_path)
    with pytest.raises(FieldRegistryError, match="registered.*owner"):
        paper_plan(registry, AttachedDocument(), source_id=selection["source_id"],
                   field_id=selection["field_id"], item_key=selection["item_key"],
                   attachment_key="EFGH2345", segment="second-paper", language="en")
    assert _files(tmp_path) == before


def test_paper_serialization_remains_unchanged_and_document_hash_is_strict():
    paper = {"resource_id": "paper:existing", "kind": "paper", "title": "Existing",
             "markdown_path": "resources/existing/Paper.md"}
    assert KnowledgeAtomicResource.model_validate(paper).model_dump(mode="json") == paper
    with pytest.raises(ValidationError):
        KnowledgeAtomicResource.model_validate(dict(paper, markdown_sha256="sha256:" + "a" * 64))
    with pytest.raises(ValidationError):
        KnowledgeAtomicResource.model_validate(dict(paper, kind="blog_post", markdown_sha256="bad"))
