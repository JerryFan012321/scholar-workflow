from __future__ import annotations

import json

import pytest

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    ProfileKind,
)
from scholar_workflow.analysis.rendering import AnalysisBundle, render_analysis


def _claim(
    role: AnalysisRole,
    claim_id: str,
    title: str,
    *,
    order: int | None = None,
    evidence_kind: EvidenceKind = EvidenceKind.AUTHOR_STATED,
) -> AnalysisClaim:
    evidence = (
        Evidence(kind=evidence_kind, anchor="Section 3.2")
        if evidence_kind is EvidenceKind.AUTHOR_STATED
        else Evidence(kind=evidence_kind, detail="The indexed text omits Figure 4")
    )
    return AnalysisClaim(
        claim_id=claim_id,
        role=role,
        title=title,
        body=f"Readable explanation for {title}.",
        evidence=evidence,
        order=order,
    )


def _whole_document() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:jepa",
        paper_title="JEPA Example",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            _claim(AnalysisRole.TASK, "task", "Prediction task"),
            _claim(AnalysisRole.INPUT, "input", "Context representation"),
            _claim(AnalysisRole.WORKFLOW, "encode", "Encode context", order=1),
            _claim(AnalysisRole.WORKFLOW, "predict", "Predict target", order=2),
            _claim(AnalysisRole.OUTPUT, "output", "Latent prediction"),
            _claim(
                AnalysisRole.BOUNDARY,
                "boundary",
                "Unavailable visual detail",
                evidence_kind=EvidenceKind.UNVERIFIABLE,
            ),
        ],
    )


def test_renderer_produces_human_readable_markdown_with_inline_evidence() -> None:
    document = _whole_document()
    bundle = render_analysis(document, note_stem="JEPA分析")

    assert "# JEPA Example：论文分析" in bundle.markdown
    assert "## 任务" in bundle.markdown
    assert "## 输入" in bundle.markdown
    assert "## 分步流程" in bundle.markdown
    assert "## 输出" in bundle.markdown
    assert "## 边界" in bundle.markdown
    assert "## Evidence" not in bundle.markdown
    assert "**Evidence：**" not in bundle.markdown
    assert "Readable explanation for Prediction task. 〔作者明确陈述 · Section 3.2〕" in bundle.markdown
    assert "^claim-task" in bundle.markdown

    report = validate_bundle(document, bundle, note_stem="JEPA分析")
    assert report.ok, report.model_dump(mode="json")


def test_canvas_is_readable_bounded_and_backlinks_each_claim() -> None:
    document = _whole_document()
    canvas = render_analysis(document, note_stem="JEPA分析").canvas

    assert len(canvas["nodes"]) <= 40
    claim_nodes = [node for node in canvas["nodes"] if "sw-analysis-claim" in node["text"]]
    assert len(claim_nodes) == len(document.claims)
    for node in canvas["nodes"]:
        assert node["type"] == "text"
        assert node["width"] >= 360
        assert node["height"] >= 140
    for node in claim_nodes:
        assert "[[JEPA分析#^claim-" in node["text"]
        assert "正文" in node["text"]
        assert "Evidence" not in node["text"]

    labels = "\n".join(node["text"] for node in canvas["nodes"])
    assert "对应挑战" not in labels
    assert "对应贡献" not in labels


def test_workflow_steps_form_one_ordered_flow() -> None:
    document = _whole_document()
    canvas = render_analysis(document, note_stem="JEPA分析").canvas
    by_marker = {node["text"]: node["id"] for node in canvas["nodes"]}
    encode_id = next(value for text, value in by_marker.items() if 'id="encode"' in text)
    predict_id = next(value for text, value in by_marker.items() if 'id="predict"' in text)

    assert any(
        edge["fromNode"] == encode_id and edge["toNode"] == predict_id
        for edge in canvas["edges"]
    )


