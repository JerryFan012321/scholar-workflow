from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.models import (
    AnalysisAuditReport,
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisClaim,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisProfile,
    AnalysisRole,
    ConformanceReport,
    Evidence,
    EvidenceKind,
    ProfileKind,
    VaultMarkdownSpan,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.updates import render_analysis_projection

ROOT = Path(__file__).resolve().parents[2]


def _claim(role: AnalysisRole, claim_id: str, *, order: int | None = None) -> AnalysisClaim:
    return AnalysisClaim(
        claim_id=claim_id,
        role=role,
        title=f"{role.value} claim",
        body="A human-readable explanation.",
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 2"),
        order=order,
    )


def _whole_document() -> AnalysisDocument:
    return AnalysisDocument(
        schema_version=1,
        artifact_id="analysis:paper:example",
        paper_title="Example Paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            _claim(AnalysisRole.TASK, "task"),
            _claim(AnalysisRole.INPUT, "input"),
            _claim(AnalysisRole.WORKFLOW, "step-1", order=1),
            _claim(AnalysisRole.OUTPUT, "output"),
            _claim(AnalysisRole.BOUNDARY, "boundary"),
        ],
    )


def test_whole_profile_requires_all_five_observable_roles() -> None:
    payload = _whole_document().model_dump()
    payload["claims"] = payload["claims"][:-1]

    with pytest.raises(ValidationError, match="whole profile must cover"):
        AnalysisDocument.model_validate(payload)


def test_focused_profile_declares_and_limits_its_role_subset() -> None:
    document = AnalysisDocument(
        schema_version=1,
        artifact_id="analysis:paper:focused",
        paper_title="Focused Paper",
        profile=AnalysisProfile(
            kind=ProfileKind.FOCUSED,
            roles=[AnalysisRole.WORKFLOW, AnalysisRole.OUTPUT],
        ),
        claims=[
            _claim(AnalysisRole.WORKFLOW, "step-1", order=1),
            _claim(AnalysisRole.OUTPUT, "result"),
        ],
    )
    assert document.profile.roles == [AnalysisRole.WORKFLOW, AnalysisRole.OUTPUT]

    payload = document.model_dump()
    payload["claims"].append(_claim(AnalysisRole.TASK, "extra").model_dump())
    with pytest.raises(ValidationError, match="outside the focused profile"):
        AnalysisDocument.model_validate(payload)


def test_ir_rejects_invented_workflow_nodes_and_more_than_40_semantic_nodes() -> None:
    workflow_payload = _claim(AnalysisRole.WORKFLOW, "challenge", order=1).model_dump()
    workflow_payload["title"] = "对应挑战"
    with pytest.raises(ValidationError, match="cannot invent challenge/contribution"):
        AnalysisClaim.model_validate(workflow_payload)

    payload = _whole_document().model_dump()
    payload["claims"] = [
        _claim(AnalysisRole.TASK, f"task-{index}").model_dump() for index in range(34)
    ] + [
        _claim(AnalysisRole.INPUT, "input").model_dump(),
        _claim(AnalysisRole.WORKFLOW, "workflow", order=1).model_dump(),
        _claim(AnalysisRole.OUTPUT, "output").model_dump(),
        _claim(AnalysisRole.BOUNDARY, "boundary").model_dump(),
    ]
    with pytest.raises(ValidationError, match="exceeds 40 generated semantic"):
        AnalysisDocument.model_validate(payload)


def test_checked_in_analysis_ir_schema_accepts_runtime_document() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(_whole_document().model_dump(mode="json"), schema)


def test_v3_source_spans_require_traceable_support_without_breaking_legacy_ir() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    payload = _whole_document().model_dump(mode="json")
    payload["schema_version"] = 3
    with pytest.raises(ValidationError, match="source span"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)

    pdf = ZoteroPdfSpan(
        library_type="personal",
        library_id="17685951",
        attachment_key="QR4ZU2S9",
        content_hash="md5:" + "a" * 32,
        page_index=3,
        page_label="4",
        section="Figure 2",
    )
    for claim in payload["claims"]:
        if claim["evidence"]["kind"] in {"author_stated", "analysis_inference"}:
            claim["evidence"]["source_spans"] = [pdf.model_dump(mode="json")]
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), schema)
    assert document.schema_version == 3

    payload["claims"][0]["points"] = [
        AnalysisPoint(
            point_id="unsupported-point",
            text="A source-backed statement.",
            evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Figure 2"),
        ).model_dump(mode="json")
    ]
    with pytest.raises(ValidationError, match="source span"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)

    legacy = _whole_document()
    assert legacy.schema_version == 1
    jsonschema.validate(legacy.model_dump(mode="json"), schema)


