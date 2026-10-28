"""Declared synthetic paper-unit references only; no Vault scan or source rewrite."""

from copy import deepcopy

import pytest

from scholar_workflow.knowledge.exploration import ExplorationError, assets, default_data, validate
from scholar_workflow.knowledge.exploration_import import import_paper_units


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "explorer"
    root.mkdir()
    source = root / "research"
    source.mkdir()
    (source / "resources").mkdir()
    files = []
    for object_id, name, kind, content in (
        ("paper:1", "paper.md", "paper", b"# Original material\n"),
        ("analysis:1", "analysis.md", "analysis", b"# Human analysis\n"),
        ("canvas:1", "tree.canvas", "canvas", b'{"nodes": []}'),
        ("image:1", "a b.png", "asset", b"image placeholder"),
        ("metadata:1", "metadata.json", "sidecar", b'{"unchanged": true}'),
    ):
        path = source / "resources" / name
        path.write_bytes(content)
        files.append({"object_id": object_id, "kind": kind, "title": name,
                      "relative_path": "resources/" + name, "file_state": "available",
                      "uri": "obsidian://open?vault=known&file=resources%2F" + name,
                      "open_state": "ready"})
    files.append({"object_id": "missing:1", "kind": "canvas", "title": "Missing tree",
                  "relative_path": "resources/missing.canvas", "file_state": "missing",
                  "uri": None, "open_state": "file_unavailable"})
    payload = {"schema_version": 1, "source_id": "source-A", "field_id": "field-A",
               "field_title": "Selected field", "status": "partial",
               "unresolved_references": [], "issues": [], "paper_units": [
                   {"source_id": "source-A", "resource_id": "paper:1", "title": "A paper",
                    "field_title": "Selected field", "selected_by": ["owned"], "purposes": [],
                    "ownership": {"status": "resolved", "object_id": "paper:1"}, "files": files}]}
    return root, source, payload