def test_conformance_rejects_generated_geometry_but_allows_custom_evidence_note() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["nodes"][0]["width"] = 220
    canvas["nodes"][0]["height"] = 80
    canvas["nodes"].append(
        {
            "id": "evidence-node",
            "type": "text",
            "x": 5000,
            "y": 5000,
            "width": 220,
            "height": 80,
            "text": "Evidence\nSection 3.2",
        }
    )
    broken = AnalysisBundle(markdown=rendered.markdown + "\n## Evidence\nDetached\n", canvas=canvas)

    report = validate_bundle(document, broken, note_stem="JEPA分析")
    codes = {finding.code for finding in report.findings}
    assert not report.ok
    assert "separate-evidence-section" in codes
    assert "canvas-node-too-small" in codes
    assert "separate-evidence-node" not in codes


def test_conformance_rejects_claim_set_drift_and_broken_workflow_flow() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    encode = next(node for node in canvas["nodes"] if 'id="encode"' in node["text"])
    predict = next(node for node in canvas["nodes"] if 'id="predict"' in node["text"])
    canvas["edges"] = [
        edge
        for edge in canvas["edges"]
        if not (edge["fromNode"] == encode["id"] and edge["toNode"] == predict["id"])
    ]
    canvas["nodes"].append(
        {
            "id": "abcdef0123456789",
            "type": "text",
            "x": 5000,
            "y": 5000,
            "width": 420,
            "height": 160,
            "text": (
                "### Extra\nUnregistered claim 〔论文未报告〕\n"
                '<!-- sw-analysis-claim id="extra" role="output" -->'
            ),
        }
    )
    broken = AnalysisBundle(
        markdown=(
            rendered.markdown
            + '\n### Extra\nUnregistered claim 〔论文未报告〕 ^claim-extra\n'
            + '<!-- sw-analysis-claim id="extra" role="output" -->\n'
        ),
        canvas=canvas,
    )

    report = validate_bundle(document, broken, note_stem="JEPA分析")
    codes = {finding.code for finding in report.findings}
    assert "unexpected-markdown-claim" in codes
    assert "unexpected-canvas-claim" in codes
    assert "workflow-edge-missing" in codes


def test_conformance_rejects_marked_claim_content_drift() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    claim_node = next(node for node in canvas["nodes"] if 'id="task"' in node["text"])
    claim_node["text"] = claim_node["text"].replace(
        "Readable explanation for Prediction task.",
        "Unrelated replacement that kept the marker.",
    )
    broken = AnalysisBundle(
        markdown=rendered.markdown.replace(
            "Readable explanation for Prediction task.",
            "Unrelated replacement that kept the marker.",
        ),
        canvas=canvas,
    )

    report = validate_bundle(document, broken, note_stem="JEPA分析")
    codes = {finding.code for finding in report.findings}
    assert not report.ok
    assert "markdown-claim-content-mismatch" in codes
    assert "canvas-claim-content-mismatch" in codes


def test_conformance_rejects_paper_title_and_root_drift() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    root = next(node for node in canvas["nodes"] if node["text"].startswith("# 论文解析树"))
    root["text"] = root["text"].replace("JEPA Example", "Changed Paper")
    broken = AnalysisBundle(
        markdown=rendered.markdown.replace(
            "# JEPA Example：论文分析",
            "# Changed Paper：论文分析",
        ),
        canvas=canvas,
    )

    report = validate_bundle(document, broken, note_stem="JEPA分析")
    codes = {finding.code for finding in report.findings}
    assert "markdown-paper-title-mismatch" in codes
    assert "canvas-structure-content-mismatch" in codes


def test_conformance_requires_complete_root_role_claim_edges() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    broken = AnalysisBundle(
        markdown=rendered.markdown,
        canvas={"nodes": rendered.canvas["nodes"], "edges": []},
    )

    report = validate_bundle(document, broken, note_stem="JEPA分析")

    assert not report.ok
    assert "missing-generated-canvas-edge" in {
        finding.code for finding in report.findings
    }


def test_conformance_allows_user_owned_role_label_and_custom_note() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["nodes"].extend(
        [
            {
                "id": "redundant-role",
                "type": "text",
                "x": 6000,
                "y": 0,
                "width": 420,
                "height": 160,
                "text": "## 输入",
            },
            {
                "id": "human-note",
                "type": "text",
                "x": 6000,
                "y": 300,
                "width": 420,
                "height": 160,
                "text": "## 我的备注\n人工内容",
            },
        ]
    )

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    assert report.ok, report.model_dump(mode="json")


