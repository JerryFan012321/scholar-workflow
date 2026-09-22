from __future__ import annotations

import json

import pytest

from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    ProfileKind,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    create_baseline,
    plan_analysis_update,
    render_analysis_projection,
)


def _claim(role: AnalysisRole, body: str, *, order: int | None = None) -> AnalysisClaim:
    return AnalysisClaim(
        claim_id=f"{role.value}-{order or 1}",
        role=role,
        title=f"{role.value} title",
        body=body,
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 2"),
        order=order,
    )


def _whole() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:update-test",
        paper_title="Update Test",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            _claim(AnalysisRole.TASK, "Original task."),
            _claim(AnalysisRole.INPUT, "Original input."),
            _claim(AnalysisRole.WORKFLOW, "Original workflow.", order=1),
            _claim(AnalysisRole.OUTPUT, "Original output."),
            _claim(AnalysisRole.BOUNDARY, "Original boundary."),
        ],
    )


def _focused_workflow() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:update-test",
        paper_title="Update Test",
        profile=AnalysisProfile(kind=ProfileKind.FOCUSED, roles=[AnalysisRole.WORKFLOW]),
        claims=[_claim(AnalysisRole.WORKFLOW, "Revised workflow.", order=1)],
    )


def test_focused_update_uses_baseline_and_preserves_other_roles() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    plan = plan_analysis_update(
        current=current,
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "ready"
    assert plan.baseline is not None
    assert "Revised workflow." in plan.proposed.markdown
    assert "Original workflow." not in plan.proposed.markdown
    for unchanged in ("Original task.", "Original input.", "Original output.", "Original boundary."):
        assert unchanged in plan.proposed.markdown
    assert plan.document.profile.kind is ProfileKind.WHOLE


def test_human_edit_returns_paired_conflict_without_replacing_current() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    edited = AnalysisBundle(
        markdown=current.markdown.replace("Original task.", "Human task edit."),
        canvas=json.loads(json.dumps(current.canvas)),
    )
    edited.canvas["nodes"][0]["x"] += 20

    plan = plan_analysis_update(
        current=edited,
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "conflict"
    assert plan.baseline is None
    assert set(plan.conflicts) == {"markdown-revision-conflict"}
    assert plan.current is edited
    assert "Human task edit." in plan.current.markdown
    assert "Revised workflow." in plan.proposed.markdown
    assert plan.proposed.canvas["nodes"][0]["x"] == edited.canvas["nodes"][0]["x"]


def test_focused_update_preserves_custom_graph_and_manual_generated_layout() -> None:
    document = _whole()
    rendered, baseline = render_analysis_projection(document, note_stem="Update Test分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    root = canvas["nodes"][0]
    root["x"] -= 240
    root["width"] += 40
    custom_node = {
        "id": "human-file",
        "type": "file",
        "x": -900,
        "y": -900,
        "width": 20,
        "height": 20,
        "file": "assets/human-note.pdf",
    }
    custom_edge = {
        "id": "human-edge",
        "fromNode": custom_node["id"],
        "toNode": root["id"],
        "label": "my context",
    }
    canvas["nodes"].append(custom_node)
    canvas["edges"].append(custom_edge)
    current = AnalysisBundle(markdown=rendered.markdown, canvas=canvas)

    mixed_baseline = create_baseline(document, current, note_stem="Update Test分析")
    assert mixed_baseline.generated_node_ids == baseline.generated_node_ids
    assert mixed_baseline.generated_edge_ids == baseline.generated_edge_ids
    assert mixed_baseline.canvas_sha256 == baseline.canvas_sha256
    assert custom_node["id"] not in mixed_baseline.generated_node_ids
    assert custom_edge["id"] not in mixed_baseline.generated_edge_ids

    plan = plan_analysis_update(
        current=current,
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "ready"
    assert plan.conflicts == ()
    proposed_nodes = {node["id"]: node for node in plan.proposed.canvas["nodes"]}
    proposed_edges = {edge["id"]: edge for edge in plan.proposed.canvas["edges"]}
    assert proposed_nodes[custom_node["id"]] == custom_node
    assert proposed_edges[custom_edge["id"]] == custom_edge
    assert proposed_nodes[root["id"]]["x"] == root["x"]
    assert proposed_nodes[root["id"]]["width"] == root["width"]
    assert plan.baseline is not None
    assert custom_node["id"] not in plan.baseline.generated_node_ids
    assert custom_edge["id"] not in plan.baseline.generated_edge_ids


def test_generated_content_edit_conflicts_but_proposal_keeps_custom_graph() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    canvas = json.loads(json.dumps(current.canvas))
    task_node = next(node for node in canvas["nodes"] if 'role="task"' in node["text"])
    task_node["text"] = task_node["text"].replace("Original task.", "Human Canvas edit.")
    custom_node = {
        "id": "human-group",
        "type": "group",
        "x": 9000,
        "y": 9000,
        "width": 10,
        "height": 10,
        "label": "My group",
    }
    canvas["nodes"].append(custom_node)
    edited = AnalysisBundle(markdown=current.markdown, canvas=canvas)

    plan = plan_analysis_update(
        current=edited,
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "conflict"
    assert plan.conflicts == ("canvas-revision-conflict",)
    assert plan.current is edited
    assert any(node == custom_node for node in plan.proposed.canvas["nodes"])
    proposed_task = next(
        node for node in plan.proposed.canvas["nodes"] if node["id"] == task_node["id"]
    )
    assert "Original task." in proposed_task["text"]
    assert "Human Canvas edit." not in proposed_task["text"]


def test_generated_node_type_edit_conflicts_and_proposal_restores_type() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    canvas = json.loads(json.dumps(current.canvas))
    task_node = next(node for node in canvas["nodes"] if 'role="task"' in node["text"])
    task_node["type"] = "group"
    edited = AnalysisBundle(markdown=current.markdown, canvas=canvas)

    plan = plan_analysis_update(
        current=edited,
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "conflict"
    assert "canvas-revision-conflict" in plan.conflicts
    proposed_task = next(
        node for node in plan.proposed.canvas["nodes"] if node["id"] == task_node["id"]
    )
    assert proposed_task["type"] == "text"


def test_nonpositive_custom_node_geometry_cannot_enter_next_baseline() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    canvas = json.loads(json.dumps(current.canvas))
    canvas["nodes"].append(
        {
            "id": "human-zero-width",
            "type": "group",
            "x": 9000,
            "y": 9000,
            "width": 0,
            "height": 10,
            "label": "Invalid group",
        }
    )

    plan = plan_analysis_update(
        current=AnalysisBundle(markdown=current.markdown, canvas=canvas),
        baseline=baseline,
        update=_focused_workflow(),
        note_stem="Update Test分析",
    )

    assert plan.status == "conflict"
    assert "canvas-integrity-conflict" in plan.conflicts
    assert plan.baseline is None


def test_corrupt_baseline_is_rejected_instead_of_silently_rebased() -> None:
    current, baseline = render_analysis_projection(_whole(), note_stem="Update Test分析")
    corrupt = baseline.model_copy(update={"markdown_sha256": "0" * 64})

    with pytest.raises(AnalysisUpdateError, match="baseline is corrupt"):
        plan_analysis_update(
            current=current,
            baseline=corrupt,
            update=_focused_workflow(),
            note_stem="Update Test分析",
        )
