from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import register, registration_plan
from scholar_workflow.workflows.register_paper import paper_plan, register_paper


class LocalPaper:
    def __init__(self, pdf: Path):
        self.pdf = pdf
        self.title = "Synthetic Paper"
        self.parent = "ABCD2345"
        self.item_key = "ABCD2345"

    def get_item(self, key):
        data = ({"itemType": "preprint", "title": self.title} if key == self.item_key else
                {"itemType": "attachment", "parentItem": self.parent,
                 "contentType": "application/pdf", "linkMode": "imported_file"})
        return {"key": key, "library": {"id": 123, "type": "user"}, "data": data}

    def resolve_attachment_locator(self, key):
        return SimpleNamespace(path=self.pdf, attachment_key=key, library_id="123")


@pytest.fixture
def scope(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("# Existing readable home\n")
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    service = FieldService(registry)
    plan = registration_plan(service, root, field_root=".", existing_source=False)
    manifest = register(service, root, field_root=".", existing_source=False,
                        approved_digest=plan.payload["approved_digest"])
    pdf = tmp_path / "local.pdf"
    pdf.write_bytes(b"%PDF-1.7 synthetic fixture\n")
    selection = {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
                 "item_key": "ABCD2345", "attachment_key": "EFGH2345",
                 "segment": "synthetic", "language": "en"}
    return root, registry, LocalPaper(pdf), selection


def test_zero_write_plan_register_and_replay(scope):
    root, registry, zotero, selection = scope
    initial = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    proposal = paper_plan(registry, zotero, **selection)
    assert proposal == paper_plan(registry, zotero, **selection)
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == initial
    assert not (registry.path.parent / "knowledge-providers").exists()
    result = register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert result["status"] == "registered" and not result["analysis_committed"]
    assert (root / result["owner_path"]).read_text() == proposal["note"]
    provider = load_knowledge_provider_snapshot(registry.path.parent / "knowledge-providers"
                                                / selection["source_id"])
    assert provider.manifest.atomic_resources[0].markdown_path == result["owner_path"]
    assert provider.catalog.resources[0].zotero.item_key == selection["item_key"]
    assert provider.receipts[0].receipt_id == result["receipt_id"]
    assert provider.artifacts == []
    assert register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                          **selection) == result
    fields = FieldService._load_manifest(root)
    assert fields.fields[0].navigation[-1].items == ["resources/papers/synthetic/Paper.md"]
    assert (root / "README.md").read_bytes() == initial[root / "README.md"]


@pytest.mark.parametrize("member", ["member-1", "member-2", "member-3"])
def test_interruption_resumes_only_exact_transaction(scope, member):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)

    def stop(phase):
        if phase == member:
            raise RuntimeError("simulated process interruption")

    with pytest.raises(RuntimeError, match="interruption"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **selection)
    result = register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert result["status"] == "registered"
    assert (root / result["owner_path"]).read_text() == proposal["note"]


def test_human_edit_after_interruption_is_never_overwritten(scope):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)

    def stop(phase):
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **selection)
    note = root / proposal["owner_path"]
    note.write_text("Human changed this note\n")
    with pytest.raises(FieldRegistryError, match="conflict"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert note.read_text() == "Human changed this note\n"
    assert not (registry.path.parent / "knowledge-providers" / selection["source_id"]
                / "knowledge-provider.snapshot.json").exists()


@pytest.mark.parametrize("change", ["title", "pdf", "manifest", "disabled", "capability", "directory"])
def test_changed_authority_refuses_publication(scope, change):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)
    if change == "title":
        zotero.title = "Changed paper"
    elif change == "pdf":
        zotero.pdf.write_bytes(b"new PDF bytes")
    elif change == "manifest":
        path = root / ".scholar-workflow/fields.yml"
        path.write_text(path.read_text() + "\n# Concurrent edit\n")
    elif change == "disabled":
        document = registry.load_document()
        document.sources[0].enabled = False
        registry.save(document)
    elif change == "capability":
        document = registry.load_document()
        document.sources[0].capabilities = ["read"]
        registry.save(document)
    else:
        (root / "resources/papers/synthetic").mkdir(parents=True)
        (root / "resources/papers/synthetic/user.md").write_text("Human\n")
    with pytest.raises((FieldRegistryError, ValueError)):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert not (root / "resources/papers/synthetic/Paper.md").exists()


