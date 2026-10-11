"""Synthetic owner-layout and v1 recovery contract; no real library operations.

New root/nested Fields must plan and register resources/<segment>/Paper.md with
Field-relative navigation and zero planning writes. Independently authored legacy
journals retain resources/papers/<segment>/Paper.md through interrupted recovery
and committed replay. Their note, navigation and provider identity must not move.
Nonexact owner paths, altered digests and duplicate existing owners must refuse.
All inputs and observable files live under pytest's temporary directory.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.knowledge.fields import (
    FieldManifest,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.models import KnowledgeAtomicResource
from scholar_workflow.knowledge.registration import registration_plan
from scholar_workflow.models import ResourceKind
from scholar_workflow.workflows.register_paper import paper_plan, register_paper
from scholar_workflow.workflows.register_source import register_source


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


def _scope(tmp_path, field_root="."):
    root = tmp_path / "source"
    root.mkdir()
    (root / "README.md").write_text("# Existing readable home\n")
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    service = FieldService(registry)
    plan = registration_plan(service, root, field_root=".", existing_source=False)
    manifest = register_source(service, root, field_root=".", existing_source=False,
                               approved_digest=plan.payload["approved_digest"])
    if field_root != ".":
        # Explicit portable manifests support nested Fields; auto-preview does not
        # infer that boundary from an empty directory in a plain Markdown Source.
        nested = root / field_root
        nested.mkdir(parents=True)
        (nested / "README.md").write_text("# Existing nested Field home\n")
        document = manifest.model_dump(mode="json")
        document["fields"][0]["relative_root"] = field_root
        manifest = FieldManifest.model_validate(document)
        (root / ".scholar-workflow/fields.yml").write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False))
    pdf = tmp_path / "local.pdf"
    pdf.write_bytes(b"%PDF-1.7 synthetic fixture\n")
    selection = {"source_id": manifest.source_id, "field_id": manifest.fields[0].field_id,
                 "item_key": "ABCD2345", "attachment_key": "EFGH2345",
                 "segment": "synthetic", "language": "en"}
    return root, registry, LocalPaper(pdf), selection


@pytest.fixture
def scope(tmp_path):
    return _scope(tmp_path)


@pytest.fixture(params=[".", "domain/topic"], ids=["root-field", "nested-field"])
def layout_scope(tmp_path, request):
    return _scope(tmp_path, request.param)


def _file_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def _seal_plan(plan):
    """V1 journal digest wire format, independent of the production planner."""
    payload = {key: value for key, value in plan.items() if key != "approved_digest"}
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    plan["approved_digest"] = hashlib.sha256(encoded).hexdigest()
    return plan


def _frozen_legacy_plan(scope):
    """Author a v1 legacy plan directly; never obtain it from paper_plan()."""
    root, registry, zotero, selection = scope
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    provider_before = (provider / "knowledge-provider.snapshot.json").read_text()
    before_snapshot = json.loads(provider_before)
    fields_before = (root / ".scholar-workflow/fields.yml").read_text()
    fields_after = yaml.safe_load(fields_before)
    field = next(row for row in fields_after["fields"]
                 if row["field_id"] == selection["field_id"])
    relative_owner = "resources/papers/synthetic/Paper.md"
    owner_path = (Path(field["relative_root"]) / relative_owner).as_posix()
    field["navigation"].append({"label": "Synthetic Paper", "items": [relative_owner]})
    # This historical note is deliberately different from any current renderer.
    note = "# Synthetic Paper\n\nFrozen legacy owner; preserve these exact bytes.\n"
    return _seal_plan({
        "schema_version": 1,
        "source_id": selection["source_id"], "field_id": selection["field_id"],
        "root_binding": before_snapshot["vault_binding"],
        "registry_hash": registry.revision(), "ownership_read_set": [],
        "paper": {"title": "Synthetic Paper", "item_key": "ABCD2345",
                  "attachment_key": "EFGH2345", "library_id": "123", "library_type": "user",
                  "pdf_hash": "sha256:" + hashlib.sha256(zotero.pdf.read_bytes()).hexdigest()},
        "resource_id": "paper:zotero:123:ABCD2345", "segment": "synthetic", "language": "en",
        "owner_path": owner_path, "note": note, "fields_before": fields_before,
        "fields_after": yaml.safe_dump(fields_after, allow_unicode=True, sort_keys=False),
        "provider_before": provider_before, "before_snapshot": before_snapshot,
    })


def _frozen_legacy_provider(plan, applied_at):
    """Build historical committed state using public schemas, not registration."""
    snapshot = copy.deepcopy(plan["before_snapshot"])
    catalog = copy.deepcopy(snapshot["catalog"])
    catalog["revision"] = ""
    catalog["resources"].append(HubResource(
        resource_id=plan["resource_id"], kind=ResourceKind.PAPER,
        zotero=ZoteroLink(item_key="ABCD2345", attachment_key="EFGH2345"),
    ).model_dump(mode="json"))
    catalog = HubCatalog.model_validate(catalog).model_dump(mode="json")
    digest = plan["approved_digest"]
    semantic = {
        "change_id": "change:" + digest, "change_fingerprint": "sha256:" + digest,
        "source_receipt": "paper-register:" + digest,
        "before_catalog_revision": snapshot["catalog"]["revision"],
        "after_catalog_revision": catalog["revision"], "applied_artifact_ids": [],
    }
    fingerprint = hashlib.sha256(json.dumps(
        semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    snapshot["manifest"]["atomic_resources"].append(KnowledgeAtomicResource(
        resource_id=plan["resource_id"], kind=ResourceKind.PAPER,
        title="Synthetic Paper", markdown_path=plan["owner_path"],
    ).model_dump(mode="json"))
    snapshot.update(snapshot_revision="", catalog=catalog)
    snapshot["receipts"].append(dict(
        semantic, schema_version=1, receipt_id="knowledge-apply:" + fingerprint,
        applied_at=applied_at,
    ))
    return KnowledgeProviderSnapshot.model_validate(snapshot).model_dump(mode="json")


def _install_frozen_legacy_journal(scope, plan, *, applied_members=0, status="prepared"):
    root, registry, _, selection = scope
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    applied_at = "2026-01-02T03:04:05+00:00"
    if applied_members >= 1:
        owner = root / plan["owner_path"]
        owner.parent.mkdir(parents=True)
        owner.write_text(plan["note"])
    if applied_members >= 2:
        (root / ".scholar-workflow/fields.yml").write_text(plan["fields_after"])
    if applied_members >= 3:
        after = _frozen_legacy_provider(plan, applied_at)
        (provider / "knowledge-provider.snapshot.json").write_text(
            json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    journal = provider / f"paper-registration-{plan['approved_digest']}.json"
    journal.write_text(json.dumps({"status": status, "plan": plan, "applied_at": applied_at},
                                  ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return journal


def test_new_owner_root_and_nested_layout_plan_is_zero_write_and_navigation_is_relative(layout_scope):
    root, registry, zotero, selection = layout_scope
    field = FieldService._load_manifest(root).fields[0]
    expected_owner = (Path(field.relative_root) / "resources/synthetic/Paper.md").as_posix()
    before_files = _file_bytes(root.parent)
    before_directories = {path.relative_to(root.parent).as_posix()
                          for path in root.parent.rglob("*") if path.is_dir()}
    proposal = paper_plan(registry, zotero, **selection)
    assert proposal == paper_plan(registry, zotero, **selection)
    assert proposal["owner_path"] == expected_owner
    assert _file_bytes(root.parent) == before_files
    assert {path.relative_to(root.parent).as_posix()
            for path in root.parent.rglob("*") if path.is_dir()} == before_directories
    planned_field = next(row for row in yaml.safe_load(proposal["fields_after"])["fields"]
                         if row["field_id"] == selection["field_id"])
    assert planned_field["navigation"][-1]["items"] == ["resources/synthetic/Paper.md"]
    result = register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert result["owner_path"] == expected_owner
    assert (root / expected_owner).read_text() == proposal["note"]
    assert not (root / field.relative_root / "resources/papers/synthetic").exists()
    registered_field = FieldService._load_manifest(root).fields[0]
    assert registered_field.navigation[-1].items == ["resources/synthetic/Paper.md"]
    provider = load_knowledge_provider_snapshot(registry.path.parent / "knowledge-providers"
                                                / selection["source_id"])
    assert provider.manifest.atomic_resources[0].markdown_path == expected_owner


@pytest.mark.parametrize("applied_members", [1, 2, 3])
def test_frozen_legacy_interruption_recovers_in_place(layout_scope, applied_members):
    root, registry, zotero, selection = layout_scope
    plan = _frozen_legacy_plan(layout_scope)
    journal = _install_frozen_legacy_journal(layout_scope, plan, applied_members=applied_members)
    original_note = (root / plan["owner_path"]).read_bytes()
    result = register_paper(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert result["status"] == "registered"
    assert result["owner_path"] == plan["owner_path"]
    assert (root / plan["owner_path"]).read_bytes() == original_note
    field = FieldService._load_manifest(root).fields[0]
    assert field.navigation[-1].items == ["resources/papers/synthetic/Paper.md"]
    assert not (root / field.relative_root / "resources/synthetic").exists()
    provider = load_knowledge_provider_snapshot(journal.parent)
    assert provider.manifest.atomic_resources[0].markdown_path == plan["owner_path"]
    assert len(provider.manifest.atomic_resources) == len(provider.receipts) == 1
    record = json.loads(journal.read_text())
    assert record["status"] == "committed" and record["plan"] == plan


def test_frozen_legacy_committed_replay_preserves_bytes_and_receipt(layout_scope):
    root, registry, zotero, selection = layout_scope
    plan = _frozen_legacy_plan(layout_scope)
    journal = _install_frozen_legacy_journal(layout_scope, plan, applied_members=3, status="committed")
    members = [root / plan["owner_path"], root / ".scholar-workflow/fields.yml",
               journal.parent / "knowledge-provider.snapshot.json", journal]
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in members}
    receipt_id = json.loads(before[members[2]][0])["receipts"][0]["receipt_id"]
    result = register_paper(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert result["owner_path"] == plan["owner_path"] and result["receipt_id"] == receipt_id
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in members} == before
    field = FieldService._load_manifest(root).fields[0]
    assert not (root / field.relative_root / "resources/synthetic").exists()


@pytest.mark.parametrize("owner_path", [
    "resources/synthetic-extra/Paper.md", "resources/papers/synthetic-extra/Paper.md",
    "resources/papers-extra/synthetic/Paper.md", "resources/synthetic/nested/Paper.md",
    "resources/papers/synthetic/nested/Paper.md", "resources/./synthetic/Paper.md",
    "resources/papers/synthetic/../synthetic/Paper.md", "other/resources/synthetic/Paper.md",
])
def test_nonexact_new_or_legacy_journal_owner_refuses_without_publication(scope, owner_path):
    root, registry, zotero, selection = scope
    plan = _frozen_legacy_plan(scope)
    plan["owner_path"] = owner_path
    _seal_plan(plan)
    journal = _install_frozen_legacy_journal(scope, plan)
    before = _file_bytes(root.parent)
    with pytest.raises(FieldRegistryError):
        register_paper(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert _file_bytes(root.parent) == before
    assert json.loads(journal.read_text())["status"] == "prepared"
    assert not (root / "resources").exists()


def test_frozen_legacy_journal_digest_tampering_preserves_interrupted_owner(scope):
    root, registry, zotero, selection = scope
    plan = _frozen_legacy_plan(scope)
    journal = _install_frozen_legacy_journal(scope, plan, applied_members=1)
    record = json.loads(journal.read_text())
    record["plan"]["note"] = "Forged replacement note\n"
    journal.write_text(json.dumps(record))
    before = _file_bytes(root.parent)
    with pytest.raises(FieldRegistryError, match="digest"):
        register_paper(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    assert _file_bytes(root.parent) == before
    assert (root / plan["owner_path"]).read_text() == plan["note"]
    assert not (root / "resources/synthetic").exists()


def test_existing_frozen_legacy_owner_blocks_duplicate_new_layout(layout_scope):
    root, registry, zotero, selection = layout_scope
    plan = _frozen_legacy_plan(layout_scope)
    _install_frozen_legacy_journal(layout_scope, plan, applied_members=3, status="committed")
    before = _file_bytes(root.parent)
    with pytest.raises(FieldRegistryError, match="duplicate"):
        paper_plan(registry, zotero, **dict(selection, segment="another-owner"))
    assert _file_bytes(root.parent) == before
    assert (root / plan["owner_path"]).read_text() == plan["note"]
    field = FieldService._load_manifest(root).fields[0]
    assert not (root / field.relative_root / "resources/another-owner").exists()


def test_zero_write_plan_register_and_replay(scope):
    root, registry, zotero, selection = scope
    initial = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    provider_path = (registry.path.parent / "knowledge-providers" / selection["source_id"]
                     / "knowledge-provider.snapshot.json")
    provider_before = provider_path.read_bytes()
    proposal = paper_plan(registry, zotero, **selection)
    assert proposal["owner_path"] == "resources/synthetic/Paper.md"
    assert proposal == paper_plan(registry, zotero, **selection)
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == initial
    assert provider_path.read_bytes() == provider_before
    assert json.loads(provider_before)["manifest"]["atomic_resources"] == []
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
    assert fields.fields[0].navigation[-1].items == ["resources/synthetic/Paper.md"]
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
    provider = (registry.path.parent / "knowledge-providers" / selection["source_id"]
                / "knowledge-provider.snapshot.json")
    provider_before = provider.read_bytes()
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
    assert provider.read_bytes() == provider_before
    assert json.loads(provider_before)["manifest"]["atomic_resources"] == []


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
        (root / "resources/synthetic").mkdir(parents=True)
        (root / "resources/synthetic/user.md").write_text("Human\n")
    with pytest.raises((FieldRegistryError, ValueError)):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert not (root / "resources/synthetic/Paper.md").exists()


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
    provider_before = (provider / "knowledge-provider.snapshot.json").read_bytes()
    journal = provider / f"paper-registration-{proposal['approved_digest']}.json"
    journal.write_text(json.dumps(record))
    with pytest.raises(FieldRegistryError, match="journal"):
        register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    assert not (root / proposal["owner_path"]).exists()
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == provider_before
    assert json.loads(provider_before)["manifest"]["atomic_resources"] == []
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