def test_source_span_identity_and_vault_block_path_are_strict() -> None:
    pdf = ZoteroPdfSpan(
        library_type="group",
        library_id="12345",
        attachment_key="QR4ZU2S9",
        content_hash="sha256:" + "b" * 64,
        page_index=0,
        annotation_key="ABCD1234",
    )
    assert pdf.page_index == 0
    with pytest.raises(ValidationError):
        ZoteroPdfSpan.model_validate({**pdf.model_dump(), "attachment_key": "../../x"})
    with pytest.raises(ValidationError):
        ZoteroPdfSpan.model_validate({**pdf.model_dump(), "content_hash": "unknown"})
    with pytest.raises(ValidationError):
        ZoteroPdfSpan.model_validate({**pdf.model_dump(), "library_id": "not-a-group"})

    note = VaultMarkdownSpan(
        source_id="2e5d87d2-3ca9-4488-bcd4-ea6562350fa2",
        artifact_id="doc:world-models:overview",
        vault_path="世界模型 (World Models)/00-领域入口.md",
        block_id="claim-scope",
    )
    assert note.block_id == "claim-scope"
    with pytest.raises(ValidationError):
        VaultMarkdownSpan.model_validate({**note.model_dump(), "vault_path": "../other.md"})
    with pytest.raises(ValidationError):
        VaultMarkdownSpan.model_validate({**note.model_dump(), "vault_path": "/tmp/other.md"})


def test_canvas_summary_contract_is_optional_bounded_and_nonblank() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    payload = _whole_document().model_dump(mode="json")
    payload["claims"][0]["canvas_summary"] = "A concise projection."
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), schema)

    payload["claims"][0]["canvas_summary"] = " "
    with pytest.raises(ValidationError, match="canvas_summary cannot be blank"):
        AnalysisDocument.model_validate(payload)

    payload["claims"][0]["canvas_summary"] = "x" * 401
    with pytest.raises(ValidationError, match="at most 400"):
        AnalysisDocument.model_validate(payload)