@pytest.mark.parametrize("segment", ["../outside", "/absolute", "a/b", ".hidden", "a\\b"])
def test_path_escape_rejected(scope, segment):
    _, registry, zotero, selection = scope
    selection["segment"] = segment
    with pytest.raises(FieldRegistryError):
        paper_plan(registry, zotero, **selection)


def test_symlink_ancestor_and_wrong_attachment_parent_refused(scope, tmp_path):
    root, registry, zotero, selection = scope
    (root / "resources").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(FieldRegistryError, match="symbolic"):
        paper_plan(registry, zotero, **selection)
    (root / "resources").unlink()
    zotero.parent = "WRNG2345"
    with pytest.raises(FieldRegistryError, match="identity"):
        paper_plan(registry, zotero, **selection)


def test_journal_digest_tampering_cannot_resume(scope):
    _, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)

    def stop(phase):
        raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=stop, **selection)
    journal = (registry.path.parent / "knowledge-providers" / selection["source_id"]
               / f"paper-registration-{proposal['approved_digest']}.json")
    record = json.loads(journal.read_text())
    record["plan"]["note"] = "Forged note"
    journal.write_text(json.dumps(record))
    with pytest.raises(FieldRegistryError, match="digest"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)


@pytest.mark.parametrize("record", [[], {"status": [], "plan": {}, "applied_at": "invalid"},
                                    {"status": "prepared", "plan": [], "applied_at": "invalid"},
                                    {"status": "prepared", "plan": {}, "applied_at": "invalid"}])
def test_malformed_journal_refuses_without_publishing(scope, record):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    provider.mkdir(parents=True)
    journal = provider / f"paper-registration-{proposal['approved_digest']}.json"
    journal.write_text(json.dumps(record))
    with pytest.raises(FieldRegistryError, match="journal"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert not (root / proposal["owner_path"]).exists()
    assert not (provider / "knowledge-provider.snapshot.json").exists()
    assert json.loads(journal.read_text()) == record


def test_existing_provider_preserved_and_old_receipt_replay(scope):
    root, registry, zotero, selection = scope
    first = paper_plan(registry, zotero, **selection)
    first_result = register_paper(registry, zotero, approved_digest=first["approved_digest"], **selection)
    old_note = (root / first_result["owner_path"]).read_bytes()
    second_zotero = LocalPaper(zotero.pdf)
    second_zotero.item_key = second_zotero.parent = "JKLM2345"
    second_zotero.title = "Second paper"
    second_selection = dict(selection, item_key="JKLM2345", segment="second-paper")
    second = paper_plan(registry, second_zotero, **second_selection)
    register_paper(registry, second_zotero, approved_digest=second["approved_digest"], **second_selection)
    snapshot = load_knowledge_provider_snapshot(registry.path.parent / "knowledge-providers"
                                                / selection["source_id"])
    assert len(snapshot.manifest.atomic_resources) == len(snapshot.catalog.resources) == 2
    assert len(snapshot.receipts) == 2
    replay = register_paper(registry, zotero, approved_digest=first["approved_digest"], **selection)
    assert replay["receipt_id"] == first_result["receipt_id"]
    assert replay["snapshot_revision"] == snapshot.snapshot_revision
    assert (root / first_result["owner_path"]).read_bytes() == old_note
    with pytest.raises(FieldRegistryError, match="duplicate"):
        paper_plan(registry, zotero, **dict(selection, segment="duplicate-paper"))


def test_field_directory_swap_retains_journal_without_false_completion(scope):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)

    def swap(phase):
        if phase == "member-1":
            (root / ".scholar-workflow").rename(root / "preserved-state")
            (root / ".scholar-workflow").mkdir()
            (root / ".scholar-workflow/fields.yml").write_text("human replacement")

    with pytest.raises(FieldRegistryError, match="directory changed"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                       fault_inject=swap, **selection)
    assert (root / ".scholar-workflow/fields.yml").read_text() == "human replacement"
    assert (root / "preserved-state/fields.yml").read_text() == proposal["fields_before"]