def test_import_retains_complete_assets_and_never_writes(corpus):
    root, source, payload = corpus
    before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    original = deepcopy(payload)
    data = default_data()
    imported = import_paper_units(root, data, payload, source_roots={"source-A": source})
    work = imported["works"][0]
    assert work["entity_ref"] == {"source_id": "source-A", "object_id": "paper:1"}
    assert len(work["assets"]) == len(payload["paper_units"][0]["files"]) == 6
    assert work["assets"][3]["uri"] == "research/resources/a%20b.png"
    assert [a["available"] for a in assets(root, imported, work["id"])] == [True] * 5 + [False]
    assert data == default_data() and payload == original
    assert not (root / ".scholar-workflow").exists()
    assert before == {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    assert imported == import_paper_units(root, imported, payload, source_roots={"source-A": source})


def test_import_reuses_identity_and_preserves_human_changes(corpus):
    root, source, payload = corpus
    data = import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
    data["works"][0].update(id="human-work-id", title="Human title", summary="Human judgment")
    data["dimensions"].append({"id": "human", "label": "Human attribute", "kind": "text",
                               "multiple": False, "scope": "work", "sortable": True, "values": []})
    data["works"][0]["attributes"]["human"] = "Preserve this"
    data["records"].append({"id": "human-record", "work_id": "human-work-id", "dimensions": {},
                             "conditions": {"Budget": "Original condition"}, "result": "Result",
                             "evidence": [data["works"][0]["assets"][0]["id"]],
                             "assessment": "Original assessment", "origin": "local"})
    payload["paper_units"][0]["files"].append({"object_id": "new:asset", "title": "Discussion",
        "kind": "webpage", "relative_path": "resources/discussion.md", "file_state": "available",
        "uri": "https://example.test/discussion", "open_state": "ready"})
    changed = import_paper_units(root, data, payload, source_roots={"source-A": source})
    assert len(changed["works"]) == 1 and len(changed["works"][0]["assets"]) == 7
    assert changed["works"][0]["title"] == "Human title"
    assert changed["works"][0]["summary"] == "Human judgment"
    assert changed["works"][0]["attributes"] == {"human": "Preserve this"}
    assert changed["records"] == data["records"]
    assert changed["edges"] == data["edges"]
    assert changed["works"][0]["assets"][-1]["uri"] == "https://example.test/discussion"


@pytest.mark.parametrize("kind", ["webpage", "other"])
def test_import_refuses_existing_nonpaper_with_same_qualified_identity(corpus, kind):
    root, source, payload = corpus
    data = default_data()
    data["works"] = [{"id": "nonpaper", "title": "Human resource", "kind": kind,
                       "entity_ref": {"source_id": "source-A", "object_id": "paper:1"},
                       "attributes": {}, "assets": []}]
    before = deepcopy(data)
    original_payload = deepcopy(payload)
    with pytest.raises(ExplorationError) as conflict:
        import_paper_units(root, data, payload, source_roots={"source-A": source})
    assert conflict.value.code == 5
    assert "non-paper" in str(conflict.value)
    assert data == before and payload == original_payload


def test_external_source_uses_only_explicit_native_links(corpus, tmp_path):
    root, source, payload = corpus
    external = tmp_path / "external"
    external.mkdir()
    unit = deepcopy(payload["paper_units"][0])
    unit["source_id"] = "source-B"
    unit["files"] = unit["files"][:-1]
    payload["paper_units"].append(unit)
    result = import_paper_units(root, default_data(), payload,
                                source_roots={"source-A": source, "source-B": external})
    first, second = result["works"]
    assert first["id"] != second["id"] and first["title"] == second["title"]
    assert all(a["uri"].startswith("obsidian://") for a in second["assets"])
    assert {a["id"] for a in first["assets"]}.isdisjoint(a["id"] for a in second["assets"])
    assert second["entity_ref"]["source_id"] == "source-B"


def test_field_explorer_inside_source_retains_local_notes_canvas_and_images(corpus):
    source_root, field_root, payload = corpus
    before = {path: path.read_bytes() for path in source_root.rglob("*") if path.is_file()}
    unit = payload["paper_units"][0]
    for row in unit["files"]:
        row["relative_path"] = "research/" + row["relative_path"]
        if row["kind"] in {"asset", "sidecar"}:
            row["uri"] = None
    result = import_paper_units(field_root, default_data(), payload,
                                source_roots={"source-A": source_root})
    work = result["works"][0]
    assert [asset["uri"] for asset in work["assets"]] == [
        "resources/paper.md", "resources/analysis.md", "resources/tree.canvas",
        "resources/a%20b.png", "resources/metadata.json", "resources/missing.canvas"]
    assert [row["available"] for row in assets(field_root, result, work["id"])] == [True] * 5 + [False]
    assert before == {path: path.read_bytes() for path in source_root.rglob("*") if path.is_file()}


def test_cross_root_without_native_uri_refuses_same_named_local_file(corpus, tmp_path):
    _, local_root, payload = corpus
    unrelated_source = tmp_path / "unrelated-source"
    unrelated_source.mkdir()
    payload["paper_units"][0]["files"][0]["uri"] = None
    assert (local_root / "resources/paper.md").is_file()
    with pytest.raises(ExplorationError, match="no root-relative location"):
        import_paper_units(local_root, default_data(), payload,
                           source_roots={"source-A": unrelated_source})


def test_field_mapping_does_not_resolve_an_asset_symlink(corpus, tmp_path):
    source_root, field_root, payload = corpus
    outside = tmp_path / "outside.md"
    outside.write_text("Outside the registered root", encoding="utf-8")
    (field_root / "resources/link.md").symlink_to(outside)
    payload["paper_units"][0]["files"] = [{
        "object_id": "link", "kind": "paper", "title": "Unverified link",
        "relative_path": "research/resources/link.md", "uri": None,
        "file_state": "missing", "open_state": "file_unavailable"}]
    result = import_paper_units(field_root, default_data(), payload,
                                source_roots={"source-A": source_root})
    work = result["works"][0]
    assert work["assets"][0]["uri"] == "resources/link.md"
    row = assets(field_root, result, work["id"])[0]
    assert row["available"] is False and str(outside) not in row["uri"]


def test_same_source_shared_asset_has_distinct_reference_id(corpus):
    root, source, payload = corpus
    second = deepcopy(payload["paper_units"][0])
    second["resource_id"] = "paper:2"
    second["title"] = "Another explicit owner"
    second["files"] = [second["files"][3]]
    payload["paper_units"].append(second)
    result = import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
    first_ref = result["works"][0]["assets"][3]
    second_ref = result["works"][1]["assets"][0]
    assert first_ref["id"] != second_ref["id"] and first_ref["uri"] == second_ref["uri"]


def test_no_source_binding_does_not_guess_same_named_local_files(corpus):
    root, _, payload = corpus
    with pytest.raises(ExplorationError, match="no root-relative location"):
        import_paper_units(root, default_data(), payload)
    payload["paper_units"][0]["files"] = payload["paper_units"][0]["files"][:-1]
    result = import_paper_units(root, default_data(), payload)
    assert all(a["uri"].startswith("obsidian://") for a in result["works"][0]["assets"])


def test_existing_asset_uri_conflict_does_not_mutate_inputs(corpus):
    root, source, payload = corpus
    data = import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
    data["works"][0]["assets"][0]["uri"] = "https://example.test/human-replacement"
    before = deepcopy(data)
    with pytest.raises(ExplorationError) as conflict:
        import_paper_units(root, data, payload, source_roots={"source-A": source})
    assert conflict.value.code == 5 and data == before


@pytest.mark.parametrize("change", [
    lambda p: p.update(unresolved_references=[{"object_id": "unresolved"}]),
    lambda p: p.update(schema_version=True),
    lambda p: p["paper_units"][0]["ownership"].update(status="conflict"),
    lambda p: p["paper_units"][0]["files"][0].update(relative_path="../outside.md"),
    lambda p: p["paper_units"][0]["files"][0].update(uri="javascript:alert(1)"),
    lambda p: p["paper_units"][0]["files"][0].update(file_state="unsafe"),
    lambda p: p["paper_units"][0]["files"][0].update(open_state="ownership_unresolved"),
    lambda p: p["paper_units"].append(deepcopy(p["paper_units"][0])),
])
def test_import_rejects_invalid_or_ambiguous_declarations(corpus, change):
    root, source, payload = corpus
    change(payload)
    with pytest.raises(ExplorationError):
        import_paper_units(root, default_data(), payload, source_roots={"source-A": source})


def test_entity_reference_schema_is_strict(corpus):
    root, source, payload = corpus
    data = import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
    for entity_ref in ({"source_id": "source-A", "object_id": ""},
                       {"source_id": "source-A", "object_id": "x", "extra": "x"}):
        changed = deepcopy(data)
        changed["works"][0]["entity_ref"] = entity_ref
        with pytest.raises(ExplorationError):
            validate(changed)
    clone = deepcopy(data["works"][0])
    clone.update(id="duplicate-qualified-work", assets=[])
    data["works"].append(clone)
    with pytest.raises(ExplorationError, match="qualified work identities"):
        validate(data)


def test_uri_only_resource_links_and_diagnostics_survive_export(corpus):
    from scholar_workflow.knowledge.exploration import render_markdown

    root, source, payload = corpus
    unit = payload["paper_units"][0]
    unit["resource_links"] = [
        {"object_id": "original-web", "title": "原文网页", "kind": "original-page",
         "uri": "https://example.test/original"},
        {"object_id": "original-pdf", "title": "原 PDF", "kind": "zotero-pdf",
         "uri": "zotero://open-pdf/library/items/ABCD2345"},
    ]
    unit["resource_notes"] = ["Zotero 子条目未读取，附件清单尚未核实。"]
    result = import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
    work = result["works"][0]
    assert len(work["assets"]) == len(unit["files"]) + 2
    assert work["assets"][-1]["uri"] == unit["resource_links"][-1]["uri"]
    assert work["asset_diagnostics"] == unit["resource_notes"]
    report = render_markdown(root, result)
    assert "https://example.test/original" in report
    assert unit["resource_notes"][0] in report
    unit["resource_notes"] = []
    refreshed = import_paper_units(root, result, payload, source_roots={"source-A": source})
    assert refreshed["works"][0]["asset_diagnostics"] == []


@pytest.mark.parametrize("uri", ["../escape.md", "file:///tmp/other", "javascript:alert(1)"])
def test_resource_link_cannot_invent_a_local_file(corpus, uri):
    root, source, payload = corpus
    payload["paper_units"][0]["resource_links"] = [
        {"object_id": "web", "title": "网页", "kind": "original-page", "uri": uri}]
    with pytest.raises(ExplorationError):
        import_paper_units(root, default_data(), payload, source_roots={"source-A": source})