def test_v2_ir_supports_sixteen_mixed_evidence_claims_without_extra_canvas_nodes() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    mixed_claims = [
        AnalysisClaim(
            claim_id=f"mixed-{index:02d}",
            role=AnalysisRole.TASK,
            title=f"Mixed claim {index}",
            body="The combined conclusion is an analysis inference.",
            evidence=Evidence(
                kind=EvidenceKind.ANALYSIS_INFERENCE,
                detail="Inferred from the cited result and its limitation.",
            ),
            points=[
                AnalysisPoint(
                    point_id="reported",
                    text=f"The paper reports result {index}.",
                    evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 4"),
                ),
                AnalysisPoint(
                    point_id="inferred",
                    text=f"Result {index} has a narrower interpretation.",
                    evidence=Evidence(
                        kind=EvidenceKind.ANALYSIS_INFERENCE,
                        detail="The reported protocol does not isolate this cause.",
                    ),
                ),
            ],
        )
        for index in range(16)
    ]
    document = AnalysisDocument(
        schema_version=2,
        artifact_id="analysis:paper:mixed-sixteen",
        paper_title="Mixed evidence example",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            *mixed_claims,
            _claim(AnalysisRole.INPUT, "input"),
            _claim(AnalysisRole.WORKFLOW, "workflow", order=1),
            _claim(AnalysisRole.OUTPUT, "output"),
            _claim(AnalysisRole.BOUNDARY, "boundary"),
        ],
    )
    jsonschema.validate(document.model_dump(mode="json"), schema)
    bundle, baseline = render_analysis_projection(document, note_stem="Mixed分析")
    assert len(bundle.canvas["nodes"]) == 1 + 5 + len(document.claims)
    assert len(baseline.generated_node_ids) == len(bundle.canvas["nodes"])

    legacy = _whole_document()
    assert legacy.schema_version == 1
    assert "points" not in legacy.model_dump(mode="json")["claims"][0]
    jsonschema.validate(legacy.model_dump(mode="json"), schema)
    legacy_payload = document.model_dump(mode="json")
    legacy_payload["schema_version"] = 1
    with pytest.raises(ValidationError, match="require analysis IR schema_version 2"):
        AnalysisDocument.model_validate(legacy_payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(legacy_payload, schema)


def test_point_identity_and_canvas_summary_are_bounded() -> None:
    point = AnalysisPoint(
        point_id="reported",
        text="The paper reports a measured result.",
        evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 4"),
    )
    payload = _claim(AnalysisRole.TASK, "task").model_dump(mode="json")
    payload["points"] = [point.model_dump(mode="json"), point.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="point_id values must be unique"):
        AnalysisClaim.model_validate(payload)

    long_point = point.model_dump(mode="json")
    long_point["text"] = "long explanation " * 20
    with pytest.raises(ValidationError, match="canvas_summary is required"):
        AnalysisPoint.model_validate(long_point)
    long_point["canvas_summary"] = "A concise, qualified result."
    AnalysisPoint.model_validate(long_point)


def test_checked_in_conformance_and_batch_schemas_are_versioned() -> None:
    for filename in (
        "analysis-audit.schema.json",
        "analysis-baseline.schema.json",
        "analysis-conformance-report.schema.json",
        "analysis-batch.schema.json",
    ):
        schema = json.loads((ROOT / "contracts" / filename).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["properties"]["schema_version"]["const"] == 1


def test_checked_in_report_and_batch_schemas_accept_runtime_models() -> None:
    ir_schema = json.loads((ROOT / "contracts" / "analysis-ir.schema.json").read_text())
    batch_schema = json.loads((ROOT / "contracts" / "analysis-batch.schema.json").read_text())
    registry = Registry().with_resource(ir_schema["$id"], Resource.from_contents(ir_schema))
    request = AnalysisBatchRequest(
        batch_id="batch-contract",
        items=[
            AnalysisBatchItem(
                item_id="paper-one",
                zotero_item_key="ABCD1234",
                note_stem="Example分析",
                document=_whole_document(),
            )
        ],
    )
    jsonschema.Draft202012Validator(batch_schema, registry=registry).validate(
        request.model_dump(mode="json")
    )

    reports = {
        "analysis-conformance-report.schema.json": ConformanceReport(ok=True),
        "analysis-audit.schema.json": AnalysisAuditReport(
            ok=True,
            checked_item_ids=["paper-one"],
        ),
    }
    for filename, report in reports.items():
        schema = json.loads((ROOT / "contracts" / filename).read_text())
        jsonschema.validate(report.model_dump(mode="json"), schema)


def test_checked_in_baseline_schema_accepts_runtime_sidecar() -> None:
    ir_schema = json.loads((ROOT / "contracts" / "analysis-ir.schema.json").read_text())
    baseline_schema = json.loads(
        (ROOT / "contracts" / "analysis-baseline.schema.json").read_text()
    )
    registry = Registry().with_resource(ir_schema["$id"], Resource.from_contents(ir_schema))
    _bundle, baseline = render_analysis_projection(
        _whole_document(),
        note_stem="Example分析",
    )

    jsonschema.Draft202012Validator(baseline_schema, registry=registry).validate(
        baseline.model_dump(mode="json")
    )

    payload = _whole_document().model_dump(mode="json")
    payload["schema_version"] = 2
    payload["claims"][0]["points"] = [
        AnalysisPoint(
            point_id="reported",
            text="The paper reports a measured result.",
            evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Table 4"),
        ).model_dump(mode="json")
    ]
    _bundle, v2_baseline = render_analysis_projection(
        AnalysisDocument.model_validate(payload),
        note_stem="Example分析",
    )
    jsonschema.Draft202012Validator(baseline_schema, registry=registry).validate(
        v2_baseline.model_dump(mode="json")
    )
