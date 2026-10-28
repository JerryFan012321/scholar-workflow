"""Whole registered knowledge units, independent of paper-only projections.

One synthetic Source and a fake Local API item exercise real document registration
and the public exploration CLI. No original bodies are analyzed, rewritten or
opened in native tools. Legacy unqualified state is supplied as an old file, not
created through the managed writer that this change is intended to constrain.
"""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.knowledge.exploration import ExplorationError, ExplorationStore, default_data
from scholar_workflow.knowledge.models import KnowledgeSupportingDocument
from scholar_workflow.workflows.register_document import document_plan, register_document
from tests.contract.test_document_registration import _files, _scope


@pytest.fixture
def document_unit(tmp_path):
    root, registry, local, selected = _scope(tmp_path)
    plan = document_plan(registry, local, **selected)
    registered = register_document(registry, local, approved_digest=plan["approved_digest"], **selected)
    from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
    snapshot = load_knowledge_provider_snapshot(
        registry.path.parent / "knowledge-providers" / selected["source_id"])
    note = root / "resources/synthetic-document/Reading.md"
    note.write_text("# Independent reading context\n\nKeep this original note.\n")
    snapshot.manifest.supporting_documents.append(KnowledgeSupportingDocument(
        document_id="reading:synthetic-document", owner_id=registered["resource_id"],
        kind="reading_note", title="Reading context", vault_path=note.relative_to(root).as_posix()))
    # Fixture setup writes the existing provider authority, not an exploration card.
    target = registry.path.parent / "knowledge-providers" / selected["source_id"] / "knowledge-provider.snapshot.json"
    snapshot.snapshot_revision = ""
    snapshot.catalog.revision = ""
    from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
    target.write_text(json.dumps(KnowledgeProviderSnapshot.model_validate(
        snapshot.model_dump(mode="json")).model_dump(mode="json")))
    return SimpleNamespace(root=root, registry=registry, selected=selected,
                           registered=registered, note=note, provider=target)


@pytest.mark.parametrize("kind", ["webpage", "report", "book", "other"])
@pytest.mark.parametrize("command", ["exploration-init", "exploration-apply"])
@pytest.mark.parametrize("qualified", [False, True])
def test_generic_cli_cannot_create_unregistered_knowledge_cards(tmp_path, kind, command, qualified):
    data = default_data()
    data["works"] = [{"id": "loose", "kind": kind, "title": "Not registered",
                       "attributes": {}, "assets": []}]
    if qualified:
        data["works"][0]["entity_ref"] = {"source_id": "unverified-source", "object_id": "unverified-owner"}
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(data))
    args = ["knowledge", command, "--root", str(tmp_path), "--spec", str(spec)]
    store = ExplorationStore(tmp_path)
    original = None
    if command == "exploration-apply":
        receipt = store.save(default_data())
        original = store.path.read_bytes()
        args += ["--expected-revision", receipt["revision"]]
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 2, result.output
    assert "exploration-import" in result.output
    assert (store.path.read_bytes() if store.path.exists() else None) == original


def test_registered_blog_imports_as_one_complete_webpage_unit(document_unit, tmp_path, monkeypatch):
    unit = document_unit
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(unit.registry.path.parent.parent))
    before = _files(unit.root)
    options = ["knowledge", "exploration-import", "--root", str(unit.root),
               "--source-id", unit.selected["source_id"], "--field-id", unit.selected["field_id"],
               "--environment", "test", "--test-root", str(tmp_path),
               "--state-root", str(unit.registry.path.parent.parent)]
    preview = CliRunner().invoke(main, options)
    assert preview.exit_code == 0, preview.output
    data = json.loads(preview.output)["data"]
    assert len(data["works"]) == 1
    work = data["works"][0]
    assert work["kind"] == "webpage"
    assert work["entity_ref"] == {"source_id": unit.selected["source_id"],
                                  "object_id": unit.registered["resource_id"]}
    assert {row["uri"] for row in work["assets"]} >= {
        "resources/synthetic-document/Source.md", "resources/synthetic-document/Reading.md",
        "https://example.org/research/model"}
    assert _files(unit.root) == before
    applied = CliRunner().invoke(main, [*options, "--apply", "--expected-revision", "absent"])
    assert applied.exit_code == 0, applied.output
    stored = ExplorationStore(unit.root).load()
    assert stored["data"] == data
    repeated = CliRunner().invoke(main, [*options, "--apply", "--expected-revision", stored["revision"]])
    assert repeated.exit_code == 0, repeated.output
    assert ExplorationStore(unit.root).load()["data"] == data
    assert {p: value for p, value in _files(unit.root).items()
            if not p.startswith(".scholar-workflow/exploration")} == before


