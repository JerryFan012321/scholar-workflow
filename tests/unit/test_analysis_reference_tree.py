"""The reference-image analysis tree is an editable, versioned projection."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from scholar_workflow.analysis.conformance import validate_bundle
from scholar_workflow.analysis.models import (
    AnalysisClaim,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisProfile,
    AnalysisReader,
    AnalysisRole,
    Evidence,
    EvidenceKind,
    ProfileKind,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.rendering import (
    AnalysisBundle,
    canvas_node_id,
    point_anchor,
    render_analysis,
)
from scholar_workflow.analysis.updates import (
    AnalysisUpdateError,
    plan_analysis_update,
    render_analysis_projection,
)


def _gap() -> Evidence:
    return Evidence(kind=EvidenceKind.NOT_APPLICABLE, detail="Layout-only fixture.")


def _source() -> Evidence:
    return Evidence(
        kind=EvidenceKind.AUTHOR_STATED,
        anchor="Abstract",
        source_spans=[
            ZoteroPdfSpan(
                library_type="personal",
                library_id="17685951",
                attachment_key="QR4ZU2S9",
                content_hash="md5:" + "a" * 32,
                page_index=3,
            )
        ],
    )


def _point(point_id: str, text: str, *, source: bool = False) -> AnalysisPoint:
    return AnalysisPoint(
        point_id=point_id,
        text=text,
        evidence=_source() if source else _gap(),
    )


def _claim(
    role: AnalysisRole,
    path: str,
    title: str,
    *points: AnalysisPoint,
    source: bool = False,
) -> AnalysisClaim:
    evidence = _source() if source else _gap()
    return AnalysisClaim(
        claim_id=path.replace("/", "-").replace("_", "-"),
        role=role,
        outline_path=path,
        title=title,
        body=f"Readable account of {title}.",
        evidence=evidence,
        points=list(points),
    )


def reference_document() -> AnalysisDocument:
    a = AnalysisRole.ABSTRACT
    i = AnalysisRole.INTRODUCTION
    m = AnalysisRole.METHOD
    l = AnalysisRole.LIMITATION
    return AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:podia-3d",
        paper_title="PODIA-3D",
        language="en",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        claims=[
            _claim(a, "abstract/task", "Text-guided domain adaptation for 3D GANs", source=True),
            _claim(
                a,
                "abstract/previous_methods/datid-3d",
                "DATID-3D",
                _point("challenge-1", "Shape–pose trade-off.", source=True),
                _point("challenge-2", "Pose bias."),
                _point("challenge-3", "Instance bias."),
            ),
            _claim(
                a,
                "abstract/insight",
                "Pose-preserved domain adaptation",
                _point("motivation", "Keep pose information."),
                _point("advantage", "Permit a larger domain change."),
            ),
            _claim(
                a,
                "abstract/contributions/pose-preservation",
                "Pose-preserved diffusion model",
                _point("summary", "Preserve pose at high noise."),
                _point("advantage", "Support substantial domain changes."),
            ),
            _claim(a, "abstract/experiment", "Reported evaluation"),
            _claim(i, "introduction/task_application", "Task and application"),
            _claim(
                i,
                "introduction/previous_methods/pose-bias",
                "Pose-bias challenge",
                _point("previous-method", "Diffusion translation."),
                _point("limitation", "Pose may change."),
                _point("technical-reason", "Bias in the diffusion prior."),
            ),
            _claim(i, "introduction/our_pipeline/insight", "Key innovation"),
            _claim(
                i,
                "introduction/our_pipeline/contributions/sampling",
                "Specialized-to-general sampling",
                _point("purpose", "Address detail bias."),
                _point("how", "Sample from specialized to general."),
                _point("advantage", "Improve generated details."),
            ),
            _claim(m, "method/overview", "Method overview"),
            _claim(
                m,
                "method/modules/sampling",
                "Pipeline module 1",
                _point("motivation", "Details need refinement."),
                _point("method", "Apply specialized-to-general sampling."),
                _point("why-it-works", "Preserve structural information."),
                _point("technical-advantage", "Improve details."),
            ),
            _claim(l, "limitation/explanation", "Reasoned limitations"),
        ],
    )


def full_reference_document() -> AnalysisDocument:
    """Exercise all three repeated contribution/challenge slots from the reference image."""
    base = reference_document()
    existing = [
        claim
        for claim in base.claims
        if claim.outline_path not in {
            "abstract/experiment",
            "method/overview",
            "limitation/explanation",
        }
    ]
    extras = [
        _claim(
            AnalysisRole.ABSTRACT,
            "abstract/contributions/sampling",
            "Specialized-to-general sampling",
            _point("summary", "Sample from specialized to general."),
            _point("advantage", "Improve generated details."),
        ),
        _claim(
            AnalysisRole.ABSTRACT,
            "abstract/contributions/debiasing",
            "Text-guided debiasing",
            _point("summary", "Debias generated target-domain instances."),
            _point("advantage", "Improve intra-domain diversity."),
        ),
        _claim(
            AnalysisRole.INTRODUCTION,
            "introduction/previous_methods/structure",
            "Generated-image structure",
            _point("previous-method", "Diffusion-generated images."),
            _point("limitation", "Image structure may degrade."),
            _point("technical-reason", "Pose bias in the diffusion model."),
        ),
        _claim(
            AnalysisRole.INTRODUCTION,
            "introduction/previous_methods/instance",
            "Instance bias",
            _point("previous-method", "Target-domain diffusion translation."),
            _point("limitation", "Too few distinct instances."),
            _point("technical-reason", "Instance bias restricts diversity."),
        ),
        _claim(
            AnalysisRole.INTRODUCTION,
            "introduction/our_pipeline/contributions/pose-preservation",
            "Pose-preserved adaptation",
            _point("purpose", "Preserve pose under substantial domain changes."),
            _point("how", "Use pose-preserved target images."),
            _point("advantage", "Keep high-level structure."),
        ),
        _claim(
            AnalysisRole.INTRODUCTION,
            "introduction/our_pipeline/contributions/debiasing",
            "Text-guided debiasing",
            _point("purpose", "Counter instance bias."),
            _point("how", "Apply text-guided debiasing."),
            _point("advantage", "Increase target-domain diversity."),
        ),
    ]
    return AnalysisDocument(
        schema_version=4,
        artifact_id=base.artifact_id,
        paper_title=base.paper_title,
        language=base.language,
        profile=base.profile,
        claims=[*existing, *extras],
    )


def test_repeated_experiments_and_limitations_keep_point_sources_inline() -> None:
    base = reference_document()
    document = AnalysisDocument(
        schema_version=4,
        artifact_id=base.artifact_id,
        paper_title=base.paper_title,
        language=base.language,
        profile=base.profile,
        claims=[
            *base.claims,
            _claim(
                AnalysisRole.ABSTRACT,
                "abstract/experiment/robot-control",
                "Robot-control result",
                _point("finding-1", "Measured control success.", source=True),
            ),
            _claim(
                AnalysisRole.LIMITATION,
                "limitation/explanation/camera",
                "Camera-view limitation",
                _point("reason-1", "View changes affect control.", source=True),
            ),
        ],
    )
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    assert "**Finding 1.** Measured control success." in bundle.markdown
    assert "**Reason 1.** View changes affect control." in bundle.markdown
    assert "[Source · PDF page 4]" in bundle.markdown
    assert any("Finding 1:" in node["text"] for node in bundle.canvas["nodes"])
    assert any("Reason 1:" in node["text"] for node in bundle.canvas["nodes"])
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_renders_full_four_branch_framework_with_editable_nodes() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    for heading in ("Abstract", "Introduction", "Method", "Limitation"):
        assert f"## {heading}" in bundle.markdown
        assert any(heading == node["text"].strip("# ").strip() for node in bundle.canvas["nodes"])
    for label in (
        "Task",
        "Technical challenge for previous methods",
        "Key insight / motivation",
        "Technical contributions",
        "Experiment",
        "Task and application",
        "Previous method",
        "Technical reason",
        "Our pipeline",
        "Overview",
        "Pipeline module 1",
        "Why it works",
        "Technical advantage",
    ):
        assert label in bundle.markdown or any(
            label in node["text"] for node in bundle.canvas["nodes"]
        )
    assert "## 分步流程" not in bundle.markdown
    assert "## Evidence" not in bundle.markdown
    assert "## 证据" not in bundle.markdown
    assert "[Source · PDF page 4]" in bundle.markdown
    assert "[[PODIA-3D Analysis#^claim-" in str(bundle.canvas)
    assert all(node["type"] == "text" for node in bundle.canvas["nodes"])
    nodes = {node["id"]: node for node in bundle.canvas["nodes"]}
    for claim in document.claims:
        if not claim.points:
            continue
        detail_id = canvas_node_id(
            document.artifact_id, f"role/{claim.role.value}/{claim.claim_id}/details"
        )
        detail = nodes[detail_id]
        for point in claim.points:
            assert f"#^{point_anchor(claim, point)}|Analysis" in detail["text"]
            assert point.text in detail["text"]
    source_detail_id = canvas_node_id(
        document.artifact_id,
        "role/abstract/abstract-previous-methods-datid-3d/details",
    )
    assert "[PDF p.4]" in nodes[source_detail_id]["text"]
    assert "Layout-only fixture." not in nodes[source_detail_id]["text"]
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_keeps_machine_claim_markers_out_of_readable_artifacts() -> None:
    document = reference_document()
    bundle, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    assert "sw-analysis-claim" not in bundle.markdown
    assert all("sw-analysis-claim" not in node["text"] for node in bundle.canvas["nodes"])
    for claim in document.claims:
        expected_id = canvas_node_id(
            document.artifact_id, f"role/{claim.role.value}/{claim.claim_id}"
        )
        assert baseline.claims[claim.claim_id].canvas_node_id == expected_id
        assert bundle.markdown.count(f"^claim-{claim.claim_id}") == 1
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_rejects_unexpected_or_misplaced_claim_anchors() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    unexpected = AnalysisBundle(
        markdown=bundle.markdown + "\nUnowned statement. ^claim-unexpected\n",
        canvas=bundle.canvas,
    )
    report = validate_bundle(document, unexpected, note_stem="PODIA-3D Analysis")
    assert not report.ok
    assert any(f.code == "unexpected-markdown-claim" for f in report.findings)

    misplaced = AnalysisBundle(
        markdown=bundle.markdown.replace(
            "^claim-abstract-task", "^claim-temporary-swap", 1
        ).replace(
            "^claim-abstract-insight", "^claim-abstract-task", 1
        ).replace(
            "^claim-temporary-swap", "^claim-abstract-insight", 1
        ),
        canvas=bundle.canvas,
    )
    report = validate_bundle(document, misplaced, note_stem="PODIA-3D Analysis")
    assert not report.ok
    assert any(
        f.code in {"duplicate-markdown-claim", "markdown-claim-placement-mismatch"}
        for f in report.findings
    )


def test_reference_tree_can_project_pdf_pages_to_obsidian_zotflow_reader() -> None:
    payload = reference_document().model_dump(mode="json")
    payload["reader"] = {"kind": "zotflow_library", "vault_id": "0123456789abcdef"}
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    reader_url = (
        "obsidian://zotflow?vault=0123456789abcdef&type=open-attachment"
        "&libraryID=17685951&key=QR4ZU2S9"
        "&navigation=%7B%22pageIndex%22%3A3%7D"
    )
    assert reader_url in bundle.markdown
    assert any(reader_url in node["text"] for node in bundle.canvas["nodes"])
    assert "zotero://open-pdf" not in bundle.markdown
    assert all("zotero://open-pdf" not in node["text"] for node in bundle.canvas["nodes"])
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_zotflow_page_link_does_not_claim_to_open_specific_annotation() -> None:
    from scholar_workflow.analysis.reference_rendering import reference_source_link

    span = ZoteroPdfSpan(
        library_type="personal",
        library_id="17685951",
        attachment_key="QR4ZU2S9",
        content_hash="md5:" + "a" * 32,
        page_index=3,
        annotation_key="AB12CD34",
    )
    link = reference_source_link(
        span, "en", reader=AnalysisReader(kind="zotflow_library", vault_id="0123456789abcdef")
    )
    assert link.startswith("[Source · PDF page 4](obsidian://zotflow?")
    assert "annotation=" not in link


def test_reference_tree_reader_requires_explicit_vault_and_v4() -> None:
    payload = reference_document().model_dump(mode="json")
    payload["reader"] = {"kind": "zotflow_library"}
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    payload["reader"] = {"kind": "zotflow_library", "vault_name": "../other"}
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)


def test_reference_tree_text_nodes_leave_clickable_line_of_vertical_space() -> None:
    from scholar_workflow.analysis.reference_rendering import _visible_height

    document = reference_document()
    nodes = render_analysis(document, note_stem="PODIA-3D Analysis").canvas["nodes"]
    for node in nodes:
        text = node["text"]
        if "obsidian://" not in text and "zotero://" not in text:
            continue
        assert node["height"] >= _visible_height(text, minimum=0, width=node["width"])
    # A mixed CJK line must count more wrap units than an ASCII line of equal length.
    assert _visible_height("世界模型" * 20, minimum=0, width=220) > _visible_height(
        "WorldModel" * 8, minimum=0, width=220
    )


def test_reference_tree_conformance_rejects_clipped_clickable_text() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    clipped = deepcopy(bundle.canvas)
    source_node = next(node for node in clipped["nodes"] if "zotero://" in node["text"])
    source_node["height"] = 30
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=bundle.markdown, canvas=clipped),
        note_stem="PODIA-3D Analysis",
    )
    assert not report.ok
    assert any(f.code == "canvas-text-click-space" for f in report.findings)


def test_reference_tree_update_restores_click_space_after_manual_resize() -> None:
    from scholar_workflow.analysis.reference_rendering import _visible_height

    document = reference_document()
    current, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    resized = deepcopy(current.canvas)
    source_node = next(node for node in resized["nodes"] if "zotero://" in node["text"])
    source_node["height"] = 30
    plan = plan_analysis_update(
        current=AnalysisBundle(markdown=current.markdown, canvas=resized),
        baseline=baseline,
        update=document,
        note_stem="PODIA-3D Analysis",
    )
    assert plan.status == "ready", plan.conflicts
    restored = next(node for node in plan.proposed.canvas["nodes"] if node["id"] == source_node["id"])
    assert restored["height"] >= _visible_height(
        restored["text"], minimum=0, width=restored["width"]
    )


def _canvas_size(document: AnalysisDocument) -> tuple[int, int]:
    nodes = render_analysis(document, note_stem="PODIA-3D Analysis").canvas["nodes"]
    left = min(node["x"] for node in nodes)
    top = min(node["y"] for node in nodes)
    right = max(node["x"] + node["width"] for node in nodes)
    bottom = max(node["y"] + node["height"] for node in nodes)
    return right - left, bottom - top


def test_reference_tree_layout_avoids_one_axis_sprawl_at_semantic_limit() -> None:
    base = reference_document()
    module = next(claim for claim in base.claims if claim.outline_path == "method/modules/sampling")
    extras = [
        module.model_copy(
            update={
                "claim_id": f"module-extra-{index}",
                "outline_path": f"method/modules/module-{index}",
                "title": f"Pipeline module {index}",
            }
        )
        for index in (2, 3)
    ]
    extras.append(
        _claim(AnalysisRole.ABSTRACT, "abstract/contributions/additional", "Additional contribution")
    )
    dense = AnalysisDocument(
        schema_version=4,
        artifact_id=base.artifact_id,
        paper_title=base.paper_title,
        language="en",
        profile=base.profile,
        claims=[*base.claims, *extras],
    )
    assert len(dense.claims) + sum(len(claim.points) for claim in dense.claims) == 40
    for document in (base, dense):
        width, height = _canvas_size(document)
        assert max(width / height, height / width) <= 1.7
        bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
        assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_can_fit_all_three_original_repeat_groups() -> None:
    document = full_reference_document()
    assert len(document.claims) + sum(len(claim.points) for claim in document.claims) > 40
    assert len(document.claims) + sum(bool(claim.points) for claim in document.claims) <= 40
    width, height = _canvas_size(document)
    assert max(width / height, height / width) <= 1.7
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_nested_pipeline_headings_and_no_invented_heading() -> None:
    document = full_reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    assert "#### Key innovation / insight\n\n##### Key innovation" in bundle.markdown
    assert "#### Technical contributions\n\n##### Specialized-to-general sampling" in bundle.markdown
    broken = AnalysisBundle(
        markdown=bundle.markdown.replace("## Method\n", "## Method\n\n### Corresponding Challenge\n", 1),
        canvas=bundle.canvas,
    )
    report = validate_bundle(document, broken, note_stem="PODIA-3D Analysis")
    assert not report.ok
    assert any(f.code == "framework-heading-order-mismatch" for f in report.findings)


def test_reference_tree_requires_explicit_version_and_compact_canvas_text() -> None:
    payload = reference_document().model_dump(mode="json")
    payload.pop("schema_version")
    with pytest.raises(ValidationError, match="schema_version"):
        AnalysisDocument.model_validate(payload)

    payload = reference_document().model_dump(mode="json")
    payload["claims"][0]["body"] = "Long account. " * 20
    with pytest.raises(ValidationError, match="canvas_summary is required"):
        AnalysisDocument.model_validate(payload)
    payload["claims"][0]["canvas_summary"] = "Faithful short account."
    assert AnalysisDocument.model_validate(payload)

    payload = reference_document().model_dump(mode="json")
    payload["claims"][1]["points"].append(
        _point("challenge-4", "An invented fourth challenge.").model_dump(mode="json")
    )
    with pytest.raises(ValidationError, match="point_id is outside"):
        AnalysisDocument.model_validate(payload)

    payload = reference_document().model_dump(mode="json")
    payload["claims"][0]["body"] = "Explanation.\n### Corresponding Challenge"
    payload["claims"][0]["canvas_summary"] = "Short explanation."
    with pytest.raises(ValidationError, match="cannot inject framework headings"):
        AnalysisDocument.model_validate(payload)


def test_reference_tree_rejects_a_single_axis_generated_sprawl() -> None:
    base = reference_document()
    claims = [
        _claim(
            AnalysisRole.ABSTRACT,
            f"abstract/contributions/contribution-{index}",
            f"Contribution {index}",
        )
        for index in range(1, 41)
    ]
    document = AnalysisDocument(
        schema_version=4,
        artifact_id=base.artifact_id,
        paper_title=base.paper_title,
        language="en",
        profile=base.profile,
        claims=claims,
    )
    with pytest.raises(ValueError, match="too elongated"):
        render_analysis(document, note_stem="PODIA-3D Analysis")


@pytest.mark.parametrize("note_stem", ["Analysis|broken", "Analysis\ncontinued"])
def test_reference_tree_rejects_broken_backlink_filename(note_stem: str) -> None:
    with pytest.raises(ValueError, match="plain filename stem"):
        render_analysis(reference_document(), note_stem=note_stem)


def test_reference_tree_conformance_rejects_missing_claim_and_broken_edge() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    broken = deepcopy(bundle.canvas)
    claim_id = canvas_node_id(document.artifact_id, "role/abstract/abstract-task")
    claim = next(node for node in broken["nodes"] if node["id"] == claim_id)
    claim["text"] = claim["text"].replace("Text-guided", "Unrelated")
    broken["edges"][0]["toNode"] = "missing-node"
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=bundle.markdown, canvas=broken),
        note_stem="PODIA-3D Analysis",
    )
    codes = {finding.code for finding in report.findings}
    assert "canvas-claim-content-mismatch" in codes
    assert "dangling-canvas-edge" in codes


def test_reference_tree_rejects_missing_point_backlink_inside_detail_node() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    broken = deepcopy(bundle.canvas)
    detail_id = canvas_node_id(
        document.artifact_id,
        "role/abstract/abstract-previous-methods-datid-3d/details",
    )
    detail = next(node for node in broken["nodes"] if node["id"] == detail_id)
    detail["text"] = detail["text"].replace("#^point-", "#^missing-", 1)
    report = validate_bundle(
        document,
        AnalysisBundle(markdown=bundle.markdown, canvas=broken),
        note_stem="PODIA-3D Analysis",
    )
    assert not report.ok
    assert any(
        finding.code in {"canvas-point-content-mismatch", "canvas-point-attribution-mismatch"}
        for finding in report.findings
    )


def test_reference_tree_rejects_missing_empty_framework_slot() -> None:
    document = reference_document()
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    broken = AnalysisBundle(
        markdown=bundle.markdown.replace("### Experiment\n", "", 1),
        canvas=bundle.canvas,
    )
    report = validate_bundle(document, broken, note_stem="PODIA-3D Analysis")
    assert not report.ok
    assert any(finding.code == "missing-framework-heading" for finding in report.findings)


def test_reference_tree_keeps_empty_source_slots_without_fabricating_claims() -> None:
    payload = reference_document().model_dump(mode="json")
    payload["claims"] = [
        claim
        for claim in payload["claims"]
        if claim["outline_path"] not in {
            "abstract/experiment",
            "method/overview",
            "limitation/explanation",
        }
    ]
    document = AnalysisDocument.model_validate(payload)
    bundle = render_analysis(document, note_stem="PODIA-3D Analysis")
    for heading in ("### Experiment", "### Overview", "## Limitation", "### Reasoned limitations"):
        assert heading in bundle.markdown
    assert "Reported evaluation" not in bundle.markdown
    assert "Reasoned account of Reasoned limitations" not in bundle.markdown
    assert validate_bundle(document, bundle, note_stem="PODIA-3D Analysis").ok


def test_reference_tree_layout_and_custom_nodes_survive_focused_update() -> None:
    document = reference_document()
    current, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    updated_canvas = deepcopy(current.canvas)
    root = updated_canvas["nodes"][0]
    root["x"] += 20
    updated_canvas["nodes"].append(
        {"id": "human-label", "type": "text", "x": 3000, "y": 0, "width": 300, "height": 80, "text": "My note"}
    )
    updated_canvas["metadata"] = {"version": "1.0-1.0", "frontmatter": {}}
    introduction = [claim for claim in document.claims if claim.role is AnalysisRole.INTRODUCTION]
    introduction[0] = introduction[0].model_copy(
        update={"body": "A revised human-readable task and application."}
    )
    focused = AnalysisDocument(
        schema_version=4,
        artifact_id=document.artifact_id,
        paper_title=document.paper_title,
        language="en",
        profile=AnalysisProfile(
            kind=ProfileKind.FOCUSED,
            framework="reference_tree",
            roles=[AnalysisRole.INTRODUCTION],
        ),
        claims=introduction,
    )
    plan = plan_analysis_update(
        current=AnalysisBundle(markdown=current.markdown, canvas=updated_canvas),
        baseline=baseline,
        update=focused,
        note_stem="PODIA-3D Analysis",
    )
    assert plan.status == "ready", plan.conflicts
    assert any(node["id"] == "human-label" for node in plan.proposed.canvas["nodes"])
    assert plan.proposed.canvas["nodes"][0]["x"] == root["x"]
    assert plan.proposed.canvas["metadata"] == updated_canvas["metadata"]


@pytest.mark.parametrize("whole_update", [False, True])
def test_reference_tree_updates_keep_verified_zotflow_reader(whole_update: bool) -> None:
    document = reference_document().model_copy(
        update={"reader": AnalysisReader(kind="zotflow_library", vault_name="test")}
    )
    current, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    if whole_update:
        update = document.model_copy(update={"reader": None})
    else:
        intro = [claim for claim in document.claims if claim.role is AnalysisRole.INTRODUCTION]
        update = AnalysisDocument(
            schema_version=4,
            artifact_id=document.artifact_id,
            paper_title=document.paper_title,
            language="en",
            profile=AnalysisProfile(
                kind=ProfileKind.FOCUSED,
                framework="reference_tree",
                roles=[AnalysisRole.INTRODUCTION],
            ),
            claims=intro,
        )
    plan = plan_analysis_update(
        current=current,
        baseline=baseline,
        update=update,
        note_stem="PODIA-3D Analysis",
    )
    assert plan.status == "ready", plan.conflicts
    assert plan.document.reader == document.reader
    assert "obsidian://zotflow" in plan.proposed.markdown
    assert "zotero://open-pdf" not in plan.proposed.markdown


def test_reference_tree_update_cannot_silently_change_reader() -> None:
    document = reference_document().model_copy(
        update={"reader": AnalysisReader(kind="zotflow_library", vault_name="test")}
    )
    current, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    update = document.model_copy(
        update={"reader": AnalysisReader(kind="zotero_native")}
    )
    with pytest.raises(AnalysisUpdateError, match="reader changes require"):
        plan_analysis_update(
            current=current,
            baseline=baseline,
            update=update,
            note_stem="PODIA-3D Analysis",
        )


def test_focused_update_preserves_empty_whole_branches_and_submitted_order() -> None:
    base = full_reference_document()
    base = AnalysisDocument.model_validate(
        {
            **base.model_dump(mode="json"),
            "claims": [
                claim.model_dump(mode="json")
                for claim in base.claims
                if claim.role is not AnalysisRole.LIMITATION
            ],
        }
    )
    current, baseline = render_analysis_projection(base, note_stem="PODIA-3D Analysis")
    intro = [claim for claim in base.claims if claim.role is AnalysisRole.INTRODUCTION]
    contributors = [
        claim for claim in intro
        if (claim.outline_path or "").startswith("introduction/our_pipeline/contributions/")
    ]
    update = AnalysisDocument(
        schema_version=4,
        artifact_id=base.artifact_id,
        paper_title=base.paper_title,
        language="en",
        profile=AnalysisProfile(
            kind=ProfileKind.FOCUSED,
            framework="reference_tree",
            roles=[AnalysisRole.INTRODUCTION],
        ),
        claims=[
            claim for claim in intro if claim not in contributors
        ] + list(reversed(contributors)),
    )
    plan = plan_analysis_update(
        current=current,
        baseline=baseline,
        update=update,
        note_stem="PODIA-3D Analysis",
    )
    assert plan.status == "ready", plan.conflicts
    assert plan.document.profile.kind is ProfileKind.WHOLE
    assert "## Limitation" in plan.proposed.markdown
    actual = [
        claim.claim_id for claim in plan.document.claims
        if (claim.outline_path or "").startswith("introduction/our_pipeline/contributions/")
    ]
    assert actual == [claim.claim_id for claim in reversed(contributors)]


def test_reference_tree_focused_update_cannot_drop_an_existing_outline_path() -> None:
    document = reference_document()
    current, baseline = render_analysis_projection(document, note_stem="PODIA-3D Analysis")
    first_intro = next(claim for claim in document.claims if claim.role is AnalysisRole.INTRODUCTION)
    incomplete = AnalysisDocument(
        schema_version=4,
        artifact_id=document.artifact_id,
        paper_title=document.paper_title,
        language="en",
        profile=AnalysisProfile(
            kind=ProfileKind.FOCUSED,
            framework="reference_tree",
            roles=[AnalysisRole.INTRODUCTION],
        ),
        claims=[first_intro],
    )
    with pytest.raises(AnalysisUpdateError, match="every existing outline path"):
        plan_analysis_update(
            current=current,
            baseline=baseline,
            update=incomplete,
            note_stem="PODIA-3D Analysis",
        )
