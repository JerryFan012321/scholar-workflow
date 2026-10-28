"""A synthetic new Source must be usable by its next real ownership operation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.knowledge.fields import FieldRegistryError, KnowledgeSourceRegistry
from scholar_workflow.project.context import ProjectOverview
from scholar_workflow.workflows.field_transaction import LocalFieldTransactions
from scholar_workflow.workflows.knowledge_ownership import resolve_project_knowledge
from scholar_workflow.workflows.register_document import document_plan, register_document
from scholar_workflow.workflows.register_paper import paper_plan, register_paper


class LocalPaper:
    """A local fixture, not a network Zotero client."""

    def __init__(self, pdf: Path):
        self.pdf = pdf

    def get_item(self, key):
        data = ({"itemType": "preprint", "title": "Handoff fixture"} if key == "ABCD2345" else
                {"itemType": "attachment", "parentItem": "ABCD2345",
                 "contentType": "application/pdf", "linkMode": "imported_file"})
        return {"key": key, "library": {"id": 123, "type": "user"}, "data": data}

    def resolve_attachment_locator(self, key):
        return SimpleNamespace(path=self.pdf, attachment_key=key, library_id="123")


def _selection(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("# Existing readable home\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    workflow = LocalFieldTransactions(registry, state_root=tmp_path / "recovery")
    planned = workflow.plan(root=root, field_root=".")
    provider = registry.path.parent / "knowledge-providers" / planned["request"]["source_id"]
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.7 local handoff fixture\n")
    paper = {"source_id": planned["request"]["source_id"],
             "field_id": planned["request"]["field"]["field_id"],
             "item_key": "ABCD2345", "attachment_key": "EFGH2345",
             "segment": "handoff-paper", "language": "en"}
    return root, registry, workflow, planned, provider, LocalPaper(pdf), paper


def test_new_source_transaction_hands_off_to_real_paper_ownership(tmp_path):
    root, registry, workflow, planned, provider, client, paper = _selection(tmp_path)
    assert not registry.path.exists() and not provider.exists()
    # The shared public plan can be consumed by a legacy HTTP client; only the
    # trusted local request envelope may contain the explicitly selected root.
    assert str(root) not in json.dumps(planned["plan"])
    workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                   external_writers_paused=True)

    snapshot = load_knowledge_provider_snapshot(provider)
    assert snapshot.vault_binding.root_path == str(root)
    assert snapshot.manifest.atomic_resources == []
    proposal = paper_plan(registry, client, **paper)
    registered = register_paper(registry, client, approved_digest=proposal["approved_digest"], **paper)
    assert registered["status"] == "registered"
    snapshot = load_knowledge_provider_snapshot(provider)
    assert len(snapshot.manifest.atomic_resources) == 1
    assert (root / "resources/handoff-paper/Paper.md").is_file()
    overview = ProjectOverview(
        project_id="11111111-1111-4111-8111-111111111111", title="Handoff project",
        summary="Reference the same registered paper unit without copying it.", entries=[{
            "entry_id": "baseline-paper", "kind": "paper", "title": "Handoff fixture",
            "purpose": "Baseline source", "state": "unverified", "diagnostic": "Not queried",
            "ref": {"kind": "external-resource", "provider": "obsidian",
                    "resource_id": registered["resource_id"], "uri": None},
        }],
    )
    before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    resolved = resolve_project_knowledge(overview, registry.path)["baseline-paper"]
    assert resolved.status == "resolved"
    assert len(resolved.locations) == 1
    assert resolved.locations[0].source_id == paper["source_id"]
    assert resolved.locations[0].field_id == paper["field_id"]
    assert resolved.locations[0].relative_path == "resources/handoff-paper/Paper.md"
    assert resolved.locations[0].file_state == "available"
    assert resolved.reader_state == "unverified"
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == before


def test_new_source_inventory_collision_is_refused_before_field_writes(tmp_path):
    root, registry, workflow, planned, provider, _, _ = _selection(tmp_path)
    provider.mkdir(parents=True)
    sentinel = provider / "human.txt"
    sentinel.write_text("Keep unknown inventory\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory|provider"):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                       external_writers_paused=True)
    assert not registry.path.exists()
    assert not (root / ".scholar-workflow/fields.yml").exists()
    assert sentinel.read_text() == "Keep unknown inventory\n"


def test_existing_source_missing_inventory_is_never_recreated(tmp_path):
    root, registry, workflow, planned, provider, client, paper = _selection(tmp_path)
    workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                   external_writers_paused=True)
    snapshot_file = provider / "knowledge-provider.snapshot.json"
    snapshot_file.unlink()
    with pytest.raises(FieldRegistryError, match="inventory is missing"):
        paper_plan(registry, client, **paper)
    assert not snapshot_file.exists()
    assert registry.resolve(paper["source_id"]) == root


@pytest.mark.parametrize("published", [False, True], ids=["before-registry", "after-registry"])
def test_interrupted_inventory_member_recovers_with_the_original_field_journal(
    tmp_path, monkeypatch, published,
):
    import scholar_workflow.knowledge.field_transaction as core

    root, registry, workflow, planned, provider, client, paper = _selection(tmp_path)
    original = registry._save_locked

    def interrupted(*args, **kwargs):
        # The Source must never become visible before its inventory is usable.
        load_knowledge_provider_snapshot(provider)
        if published:
            original(*args, **kwargs)
        raise OSError("synthetic stop at registry publication")

    def stopped(*args, **kwargs):
        raise core.FieldTransactionError("synthetic process ended")

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_save_locked", interrupted)
        patch.setattr(core.FieldTransactionService, "_recover_locked", stopped)
        with pytest.raises(ValueError, match="recover explicitly"):
            workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                           external_writers_paused=True)
    restarted = LocalFieldTransactions(registry, state_root=workflow.state_root)
    result = restarted.recover(paper["source_id"], paper["field_id"], external_writers_paused=True)
    assert result.outcome == ("committed" if published else "rolled-back")
    assert load_knowledge_provider_snapshot(provider).manifest.atomic_resources == []
    if published:
        assert paper_plan(registry, client, **paper)["resource_id"] == "paper:zotero:123:ABCD2345"
    else:
        assert not (root / ".scholar-workflow/fields.yml").exists()
        assert registry.load_document().sources == []


def test_published_inventory_missing_during_recovery_is_not_recreated(tmp_path, monkeypatch):
    import scholar_workflow.knowledge.field_transaction as core

    _, _registry, workflow, planned, provider, _, paper = _selection(tmp_path)

    def stopped(*args, **kwargs):
        raise OSError("synthetic stop before clearing journal")

    with monkeypatch.context() as patch:
        patch.setattr(core.FieldTransactionService, "_clear_journal", stopped)
        with pytest.raises(ValueError, match="may already be published"):
            workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                           external_writers_paused=True)
    snapshot_file = provider / "knowledge-provider.snapshot.json"
    snapshot_file.unlink()
    with pytest.raises(ValueError, match="inventory.*missing"):
        workflow.recover(paper["source_id"], paper["field_id"], external_writers_paused=True)
    assert not snapshot_file.exists()
    assert list(workflow.state_root.rglob("pending.json"))


def test_unknown_inventory_change_refuses_unpublished_recovery(tmp_path, monkeypatch):
    import scholar_workflow.knowledge.field_transaction as core

    root, registry, workflow, planned, provider, _, paper = _selection(tmp_path)

    def stopped(*args, **kwargs):
        raise core.FieldTransactionError("synthetic process ended")

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_save_locked", stopped)
        patch.setattr(core.FieldTransactionService, "_recover_locked", stopped)
        with pytest.raises(ValueError, match="recover explicitly"):
            workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                           external_writers_paused=True)
    path = provider / "knowledge-provider.snapshot.json"
    # Semantically empty but externally edited bytes are not this journal's member.
    changed = path.read_bytes() + b"\n"
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="inventory.*changed"):
        workflow.recover(paper["source_id"], paper["field_id"], external_writers_paused=True)
    assert path.read_bytes() == changed
    assert (root / ".scholar-workflow/fields.yml").exists()
    assert registry.load_document().sources == []


def test_inventory_creation_failure_rolls_back_field_and_never_registers_source(tmp_path, monkeypatch):
    import scholar_workflow.knowledge.field_transaction as core

    root, registry, workflow, planned, provider, _, _ = _selection(tmp_path)

    def stopped(*args, **kwargs):
        raise OSError("synthetic inventory write failure")

    monkeypatch.setattr(core, "create_inventory", stopped)
    with pytest.raises(ValueError, match="rolled back"):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                       external_writers_paused=True)
    assert registry.load_document().sources == []
    assert not (root / ".scholar-workflow/fields.yml").exists()
    assert not provider.exists()


def test_new_source_retains_staged_relocation_and_usable_inventory(tmp_path):
    root, registry, workflow, _initial, provider, client, paper = _selection(tmp_path)
    (root / "Note.md").write_text("# Retain this note\n", encoding="utf-8")
    (root / "README.md").write_text("# Home\n\n[Note](Note.md)\n", encoding="utf-8")
    baseline = workflow.plan(root=root, field_root=".")
    field = baseline["request"]["field"]
    for group in field["navigation"]:
        group["items"] = ["notes/Note.md" if item == "Note.md" else item for item in group["items"]]
    planned = workflow.plan(root=root, field_root=".", proposal={
        "field": field, "relocations": {"Note.md": "notes/Note.md"},
        "link_rewrites": {"README.md": {"Note.md": "notes/Note.md"}},
    })
    workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                   external_writers_paused=True)
    source_id = planned["request"]["source_id"]
    provider = registry.path.parent / "knowledge-providers" / source_id
    assert load_knowledge_provider_snapshot(provider).manifest.atomic_resources == []
    assert not (root / "Note.md").exists()
    assert (root / "notes/Note.md").read_text() == "# Retain this note\n"
    assert paper_plan(registry, client, **dict(paper, source_id=source_id,
        field_id=field["field_id"]))["resource_id"] == "paper:zotero:123:ABCD2345"


def test_inventory_parent_symlink_is_not_followed(tmp_path):
    root, registry, workflow, planned, _, _, _ = _selection(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    registry.path.parent.mkdir(parents=True)
    (registry.path.parent / "knowledge-providers").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="inventory|provider"):
        workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                       external_writers_paused=True)
    assert list(outside.iterdir()) == []
    assert not (root / ".scholar-workflow/fields.yml").exists()


def test_inventory_recovery_rejects_a_symlinked_parent(tmp_path, monkeypatch):
    import scholar_workflow.knowledge.field_transaction as core

    _, registry, workflow, planned, provider, _, paper = _selection(tmp_path)

    def stopped(*args, **kwargs):
        raise core.FieldTransactionError("synthetic process ended")

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_save_locked", stopped)
        patch.setattr(core.FieldTransactionService, "_recover_locked", stopped)
        with pytest.raises(ValueError, match="recover explicitly"):
            workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                           external_writers_paused=True)
    before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    moved = registry.path.parent / "retained-inventories"
    provider.parent.rename(moved)
    provider.parent.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match="inventory recovery"):
        workflow.recover(paper["source_id"], paper["field_id"], external_writers_paused=True)
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == before
    assert list(workflow.state_root.rglob("pending.json"))


def test_inventory_recovery_member_cannot_be_retargeted(tmp_path, monkeypatch):
    import scholar_workflow.knowledge.field_transaction as core

    _, registry, workflow, planned, provider, _, paper = _selection(tmp_path)

    def stopped(*args, **kwargs):
        raise core.FieldTransactionError("synthetic process ended")

    with monkeypatch.context() as patch:
        patch.setattr(registry, "_save_locked", stopped)
        patch.setattr(core.FieldTransactionService, "_recover_locked", stopped)
        with pytest.raises(ValueError, match="recover explicitly"):
            workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                           external_writers_paused=True)
    journal = next(workflow.state_root.rglob("pending.json"))
    payload = json.loads(journal.read_text())
    payload["inventory_initialization"]["source_id"] = "00000000-0000-0000-0000-000000000001"
    journal.write_text(json.dumps(payload))
    before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    with pytest.raises(ValueError, match="inventory|snapshot receipt"):
        workflow.recover(paper["source_id"], paper["field_id"], external_writers_paused=True)
    assert journal.is_file()
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == before


@pytest.mark.parametrize("item_type", ["webpage", "blogPost"])
def test_new_source_hands_off_complete_nonpaper_units_without_fake_pdf(tmp_path, item_type):
    root, registry, workflow, planned, provider, _, paper = _selection(tmp_path)
    workflow.apply(planned, approved_digest=planned["plan"]["plan_digest"],
                   external_writers_paused=True)
    url = "https://example.org/research/selected-article"
    client = SimpleNamespace(get_item=lambda key: {
        "key": key, "version": 1, "library": {"id": 123, "type": "user"},
        "data": {"itemType": item_type, "title": "Selected source fixture", "url": url},
    })
    source = tmp_path / "original.md"
    source.write_text("# Selected article\n\nA synthetic source statement.\n^source-one\n")
    selection = {"source_id": paper["source_id"], "field_id": paper["field_id"],
                 "item_key": "BLAG2345", "segment": "article", "language": "en",
                 "markdown_path": source, "source_url": url,
                 "retrieved_at": "2026-01-02T03:04:05+00:00"}
    preview = document_plan(registry, client, **selection)
    result = register_document(registry, client, approved_digest=preview["approved_digest"], **selection)
    assert result["resource_id"] == "document:zotero:123:BLAG2345"
    assert not result["analysis_committed"]
    snapshot = load_knowledge_provider_snapshot(provider)
    assert len(snapshot.manifest.atomic_resources) == 1
    assert snapshot.catalog.resources[0].zotero.attachment_key is None
    assert (root / "resources/article/Source.md").read_bytes() == source.read_bytes()