def test_generic_edit_keeps_registered_nonpaper_identity_and_members(document_unit):
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    unit = document_unit
    service = ExplorationReferenceService(unit.registry.path, resolve_reader=False, enrich_resources=False)
    data = service.reference(unit.root, default_data(), unit.selected["source_id"],
        unit.selected["field_id"], [{"source_id": unit.selected["source_id"],
                                    "object_id": unit.registered["resource_id"]}])
    store = ExplorationStore(unit.root)
    receipt = store.save(data)
    original = store.path.read_bytes()
    for change in ("identity", "member", "kind", "rekey"):
        proposed = deepcopy(receipt["data"])
        work = proposed["works"][0]
        if change == "identity":
            work["entity_ref"]["object_id"] = "document:other"
        elif change == "member":
            work["assets"].pop()
        elif change == "kind":
            work["kind"] = "report"
        else:
            work["id"] += "-moved"
        with pytest.raises(ExplorationError):
            store.save(proposed, expected_revision=receipt["revision"])
        assert store.path.read_bytes() == original
    proposed = deepcopy(receipt["data"])
    proposed["works"][0]["summary"] = "Human positioning remains editable."
    store.save(proposed, expected_revision=receipt["revision"])
    assert store.load()["data"]["works"][0]["summary"] == "Human positioning remains editable."


