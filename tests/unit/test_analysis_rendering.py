from __future__ import annotations

import json

import pytest

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisProfile,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    ProfileKind,
    VaultMarkdownSpan,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    canvas_node_id,
    point_anchor,
    render_analysis,
)


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
        schema_version=1,
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


def test_source_links_stay_inline_in_markdown_and_canvas_and_are_conformant() -> None:
    payload = _whole_document().model_dump(mode="json")
    payload["schema_version"] = 3
    pdf = ZoteroPdfSpan(
        library_type="personal",
        library_id="17685951",
        attachment_key="QR4ZU2S9",
        content_hash="md5:" + "a" * 32,
        page_index=3,
        page_label="iv",
        section="Figure 2",
    ).model_dump(mode="json")
    note = VaultMarkdownSpan(
        source_id="2e5d87d2-3ca9-4488-bcd4-ea6562350fa2",
        artifact_id="doc:world-models:overview",
        vault_path="世界模型 (World Models)/00-领域入口.md",
        block_id="scope",
    ).model_dump(mode="json")
    for claim in payload["claims"]:
        if claim["evidence"]["kind"] == "author_stated":
            claim["evidence"]["source_spans"] = [pdf]
    payload["claims"][0]["evidence"]["source_spans"].append(note)
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="JEPA分析")
    pdf_link = (
        "[原文·PDF 第 4 页](zotero://open-pdf/library/items/QR4ZU2S9?page=4)"
    )
    vault_link = "[[世界模型 (World Models)/00-领域入口#^scope|原文·段落]]"
    assert pdf_link in bundle.markdown
    assert vault_link in bundle.markdown
    task_node = next(node for node in bundle.canvas["nodes"] if 'id="task"' in node["text"])
    assert pdf_link in task_node["text"]
    assert vault_link in task_node["text"]
    assert "[[JEPA分析#^claim-task|正文]]" in task_node["text"]
    assert validate_bundle(document, bundle, note_stem="JEPA分析").ok

    broken_markdown = bundle.markdown.replace("?page=4", "?page=5", 1)
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=broken_markdown, canvas=bundle.canvas),
        note_stem="JEPA分析",
    )
    assert "markdown-claim-content-mismatch" in {finding.code for finding in report.findings}

    broken_canvas = json.loads(json.dumps(bundle.canvas))
    task_node = next(node for node in broken_canvas["nodes"] if 'id="task"' in node["text"])
    task_node["text"] = task_node["text"].replace("?page=4", "?page=5", 1)
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=bundle.markdown, canvas=broken_canvas),
        note_stem="JEPA分析",
    )
    assert "canvas-claim-content-mismatch" in {finding.code for finding in report.findings}


def test_annotation_deep_link_uses_verified_key_shape_without_fake_selection() -> None:
    evidence = Evidence(
        kind=EvidenceKind.AUTHOR_STATED,
        anchor="Table 4",
        source_spans=[
            ZoteroPdfSpan(
                library_type="group",
                library_id="12345",
                attachment_key="QR4ZU2S9",
                content_hash="md5:" + "a" * 32,
                page_index=4,
                annotation_key="ABCD1234",
            )
        ],
    )
    payload = _whole_document().model_dump(mode="json")
    payload["claims"][0]["evidence"] = evidence.model_dump(mode="json")
    document = AnalysisDocument.model_validate(payload)
    text = render_analysis(document, note_stem="JEPA分析").markdown
    assert (
        "[原批注·PDF 第 5 页]"
        "(zotero://open-pdf/groups/12345/items/QR4ZU2S9?page=5&annotation=ABCD1234)"
    ) in text


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


def test_canvas_summary_keeps_complete_markdown_and_short_canvas_projection() -> None:
    payload = _whole_document().model_dump(mode="json")
    complete_body = "Detailed explanation and qualification. " * 80
    payload["claims"][0]["body"] = complete_body
    payload["claims"][0]["canvas_summary"] = "Predict the target representation from context."
    document = AnalysisDocument.model_validate(payload)

    bundle = render_analysis(document, note_stem="JEPA分析")
    task_node = next(node for node in bundle.canvas["nodes"] if 'id="task"' in node["text"])

    assert complete_body in bundle.markdown
    assert "Predict the target representation from context." not in bundle.markdown
    assert "Predict the target representation from context." in task_node["text"]
    assert complete_body not in task_node["text"]
    assert "〔作者明确陈述 · Section 3.2〕" in task_node["text"]
    assert "[[JEPA分析#^claim-task|正文]]" in task_node["text"]
    assert validate_bundle(document, bundle, note_stem="JEPA分析").ok