def test_public_cli_plan_and_register(scope, monkeypatch):
    from click.testing import CliRunner

    from scholar_workflow.cli import main

    _, registry, zotero, selection = scope

    class ContextPaper(LocalPaper):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("scholar_workflow.adapters.zotero_local.ZoteroLocalAdapter",
                        lambda: ContextPaper(zotero.pdf))
    args = [part for key, value in selection.items()
            for part in ("--" + key.replace("_", "-"), value)]
    runner = CliRunner()
    env = {"SCHOLAR_WORKFLOW_HOME": str(registry.path.parent.parent)}
    proposal = runner.invoke(main, ["knowledge", "paper-plan", *args, "--format", "json"], env=env)
    assert proposal.exit_code == 0, proposal.output
    digest = json.loads(proposal.output)["approved_digest"]
    result = runner.invoke(main, ["knowledge", "register-paper", *args,
                                 "--approved-digest", digest, "--yes"], env=env)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "registered"


def test_registered_owner_accepts_existing_v5_paired_commit(scope, tmp_path):
    from scholar_workflow.analysis.apply_changes import apply_knowledge_change_set
    from scholar_workflow.analysis.commit import commit_analysis_bundle
    from scholar_workflow.analysis.models import AnalysisCommitRequest, AnalysisDocument
    from scholar_workflow.analysis.rendering import render_analysis
    from scholar_workflow.analysis.updates import create_baseline

    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)
    owner = register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    document = AnalysisDocument.model_validate({
        "schema_version": 5, "artifact_id": "analysis:" + owner["resource_id"],
        "paper_title": zotero.title, "language": "en",
        "profile": {"kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True},
        "claims": [{"claim_id": "task", "role": "abstract", "outline_path": "abstract/task",
                    "title": "Task", "body": "Synthetic registration fixture; no scientific claim.",
                    "evidence": {"kind": "not_applicable", "detail": "Synthetic fixture."}}],
    })
    bundle = render_analysis(document, note_stem="Analysis")
    baseline = create_baseline(document, bundle, note_stem="Analysis")
    folder = str(Path(owner["owner_path"]).parent)
    paths = {"markdown": folder + "/Analysis.md", "canvas": folder + "/Tree.canvas",
             "sidecar": folder + "/analysis.baseline.json"}
    request = AnalysisCommitRequest.model_validate({
        "commit_id": "registered-v5-owner", "batch_id": "synthetic-batch", "item_id": "one",
        "source_state": "validated", "resource_id": owner["resource_id"], "note_stem": "Analysis",
        "document": document.model_dump(mode="json"), "paths": paths,
        "base_revisions": {p: None for p in paths.values()},
        "base_catalog_revision": owner["catalog_revision"],
        "base_snapshot_revision": owner["snapshot_revision"], "zotero_item_key": selection["item_key"],
        "relations": [{"from_id": owner["resource_id"], "relation": "has-analysis",
                       "to_id": document.artifact_id}],
    })
    receipt = commit_analysis_bundle(vault_root=root, state_root=tmp_path / "commit-state",
                                    request=request, bundle=bundle, baseline=baseline,
                                    source_registry=registry)
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    apply_knowledge_change_set(state_root=provider, change_set=receipt.change_set)
    snapshot = load_knowledge_provider_snapshot(provider)
    assert len(snapshot.artifacts) == 3
    assert len(snapshot.manifest.supporting_documents) == 2
    assert (root / paths["markdown"]).read_text() == bundle.markdown
    assert register_paper(registry, zotero, approved_digest=proposal["approved_digest"],
                          **selection)["analysis_committed"]