def test_legacy_unregistered_state_is_readable_but_not_silently_adopted(tmp_path):
    data = default_data()
    data["works"] = [{"id": "old", "kind": "webpage", "title": "Legacy unregistered article",
                       "attributes": {}, "assets": []}]
    store = ExplorationStore(tmp_path)
    store.path.parent.mkdir()
    store.path.write_text(yaml.safe_dump(data))
    original = store.path.read_bytes()
    loaded = store.load()
    result = CliRunner().invoke(main, ["knowledge", "exploration-export", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Legacy unregistered article" in result.output
    assert "未登记" in result.output or "未核实" in result.output
    assert store.path.read_bytes() == original
    proposed = deepcopy(loaded["data"])
    proposed["works"][0]["summary"] = "This must not silently register an old card."
    with pytest.raises(ExplorationError):
        store.save(proposed, expected_revision=loaded["revision"])
    assert store.path.read_bytes() == original


def test_paper_projection_excludes_blog_but_asset_projection_keeps_it(document_unit):
    from scholar_workflow.workflows.field_paper_units import field_asset_units, field_paper_units
    unit = document_unit
    options = {"source_id": unit.selected["source_id"], "field_id": unit.selected["field_id"],
               "resolve_reader": False}
    assert field_paper_units(unit.registry.path, **options)["paper_units"] == []
    whole = field_asset_units(unit.registry.path, **options)["asset_units"]
    assert len(whole) == 1 and whole[0]["resource_kind"] == "blog_post"
    assert {row["object_id"] for row in whole[0]["files"]} == {
        unit.registered["resource_id"], "reading:synthetic-document"}


def test_existing_technical_document_is_a_report_not_a_paper(tmp_path):
    from scholar_workflow.analysis.apply_changes import (
        KnowledgeProviderSnapshot,
        load_knowledge_provider_snapshot,
    )
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    root, registry, _local, selected = _scope(tmp_path)
    provider = registry.path.parent / "knowledge-providers" / selected["source_id"] / "knowledge-provider.snapshot.json"
    payload = load_knowledge_provider_snapshot(provider.parent).model_dump(mode="json")
    path = "resources/technical-document/Document.md"
    (root / path).parent.mkdir(parents=True)
    (root / path).write_text("# Existing technical document\n\nOriginal technical context.\n")
    payload["manifest"]["atomic_resources"].append({
        "resource_id": "technical:synthetic", "kind": "technical_document",
        "title": "Existing technical document", "markdown_path": path})
    payload["catalog"]["resources"].append({
        "resource_id": "technical:synthetic", "kind": "technical_document",
        "title": "Existing technical document"})
    payload["snapshot_revision"] = ""
    payload["catalog"]["revision"] = ""
    provider.write_text(json.dumps(KnowledgeProviderSnapshot.model_validate(payload).model_dump(mode="json")))
    original = _files(root)
    service = ExplorationReferenceService(registry.path, resolve_reader=False, enrich_resources=False)
    result = service.reference(root, default_data(), selected["source_id"],
        selected["field_id"], [{"source_id": selected["source_id"],
                                    "object_id": "technical:synthetic"}])
    assert len(result["works"]) == 1 and result["works"][0]["kind"] == "report"
    assert result["works"][0]["assets"][0]["uri"] == path
    assert _files(root) == original


def test_historical_http_writer_needs_confirmation_for_nonpaper_units(document_unit):
    from scholar_workflow.adapters.knowledge_explorer import ExplorerHTTPServer
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    unit = document_unit
    reference = {"source_id": unit.selected["source_id"], "object_id": unit.registered["resource_id"]}
    service = ExplorationReferenceService(unit.registry.path, resolve_reader=False, enrich_resources=False)
    proposed = service.reference(unit.root, default_data(), unit.selected["source_id"],
                                 unit.selected["field_id"], [reference])
    # Exercise the existing gate without a socket, service, worker or UI.
    server = object.__new__(ExplorerHTTPServer)
    server.store, server.read_only, server.unit_proposals = ExplorationStore(unit.root), False, {}
    with pytest.raises(ExplorationError):
        server.checked_draft(proposed)
    assert server.remember_units(proposed, [reference]) == proposed
    fragment = deepcopy(proposed)
    fragment["works"][0]["assets"].pop()
    with pytest.raises(ExplorationError):
        server.checked_draft(fragment)


def test_missing_member_stays_visible_without_splitting_or_recreating_the_unit(document_unit):
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    unit = document_unit
    unit.note.unlink()  # Remove only an independently prepared synthetic member.
    service = ExplorationReferenceService(unit.registry.path, resolve_reader=False, enrich_resources=False)
    units = service.units(unit.selected["source_id"], unit.selected["field_id"])
    assert len(units["units"]) == 1 and units["units"][0]["diagnostics"]
    data = service.reference(unit.root, default_data(), unit.selected["source_id"],
        unit.selected["field_id"], [{"source_id": unit.selected["source_id"],
                                    "object_id": unit.registered["resource_id"]}])
    assert len(data["works"]) == 1
    assert any(row["uri"].endswith("Reading.md") for row in data["works"][0]["assets"])
    assert not unit.note.exists()


def test_owner_and_catalog_kind_conflict_refuses_reference(tmp_path):
    from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    root, registry, _local, selected = _scope(tmp_path)
    provider = registry.path.parent / "knowledge-providers" / selected["source_id"] / "knowledge-provider.snapshot.json"
    payload = load_knowledge_provider_snapshot(provider.parent).model_dump(mode="json")
    (root / "Document.md").write_text("# Existing document\n")
    payload["manifest"]["atomic_resources"].append({
        "resource_id": "document:conflict", "kind": "blog_post", "title": "Conflicting type",
        "markdown_path": "Document.md"})
    payload["catalog"]["resources"].append({
        "resource_id": "document:conflict", "kind": "paper", "title": "Conflicting type"})
    payload["snapshot_revision"] = ""
    payload["catalog"]["revision"] = ""
    # Supply a deliberately corrupted old declaration, never a fabricated receipt.
    provider.write_text(json.dumps(payload))
    service = ExplorationReferenceService(registry.path, resolve_reader=False, enrich_resources=False)
    with pytest.raises(ExplorationError):
        service.reference(root, default_data(), selected["source_id"],
            selected["field_id"], [{"source_id": selected["source_id"],
                                   "object_id": "document:conflict"}])


def test_legacy_relations_cannot_be_extended_as_if_the_unit_were_registered(tmp_path):
    data = default_data()
    data["works"] = [{"id": "old", "kind": "webpage", "title": "Legacy record",
                       "attributes": {}, "assets": []}]
    store = ExplorationStore(tmp_path)
    store.path.parent.mkdir()
    store.path.write_text(yaml.safe_dump(data))
    current = store.load()
    original = store.path.read_bytes()
    proposed = deepcopy(current["data"])
    proposed["records"].append({"id": "new", "work_id": "old", "dimensions": {},
        "conditions": {}, "result": "Unverified new assertion", "assessment": "Not adopted",
        "origin": "analysis", "evidence": []})
    with pytest.raises(ExplorationError):
        store.save(proposed, expected_revision=current["revision"])
    assert store.path.read_bytes() == original


def test_existing_qualified_card_cannot_smuggle_unregistered_members_into_an_import(document_unit):
    from scholar_workflow.workflows.exploration_references import ExplorationReferenceService
    unit = document_unit
    identity = {"source_id": unit.selected["source_id"], "object_id": unit.registered["resource_id"]}
    data = default_data()
    data["works"] = [{"id": "old-qualified-card", "title": "Old reference", "kind": "webpage",
                       "entity_ref": identity, "attributes": {}, "assets": [
                           {"id": "unregistered-member", "label": "Not declared by the owner",
                            "kind": "markdown", "uri": "unrelated.md"}]}]
    before = deepcopy(data)
    original = _files(unit.root)
    service = ExplorationReferenceService(unit.registry.path, resolve_reader=False, enrich_resources=False)
    with pytest.raises(ExplorationError):
        service.reference(unit.root, data, unit.selected["source_id"], unit.selected["field_id"], [identity])
    assert data == before and _files(unit.root) == original


@pytest.mark.parametrize("fmt", ["md", "json"])
def test_public_asset_list_reads_whole_units_without_writes_or_native_probes(document_unit, monkeypatch, fmt):
    from scholar_workflow.workflows import field_paper_units as module
    unit = document_unit
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(unit.registry.path.parent.parent))
    original_query = module.field_asset_units
    monkeypatch.setattr(module, "field_asset_units", lambda *a, **kw:
                        original_query(*a, **kw, resolve_reader=False))
    original = _files(unit.root)
    result = CliRunner().invoke(main, ["knowledge", "list", "--asset-units",
        "--source-id", unit.selected["source_id"], "--field-id", unit.selected["field_id"],
        "--format", fmt, "--language", "zh"])
    assert result.exit_code == 0, result.output
    if fmt == "json":
        units = json.loads(result.output)["asset_units"]
        assert len(units) == 1 and units[0]["resource_id"] == unit.registered["resource_id"]
        assert len(units[0]["files"]) == 2
        assert "https://example.org/research/model" in {row["uri"] for row in units[0]["resource_links"]}
    else:
        assert "知识资料" in result.output and "Blog" in result.output
        assert "Reading context" in result.output and "Synthetic official Webpage" in result.output
        assert "https://example.org/research/model" in result.output
    assert _files(unit.root) == original


@pytest.mark.parametrize("options", [[], ["--paper-units"], ["--resolve-references"]])
def test_asset_list_rejects_ambiguous_or_incomplete_selection_before_reading_config(monkeypatch, options):
    from scholar_workflow import cli
    def forbidden():
        pytest.fail("Invalid selectors must refuse before host configuration")
    monkeypatch.setattr(cli, "_local_field_service", forbidden)
    result = CliRunner().invoke(main, ["knowledge", "list", "--asset-units", *options])
    assert result.exit_code == 2
