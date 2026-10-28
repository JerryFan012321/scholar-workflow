"""Public CLI exploration operations use isolated roots and preserve paper bytes."""
import json
from copy import deepcopy

import pytest
from click.testing import CliRunner

from scholar_workflow.cli import main
from scholar_workflow.knowledge.exploration import ExplorationStore, default_data


def _synthetic_paper():
    return {"id": "paper", "title": "Accepted paper", "kind": "paper",
            "entity_ref": {"source_id": "synthetic-source", "object_id": "synthetic-paper"},
            "attributes": {}, "assets": [{"id": "body", "label": "分析正文",
                                           "kind": "markdown", "uri": "accepted-analysis.md"}]}


def test_query_and_help_never_initialize(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["knowledge", "exploration-query", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["works"] == []
    assert not (tmp_path / ".scholar-workflow").exists()
    help_result = runner.invoke(main, ["knowledge", "explore", "--help"])
    assert help_result.exit_code == 0
    assert "--no-open" in help_result.output
    assert not (tmp_path / ".scholar-workflow").exists()


def test_init_apply_and_export_preserve_existing_paper(tmp_path):
    paper = tmp_path / "accepted-analysis.md"
    paper.write_bytes(b"# Accepted paper\n\nOriginal evidence.\n")
    baseline = paper.read_bytes()
    runner = CliRunner()
    # Establish the already-referenced unit as synthetic test preparation, not
    # through a generic CLI path that would invent a new paper reference.
    initial = default_data()
    initial["works"] = [_synthetic_paper()]
    receipt = ExplorationStore(tmp_path).save(initial)
    data = deepcopy(receipt["data"])
    data["dimensions"].append({"id": "modality", "label": "输入模态", "kind": "enum",
                               "multiple": True, "scope": "work", "sortable": False,
                               "values": [{"id": "video", "label": "视频"}]})
    data["works"][0]["attributes"] = {"modality": ["video"]}
    data["works"][0]["summary"] = "Human positioning remains editable"
    spec = tmp_path / "edit.json"
    spec.write_text(json.dumps(data), encoding="utf-8")
    args = ["knowledge", "exploration-apply", "--root", str(tmp_path), "--spec", str(spec),
            "--expected-revision", receipt["revision"]]
    updated = runner.invoke(main, args)
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["data"]["works"][0]["summary"] == "Human positioning remains editable"
    stale = runner.invoke(main, args)
    assert stale.exit_code == 5, stale.output
    report = runner.invoke(main, ["knowledge", "exploration-export", "--root", str(tmp_path)])
    assert report.exit_code == 0, report.output
    assert "Accepted paper" in report.output
    assert "accepted-analysis.md" in report.output
    assert paper.read_bytes() == baseline
    assert not (tmp_path / "研究探索.md").exists()


def test_init_spec_rejects_new_paper_reference_without_writing(tmp_path):
    data = default_data()
    data["works"] = [_synthetic_paper()]
    spec = tmp_path / "new-paper.json"
    spec.write_text(json.dumps(data), encoding="utf-8")
    result = CliRunner().invoke(main, ["knowledge", "exploration-init", "--root", str(tmp_path),
                                      "--spec", str(spec)])
    assert result.exit_code == 2, result.output
    assert "exploration-import" in result.output
    assert not (tmp_path / ".scholar-workflow").exists()


@pytest.mark.parametrize("new_identity", [False, True])
def test_apply_rejects_new_paper_reference_without_writing(tmp_path, new_identity):
    initial = default_data()
    if new_identity:
        initial["works"] = [_synthetic_paper()]
    store = ExplorationStore(tmp_path)
    receipt = store.save(initial)
    before = store.path.read_bytes()
    data = deepcopy(receipt["data"])
    if new_identity:
        data["works"][0]["entity_ref"]["object_id"] = "another-synthetic-paper"
    else:
        data["works"].append(_synthetic_paper())
    spec = tmp_path / "new-reference.json"
    spec.write_text(json.dumps(data), encoding="utf-8")
    result = CliRunner().invoke(main, ["knowledge", "exploration-apply", "--root", str(tmp_path),
                                      "--spec", str(spec), "--expected-revision", receipt["revision"]])
    assert result.exit_code == 2, result.output
    assert "exploration-import" in result.output
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("change", ["append", "replace"])
def test_apply_rejects_paper_asset_changes_without_writing(tmp_path, change):
    data = default_data()
    data["works"] = [_synthetic_paper()]
    store = ExplorationStore(tmp_path)
    receipt = store.save(data)
    before = store.path.read_bytes()
    proposed = deepcopy(receipt["data"])
    if change == "append":
        proposed["works"][0]["assets"].append({"id": "unregistered-image", "label": "Image",
                                               "kind": "image", "uri": "undeclared.png"})
    else:
        proposed["works"][0]["assets"][0]["uri"] = "replacement.md"
    spec = tmp_path / "changed-assets.json"
    spec.write_text(json.dumps(proposed), encoding="utf-8")
    result = CliRunner().invoke(main, ["knowledge", "exploration-apply", "--root", str(tmp_path),
                                      "--spec", str(spec), "--expected-revision", receipt["revision"]])
    assert result.exit_code == 2, result.output
    assert "exploration-import" in result.output
    assert store.path.read_bytes() == before


def test_nonpaper_init_and_apply_remain_available(tmp_path):
    data = default_data()
    data["works"] = [{"id": "article", "kind": "webpage", "title": "Existing blog",
                       "attributes": {}, "assets": []}]
    spec = tmp_path / "nonpaper.json"
    spec.write_text(json.dumps(data), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(main, ["knowledge", "exploration-init", "--root", str(tmp_path),
                                  "--spec", str(spec)])
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    data["works"].append({"id": "report", "kind": "report", "title": "Research report",
                          "attributes": {}, "assets": []})
    spec.write_text(json.dumps(data), encoding="utf-8")
    result = runner.invoke(main, ["knowledge", "exploration-apply", "--root", str(tmp_path),
                                  "--spec", str(spec), "--expected-revision", receipt["revision"]])
    assert result.exit_code == 0, result.output
    assert {work["kind"] for work in json.loads(result.output)["data"]["works"]} == {"webpage", "report"}


def test_repeat_init_does_not_replace(tmp_path):
    runner = CliRunner()
    args = ["knowledge", "exploration-init", "--root", str(tmp_path)]
    assert runner.invoke(main, args).exit_code == 0
    path = tmp_path / ".scholar-workflow" / "exploration.yml"
    baseline = path.read_bytes()
    result = runner.invoke(main, args)
    assert result.exit_code == 5, result.output
    assert path.read_bytes() == baseline


def test_cmux_opening_is_an_optional_destination(monkeypatch):
    from scholar_workflow.knowledge import exploration_cli

    monkeypatch.setenv("CMUX_WORKSPACE_ID", "workspace-sample")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(exploration_cli.subprocess, "run", run)
    assert exploration_cli.open_explorer("http://127.0.0.1:1234/#token=example") == "cmux"
    assert calls[0][0][:3] == ["cmux", "browser", "open"]
    assert calls[0][1]["shell"] is False


def test_import_registered_references_preview_then_apply(tmp_path, monkeypatch):
    from scholar_workflow.workflows import field_paper_units

    root = tmp_path / "vault"
    root.mkdir()
    paper = root / "paper.md"
    paper.write_bytes(b"# Original\n")
    state = tmp_path / "private"
    (state / "hub").mkdir(parents=True)
    source_id = "11111111-1111-4111-8111-111111111111"
    (state / "hub" / "sources.json").write_text(json.dumps({
        "schema_version": 1,
        "folders": [{"folder_id": "known", "root": str(root), "capabilities": ["read"]}],
        "sources": [{"source_id": source_id, "folder_id": "known", "capabilities": ["read"]}],
    }), encoding="utf-8")
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(state))
    payload = {"schema_version": 1, "source_id": source_id, "field_id": "field",
               "field_title": "Selected", "status": "complete", "issues": [],
               "unresolved_references": [], "paper_units": [{"source_id": source_id,
                   "resource_id": "paper", "title": "Existing", "ownership": {"status": "resolved"},
                   "files": [{"object_id": "body", "relative_path": "paper.md", "title": "Body",
                              "kind": "analysis", "file_state": "available", "open_state": "ready",
                              "uri": "obsidian://open?file=paper.md"}],
                   "catalog_resource": {"resource_id": "paper",
                                        "identifiers": {"url": "https://example.test/original"},
                                        "zotero": {"item_key": "ABCD2345"}}}]}
    monkeypatch.setattr(field_paper_units, "field_paper_units", lambda *_args, **_kwargs: payload)
    from scholar_workflow.adapters import zotero_local
    calls = []

    class LocalFixture:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_item(self, key):
            calls.append(("item", key))
            return {"key": key, "library": {"type": "user", "id": 1},
                    "data": {"itemType": "journalArticle"}}

        def get_children_all(self, key):
            calls.append(("children", key))
            return [{"key": "EFGH2345", "library": {"type": "user", "id": 1},
                     "data": {"itemType": "attachment", "parentItem": key,
                              "contentType": "application/pdf"}}]

    monkeypatch.setattr(zotero_local, "ZoteroLocalAdapter", LocalFixture)
    runner = CliRunner()
    args = ["knowledge", "exploration-import", "--root", str(root),
            "--source-id", source_id, "--field-id", "field"]
    preview = runner.invoke(main, args)
    assert preview.exit_code == 0, preview.output
    assert json.loads(preview.output)["written"] is False
    assert not (root / ".scholar-workflow").exists()
    applied = runner.invoke(main, [*args, "--apply", "--expected-revision", "absent"])
    assert applied.exit_code == 0, applied.output
    receipt = json.loads(applied.output)
    assert receipt["data"]["works"][0]["entity_ref"]["object_id"] == "paper"
    assert receipt["data"]["works"][0]["assets"][0]["uri"] == "paper.md"
    uris = {asset["uri"] for asset in receipt["data"]["works"][0]["assets"]}
    assert "https://example.test/original" in uris
    assert "zotero://open-pdf/library/items/EFGH2345" in uris
    assert calls[:2] == [("item", "ABCD2345"), ("children", "ABCD2345")]
    assert paper.read_bytes() == b"# Original\n"
    stale = runner.invoke(main, [*args, "--apply", "--expected-revision", "absent"])
    assert stale.exit_code == 5
    # Only a new provider-declared asset may grow the existing paper inventory.
    payload["paper_units"][0]["files"].append({
        "object_id": "new-declared-canvas", "relative_path": "missing.canvas", "title": "Canvas",
        "kind": "analysis_canvas", "file_state": "missing", "open_state": "file_unavailable",
        "uri": None,
    })
    grown = runner.invoke(main, [*args, "--apply", "--expected-revision", receipt["revision"]])
    assert grown.exit_code == 0, grown.output
    grown_data = json.loads(grown.output)["data"]
    assert len(grown_data["works"]) == 1
    assert len(grown_data["works"][0]["assets"]) == len(receipt["data"]["works"][0]["assets"]) + 1
    assert "missing.canvas" in {asset["uri"] for asset in grown_data["works"][0]["assets"]}
    assert paper.read_bytes() == b"# Original\n"


@pytest.mark.parametrize("unavailable", [True, False])
def test_resource_enrichment_offline_keeps_web_and_original_payload(monkeypatch, unavailable):
    from scholar_workflow.adapters import zotero_local
    from scholar_workflow.knowledge.exploration_cli import _include_resource_links

    calls = []

    class OfflineFixture:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_item(self, key):
            calls.append(key)
            error = (zotero_local.ZoteroLocalUnavailable if unavailable
                     else zotero_local.ZoteroLocalError)
            raise error("Synthetic unavailable response, never display raw details")

    monkeypatch.setattr(zotero_local, "ZoteroLocalAdapter", OfflineFixture)
    payload = {"paper_units": [{"resource_id": identity, "catalog_resource": {
        "resource_id": identity, "identifiers": {"url": "https://example.test/original"},
        "zotero": {"item_key": "ABCD2345"}}} for identity in ("first", "second")]}
    before = deepcopy(payload)
    result = _include_resource_links(payload)
    assert payload == before
    assert len(calls) == (1 if unavailable else 2)
    for unit in result["paper_units"]:
        assert [row["uri"] for row in unit["resource_links"]] == ["https://example.test/original"]
        assert unit["resource_notes"]
        assert "Synthetic" not in str(unit["resource_notes"])
