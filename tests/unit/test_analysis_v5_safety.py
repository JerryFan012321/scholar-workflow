"""Independent synthetic v5 update, geometry and budget safety cases.

Fixed inputs and expectations are described in analysis-v5-update-safety-inputs.md;
execution approval and result records belong to the planning layer. Importing
this module does not prepare or alter its input fixtures.

Covered layers: render, conformance, baseline, zero-write update planning and
the existing targeted-repair identity boundary. Batch state/cleanup, canonical
commit, installed CLI, GUI, real-source verification and migrations are outside
this suite's coverage and cannot be inferred from its results.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.batch import _validate_targeted_repair
from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisDocument,
    ConformanceFinding,
    ConformanceReport,
)
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    create_baseline,
    plan_analysis_update,
)

INPUTS = Path(__file__).resolve().parents[1] / "fixtures" / "analysis-v5-safety-inputs"
NOTE_STEM = "Synthetic Scalar Reader Analysis"
ARTIFACT_ID = "analysis:paper:synthetic-scalar-reader"
ROLES = ("abstract", "introduction", "method", "experiments", "limitation")
LABELS = ("Abstract", "Introduction", "Method", "Experiments", "Limitation")
INPUT_HASHES = {
    "../analysis_v5_toy.json": "89640ecef880ec49bdf4210f440b7938952b0529267f09aae55a02faafa2a5d4",
    "focused-method.json": "c1ff6fc4bd090bb1795cd185adb47653bb78e86cd4bc25c1eea42b1bdbc98c5b",
    "v4-base.json": "4958a443190f8d20b3c6847b2ce710ef7dfcfb2dca0725a195043e1bc3c3db6d",
    "budget-40-modules.json": "a7de42e65adc8037a28f3ab16ec7215c96ddfecc7501bb151693d91e855bc573",
    "repair-mutations.json": "c80be0822fc5f9c450d42a1f0352a6838a79096735179f45a6d3982077c36863",
    "canvas-mutations.json": "309d0d2960fce11df9230f3290aad5e50e4fac44a1ab6c9312e4a34dc49dd7e9",
    "focused-limitation.json": "1551b7b837bb6713cfaa703187da23d8d85f0e4c51d23aa6ad0ac37999c9dbdb",
    "geometry-mutations.json": "1fa29ce6f02dca72099a091867b1151449e8bc473ae2c088c1e628b2862287e7",
    "human-edge-mutations.json": "2f6346f5b3d0bd8b82f5df4ed6a3983305b3155121c3855446f01a1292fb0913",
    "point-prose-mutations.json": "53d6378874a0e447aebb61277ec9d7ce089c8a1b895f3c394c29ebf68fd7ef52",
    "manifest.json": "8ebdbb0a15ea92bf79ad7e8f5e7e0ce360dd26a288779b8b0fac2b97e31af4b6",
}
GEOMETRY_CANVAS_HASH = "6dab532f4b5bbf261716ede769eb1e135eac92ea5c8fe50531ba9fe98ff12b9d"


def _input(name: str) -> dict:
    raw = (INPUTS / name).read_bytes()
    assert sha256(raw).hexdigest() == INPUT_HASHES[name], f"Fixed input changed: {name}"
    return json.loads(raw)


@pytest.fixture(autouse=True)
def _fixed_input_preflight() -> None:
    for name in INPUT_HASHES:
        _input(name)


def _document(name: str = "../analysis_v5_toy.json") -> AnalysisDocument:
    return AnalysisDocument.model_validate(_input(name))


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _node_id(path: str, artifact_id: str = ARTIFACT_ID) -> str:
    # The public stable-ID convention; not a production renderer snapshot.
    return sha256(f"{artifact_id}\n{path}".encode()).hexdigest()[:16]


def _bbox(canvas: dict) -> dict[str, int]:
    nodes = canvas["nodes"]
    return {
        "min_x": min(node["x"] for node in nodes),
        "min_y": min(node["y"] for node in nodes),
        "max_x": max(node["x"] + node["width"] for node in nodes),
        "max_y": max(node["y"] + node["height"] for node in nodes),
    }


def _case(spec: dict, case_id: str) -> dict:
    matches = [case for case in spec["cases"] if case["case_id"] == case_id]
    assert len(matches) == 1, f"Case {case_id} must have one fixed definition"
    return matches[0]


def _write_state(
    folder: Path,
    document: AnalysisDocument,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline | None,
) -> dict[str, Path]:
    """Prepare only three isolated synthetic files before the zero-write check.

    A rejected candidate has an input IR, never a fabricated trusted baseline.
    """
    folder.mkdir()
    paths = {"markdown": folder / "analysis.md", "canvas": folder / "analysis.canvas"}
    paths["markdown"].write_bytes(bundle.markdown.encode("utf-8"))
    paths["canvas"].write_bytes(_json_bytes(bundle.canvas))
    if baseline is None:
        paths["ir"] = folder / "analysis.ir.json"
        paths["ir"].write_bytes(_json_bytes(document.model_dump(mode="json")))
    else:
        paths["baseline"] = folder / "analysis.baseline.json"
        paths["baseline"].write_bytes(_json_bytes(baseline.model_dump(mode="json")))
    assert len(list(folder.iterdir())) == 3
    return paths


def _base_state(
    tmp_path: Path, name: str = "../analysis_v5_toy.json"
) -> tuple[AnalysisDocument, AnalysisBundle, AnalysisBaseline, dict[str, Path]]:
    document = _document(name)
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    baseline = create_baseline(document, bundle, note_stem=NOTE_STEM)
    paths = _write_state(tmp_path / "current", document, bundle, baseline)
    return document, bundle, baseline, paths


def _read_pair(paths: dict[str, Path]) -> AnalysisBundle:
    return AnalysisBundle(
        markdown=paths["markdown"].read_text(encoding="utf-8"),
        canvas=json.loads(paths["canvas"].read_bytes()),
    )


def _read_baseline(paths: dict[str, Path]) -> AnalysisBaseline:
    return AnalysisBaseline.model_validate_json(paths["baseline"].read_bytes())


@contextmanager
def _unchanged_files(paths: dict[str, Path]) -> Iterator[None]:
    """Observe per-file bytes, hashes and revisions after preparation, not intent."""
    folder = paths["markdown"].parent

    def snapshot() -> dict:
        result = {}
        for path in folder.iterdir():
            assert path.is_file() and not path.is_symlink()
            raw, stat = path.read_bytes(), path.stat()
            result[path.name] = (
                raw, sha256(raw).hexdigest(), stat.st_ino, stat.st_mtime_ns, stat.st_size
            )
        return result

    before = snapshot()
    assert set(before) == {path.name for path in paths.values()}
    assert len(before) == 3
    try:
        yield
    finally:
        assert snapshot() == before, "Planning/validation changed protected current files"


def _markdown_sections(markdown: str) -> dict[str, str]:
    headings = list(re.finditer(r"(?m)^## ([^\r\n]+)$", markdown))
    return {
        match.group(1): markdown[match.start() : headings[index + 1].start()]
        if index + 1 < len(headings)
        else markdown[match.start() :]
        for index, match in enumerate(headings)
    }


def _subtree_ids(canvas: dict, root_id: str) -> set[str]:
    children: dict[str, list[str]] = {}
    for edge in canvas["edges"]:
        children.setdefault(edge["fromNode"], []).append(edge["toNode"])
    pending, found = [root_id], set()
    while pending:
        node_id = pending.pop()
        assert node_id not in found, "The fixed managed tree cannot have cycles/shared children"
        found.add(node_id)
        pending.extend(children.get(node_id, []))
    return found


def _record_node(canvas: dict, selector: dict) -> dict:
    record = selector["record"]
    block = record["markdown_block"]
    backlink = f"[[{NOTE_STEM}#^{block}|Analysis]]"
    matches = [node for node in canvas["nodes"] if backlink in node.get("text", "")]
    assert len(matches) == selector["uniqueness"] == 1
    assert matches[0]["id"] == _node_id(
        f"role/method/{record['claim_id']}/point/{record['point_id']}"
    )
    return matches[0]


def _apply_patch(payload: dict, operations: list[dict]) -> dict:
    """Apply the prepared test/replace-only RFC6902 subset, never an inferred patch."""
    result = deepcopy(payload)
    for operation in operations:
        parts = operation["path"].split("/")[1:]
        parent = result
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = int(parts[-1]) if isinstance(parent, list) else parts[-1]
        if operation["op"] == "test":
            assert parent[key] == operation["value"], operation["path"]
        else:
            assert operation["op"] == "replace"
            assert (key in parent if isinstance(parent, dict) else 0 <= key < len(parent))
            parent[key] = deepcopy(operation["value"])
    return result


def _assert_finding(report: ConformanceReport, code: str) -> None:
    assert not report.ok
    codes = {finding.code for finding in report.findings}
    assert code in codes, [(f.code, f.path, f.message) for f in report.findings]


def _fixed_geometry_state(
    tmp_path: Path,
) -> tuple[AnalysisDocument, AnalysisBundle, AnalysisBaseline, dict[str, Path], dict]:
    """Abort before mutation if the displayed fixed base cannot be reconstructed."""
    spec = _input("geometry-mutations.json")
    base = spec["base_canvas"]
    assert base["ir_sha256"] == INPUT_HASHES["../analysis_v5_toy.json"]
    document, bundle, baseline, paths = _base_state(tmp_path)
    raw = paths["canvas"].read_bytes()
    assert sha256(raw).hexdigest() == base["sha256"] == GEOMETRY_CANVAS_HASH, (
        "Fixed Canvas base mismatch: stop before applying any geometry mutation"
    )
    assert len(bundle.canvas["nodes"]) == base["managed_nodes"] == 58
    assert len(bundle.canvas["edges"]) == base["managed_edges"] == 57
    assert _bbox(bundle.canvas) == base["bbox"] == {
        "min_x": 0, "min_y": 0, "max_x": 3056, "max_y": 4538
    }
    nodes = {node["id"]: node for node in bundle.canvas["nodes"]}
    old_ys = _case(spec, "G-03")["mutation"]["by_node"]
    assert len(old_ys) == len(nodes) == 58
    assert {row["node_id"] for row in old_ys} == set(nodes)
    for row in old_ys:
        assert nodes[row["node_id"]]["y"] == row["old_y"], row["node_id"]
    reference = _case(spec, "G-02")["mutation"]["reference_node"]
    assert {key: nodes[reference["id"]][key] for key in reference} == reference
    return document, bundle, baseline, paths, spec


def test_u01_focused_method_preserves_all_four_unselected_branches(tmp_path: Path) -> None:
    original, current, _, paths = _base_state(tmp_path)
    incoming = _document("focused-method.json")
    original_claims = {claim.claim_id: claim for claim in original.claims}
    assert sum(len(claim.points) for claim in incoming.claims) == 10
    assert {claim.claim_id for claim in incoming.claims} == {"m-o", "m-1", "m-2"}
    for claim in incoming.claims:
        expected = original_claims[claim.claim_id].model_dump(mode="json")
        if claim.claim_id == "m-2":
            expected["points"][0]["text"] = "Module 2 has no supplied motivation."
            expected["points"][0]["evidence"]["detail"] = "Module 2 has no supplied motivation."
        assert claim.model_dump(mode="json") == expected
    with _unchanged_files(paths):
        plan = plan_analysis_update(
            current=_read_pair(paths), baseline=_read_baseline(paths), update=incoming,
            note_stem=NOTE_STEM,
        )
        assert plan.status == "ready" and plan.baseline is not None and not plan.conflicts
        assert plan.document.profile.kind.value == "whole"
        assert [role.value for role in plan.document.profile.roles] == list(ROLES)
        assert plan.document.schema_version == 5 and plan.document.profile.markdown_quotes
        planned_claims = {claim.claim_id: claim for claim in plan.document.claims}
        for claim in original.claims:
            if claim.role.value != "method":
                assert planned_claims[claim.claim_id] == claim
        assert [c for c in plan.document.claims if c.role.value == "method"] == incoming.claims
        original_sections = _markdown_sections(current.markdown)
        proposed_sections = _markdown_sections(plan.proposed.markdown)
        assert tuple(proposed_sections) == LABELS
        proposed_nodes = {node["id"]: node for node in plan.proposed.canvas["nodes"]}
        original_nodes = {node["id"]: node for node in current.canvas["nodes"]}
        for role, label in zip(ROLES, LABELS, strict=True):
            if role == "method":
                continue
            assert proposed_sections[label] == original_sections[label]
            branch_ids = _subtree_ids(current.canvas, _node_id(f"role/{role}"))
            assert _subtree_ids(plan.proposed.canvas, _node_id(f"role/{role}")) == branch_ids
            for node_id in branch_ids:
                assert proposed_nodes[node_id] == original_nodes[node_id]
            assert [e for e in plan.proposed.canvas["edges"] if e["toNode"] in branch_ids] == [
                e for e in current.canvas["edges"] if e["toNode"] in branch_ids
            ]
        assert validate_bundle(plan.document, plan.proposed, note_stem=NOTE_STEM).ok


@pytest.mark.parametrize("case_id", ["U-02", "U-03", "U-04"])
def test_targeted_repair_rejects_exact_container_or_point_identity_change(
    tmp_path: Path, case_id: str
) -> None:
    original, _, _, paths = _base_state(tmp_path)
    spec = _case(_input("repair-mutations.json"), case_id)
    original_payload = _input("../analysis_v5_toy.json")
    repaired = AnalysisDocument.model_validate(_apply_patch(original_payload, spec["operations"]))
    assert repaired != original  # These payloads are valid IR, not accidental schema failures.
    report = ConformanceReport(
        ok=False,
        findings=[ConformanceFinding(
            code="synthetic-claim-repair", path="canvas/claims/m-1",
            message="Prepared identity-boundary probe for the existing m-1 claim.",
            repairable=True,
        )],
    )
    reason = "container state" if case_id == "U-02" else "point identities or order"
    with _unchanged_files(paths):
        with pytest.raises(ValueError, match=reason):
            _validate_targeted_repair(original, repaired, report)
        assert original.model_dump(mode="json") == _document().model_dump(mode="json")


def test_u05_manual_managed_text_conflicts_without_overwriting_files(tmp_path: Path) -> None:
    _, current, _, paths = _base_state(tmp_path)
    spec = _case(_input("canvas-mutations.json"), "U-05")
    canvas = deepcopy(current.canvas)
    operation = spec["operation"]
    node = _record_node(canvas, operation["selector"])
    assert operation["replace_field"] == "text"
    node["text"] = operation["value"]
    paths["canvas"].write_bytes(_json_bytes(canvas))
    with _unchanged_files(paths):
        plan = plan_analysis_update(
            current=_read_pair(paths), baseline=_read_baseline(paths),
            update=_document(spec["incoming_ir"]), note_stem=NOTE_STEM,
        )
        assert plan.status == "conflict" and plan.baseline is None
        assert "canvas-revision-conflict" in plan.conflicts
        assert plan.current.canvas == canvas
        assert operation["value"] in paths["canvas"].read_text(encoding="utf-8")
        assert plan.current.markdown == current.markdown


def test_u06_safe_translation_color_and_custom_graph_survive_ready_proposal(tmp_path: Path) -> None:
    original, current, baseline, paths = _base_state(tmp_path)
    spec = _case(_input("canvas-mutations.json"), "U-06")
    canvas = deepcopy(current.canvas)
    for operation in spec["operations"]:
        if "translate" in operation:
            assert operation["selector"] == {"all_managed_nodes": True}
            assert operation["translate"] == {"x": 120, "y": 80}
            for node in canvas["nodes"]:
                node["x"] += 120
                node["y"] += 80
        elif "replace_field" in operation:
            assert operation["replace_field"] == "color"
            _record_node(canvas, operation["selector"])["color"] = operation["value"]
        elif "add_custom_node" in operation:
            node = deepcopy(operation["add_custom_node"])
            position = node.pop("position")
            bounds = _bbox(current.canvas)
            assert position["x"] == "translated_managed_bbox.max_x + 200"
            node["x"] = bounds["max_x"] + 120 + 200
            choices = {
                "translated_managed_bbox.min_y": bounds["min_y"] + 80,
                "translated_managed_bbox.min_y + 200": bounds["min_y"] + 80 + 200,
            }
            assert position["y"] in choices
            node["y"] = choices[position["y"]]
            canvas["nodes"].append(node)
        else:
            assert set(operation) == {"add_custom_edge"}
            canvas["edges"].append(deepcopy(operation["add_custom_edge"]))
    paths["canvas"].write_bytes(_json_bytes(canvas))
    assert validate_bundle(original, AnalysisBundle(current.markdown, canvas), note_stem=NOTE_STEM).ok
    with _unchanged_files(paths):
        plan = plan_analysis_update(
            current=_read_pair(paths), baseline=_read_baseline(paths),
            update=_document(spec["incoming_ir"]), note_stem=NOTE_STEM,
        )
        assert plan.status == "ready" and plan.baseline is not None and not plan.conflicts
        before = {node["id"]: node for node in canvas["nodes"]}
        after = {node["id"]: node for node in plan.proposed.canvas["nodes"]}
        assert set(after) == set(before)
        for node_id in baseline.generated_node_ids:
            assert (after[node_id]["x"], after[node_id]["y"]) == (
                before[node_id]["x"], before[node_id]["y"]
            )
        colored_id = _node_id("role/method/m-1/point/motivation")
        assert after[colored_id]["color"] == before[colored_id]["color"] == "3"
        for node_id in ("user-review-note-a", "user-review-note-b"):
            assert after[node_id] == before[node_id]
            assert node_id not in plan.baseline.generated_node_ids
        expected_edge = next(edge for edge in canvas["edges"] if edge["id"] == "user-review-edge")
        assert [e for e in plan.proposed.canvas["edges"] if e["id"] == "user-review-edge"] == [expected_edge]
        assert "user-review-edge" not in plan.baseline.generated_edge_ids
        assert len(plan.baseline.generated_node_ids) == len(baseline.generated_node_ids) == 58
        assert validate_bundle(plan.document, plan.proposed, note_stem=NOTE_STEM).ok


@pytest.mark.parametrize(
    ("case_id", "base_name", "incoming_name"),
    [
        ("U-07", "v4-base.json", "../analysis_v5_toy.json"),
        ("U-08", "../analysis_v5_toy.json", "v4-base.json"),
    ],
)
def test_version_cutover_requires_explicit_migration_and_leaves_current_bytes(
    tmp_path: Path, case_id: str, base_name: str, incoming_name: str
) -> None:
    _input("manifest.json")
    document, current, _, paths = _base_state(tmp_path, base_name)
    incoming = _document(incoming_name)
    assert document.artifact_id == incoming.artifact_id == ARTIFACT_ID
    assert document.schema_version != incoming.schema_version
    v4 = document if document.schema_version == 4 else incoming
    assert [role.value for role in v4.profile.roles] == list(ROLES[:3]) + ["limitation"]
    assert v4.profile.framework == "reference_tree" and not v4.profile.markdown_quotes
    if case_id == "U-07":
        details_id = _node_id("role/method/v4-m/details")
        assert any(node["id"] == details_id for node in current.canvas["nodes"])
        assert "## Experiments" not in current.markdown
    else:
        assert "## Experiments" in current.markdown and document.profile.markdown_quotes
    with (
        _unchanged_files(paths),
        pytest.raises(AnalysisUpdateError, match="five-branch cutover requires an explicit migration"),
    ):
        plan_analysis_update(
            current=_read_pair(paths), baseline=_read_baseline(paths),
            update=incoming, note_stem=NOTE_STEM,
        )


@pytest.mark.parametrize("case_id", ["G-01", "G-02", "G-03"])
def test_fixed_geometry_mutation_reports_its_specific_contract_failure(
    tmp_path: Path, case_id: str
) -> None:
    document, current, _, paths, spec = _fixed_geometry_state(tmp_path)
    case = _case(spec, case_id)
    canvas = deepcopy(current.canvas)
    mutation = case["mutation"]
    if case_id == "G-01":
        extra = deepcopy(mutation["add_edge"])
        assert extra["id"] not in {edge["id"] for edge in canvas["edges"]}
        canvas["edges"].append(extra)
        assert canvas["nodes"] == current.canvas["nodes"]
        assert canvas["edges"][:-1] == current.canvas["edges"]
    elif case_id == "G-02":
        extra = deepcopy(mutation["add_node"])
        assert extra["id"] not in {node["id"] for node in canvas["nodes"]}
        canvas["nodes"].append(extra)
        assert canvas["nodes"][:-1] == current.canvas["nodes"]
        assert canvas["edges"] == current.canvas["edges"]
    else:
        nodes = {node["id"]: node for node in canvas["nodes"]}
        for row in mutation["by_node"]:
            assert nodes[row["node_id"]]["y"] == row["old_y"]
            assert row["new_y"] == (row["old_y"] * 9039 * 2 + 4409) // (4409 * 2)
            assert type(row["new_y"]) is int
            nodes[row["node_id"]]["y"] = row["new_y"]
        assert _bbox(canvas) == case["expected"]["bbox"] == {
            "min_x": 0, "min_y": 0, "max_x": 3056, "max_y": 9169
        }
        for old, new in zip(current.canvas["nodes"], canvas["nodes"], strict=True):
            assert {k: v for k, v in old.items() if k != "y"} == {
                k: v for k, v in new.items() if k != "y"
            }
        assert canvas["edges"] == current.canvas["edges"]
    paths["canvas"].write_bytes(_json_bytes(canvas))
    with _unchanged_files(paths):
        report = validate_bundle(document, _read_pair(paths), note_stem=NOTE_STEM)
        _assert_finding(report, case["expected"]["finding"])
        assert "invalid-json-canvas-contract" not in {f.code for f in report.findings}


@pytest.mark.parametrize("case_id", ["G-05", "G-06", "G-07"])
def test_human_edge_or_floating_endpoint_cannot_bypass_managed_geometry(
    tmp_path: Path, case_id: str
) -> None:
    document, current, _, paths, _ = _fixed_geometry_state(tmp_path)
    spec = _input("human-edge-mutations.json")
    assert spec["base_canvas_sha256"] == GEOMETRY_CANVAS_HASH
    case = _case(spec, case_id)
    canvas = deepcopy(current.canvas)
    canvas["nodes"].extend(deepcopy(case["add_nodes"]))
    assert canvas["nodes"][:58] == current.canvas["nodes"]
    if "add_edge" in case:
        canvas["edges"].append(deepcopy(case["add_edge"]))
        assert canvas["edges"][:-1] == current.canvas["edges"]
    else:
        operation = case["patch_existing_edge"]
        matches = [e for e in canvas["edges"] if e["id"] == operation["edge_id"]]
        assert len(matches) == 1 and operation["field"] not in matches[0]
        matches[0][operation["field"]] = operation["value"]
        for old, new in zip(current.canvas["edges"], canvas["edges"], strict=True):
            expected = deepcopy(old)
            if old["id"] == operation["edge_id"]:
                expected[operation["field"]] = operation["value"]
            assert new == expected
    paths["canvas"].write_bytes(_json_bytes(canvas))
    with _unchanged_files(paths):
        report = validate_bundle(document, _read_pair(paths), note_stem=NOTE_STEM)
        expected = case["expected"]
        _assert_finding(report, expected["finding"])
        matches = [f for f in report.findings if f.code == expected["finding"]]
        if "finding_path" in expected:
            matches = [f for f in matches if f.path == expected["finding_path"]]
        if "finding_path_contains" in expected:
            matches = [f for f in matches if expected["finding_path_contains"] in f.path]
        assert matches, "Failure must identify the fixed edge, not an unrelated finding"
        if "message_contains" in expected:
            assert any(expected["message_contains"] in f.message for f in matches)
        codes = {f.code for f in report.findings}
        assert "invalid-json-canvas-contract" not in codes
        assert "overlapping-canvas-nodes" not in codes
        assert not codes.intersection(expected.get("forbidden_findings", []))


def test_g04_focused_limitation_keeps_exact_source_and_a_compact_editable_tree(tmp_path: Path) -> None:
    document = _document("focused-limitation.json")
    base = _document()
    assert document.claims == [next(claim for claim in base.claims if claim.claim_id == "l-r")]
    assert document.profile.kind.value == "focused"
    assert [role.value for role in document.profile.roles] == ["limitation"]
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    baseline = create_baseline(document, bundle, note_stem=NOTE_STEM)
    paths = _write_state(tmp_path / "current", document, bundle, baseline)
    with _unchanged_files(paths):
        assert validate_bundle(document, _read_pair(paths), note_stem=NOTE_STEM).ok
        assert re.findall(r"(?m)^## ([^\r\n]+)$", bundle.markdown) == ["Limitation"]
        assert "> Scope: Focused: Limitation" in bundle.markdown
        assert "> Scope: Whole paper" not in bundle.markdown
        assert len(bundle.canvas["nodes"]) == 3 and len(bundle.canvas["edges"]) == 2
        assert all(node["type"] == "text" for node in bundle.canvas["nodes"])
        claim = document.claims[0]
        assert claim.body in bundle.markdown
        node = next(node for node in bundle.canvas["nodes"] if node["id"] == _node_id("role/limitation/l-r"))
        assert claim.body in node["text"] and "#^claim-l-r|Analysis]]" in node["text"]
        assert "SYNTH001?page=4" in node["text"]
        expected_quote = r'> Q\_LIMIT: "Evidence is limited to the three\-input toy setting\."'
        assert expected_quote in bundle.markdown
        assert "Q_LIMIT" not in node["text"] and r"Q\_LIMIT" not in node["text"]
        bounds = _bbox(bundle.canvas)
        width, height = bounds["max_x"] - bounds["min_x"], bounds["max_y"] - bounds["min_y"]
        assert max(width / height, height / width) <= 2


def test_n18_expanded_budget_preserves_all_slots_but_refuses_baseline(tmp_path: Path) -> None:
    payload = _input("budget-40-modules.json")
    assert len(payload["claims"]) == 40
    assert [claim["claim_id"] for claim in payload["claims"]] == [
        f"budget-{index:02d}" for index in range(1, 41)
    ]
    assert all(not claim.get("container") and not claim.get("points") for claim in payload["claims"])
    assert payload["profile"]["roles"] == list(ROLES)
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem=NOTE_STEM)
    paths = _write_state(tmp_path / "current", document, bundle, baseline=None)
    nodes = {node["id"]: node for node in bundle.canvas["nodes"]}
    assert len(nodes) == len(bundle.canvas["nodes"]) >= 206
    assert len(nodes) > 96
    slot_labels = {
        "motivation": "Motivation", "method": "Method",
        "why-it-works": "Why it works", "technical-advantage": "Technical advantage",
    }
    slots = set()
    for claim in document.claims:
        path = f"role/method/{claim.claim_id}"
        parent_id = _node_id(path, document.artifact_id)
        assert nodes[parent_id]["type"] == "text"
        assert claim.body in nodes[parent_id]["text"] and claim.body in bundle.markdown
        assert f"^claim-{claim.claim_id}" in bundle.markdown
        for slot, label in slot_labels.items():
            slot_id = _node_id(f"{path}/point/{slot}", document.artifact_id)
            slots.add(slot_id)
            assert nodes[slot_id]["type"] == "text" and nodes[slot_id]["text"] == f"**{label}**"
            assert [edge["fromNode"] for edge in bundle.canvas["edges"] if edge["toNode"] == slot_id] == [parent_id]
    assert len(slots) == 160
    assert re.findall(r"(?m)^## ([^\r\n]+)$", bundle.markdown) == list(LABELS)
    for role, label in zip(ROLES, LABELS, strict=True):
        node = nodes[_node_id(f"role/{role}", document.artifact_id)]
        assert node["type"] == "text" and node["text"] == f"**{label}**"
    baseline_path = paths["markdown"].parent / "analysis.baseline.json"
    assert not baseline_path.exists()
    with _unchanged_files(paths):
        report = validate_bundle(document, _read_pair(paths), note_stem=NOTE_STEM)
        _assert_finding(report, "canvas-node-limit")
        with pytest.raises(AnalysisUpdateError, match="canvas-node-limit"):
            create_baseline(document, bundle, note_stem=NOTE_STEM)
        assert not baseline_path.exists()


@pytest.mark.parametrize("case_id", [f"P-{index:02d}" for index in range(1, 11)])
def test_point_prose_preserves_versioned_framework_without_injected_headings(case_id: str) -> None:
    spec = _input("point-prose-mutations.json")
    case = _case(spec, case_id)
    original = (
        deepcopy(spec["inline_legacy_v3"])
        if case["base_fixture"] == "inline_legacy_v3" else _input(case["base_fixture"])
    )
    payload = deepcopy(original)
    claims = [claim for claim in payload["claims"] if claim["claim_id"] == case["claim_id"]]
    assert len(claims) == 1
    points = [point for point in claims[0]["points"] if point["point_id"] == case["point_id"]]
    assert len(points) == 1
    points[0][case["field"]] = case["value"]
    schema_path = Path(__file__).resolve().parents[2] / "contracts" / "analysis-ir.schema.json"
    validator = jsonschema.Draft202012Validator(json.loads(schema_path.read_bytes()))
    if case["expected"]["model_and_schema"] == "reject":
        with pytest.raises(ValidationError, match=case["expected"]["reason"]):
            AnalysisDocument.model_validate(payload)
        errors = list(validator.iter_errors(payload))
        assert any(
            error.validator == "not" and list(error.path)[-1] == case["field"]
            for error in errors
        ), [(list(error.path), error.message) for error in errors]
        return
    assert not list(validator.iter_errors(payload))
    document = AnalysisDocument.model_validate(payload)
    assert document.schema_version == original["schema_version"]
    original_document = AnalysisDocument.model_validate(original)
    original_claims = {claim.claim_id: claim for claim in original_document.claims}
    for claim in document.claims:
        expected_claim = original_claims[claim.claim_id].model_dump(mode="json")
        if claim.claim_id == case["claim_id"]:
            selected = [p for p in expected_claim["points"] if p["point_id"] == case["point_id"]]
            assert len(selected) == 1
            selected[0][case["field"]] = case["value"]
        assert claim.model_dump(mode="json") == expected_claim
    if case["expected"].get("render_literal_text"):
        bundle = render_analysis(document, note_stem=NOTE_STEM)
        assert case["value"] in bundle.markdown
        assert any(case["value"] in node.get("text", "") for node in bundle.canvas["nodes"])
        expected_labels = list(LABELS) if document.schema_version == 5 else [
            "Abstract", "Introduction", "Method", "Limitation"
        ]
        assert re.findall(r"(?m)^## ([^\r\n]+)$", bundle.markdown) == expected_labels
        assert not re.search(r"(?m)^#{1,6}[ \t]+Extra section(?:[ \t]|$)", bundle.markdown)
        if document.schema_version == 4:
            point_line = next(line for line in bundle.markdown.splitlines() if case["value"] in line)
            assert point_line.startswith("- **")
