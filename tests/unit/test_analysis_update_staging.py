"""Synthetic expectations for preserving an existing pair during staging."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from scholar_workflow.analysis.models import AnalysisCommitRequest, AnalysisDocument
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import _merge_canvas, render_analysis_projection
from scholar_workflow.cli import main


def _graph_base(version: int = 5):
    return SimpleNamespace(
        document=SimpleNamespace(schema_version=version),
        generated_node_ids=["parent", "old-child"],
        generated_edge_ids=[],
    )


def _graphs():
    current = {"nodes": [
        {"id": "parent", "type": "text", "text": "parent", "x": 120, "y": 0},
        {"id": "old-child", "type": "text", "text": "old", "x": 420, "y": 0},
        {"id": "human", "type": "text", "text": "human", "x": -500, "y": -500},
    ], "edges": [], "metadata": {"version": "1.0"}}
    rendered = {"nodes": [
        {"id": "parent", "type": "text", "text": "parent", "x": 300, "y": 0},
        {"id": "old-child", "type": "text", "text": "updated", "x": 600, "y": 0},
        {"id": "new-child", "type": "text", "text": "new", "x": 600, "y": 200},
    ], "edges": []}
    return current, rendered


def test_new_tree_node_uses_existing_column_without_moving_old_nodes() -> None:
    current, rendered = _graphs()
    result = _merge_canvas(current, baseline=_graph_base(), rendered=rendered)
    by_id = {node["id"]: node for node in result["nodes"]}
    assert by_id["new-child"]["x"] == 420
    assert by_id["new-child"]["y"] == 200
    assert by_id["parent"]["x"] == 120
    assert by_id["old-child"]["x"] == 420
    assert by_id["human"] == current["nodes"][2]
    assert result["metadata"] == current["metadata"]
    assert current == _graphs()[0]


def test_split_existing_columns_are_not_silently_normalized() -> None:
    current, rendered = _graphs()
    current["nodes"].append(
        {"id": "other", "type": "text", "text": "other", "x": 450, "y": 300}
    )
    rendered["nodes"].append(
        {"id": "other", "type": "text", "text": "other", "x": 600, "y": 300}
    )
    baseline = _graph_base()
    baseline.generated_node_ids.append("other")
    result = _merge_canvas(current, baseline=baseline, rendered=rendered)
    by_id = {node["id"]: node for node in result["nodes"]}
    assert by_id["old-child"]["x"] == 420
    assert by_id["other"]["x"] == 450
    assert by_id["new-child"]["x"] == 600


def test_legacy_projection_does_not_adopt_tree_column_rule() -> None:
    current, rendered = _graphs()
    result = _merge_canvas(current, baseline=_graph_base(1), rendered=rendered)
    assert next(n for n in result["nodes"] if n["id"] == "new-child")["x"] == 600


def _package(tmp_path: Path):
    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures/analysis_v5_toy.json").read_text()
    )
    document = AnalysisDocument.model_validate(payload)
    stem = "Synthetic Scalar Reader Analysis"
    bundle, baseline = render_analysis_projection(document, note_stem=stem)
    canvas = deepcopy(bundle.canvas)
    for node in canvas["nodes"]:
        node["x"] += 128
    bundle = AnalysisBundle(markdown=bundle.markdown, canvas=canvas)
    root = tmp_path / "vault"
    paper = root / "field/resources/papers/toy"
    paper.mkdir(parents=True)
    names = (stem + ".md", "Tree.canvas", "analysis.baseline.json")
    values = (bundle.markdown, json.dumps(canvas), baseline.model_dump_json())
    paths = dict(zip(("markdown", "canvas", "sidecar"),
                     ("field/resources/papers/toy/" + name for name in names), strict=True))
    hashes = {}
    for name, value in zip(names, values, strict=True):
        (paper / name).write_text(value)
        hashes["field/resources/papers/toy/" + name] = "sha256:" + sha256(value.encode()).hexdigest()
    update = document.model_dump(mode="json")
    next(c for c in update["claims"] if c["claim_id"] == "e-c")["body"] = (
        "This synthetic source still supplies no independent baseline comparison."
    )
    request = AnalysisCommitRequest.model_validate({
        "schema_version": 1, "commit_id": "toy-update", "batch_id": "toy-update",
        "item_id": "toy", "source_state": "validated", "resource_id": "paper:toy",
        "note_stem": stem, "document": update, "paths": paths, "base_revisions": hashes,
        "base_catalog_revision": None, "base_snapshot_revision": None,
        "zotero_item_key": "TOY23456",
        "relations": [{"from_id": "paper:toy", "relation": "has-analysis",
                       "to_id": document.artifact_id}], "projections": [],
    })
    request_file = tmp_path / "request.json"
    request_file.write_text(request.model_dump_json())
    return root, request, request_file, canvas


def test_public_update_stage_preserves_layout_and_leaves_original_files(tmp_path: Path) -> None:
    root, request, input_file, canvas = _package(tmp_path)
    before = {p: (root / p).read_bytes() for p in request.paths.as_list()}
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    assert value["batch"]["state"] == "completed"
    assert value["commit_request"]["base_revisions"] == request.base_revisions
    stage = Path(value["batch"]["items"][0]["stage_path"])
    updated = json.loads((stage / "analysis.canvas").read_text())
    positions = lambda graph: {n["id"]: (n["x"], n["y"]) for n in graph["nodes"]}
    assert positions(updated) == positions(canvas)
    assert {p: (root / p).read_bytes() for p in request.paths.as_list()} == before


def test_update_stage_rejects_stale_base_before_creating_batch(tmp_path: Path) -> None:
    root, request, input_file, _ = _package(tmp_path)
    (root / request.paths.markdown).write_text("Human content must remain.")
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 5, result.output
    assert (root / request.paths.markdown).read_text() == "Human content must remain."
    assert not (tmp_path / "state.db").exists()
    assert not (tmp_path / "stage").exists()


def test_update_stage_rejects_acknowledged_human_text_without_overwriting(tmp_path: Path) -> None:
    root, request, input_file, _ = _package(tmp_path)
    path = root / request.paths.markdown
    path.write_text(path.read_text() + "\nHuman observation must remain.\n")
    payload = request.model_dump(mode="json")
    payload["base_revisions"][request.paths.markdown] = "sha256:" + sha256(path.read_bytes()).hexdigest()
    input_file.write_text(json.dumps(payload))
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 5, result.output
    assert "Human observation must remain." in path.read_text()
    assert not (tmp_path / "state.db").exists()


def test_update_batch_identity_binds_base_context(tmp_path: Path) -> None:
    import pytest

    from scholar_workflow.analysis.batch import AnalysisBatchConflict, AnalysisBatchStore
    from scholar_workflow.analysis.models import AnalysisBatchRequest

    _root, request, _input, _canvas = _package(tmp_path)
    batch = AnalysisBatchRequest.model_validate({
        "schema_version": 1, "batch_id": "same-id",
        "items": [{"item_id": "toy", "zotero_item_key": "TOY23456",
                   "note_stem": request.note_stem, "document": request.document.model_dump(mode="json")}],
    })
    store = AnalysisBatchStore(tmp_path / "state.db")
    try:
        store.ensure_batch(batch, input_context="base-one")
        store.ensure_batch(batch, input_context="base-one")
        with pytest.raises(AnalysisBatchConflict):
            store.ensure_batch(batch, input_context="base-two")
        with pytest.raises(AnalysisBatchConflict):
            store.ensure_batch(batch)
    finally:
        store.close()


def test_focused_update_returns_complete_merged_commit_request(tmp_path: Path) -> None:
    root, request, input_file, _ = _package(tmp_path)
    payload = request.model_dump(mode="json")
    payload["document"]["profile"]["kind"] = "focused"
    payload["document"]["profile"]["roles"] = ["experiments"]
    payload["document"]["claims"] = [
        claim for claim in payload["document"]["claims"] if claim["role"] == "experiments"
    ]
    input_file.write_text(json.dumps(payload))
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 0, result.output
    returned = AnalysisCommitRequest.model_validate(json.loads(result.output)["commit_request"])
    assert returned.document.profile.kind.value == "whole"
    assert len(returned.document.claims) == len(request.document.claims)
    original_by_id = {c.claim_id: c for c in request.document.claims}
    assert all(c == original_by_id[c.claim_id] for c in returned.document.claims)


def test_update_stage_rejects_symlink_without_reading_target(tmp_path: Path) -> None:
    root, request, input_file, _ = _package(tmp_path)
    path = root / request.paths.canvas
    outside = tmp_path / "outside.canvas"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    before = outside.read_bytes()
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 7, result.output
    assert outside.read_bytes() == before
    assert path.is_symlink()
    assert not (tmp_path / "state.db").exists()


def test_update_stage_requires_complete_three_file_base(tmp_path: Path) -> None:
    root, request, input_file, _ = _package(tmp_path)
    payload = request.model_dump(mode="json")
    payload["base_revisions"][request.paths.sidecar] = None
    input_file.write_text(json.dumps(payload))
    result = CliRunner().invoke(main, ["analysis", "stage-update", "--request", str(input_file),
        "--vault-root", str(root), "--state-db", str(tmp_path / "state.db"),
        "--stage-root", str(tmp_path / "stage")])
    assert result.exit_code == 7, result.output
    assert not (tmp_path / "state.db").exists()