def test_conformance_requires_standard_type_for_user_owned_nodes() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["nodes"].append(
        {
            "id": "human-note-without-type",
            "x": 6000,
            "y": 300,
            "width": 420,
            "height": 160,
            "text": "## 我的备注\n人工内容",
        }
    )

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    assert not report.ok
    assert "invalid-canvas-node-type" in {
        finding.code for finding in report.findings
    }


def test_custom_nodes_do_not_consume_generated_budget_or_geometry_rules() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    for index in range(50):
        canvas["nodes"].append(
            {
                "id": f"custom-{index}",
                "type": "file",
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "file": f"assets/custom-{index}.png",
            }
        )
    canvas["nodes"].append(
        {
            "id": "custom-group",
            "type": "group",
            "x": -10,
            "y": -10,
            "width": 2,
            "height": 2,
            "label": "Human group",
        }
    )

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    assert len(canvas["nodes"]) > 40
    assert report.ok, report.model_dump(mode="json")


def test_conformance_rejects_nonpositive_custom_node_geometry() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
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

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    assert not report.ok
    assert "invalid-json-canvas-contract" in {
        finding.code for finding in report.findings
    }


def test_generated_node_budget_accepts_40_and_rejects_41() -> None:
    payload = _whole_document().model_dump()
    for index in range(28):
        payload["claims"].append(
            _claim(
                AnalysisRole.TASK,
                f"extra-task-{index}",
                f"Extra task {index}",
            ).model_dump()
        )

    exactly_forty = AnalysisDocument.model_validate(payload)
    rendered = render_analysis(exactly_forty, note_stem="JEPA分析")
    assert len(rendered.canvas["nodes"]) == 40
    assert validate_bundle(exactly_forty, rendered, note_stem="JEPA分析").ok

    payload["claims"].append(
        _claim(AnalysisRole.TASK, "extra-task-overflow", "Overflow task").model_dump()
    )
    with pytest.raises(ValueError, match="40 generated semantic Canvas nodes"):
        AnalysisDocument.model_validate(payload)


def test_conformance_rejects_dangling_user_edge() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["edges"].append(
        {
            "id": "custom-dangling",
            "fromNode": "missing-user-node",
            "toNode": canvas["nodes"][0]["id"],
        }
    )

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    assert not report.ok
    assert "dangling-canvas-edge" in {finding.code for finding in report.findings}


def test_conformance_reports_scalar_canvas_entries_without_crashing() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["nodes"].append("not-a-node")
    canvas["edges"].append(42)

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

    codes = {finding.code for finding in report.findings}
    assert not report.ok
    assert "invalid-canvas-node" in codes
    assert "invalid-canvas-edge" in codes


def test_focused_render_declares_scope_and_omits_unrequested_roles() -> None:
    document = AnalysisDocument(
        artifact_id="analysis:paper:jepa",
        paper_title="JEPA Example",
        profile=AnalysisProfile(kind=ProfileKind.FOCUSED, roles=[AnalysisRole.WORKFLOW]),
        claims=[_claim(AnalysisRole.WORKFLOW, "predict", "Predict target", order=1)],
    )
    bundle = render_analysis(document, note_stem="JEPA分析")

    assert "分析范围：局部（分步流程）" in bundle.markdown
    assert "## 分步流程" in bundle.markdown
    assert "## 任务" not in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="JEPA分析").ok


def test_non_workflow_layout_accumulates_dynamic_node_heights() -> None:
    document = _whole_document()
    payload = document.model_dump()
    payload["claims"].insert(
        1,
        _claim(AnalysisRole.TASK, "task-second", "Second task").model_dump(),
    )
    payload["claims"][0]["body"] = "Long readable paragraph. " * 120
    expanded = AnalysisDocument.model_validate(payload)

    bundle = render_analysis(expanded, note_stem="JEPA分析")
    report = validate_bundle(expanded, bundle, note_stem="JEPA分析")

    assert report.ok, report.model_dump(mode="json")
    task_nodes = [
        node for node in bundle.canvas["nodes"] if 'role="task"' in node["text"]
    ]
    first, second = sorted(task_nodes, key=lambda node: node["y"])
    assert second["y"] >= first["y"] + first["height"]