def test_mixed_evidence_points_stay_inline_and_backlink_to_exact_markdown_blocks() -> None:
    payload = _whole_document().model_dump(mode="json")
    payload["schema_version"] = 2
    payload["claims"][0]["evidence"] = Evidence(
        kind=EvidenceKind.ANALYSIS_INFERENCE,
        detail="Combines the stated score with the protocol limitation.",
    ).model_dump(mode="json")
    payload["claims"][0]["points"] = [
        AnalysisPoint(
            point_id="reported-score",
            text="The model scores 39.7 mR@5.",
            evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 5"),
        ).model_dump(mode="json"),
        AnalysisPoint(
            point_id="interpretation",
            text="This score alone does not prove long-horizon dynamics.",
            evidence=Evidence(
                kind=EvidenceKind.ANALYSIS_INFERENCE,
                detail="The encoder-only ablation scores 39.1 in Table 20.",
            ),
        ).model_dump(mode="json"),
    ]
    document = AnalysisDocument.model_validate(payload)
    rendered = render_analysis(document, note_stem="JEPA分析")
    task_node = next(node for node in rendered.canvas["nodes"] if 'id="task"' in node["text"])

    assert len(rendered.canvas["nodes"]) == 1 + 5 + len(document.claims)
    assert "The model scores 39.7 mR@5. 〔作者明确陈述 · Table 5〕 ^point-4-task-reported-score" in rendered.markdown
    assert (
        "This score alone does not prove long-horizon dynamics. "
        "〔分析推断 · The encoder-only ablation scores 39.1 in Table 20.〕 "
        "^point-4-task-interpretation"
    ) in rendered.markdown
    assert "[[JEPA分析#^point-4-task-reported-score|正文]]" in task_node["text"]
    assert "[[JEPA分析#^point-4-task-interpretation|正文]]" in task_node["text"]
    assert "The model scores 39.7 mR@5. 〔作者明确陈述 · Table 5〕" in task_node["text"]
    assert "This score alone does not prove long-horizon dynamics. 〔分析推断 · " in task_node["text"]
    assert "## Evidence" not in rendered.markdown
    assert len([node for node in rendered.canvas["nodes"] if "Evidence" in node["text"]]) == 0
    assert validate_bundle(document, rendered, note_stem="JEPA分析").ok

    broken_markdown = rendered.markdown.replace(
        "The model scores 39.7 mR@5. 〔作者明确陈述 · Table 5〕",
        "The model scores 39.7 mR@5. 〔分析推断 · Table 5〕",
    )
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=broken_markdown, canvas=rendered.canvas),
        note_stem="JEPA分析",
    )
    assert "markdown-point-attribution-mismatch" in {finding.code for finding in report.findings}

    broken_canvas = json.loads(json.dumps(rendered.canvas))
    target_node = next(node for node in broken_canvas["nodes"] if 'id="task"' in node["text"])
    target_node["text"] = target_node["text"].replace(
        "[[JEPA分析#^point-4-task-reported-score|正文]]",
        "[[JEPA分析#^claim-task|正文]]",
    )
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=broken_canvas),
        note_stem="JEPA分析",
    )
    assert "missing-point-backlink" in {finding.code for finding in report.findings}


def test_point_anchor_namespace_cannot_collide_with_a_claim_anchor() -> None:
    point = AnalysisPoint(
        point_id="b",
        text="A separately attributable fact.",
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 1"),
    )
    document = AnalysisDocument(
        schema_version=2,
        artifact_id="analysis:paper:anchor-namespace",
        paper_title="Anchor namespace",
        profile=AnalysisProfile(kind=ProfileKind.FOCUSED, roles=[AnalysisRole.TASK]),
        claims=[
            AnalysisClaim(
                claim_id="a",
                role=AnalysisRole.TASK,
                title="First claim",
                body="First body.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 1"),
                points=[point],
            ),
            _claim(AnalysisRole.TASK, "a-point-b", "Second claim"),
        ],
    )
    anchor = point_anchor(document.claims[0], point)
    assert anchor == "point-1-a-b"
    assert anchor != "claim-a-point-b"
    assert anchor.replace("-", "").isalnum()
    bundle = render_analysis(document, note_stem="Anchor分析")
    assert f"^{anchor}" in bundle.markdown
    assert "^claim-a-point-b" in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="Anchor分析").ok


def test_point_anchor_length_prefix_prevents_hyphen_resegmentation_collision() -> None:
    first_point = AnalysisPoint(
        point_id="c",
        text="The first fact.",
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 1"),
    )
    second_point = AnalysisPoint(
        point_id="b-point-c",
        text="The second fact.",
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 2"),
    )
    document = AnalysisDocument(
        schema_version=2,
        artifact_id="analysis:paper:anchor-boundary",
        paper_title="Anchor boundary",
        profile=AnalysisProfile(kind=ProfileKind.FOCUSED, roles=[AnalysisRole.TASK]),
        claims=[
            AnalysisClaim(
                claim_id="a-point-b",
                role=AnalysisRole.TASK,
                title="First claim",
                body="First body.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 1"),
                points=[first_point],
            ),
            AnalysisClaim(
                claim_id="a",
                role=AnalysisRole.TASK,
                title="Second claim",
                body="Second body.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 2"),
                points=[second_point],
            ),
        ],
    )
    first_anchor = point_anchor(document.claims[0], first_point)
    second_anchor = point_anchor(document.claims[1], second_point)
    assert first_anchor == "point-9-a-point-b-c"
    assert second_anchor == "point-1-a-b-point-c"
    assert first_anchor != second_anchor
    bundle = render_analysis(document, note_stem="Anchor分析")
    assert bundle.markdown.split().count(f"^{first_anchor}") == 1
    assert bundle.markdown.split().count(f"^{second_anchor}") == 1
    assert validate_bundle(document, bundle, note_stem="Anchor分析").ok


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
            "id": canvas_node_id(document.artifact_id, "role/output/extra"),
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


def test_user_owned_canvas_node_cannot_be_claimed_by_embedded_marker() -> None:
    document = _whole_document()
    rendered = render_analysis(document, note_stem="JEPA分析")
    canvas = json.loads(json.dumps(rendered.canvas))
    canvas["nodes"].append(
        {
            "id": "human-marker-note",
            "type": "text",
            "x": 9000,
            "y": 9000,
            "width": 360,
            "height": 140,
            "text": (
                '<!-- sw-analysis-claim id="human-extra" role="workflow" -->\n'
                "对应挑战：这是用户自己的自由文本。"
            ),
        }
    )

    report = validate_bundle(
        document,
        AnalysisBundle(markdown=rendered.markdown, canvas=canvas),
        note_stem="JEPA分析",
    )

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
        schema_version=1,
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
