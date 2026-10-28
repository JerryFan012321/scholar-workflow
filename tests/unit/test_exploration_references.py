"""Whole-unit selection over synthetic registered sources, with no live services."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scholar_workflow.knowledge.exploration import ExplorationError, default_data
from scholar_workflow.workflows import exploration_references as module


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    root = tmp_path / "explorer"
    root.mkdir()
    source_root = root / "source"
    source_root.mkdir()
    (source_root / "paper.md").write_text("# Existing paper\n", encoding="utf-8")
    (source_root / "analysis.md").write_text("# Existing analysis\n", encoding="utf-8")
    (source_root / "tree.canvas").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    files = [{"object_id": name, "kind": kind, "title": title, "relative_path": path,
              "file_state": "available", "open_state": "ready", "uri": None}
             for name, kind, title, path in (
                 ("paper-a", "paper", "Paper A", "paper.md"),
                 ("analysis-a", "analysis", "Analysis A", "analysis.md"),
                 ("canvas-a", "canvas", "Tree A", "tree.canvas"))]
    unit = {"source_id": "source-a", "resource_id": "paper-a", "title": "Paper A",
            "resource_kind": "paper",
            "ownership": {"status": "resolved"}, "files": files,
            "catalog_resource": {"resource_id": "paper-a",
                                 "identifiers": {"url": "https://research.example/a"},
                                 "zotero": {"item_key": "ABCD2345"}}}
    second = deepcopy(unit)
    second.update(resource_id="paper-b", title="Paper B")
    second["files"] = [{**files[0], "object_id": "paper-b", "title": "Paper B"}]
    second["catalog_resource"]["resource_id"] = "paper-b"
    state = SimpleNamespace(
        root=root, source_root=source_root, calls=[], revision="sha256:original", change=False,
        fields=[{"source_id": "source-a", "field_id": "field-a", "title": "Research",
                 "relative_root": ".", "available": True}],
        document=SimpleNamespace(
            folders=[SimpleNamespace(folder_id="folder-a", root=str(source_root), enabled=True,
                                     capabilities=["read"])],
            sources=[SimpleNamespace(source_id="source-a", folder_id="folder-a", enabled=True,
                                     capabilities=["read"])],
        ),
        payload={"schema_version": 1, "source_id": "source-a", "field_id": "field-a",
                 "asset_units": [unit, second], "unresolved_references": [], "issues": [],
                 "status": "complete"},
    )

    class Registry:
        def __init__(self, path):
            self.path = Path(path)

        def revision(self):
            return state.revision

        def load_document(self):
            return deepcopy(state.document)

    class Fields:
        def __init__(self, registry):
            self.registry = registry

        def list_fields(self):
            state.calls.append("fields")
            if state.change:
                state.revision = "sha256:changed"
            return deepcopy(state.fields)

    def paper_units(path, *, source_id, field_id, include_resource_links):
        assert include_resource_links is True
        state.calls.append((str(path), source_id, field_id))
        if state.change:
            state.revision = "sha256:changed"
        return deepcopy(state.payload)

    monkeypatch.setattr(module, "KnowledgeSourceRegistry", Registry)
    monkeypatch.setattr(module, "FieldService", Fields)
    monkeypatch.setattr(module, "field_asset_units", paper_units)
    state.enriched = []

    def enrich_selected(payload):
        state.enriched.append([row["resource_id"] for row in payload["asset_units"]])
        return deepcopy(payload)

    monkeypatch.setattr(module, "include_resource_links", enrich_selected)
    state.service = module.ExplorationReferenceService(tmp_path / "registry.json")
    return state


def refs(*pairs):
    return [{"source_id": source, "object_id": owner} for source, owner in pairs]


def test_fields_only_return_public_registered_selectors(inventory):
    inventory.fields.append({"source_id": "source-b", "available": False,
                             "detail": "Unavailable fixture"})
    result = inventory.service.fields()
    assert result["fields"] == [{"source_id": "source-a", "field_id": "field-a", "title": "Research"}]
    assert result["diagnostics"] and inventory.calls == ["fields"]
    assert str(inventory.source_root) not in str(result)


def test_units_list_whole_packages_with_all_known_assets_and_offline_diagnostics(inventory):
    before = deepcopy(inventory.payload)
    result = inventory.service.units("source-a", "field-a")
    first = result["units"][0]
    assert first["entity_ref"] == {"source_id": "source-a", "object_id": "paper-a"}
    assert first["title"] == "Paper A" and first["asset_count"] == 4
    assert any("Zotero" in note for note in first["diagnostics"])
    assert inventory.payload == before


def test_reference_selects_one_whole_unit_and_preserves_files_and_other_data(inventory):
    before = {path: path.read_bytes() for path in inventory.root.rglob("*") if path.is_file()}
    data = default_data()
    original = deepcopy(data)
    result = inventory.service.reference(inventory.root, data, "source-a", "field-a",
                                         refs(("source-a", "paper-a")))
    assert inventory.enriched == [["paper-a"]]
    assert data == original
    assert len(result["works"]) == 1
    work = result["works"][0]
    assert work["entity_ref"] == {"source_id": "source-a", "object_id": "paper-a"}
    assert {asset["label"] for asset in work["assets"]} == {
        "Paper A", "Analysis A", "Tree A", "原文网页"}
    assert before == {path: path.read_bytes() for path in inventory.root.rglob("*") if path.is_file()}
    assert not (inventory.root / ".scholar-workflow").exists()


def test_repeated_reference_reuses_one_work_and_retains_outer_research_records(inventory):
    selected = refs(("source-a", "paper-a"))
    data = inventory.service.reference(inventory.root, default_data(), "source-a", "field-a", selected)
    work = data["works"][0]
    work.update(title="Human title", summary="Human interpretation")
    data["records"] = [{"id": "run-a", "work_id": work["id"], "dimensions": {},
                         "conditions": {"Budget": "One GPU"}, "result": "Observed result",
                         "assessment": "Limited scope", "origin": "local", "evidence": []},
                        {"id": "run-b", "work_id": work["id"], "dimensions": {},
                         "conditions": {"Budget": "Two GPUs"}, "result": "Different result",
                         "assessment": "Different setup", "origin": "local", "evidence": []}]
    repeated = inventory.service.reference(inventory.root, data, "source-a", "field-a", selected)
    assert repeated == data and len(repeated["works"]) == 1 and len(repeated["records"]) == 2


@pytest.mark.parametrize("selected", [
    [], refs(("source-a", "unknown")), refs(("source-b", "paper-a")),
    refs(("source-a", "paper-a"), ("source-a", "paper-a")),
    [{"source_id": "source-a", "object_id": "paper-a", "files": ["paper-a"]}],
    [{"source_id": "source-a"}], "paper-a", [None],
])
def test_unknown_duplicate_or_file_subset_selection_is_rejected(inventory, selected):
    with pytest.raises(ExplorationError) as error:
        inventory.service.reference(inventory.root, default_data(), "source-a", "field-a", selected)
    assert error.value.code in {2, 5}


def test_unresolved_owner_is_visible_in_selection_and_refused_on_reference(inventory):
    inventory.payload["asset_units"][0]["ownership"] = {"status": "conflict"}
    listed = inventory.service.units("source-a", "field-a")
    assert listed["units"][0]["diagnostics"]
    with pytest.raises(ExplorationError) as error:
        inventory.service.reference(inventory.root, default_data(), "source-a", "field-a",
                                    refs(("source-a", "paper-a")))
    assert error.value.code == 5


@pytest.mark.parametrize("method", ["fields", "units", "reference"])
def test_registry_revision_change_refuses_observation(inventory, method):
    inventory.change = True
    with pytest.raises(ExplorationError) as error:
        if method == "fields":
            inventory.service.fields()
        elif method == "units":
            inventory.service.units("source-a", "field-a")
        else:
            inventory.service.reference(inventory.root, default_data(), "source-a", "field-a",
                                        refs(("source-a", "paper-a")))
    assert error.value.code == 5


def test_disabled_or_unreadable_source_is_not_used(inventory):
    inventory.document.sources[0].enabled = False
    with pytest.raises(ExplorationError):
        inventory.service.units("source-a", "field-a")
    assert inventory.calls == []


def test_other_source_with_same_owner_id_remains_a_distinct_whole_unit(inventory):
    inventory.document.sources.append(SimpleNamespace(
        source_id="source-b", folder_id="folder-a", enabled=True, capabilities=["read"]))
    second = deepcopy(inventory.payload["asset_units"][0])
    second["source_id"] = "source-b"
    inventory.payload["asset_units"].append(second)
    result = inventory.service.reference(inventory.root, default_data(), "source-a", "field-a",
                                         refs(("source-a", "paper-a"), ("source-b", "paper-a")))
    assert len(result["works"]) == 2
    assert {work["entity_ref"]["source_id"] for work in result["works"]} == {"source-a", "source-b"}


def test_malformed_or_duplicate_provider_units_are_not_silently_dropped(inventory):
    inventory.payload["asset_units"].append(deepcopy(inventory.payload["asset_units"][0]))
    with pytest.raises(ExplorationError) as error:
        inventory.service.units("source-a", "field-a")
    assert error.value.code == 5


def test_provider_selection_mismatch_is_rejected(inventory):
    inventory.payload["field_id"] = "field-b"
    with pytest.raises(ExplorationError) as error:
        inventory.service.units("source-a", "field-a")
    assert error.value.code == 5


def test_default_registry_path_uses_the_existing_workflow_home(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path))
    service = module.ExplorationReferenceService()
    assert service.registry_path == tmp_path / "hub" / "sources.json"


def test_current_unit_reloads_registered_owner_without_body_reads_or_saving(inventory):
    result = inventory.service.current_unit({"source_id": "source-a", "object_id": "paper-a"})
    assert result["resource_id"] == "paper-a"
    assert result["catalog_resource"] == inventory.payload["asset_units"][0]["catalog_resource"]
    assert len(result["files"]) == 3
    assert not (inventory.root / ".scholar-workflow").exists()


@pytest.mark.parametrize("ref", [
    {"source_id": "source-a", "object_id": "unknown"},
    {"source_id": "source-b", "object_id": "paper-a"},
    {"source_id": "source-a", "object_id": "paper-a", "path": "paper.md"},
])
def test_current_unit_rejects_unknown_or_unqualified_reference(inventory, ref):
    with pytest.raises(ExplorationError):
        inventory.service.current_unit(ref)


def test_current_unit_refuses_conflicting_ownership(inventory):
    inventory.payload["asset_units"][0]["ownership"] = {"status": "conflict"}
    with pytest.raises(ExplorationError) as error:
        inventory.service.current_unit({"source_id": "source-a", "object_id": "paper-a"})
    assert error.value.code == 5
