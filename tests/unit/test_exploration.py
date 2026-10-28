"""Synthetic knowledge roots only; paper units are read but never changed."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
import yaml

from scholar_workflow.knowledge import exploration as module
from scholar_workflow.knowledge.exploration import (
    ExplorationError,
    ExplorationStore,
    assets,
    default_data,
    query,
    render_markdown,
    validate,
)


@pytest.fixture
def document():
    data = default_data()
    for dim, ids in zip(data["dimensions"], (("b1", "b2"), ("p1", "p2"),
                                          ("q1", "q2"), ("t1", "t2"))):
        dim["values"] = [{"id": value, "label": value.upper()} for value in ids]
    data["dimensions"].append({"id": "modality", "label": "Input modality", "kind": "enum",
                               "scope": "work", "multiple": True, "sortable": False,
                               "values": [{"id": "image", "label": "Image"},
                                          {"id": "action", "label": "Action"}]})
    data["works"] = [
        {"id": "w1", "title": "Alpha", "kind": "paper", "year": 2020,
         "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper-alpha"},
         "attributes": {"modality": ["image", "action"]}, "assets": [
             {"id": "a1", "label": "Analysis", "kind": "markdown", "uri": "paper/body.md#claim"},
             {"id": "canvas", "label": "Canvas", "kind": "canvas", "uri": "paper/tree.canvas"},
             {"id": "missing", "label": "Missing", "kind": "file", "uri": "paper/missing.pdf"},
             {"id": "source", "label": "Source", "kind": "web", "uri": "https://example.test/w1"},
             {"id": "native", "label": "Reader", "kind": "pdf", "uri": "zotero://open-pdf/library/items/ABC"},
         ]},
        {"id": "w2", "title": "Beta", "kind": "paper", "year": 2021,
         "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper-beta"},
         "attributes": {"modality": ["image"]}, "assets": [
             {"id": "a2", "label": "Original", "kind": "file", "uri": "paper/figure.png"}]},
        {"id": "w3", "title": "Gamma update", "kind": "webpage",
         "attributes": {}, "assets": []},
    ]
    data["records"] = [
        {"id": "r1", "work_id": "w1", "dimensions": {"foundation": ["b1"], "task": ["t1"]},
         "conditions": {"Data": "D1", "Budget": "One hour"}, "result": "Result one",
         "evidence": ["a1"], "assessment": "Specific conditions only", "origin": "author"},
        {"id": "r2", "work_id": "w1", "dimensions": {"foundation": ["b2"], "task": ["t2"]},
         "conditions": {"Data": "D2"}, "result": "Result two", "evidence": ["a1"],
         "assessment": "Not comparable with D1", "origin": "local"},
    ]
    data["edges"] = [
        {"id": "e1", "from_id": "w1", "to_id": "w2", "kind": "extends", "label": "Extension",
         "evidence": ["source"], "explanation": "An explicitly supported extension"},
        {"id": "e2", "from_id": "w1", "to_id": "w3", "kind": "context", "label": "Discussion",
         "evidence": ["a1"], "explanation": "Additional context"},
    ]
    return data


def selection(**entries):
    return {"filters": {key: {"mode": "all", "values": values} for key, values in entries.items()}}


def test_reading_missing_store_has_no_side_effects_and_cas(tmp_path, document):
    store = ExplorationStore(tmp_path)
    empty = store.load()
    assert empty["revision"] is None and len(empty["data"]["dimensions"]) == 4
    assert list(tmp_path.iterdir()) == []
    saved = store.save(document, expected_revision=None)
    assert saved == store.load()
    assert saved["revision"].startswith("sha256:")
    assert list((tmp_path / ".scholar-workflow").iterdir()) == [store.path]
    with pytest.raises(ExplorationError) as conflict:
        store.save(document, expected_revision=None)
    assert conflict.value.code == 5
    revised = deepcopy(document)
    revised["works"][0]["summary"] = "Changed with explicit revision"
    store.save(revised, expected_revision=saved["revision"])
    assert store.load()["data"]["works"][0]["summary"] == revised["works"][0]["summary"]


@pytest.mark.parametrize("change", ["remove-asset", "replace-uri", "change-kind", "retarget", "rekey"])
def test_save_cannot_split_or_retarget_an_existing_paper_unit(tmp_path, document, change):
    store = ExplorationStore(tmp_path)
    saved = store.save(document, expected_revision=None)
    before = store.path.read_bytes()
    proposed = deepcopy(saved["data"])
    paper = proposed["works"][0]
    if change == "remove-asset":
        paper["assets"] = [row for row in paper["assets"] if row["id"] != "canvas"]
    elif change == "replace-uri":
        paper["assets"][1]["uri"] = "paper/unrelated.canvas"
    elif change == "change-kind":
        paper["kind"] = "webpage"
    elif change == "retarget":
        paper["entity_ref"]["object_id"] = "different-paper"
    else:
        paper["id"] = "new-local-id"
        for record in proposed["records"]:
            record["work_id"] = "new-local-id"
        for edge in proposed["edges"]:
            edge["from_id"] = "new-local-id"
    with pytest.raises(ExplorationError, match="paper unit"):
        store.save(proposed, expected_revision=saved["revision"])
    assert store.path.read_bytes() == before


def test_removing_a_whole_unit_reference_does_not_delete_its_files(tmp_path, document):
    original = tmp_path / "paper" / "figure.png"
    original.parent.mkdir()
    original.write_bytes(b"synthetic original figure")
    store = ExplorationStore(tmp_path)
    saved = store.save(document, expected_revision=None)
    proposed = deepcopy(saved["data"])
    proposed["works"] = [row for row in proposed["works"] if row["id"] != "w2"]
    proposed["edges"] = [row for row in proposed["edges"] if row["to_id"] != "w2"]
    receipt = store.save(proposed, expected_revision=saved["revision"])
    assert [row["id"] for row in receipt["data"]["works"]] == ["w1", "w3"]
    assert original.read_bytes() == b"synthetic original figure"


def test_external_edit_is_read_and_not_overwritten(tmp_path, document):
    store = ExplorationStore(tmp_path)
    initial = store.save(document)
    document["works"][0]["title"] = "Human edit"
    store.path.write_text(yaml.safe_dump(document), encoding="utf-8")
    before = store.path.read_bytes()
    assert store.load()["data"]["works"][0]["title"] == "Human edit"
    with pytest.raises(ExplorationError) as conflict:
        store.save(document, expected_revision=initial["revision"])
    assert conflict.value.code == 5 and store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["mixed-revision", "short-read"])
def test_loading_rejects_changed_fd_or_incomplete_snapshot(tmp_path, document, monkeypatch, change):
    document["records"][0].update(conditions={"Data": "old-data"}, result="old-result")
    store = ExplorationStore(tmp_path)
    store.save(document)
    before = store.path.read_bytes()
    replacement = before.replace(b"Data: old-data", b"Data: new-data").replace(
        b"result: old-result", b"result: new-result")
    assert len(before) == len(replacement)
    split = before.index(b"result: old-result")
    mixed = before[:split] + replacement[split:]
    mixed_data = yaml.safe_load(mixed)
    assert mixed_data["records"][0]["conditions"] == {"Data": "old-data"}
    assert mixed_data["records"][0]["result"] == "new-result"
    original_fdopen = module.os.fdopen

    class InterruptedRead:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size):
            raw = self.stream.read(size)
            if change == "short-read":
                return raw[:-1]  # Missing final LF remains valid YAML, but not a full snapshot.
            info = store.path.stat()
            store.path.write_bytes(replacement)
            os.utime(store.path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
            return mixed

    monkeypatch.setattr(module.os, "fdopen", lambda *args, **kwargs:
                        InterruptedRead(original_fdopen(*args, **kwargs)))
    with pytest.raises(ExplorationError, match="changed while reading"):
        store.load()
    assert store.path.read_bytes() == (replacement if change == "mixed-revision" else before)


def test_oversized_state_is_rejected_without_changing_files(tmp_path, document):
    store = ExplorationStore(tmp_path)
    revision = store.save(document)["revision"]
    before = store.path.read_bytes()
    document["works"][0]["summary"] = "x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(ExplorationError, match="2 MiB limit"):
        store.save(document, expected_revision=revision)
    assert store.path.read_bytes() == before
    external = b"# external editor content\n" + b"x" * (2 * 1024 * 1024 + 1)
    store.path.write_bytes(external)
    with pytest.raises(ExplorationError, match="2 MiB limit"):
        store.load()
    assert store.path.read_bytes() == external


def test_concurrent_saves_do_not_overwrite_each_other(tmp_path, document):
    store = ExplorationStore(tmp_path)
    revision = store.save(document)["revision"]

    def write(title):
        changed = deepcopy(document)
        changed["works"][0]["title"] = title
        try:
            store.save(changed, expected_revision=revision)
            return "saved"
        except ExplorationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ("First", "Second")), key=str) == [5, "saved"]


def test_joint_query_does_not_combine_unrelated_records(document):
    assert query(document, selection(foundation=["b1"], task=["t2"]))["works"] == []
    found = query(document, selection(foundation=["b1"], task=["t1"]))
    assert [w["id"] for w in found["works"]] == ["w1"]
    assert [r["id"] for r in found["records"]] == ["r1"]
    assert found["context_work_ids"] == ["w2", "w3"]
    assert [e["id"] for e in found["edges"]] == ["e1", "e2"]
    found = query(document, {**selection(foundation=["b1"]), "include_context": False})
    assert found["context_work_ids"] == [] and found["edges"] == []


@pytest.mark.parametrize("identity", [None, {}])
def test_paper_requires_qualified_unit_identity(document, identity):
    if identity is None:
        document["works"][0].pop("entity_ref")
    else:
        document["works"][0]["entity_ref"] = identity
    with pytest.raises(ExplorationError):
        validate(document)


def test_one_paper_cannot_be_split_into_duplicate_qualified_works(document):
    duplicate = deepcopy(document["works"][0])
    duplicate.update(id="paper-fragment", title="Convenient fragment", assets=[])
    document["works"].append(duplicate)
    with pytest.raises(ExplorationError, match="qualified work identities"):
        validate(document)


def test_multiple_conditional_records_keep_one_paper_result(document):
    selected = {"filters": {"foundation": {"mode": "any", "values": ["b1", "b2"]}}}
    actual = query(document, selected)
    assert [work["id"] for work in actual["works"]] == ["w1"]
    assert [record["id"] for record in actual["records"]] == ["r1", "r2"]
    assert actual["works"][0]["entity_ref"] == document["works"][0]["entity_ref"]


def test_missing_or_undeclared_assets_do_not_discard_paper_unit(tmp_path, document):
    paper = document["works"][0]
    paper["assets"] = [{"id": "missing-pdf", "label": "Original PDF", "kind": "pdf",
                         "uri": "missing.pdf"}]
    paper["asset_diagnostics"] = ["Synthetic Canvas not declared in this inventory"]
    document["records"] = []
    document["edges"] = []
    selected = query(document, {"text": "Alpha"})
    assert [work["id"] for work in selected["works"]] == ["w1"]
    assert selected["works"][0]["asset_diagnostics"] == paper["asset_diagnostics"]
    assert assets(tmp_path, document, "w1")[0]["available"] is False
    paper["assets"] = []
    assert query(document, {"text": "Alpha"})["works"][0]["id"] == "w1"


def test_complete_nonpaper_resources_keep_their_real_kind():
    data = default_data()
    data["works"] = [{"id": kind, "title": kind, "kind": kind, "attributes": {}, "assets": []}
                     for kind in ("webpage", "report", "book", "other")]
    assert {work["kind"] for work in validate(data)["works"]} == {"webpage", "report", "book", "other"}


def test_fifth_dimension_any_all_and_no_record_work(document):
    both = selection(modality=["image", "action"])
    assert [w["id"] for w in query(document, both)["works"]] == ["w1"]
    both["filters"]["modality"]["mode"] = "any"
    assert [w["id"] for w in query(document, both)["works"]] == ["w1", "w2"]
    assert [w["id"] for w in query(document)["works"]] == ["w1", "w2", "w3"]
    assert [w["id"] for w in query(document, {"text": "UPDATE"})["works"]] == ["w3"]


def test_sorting_values_and_missing_last(document):
    assert [w["id"] for w in query(document, {"sort_by": "year", "descending": True})["works"]] == ["w2", "w1", "w3"]
    document["dimensions"].append({"id": "latency", "label": "Latency", "kind": "number",
                                    "scope": "record", "multiple": False, "sortable": True,
                                    "unit": "ms", "values": []})
    document["records"][0]["dimensions"]["latency"] = 12
    document["records"][1]["dimensions"]["latency"] = 24
    with pytest.raises(ExplorationError, match="narrower comparison"):
        query(document, {"sort_by": "latency"})
    actual = query(document, {**selection(task=["t1"]), "sort_by": "latency"})
    assert actual["works"][0]["id"] == "w1"
    with pytest.raises(ExplorationError, match="sortable"):
        query(document, {"sort_by": "foundation"})


def test_extensible_scalar_types_reference_and_sorting(document):
    for identifier, kind in (("released", "date"), ("cost", "number"),
                             ("uses", "reference"), ("note", "text")):
        document["dimensions"].append({"id": identifier, "label": identifier, "kind": kind,
                                       "scope": "work", "multiple": False,
                                       "sortable": kind != "reference", "values": []})
    document["works"][0]["attributes"].update(released="2024-04-01", cost=2.5,
                                               uses="w2", note="A readable value")
    document["works"][1]["attributes"].update(released="2025-04-01", cost=5)
    assert query(document, selection(uses=["w2"]))["works"][0]["id"] == "w1"
    assert [w["id"] for w in query(document, {"sort_by": "released"})["works"]] == ["w1", "w2", "w3"]
    assert [w["id"] for w in query(document, {"sort_by": "cost", "descending": True})["works"]] == ["w2", "w1", "w3"]
    for key, value in (("cost", True), ("cost", float("nan")), ("released", "2024-99-01"),
                       ("released", "20240401"), ("uses", "unknown"), ("note", [])):
        broken = deepcopy(document)
        broken["works"][0]["attributes"][key] = value
        with pytest.raises(ExplorationError):
            validate(broken)


def test_stored_views_validate_filter_references(document):
    document["views"] = [{"id": "v1", "title": "Specific comparison",
                           "query": selection(foundation=["b1"])}]
    assert validate(document)["views"][0]["query"]["filters"]["foundation"]["values"] == ["b1"]
    document["views"][0]["query"] = selection(foundation=["unknown"])
    with pytest.raises(ExplorationError):
        validate(document)


@pytest.mark.parametrize("change", [
    lambda d: d.update(extra="no"),
    lambda d: d.update(schema_version=True),
    lambda d: d["works"][0].update(extra="no"),
    lambda d: d["works"][1]["assets"][0].update(id="a1"),
    lambda d: d["records"][0].update(work_id="unknown"),
    lambda d: d["records"][0]["dimensions"].update(no_such_dimension=["b1"]),
    lambda d: d["records"][0]["dimensions"].update(modality=["image"]),
    lambda d: d["records"][0]["dimensions"].update(foundation=["no_such_value"]),
    lambda d: d["records"][0]["dimensions"].update(foundation="b1"),
    lambda d: d["records"][0].update(evidence=["unknown"]),
    lambda d: d["edges"][0].update(evidence=[]),
    lambda d: d["edges"][0].update(to_id="unknown"),
    lambda d: d["edges"][0].update(to_id="w1"),
    lambda d: d["dimensions"][0]["values"][0].update(parent_id="b1"),
    lambda d: d["views"].append({"id": "v1", "title": "Invalid view", "query": {"unknown": 1}}),
])
def test_strict_schema_and_references(document, change):
    change(document)
    with pytest.raises(ExplorationError):
        validate(document)


@pytest.mark.parametrize("uri", ["/etc/passwd", "../outside.md", "foo/../body.md",
                                 "https://user:password@example.test/", "javascript:alert(1)",
                                 "file:///etc/passwd", "//example.test/file", "%2e%2e/outside.md"])
def test_invalid_asset_routes_are_rejected(document, uri):
    document["works"][0]["assets"][0]["uri"] = uri
    with pytest.raises(ExplorationError):
        validate(document)


def test_complete_assets_and_readable_render_preserve_originals(tmp_path, document):
    paper = tmp_path / "paper"
    paper.mkdir()
    originals = {paper / "body.md": b"# Human body\n", paper / "tree.canvas": b'{"nodes":[]}',
                 paper / "figure.png": b"image placeholder"}
    for path, content in originals.items():
        path.write_bytes(content)
    before = {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
    ExplorationStore(tmp_path).save(document)
    actual = assets(tmp_path, document, "w1")
    assert len(actual) == 5
    assert [a["available"] for a in actual] == [True, True, False, True, True]
    assert [a["local"] for a in actual] == [True, True, True, False, False]
    assert actual[0]["uri"] == "paper/body.md#claim"
    rendered = render_markdown(tmp_path, document)
    assert "Result one" in rendered and "One hour" in rendered and "Specific conditions only" in rendered
    assert "paper/body.md#claim" in rendered and "文件缺失" in rendered
    assert "An explicitly supported extension" in rendered
    assert before == {path: hashlib.sha256(path.read_bytes()).digest() for path in originals}
    encoded = "paper/a%20b.md#claim"
    (paper / "a b.md").write_text("# Another local body\n", encoding="utf-8")
    document["works"][0]["assets"][0]["uri"] = encoded
    assert assets(tmp_path, document, "w1")[0]["available"] is True
    assert assets(tmp_path, document, "w1")[0]["uri"] == encoded
    assert encoded in render_markdown(tmp_path, document)
    assert "%2520" not in render_markdown(tmp_path, document)
    with pytest.raises(ExplorationError, match="unknown work"):
        assets(tmp_path, document, "unknown")


def test_markdown_only_reference_dimensions_resolve_work_titles(tmp_path, document):
    for identifier, kind in (("run_name", "text"), ("related", "reference")):
        document["dimensions"].append({"id": identifier, "label": identifier, "kind": kind,
                                        "scope": "work", "multiple": False,
                                        "sortable": False, "values": []})
    document["works"][0]["attributes"].update(run_name="w2", related="w2")
    rendered = render_markdown(tmp_path, document)
    assert "- run\\_name：w2" in rendered
    assert "- related：Beta" in rendered
    assert "- run\\_name：Beta" not in rendered


def test_symlink_assets_stay_visible_but_unavailable(tmp_path, document):
    (tmp_path / "paper").symlink_to(tmp_path.parent, target_is_directory=True)
    result = assets(tmp_path, document, "w1")
    assert not result[0]["available"] and result[0]["id"] == "a1"
    state = tmp_path / ".scholar-workflow"
    state.symlink_to(tmp_path.parent, target_is_directory=True)
    store = ExplorationStore(tmp_path)
    with pytest.raises(ExplorationError):
        store.save(document)
    with pytest.raises(ExplorationError):
        store.load()


def test_yaml_duplicates_and_aliases_rejected(tmp_path, document):
    store = ExplorationStore(tmp_path)
    store.save(document)
    for text in ("schema_version: 1\nschema_version: 1\n", "a: &a [1]\nb: *a\n"):
        store.path.write_text(text, encoding="utf-8")
        with pytest.raises(ExplorationError):
            store.load()


def test_markdown_escapes_material_html_and_link_breakout(tmp_path, document):
    document["works"][0]["title"] = '<script>alert("x")</script>'
    document["works"][0]["assets"][0]["label"] = "[bad](javascript:alert)"
    actual = render_markdown(tmp_path, document)
    assert "<script>" not in actual and "&lt;script&gt;" in actual
    assert "\\[bad\\]" in actual


def test_special_asset_is_not_opened_as_a_stream(tmp_path, document):
    (tmp_path / "paper").mkdir()
    os.mkfifo(tmp_path / "paper" / "body.md")
    assert assets(tmp_path, document, "w1")[0]["available"] is False
