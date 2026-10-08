"""A copied Source restores ownership, never overwrites content or host authority."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.models import AnalysisBaseline, AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import create_baseline
from scholar_workflow.cli import main
from scholar_workflow.knowledge.catalog_models import HubCatalog
from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import register, registration_plan
from scholar_workflow.workflows.knowledge_reproduction import (
    reproduction_plan,
    restore,
    restore_plan,
)
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def destination(canvas_scope, scope, tmp_path):
    source, source_registry, selection, paths, _ = canvas_scope
    exported = reproduction_plan(source_registry, source_id=selection["source_id"])
    root = tmp_path / "copied-source"
    shutil.copytree(source, root)
    registry = KnowledgeSourceRegistry(tmp_path / "new-host/hub/sources.json")
    service = FieldService(registry)
    preview = registration_plan(service, root, field_root=None, existing_source=True)
    register(service, root, field_root=None, existing_source=True,
             approved_digest=preview.payload["approved_digest"])
    package = tmp_path / "replay.json"
    package.write_text(json.dumps(exported))
    return root, registry, scope[2], selection["source_id"], package, paths, source, source_registry


def plan_and_restore(destination, **kwargs):
    root, registry, zotero, source_id, package, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    result = restore(registry, zotero, source_id=source_id, package=package,
                     approved_digest=plan["approved_digest"], **kwargs)
    return root, plan, result


def test_fresh_host_plan_is_zero_write_and_restoration_preserves_every_byte(destination):
    root, registry, zotero, source_id, package, _, source, source_registry = destination
    before, old_state, new_state = files(root), files(source_registry.path.parent), files(registry.path.parent)
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    assert plan == restore_plan(registry, zotero, source_id=source_id, package=package)
    assert files(root) == before and files(registry.path.parent) == new_state
    result = restore(registry, zotero, source_id=source_id, package=package,
                     approved_digest=plan["approved_digest"])
    assert result["status"] == "ownership-restored" and result["content_rewritten"] is False
    assert result["source_identity_verified"] is True
    assert result["human_verified"] is False and result["reproduction_complete"] is False
    provider = load_knowledge_provider_snapshot(registry.path.parent / "knowledge-providers" / source_id)
    assert provider.vault_binding.root_path == str(root)
    assert provider.manifest == load_knowledge_provider_snapshot(
        source_registry.path.parent / "knowledge-providers" / source_id).manifest
    assert provider.receipts == []
    assert files(root) == before == files(source) and files(source_registry.path.parent) == old_state
    assert restore(registry, zotero, source_id=source_id, package=package,
                   approved_digest=plan["approved_digest"]) == result
    with pytest.raises(FieldRegistryError, match="existing provider"):
        restore_plan(registry, zotero, source_id=source_id, package=package)


@pytest.mark.parametrize("member", ["markdown", "fields", "package", "registry", "pdf"])
def test_changed_reviewed_input_never_creates_provider(destination, member):
    root, registry, zotero, source_id, package, paths, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    path = {"markdown": root / paths["markdown"], "fields": root / ".scholar-workflow/fields.yml",
            "package": package, "registry": registry.path, "pdf": zotero.pdf}[member]
    path.write_bytes(path.read_bytes() + b"\n")
    before = files(root)
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        restore(registry, zotero, source_id=source_id, package=package, approved_digest=plan["approved_digest"])
    assert files(root) == before
    assert not (registry.path.parent / "knowledge-providers" / source_id / "knowledge-provider.snapshot.json").exists()


def test_wrong_attachment_membership_refuses_without_initializing_state(destination):
    _, registry, zotero, source_id, package, *_ = destination
    zotero.parent = "WRNG2345"
    before = files(registry.path.parent)
    with pytest.raises(FieldRegistryError, match="identity"):
        restore_plan(registry, zotero, source_id=source_id, package=package)
    assert files(registry.path.parent) == before


@pytest.mark.parametrize("phase", ["prepared", "provider-created"])
def test_interruption_can_replay_only_the_same_reviewed_transaction(destination, phase):
    _, registry, zotero, source_id, package, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    def interrupt(current):
        if current == phase:
            raise RuntimeError("interrupted")
    with pytest.raises(RuntimeError, match="interrupted"):
        restore(registry, zotero, source_id=source_id, package=package,
                approved_digest=plan["approved_digest"], fault_inject=interrupt)
    result = restore(registry, zotero, source_id=source_id, package=package, approved_digest=plan["approved_digest"])
    assert result["status"] == "ownership-restored"


def test_edit_after_interruption_is_preserved_and_not_claimed_as_restored(destination):
    root, registry, zotero, source_id, package, paths, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    def interrupt(_):
        raise RuntimeError("interrupted")
    with pytest.raises(RuntimeError):
        restore(registry, zotero, source_id=source_id, package=package,
                approved_digest=plan["approved_digest"], fault_inject=interrupt)
    target = root / paths["markdown"]
    target.write_text("Human edit\n")
    with pytest.raises(FieldRegistryError):
        restore(registry, zotero, source_id=source_id, package=package, approved_digest=plan["approved_digest"])
    assert target.read_text() == "Human edit\n"


def test_symlink_package_is_rejected(destination, tmp_path):
    _, registry, zotero, source_id, package, *_ = destination
    link = tmp_path / "linked.json"
    link.symlink_to(package)
    with pytest.raises((FieldRegistryError, OSError)):
        restore_plan(registry, zotero, source_id=source_id, package=link)


def test_portable_input_cannot_reintroduce_host_binding(destination):
    root, registry, zotero, source_id, package, *_ = destination
    data = json.loads(package.read_text())["package"]
    data["provider"]["vault_binding"] = {"root_path": str(root), "device": 1, "inode": 1}
    data["provider"]["snapshot_revision"] = ""
    data["provider"] = KnowledgeProviderSnapshot.model_validate(data["provider"]).model_dump(mode="json")
    package.write_text(json.dumps(data))
    with pytest.raises(FieldRegistryError, match="portable"):
        restore_plan(registry, zotero, source_id=source_id, package=package)


@pytest.mark.parametrize("member", ["markdown", "provider", "root", "state-directory", "registry"])
def test_concurrent_change_during_restore_inspection_cannot_return_approval(destination, member):
    root, registry, zotero, source_id, package, paths, *_ = destination
    def change():
        if member == "root":
            root.rename(root.parent / "preserved-source")
            root.mkdir()
        elif member == "state-directory":
            (root / ".scholar-workflow").rename(root / "preserved-manifest")
            (root / ".scholar-workflow").mkdir()
        elif member == "provider":
            folder = registry.path.parent / "knowledge-providers" / source_id
            folder.mkdir(parents=True)
            (folder / "knowledge-provider.snapshot.json").write_text("Concurrent provider\n")
        else:
            path = root / paths["markdown"] if member == "markdown" else registry.path
            path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        restore_plan(registry, zotero, source_id=source_id, package=package, _before_verify=change)


def test_journal_tampering_never_creates_provider(destination):
    _, registry, zotero, source_id, package, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    def stop(_):
        raise RuntimeError("interruption")
    with pytest.raises(RuntimeError):
        restore(registry, zotero, source_id=source_id, package=package,
                approved_digest=plan["approved_digest"], fault_inject=stop)
    provider = registry.path.parent / "knowledge-providers" / source_id
    journal = provider / f"knowledge-reproduction-{plan['approved_digest']}.json"
    record = json.loads(journal.read_text())
    record["plan"]["root_binding"]["inode"] += 1
    journal.write_text(json.dumps(record))
    with pytest.raises(FieldRegistryError, match="digest"):
        restore(registry, zotero, source_id=source_id, package=package, approved_digest=plan["approved_digest"])
    assert not (provider / "knowledge-provider.snapshot.json").exists()


@pytest.mark.parametrize("content", ["[]", '{"package":[]}',
                                    '{"schema_version":1,"schema_version":1}', '{"unexpected":true}'])
def test_malformed_input_is_a_refusal(destination, content):
    _, registry, zotero, source_id, package, *_ = destination
    package.write_text(content)
    with pytest.raises((FieldRegistryError, ValueError)):
        restore_plan(registry, zotero, source_id=source_id, package=package)


def test_read_only_destination_never_receives_provider(destination):
    _, registry, zotero, source_id, package, *_ = destination
    document = registry.load_document()
    document.sources[0].capabilities = ["read"]
    registry.save(document)
    before = files(registry.path.parent)
    with pytest.raises(FieldRegistryError):
        restore(registry, zotero, source_id=source_id, package=package, approved_digest="a" * 64)
    assert files(registry.path.parent) == before


@pytest.mark.parametrize("fmt,language", [("json", "en"), ("md", "en"), ("md", "zh")])
def test_public_restore_cli_separates_human_summary_and_machine_record(destination, monkeypatch, fmt, language):
    _, registry, zotero, source_id, package, *_ = destination
    from contextlib import nullcontext
    monkeypatch.setattr("scholar_workflow.adapters.zotero_local.ZoteroLocalAdapter", lambda: nullcontext(zotero))
    args = ["--source-id", source_id, "--package", str(package), "--format", fmt, "--language", language]
    env = {"SCHOLAR_WORKFLOW_HOME": str(registry.path.parent.parent)}
    runner = CliRunner()
    preview = runner.invoke(main, ["knowledge", "restore-plan", *args], env=env)
    assert preview.exit_code == 0, preview.output
    if fmt == "json":
        plan = json.loads(preview.output)
        assert plan["human_verified"] is False
    else:
        assert '"provider_after"' not in preview.output
        assert "尚未写入" in preview.output if language == "zh" else "Nothing written" in preview.output
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    published = runner.invoke(main, ["knowledge", "restore", *args, "--yes",
                                     "--approved-digest", plan["approved_digest"]], env=env)
    assert published.exit_code == 0, published.output
    if fmt == "json":
        assert json.loads(published.output)["status"] == "ownership-restored"
    else:
        assert '"snapshot_revision"' not in published.output
        assert "已恢复归属" in published.output if language == "zh" else "Ownership restored" in published.output


def changed_synthetic_document(destination, *, reader=None, evidence=None, canvas_note_path=None):
    """Independent synthetic input, not a real paper re-analysis."""
    root, _, _, _, package, paths, *_ = destination
    portable = json.loads(package.read_text())["package"]
    baseline = AnalysisBaseline.model_validate_json((root / paths["sidecar"]).read_bytes())
    value = baseline.document.model_dump(mode="json")
    if canvas_note_path is not None:
        value["profile"]["canvas_note_path"] = canvas_note_path
    if reader is not None:
        value["reader"] = reader
    if evidence is not None:
        value["claims"][0]["evidence"] = evidence
    document = AnalysisDocument.model_validate(value)
    bundle = render_analysis(document, note_stem="Analysis")
    fresh = create_baseline(document, bundle, note_stem="Analysis")
    (root / paths["markdown"]).write_text(bundle.markdown)
    (root / paths["canvas"]).write_text(json.dumps(bundle.canvas, ensure_ascii=False))
    (root / paths["sidecar"]).write_text(fresh.model_dump_json())
    for artifact in portable["provider"]["artifacts"]:
        artifact["sha256"] = "sha256:" + hashlib.sha256((root / artifact["vault_path"]).read_bytes()).hexdigest()
    revisions = {a["artifact_id"]: a["sha256"] for a in portable["provider"]["artifacts"]}
    for artifact in portable["provider"]["catalog"]["artifacts"]:
        artifact["revision"] = revisions[artifact["artifact_id"]]
    portable["provider"]["catalog"]["revision"] = ""
    portable["provider"]["catalog"] = HubCatalog.model_validate(
        portable["provider"]["catalog"]).model_dump(mode="json")
    portable["provider"]["snapshot_revision"] = ""
    portable["provider"] = KnowledgeProviderSnapshot.model_validate(portable["provider"]).model_dump(mode="json")
    for path in portable["files"]:
        portable["files"][path] = "sha256:" + hashlib.sha256((root / path).read_bytes()).hexdigest()
    portable["reader_rebind_required"] = [document.artifact_id] if reader else []
    package.write_text(json.dumps(portable))


def test_new_reader_id_is_pending_and_does_not_block_file_ownership(destination, monkeypatch):
    changed_synthetic_document(destination, reader={"kind": "zotflow_library", "vault_id": "a" * 16})
    from types import SimpleNamespace
    monkeypatch.setattr("scholar_workflow.adapters.obsidian_registry.resolve_obsidian_reader",
                        lambda _: SimpleNamespace(vault_id="b" * 16))
    root, _, result = plan_and_restore(destination)
    assert result["readers"][0]["status"] == "rebinding-required"
    assert result["readers"][0]["reader_launch_verified"] is False
    assert not result["reproduction_complete"]
    assert "a" * 16 in (root / destination[5]["sidecar"]).read_text()


@pytest.mark.parametrize('moved', [False, True])
def test_reader_companion_uses_owned_nested_markdown_path(destination, monkeypatch, moved):
    from types import SimpleNamespace
    root, registry, zotero, source_id, package, paths, *_ = destination
    expected = (root / paths['markdown']).relative_to(root.parent).as_posix()
    saved = 'old-source/' + paths['markdown'] if moved else expected
    changed_synthetic_document(destination, canvas_note_path=saved)
    monkeypatch.setattr('scholar_workflow.adapters.obsidian_registry.resolve_obsidian_reader',
                        lambda _: SimpleNamespace(vault_id='b' * 16, vault_root=root.parent))
    before = files(root)
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    reader = plan['readers'][0]
    assert reader['destination_canvas_note_path'] == expected
    assert reader['saved_canvas_note_path'] == saved
    assert reader['canvas_note_binding'] == ('rebinding-required' if moved else 'binding-matched')
    assert not reader['reader_launch_verified']
    assert files(root) == before


def test_saved_evidence_hash_must_match_current_local_pdf(destination):
    changed_synthetic_document(destination, evidence={
        "kind": "author_stated", "anchor": "PDF page 1", "source_spans": [{
            "kind": "zotero_pdf", "library_type": "personal", "library_id": "123",
            "attachment_key": "EFGH2345", "content_hash": "sha256:" + "0" * 64,
            "page_index": 0, "quote": "A synthetic sentence."}]})
    _, registry, zotero, source_id, package, *_ = destination
    with pytest.raises(FieldRegistryError, match="PDF hash"):
        restore_plan(registry, zotero, source_id=source_id, package=package)


def test_provider_created_by_another_actor_after_preparation_is_not_overwritten(destination):
    _, registry, zotero, source_id, package, *_ = destination
    plan = restore_plan(registry, zotero, source_id=source_id, package=package)
    provider = registry.path.parent / "knowledge-providers" / source_id / "knowledge-provider.snapshot.json"
    def conflict(phase):
        if phase == "prepared":
            provider.write_text("Other owner\n")
    with pytest.raises(FieldRegistryError, match="existing provider"):
        restore(registry, zotero, source_id=source_id, package=package,
                approved_digest=plan["approved_digest"], fault_inject=conflict)
    assert provider.read_text() == "Other owner\n"


def test_modified_completed_provider_is_never_replaced_by_old_receipt(destination):
    _, plan, _ = plan_and_restore(destination)
    _, registry, zotero, source_id, package, *_ = destination
    provider = registry.path.parent / "knowledge-providers" / source_id / "knowledge-provider.snapshot.json"
    provider.write_text("Later ownership edit\n")
    with pytest.raises(FieldRegistryError, match="existing provider"):
        restore(registry, zotero, source_id=source_id, package=package, approved_digest=plan["approved_digest"])
    assert provider.read_text() == "Later ownership edit\n"
