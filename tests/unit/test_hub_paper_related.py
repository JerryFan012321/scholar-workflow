"""Prepared fixtures for paper-owned document and reader action boundaries."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.hub.actions import (
    ActionKind,
    CatalogActionService,
    InvalidActionTarget,
    ZotFlowSourceNoteLauncher,
)
from scholar_workflow.hub.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
    ZoteroLink,
)
from scholar_workflow.hub.related import PaperRelatedError, PaperRelatedService
from scholar_workflow.hub.zotflow import ZotFlowCapability
from scholar_workflow.models import ResourceKind

_PAPER = "PAPER234"
_OTHER = "THERE234"
_SOURCE = "f0784bc9-aa47-49b8-9c54-4b364789a472"


class _CatalogProvider:
    def __init__(self, catalog):
        self.catalog = catalog

    def load(self):
        return self.catalog


class _Zotero:
    children = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_item(self, key):
        return {"key": key, "library": {"id": 1}, "data": {"itemType": "journalArticle"}}

    def get_children(self, _key):
        return self.children


class _Launcher:
    def open(self, target, **_kwargs):
        return target


def _catalog():
    return HubCatalog(
        generated_at=datetime.now(UTC),
        resources=[
            HubResource(
                resource_id="paper:one", kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key=_PAPER), artifact_ids=["analysis:one", "canvas:one"],
            ),
            HubResource(
                resource_id="paper:other", kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key=_OTHER), artifact_ids=["analysis:other"],
            ),
        ],
        artifacts=[
            HubArtifact(
                artifact_id="analysis:one", kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN, vault_path="one/Analysis.md", resource_id="paper:one",
            ),
            HubArtifact(
                artifact_id="canvas:one", kind=ArtifactKind.ANALYSIS_CANVAS,
                format=ArtifactFormat.CANVAS, vault_path="one/Tree.canvas", resource_id="paper:one",
            ),
            HubArtifact(
                artifact_id="analysis:other", kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN, vault_path="other/Analysis.md", resource_id="paper:other",
            ),
        ],
    )


def _service(tmp_path):
    vault = tmp_path / "vault"
    (vault / "one").mkdir(parents=True)
    (vault / "one" / "Analysis.md").write_text("# A visible analysis\n", encoding="utf-8")
    provider = _CatalogProvider(_catalog())
    actions = CatalogActionService(provider, {ActionKind.ZOTERO_ITEM: _Launcher()})
    return PaperRelatedService(provider, actions, vault, adapter_factory=_Zotero), provider, actions, vault


def test_related_files_use_explicit_ownership_and_keep_missing_canvas(tmp_path):
    service, _provider, _actions, vault = _service(tmp_path)
    # A matching filename cannot establish ownership.
    (vault / "Analysis.md").write_text("Unregistered content", encoding="utf-8")
    result = service.public_related(_PAPER)
    rows = {row["ref"]["entity_id"]: row for row in result["documents"]}
    assert set(rows) == {"analysis:one", "canvas:one"}
    assert rows["analysis:one"]["available"] is True
    assert rows["canvas:one"]["available"] is False
    assert rows["canvas:one"]["reason"]
    assert "preview_id" in rows["analysis:one"]
    assert str(vault) not in repr(result)
    assert "vault_path" not in repr(result)


def test_preview_rechecks_current_declaration_and_rejects_symlinks(tmp_path):
    service, provider, _actions, vault = _service(tmp_path)
    row = service.public_related(_PAPER)["documents"][0]
    token = row["preview_id"]
    assert service.read_preview(token)["content"] == "# A visible analysis\n"
    original = vault / "one" / "Analysis.md"
    original.unlink()
    original.symlink_to(vault / "one" / "Tree.canvas")
    with pytest.raises(PaperRelatedError, match="missing|unsafe"):
        service.read_preview(token)
    provider.catalog = HubCatalog(generated_at=datetime.now(UTC))
    with pytest.raises(PaperRelatedError, match="registration changed"):
        service.read_preview(token)


def test_zotero_child_notes_require_matching_parent_and_library(tmp_path):
    service, _provider, _actions, _vault = _service(tmp_path)

    class ZoteroChildren(_Zotero):
        children = [
            {"key": "NATE2345", "library": {"id": 1}, "data": {
                "itemType": "note", "parentItem": _PAPER, "note": "<p>Owned note</p>"}},
            {"key": "NATE3456", "library": {"id": 1}, "data": {
                "itemType": "note", "parentItem": _OTHER, "note": "Foreign paper"}},
            {"key": "NATE4567", "library": {"id": 2}, "data": {
                "itemType": "note", "parentItem": _PAPER, "note": "Foreign library"}},
        ]

    service._adapter_factory = ZoteroChildren
    rows = service.public_related(_PAPER)["documents"]
    zotero_rows = [row for row in rows if row["ref"]["provider_id"] == "zotero"]
    assert [row["ref"]["entity_id"] for row in zotero_rows] == ["NATE2345"]
    assert zotero_rows[0]["title"] == "Owned note"
    assert zotero_rows[0]["actions"][0].kind is ActionKind.ZOTERO_ITEM


def test_manifest_title_and_owner_supply_related_resource_note(tmp_path):
    service, _provider, _actions, vault = _service(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="vault-one", root=vault, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(source_id=_SOURCE, folder_id="vault-one", capabilities=["read"])],
    ))
    (vault / "one" / "Resource.md").write_text("# Source", encoding="utf-8")
    metadata = vault.stat()
    service._sources = registry
    service._snapshot_loader = lambda: SimpleNamespace(
        vault_binding=SimpleNamespace(root_path=str(vault), device=metadata.st_dev, inode=metadata.st_ino),
        manifest=SimpleNamespace(
            atomic_resources=[SimpleNamespace(resource_id="paper:one", title="Declared paper note", markdown_path="one/Resource.md")],
            supporting_documents=[],
        ),
    )
    rows = service.public_related(_PAPER)["documents"]
    resource = next(row for row in rows if row["ref"]["entity_id"] == "paper:one")
    assert resource["title"] == "Declared paper note"
    assert resource["role"] == "resource-note"
    assert resource["ref"]["provider_id"] == f"obsidian:{_SOURCE}"


def test_source_note_action_keeps_key_library_and_source_server_side(tmp_path):
    service, _provider, actions, vault = _service(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="vault-one", root=vault, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(source_id=_SOURCE, folder_id="vault-one", capabilities=["read"])],
    ))

    class SourceNoteAdapter:
        def probe_source_note(self, library_id, item_key, *, source_id):
            assert (library_id, item_key, source_id) == ("1", _PAPER, _SOURCE)
            return ZotFlowCapability(available=True)

        def open_source_note(self, library_id, item_key, *, source_id):
            return {"opened": True, "identity": (library_id, item_key, source_id)}

    service._sources = registry
    service._zotflow = ZotFlowSourceNoteLauncher(SourceNoteAdapter())
    actions.add_launcher(ActionKind.ZOTFLOW_SOURCE_NOTE, service._zotflow)
    row = next(row for row in service.public_related(_PAPER)["documents"] if row["role"] == "zotflow-source-note")
    action = row["actions"][0]
    assert row["ref"]["entity_id"] == f"1:{_PAPER}"
    assert actions.execute(action.id)["identity"] == ("1", _PAPER, _SOURCE)
    with pytest.raises(InvalidActionTarget, match="identity is invalid"):
        service._zotflow.open(json.dumps({"library_id": 1, "item_key": "../../oops"}))


def test_related_file_action_has_no_cmux_requirement(tmp_path):
    service, _provider, actions, _vault = _service(tmp_path)
    row = service.public_related(_PAPER)["documents"][0]
    action = row["actions"][0]
    assert action.kind is ActionKind.OBSIDIAN_RELATED_FILE
    assert action.workspace_policy.value == "none"
    assert action in actions.public_actions()["__related__"]
    # Resolve only; opening an application is never part of this fixture.
    registered = actions._registry.resolve(action.id)
    assert service.resolve_file(registered.target).name == "Analysis.md"


def test_conflicting_artifact_owner_is_not_exposed(tmp_path):
    service, provider, _actions, _vault = _service(tmp_path)
    payload = provider.catalog.model_dump(mode="json", exclude={"revision"})
    payload["resources"][0]["artifact_ids"].append("analysis:other")
    provider.catalog = HubCatalog.model_validate(payload)
    result = service.public_related(_PAPER)
    assert "analysis:other" not in {row["ref"]["entity_id"] for row in result["documents"]}
    assert "A related artifact has conflicting paper ownership" in result["diagnostics"]


def test_task_document_ref_checks_current_file_and_owner(tmp_path):
    service, _provider, _actions, vault = _service(tmp_path)
    row = service.public_related(_PAPER)["documents"][0]
    assert service.contains_ref(row["ref"]) is True
    (vault / "one" / "Analysis.md").unlink()
    assert service.contains_ref(row["ref"]) is False
    assert service.contains_ref({**row["ref"], "entity_id": "analysis:other"}) is False
