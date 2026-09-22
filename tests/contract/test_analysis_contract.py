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
    AnalysisProfile,
    AnalysisRole,
    ConformanceReport,
    Evidence,
    EvidenceKind,
    ProfileKind,
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
    with pytest.raises(ValidationError, match="exceeds 40 semantic"):
        AnalysisDocument.model_validate(payload)


def test_checked_in_analysis_ir_schema_accepts_runtime_document() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    jsonschema.validate(_whole_document().model_dump(mode="json"), schema)


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
