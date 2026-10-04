"""Versioned reference-tree IR stays separate from the published five-role IR."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.models import (
    ALL_ROLES,
    TREE_ROLES,
    AnalysisBaseline,
    AnalysisBaselineClaim,
    AnalysisBatchItem,
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisPoint,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeRelation,
    ProfileKind,
    ZoteroPdfSpan,
)

ROOT = Path(__file__).resolve().parents[2]
IR_SCHEMA = json.loads((ROOT / "contracts/analysis-ir.schema.json").read_text(encoding="utf-8"))
BASELINE_SCHEMA = json.loads(
    (ROOT / "contracts/analysis-baseline.schema.json").read_text(encoding="utf-8")
)
BASELINE_VALIDATOR = jsonschema.Draft202012Validator(
    BASELINE_SCHEMA,
    registry=Registry().with_resource(IR_SCHEMA["$id"], Resource.from_contents(IR_SCHEMA)),
)


def _claim(
    role: AnalysisRole,
    path: str,
    *,
    claim_id: str | None = None,
    points: list[AnalysisPoint] | None = None,
    evidence: Evidence | None = None,
) -> AnalysisClaim:
    return AnalysisClaim(
        claim_id=claim_id or role.value,
        role=role,
        title="A checked statement",
        body="The complete explanation stays in the Markdown analysis.",
        evidence=evidence or Evidence(kind=EvidenceKind.NOT_REPORTED),
        points=points or [],
        outline_path=path,
    )


def _tree_document(*, claims: list[AnalysisClaim] | None = None) -> AnalysisDocument:
    return AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:reference-tree",
        paper_title="Reference-tree example",
        language="en",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        claims=claims or [
            _claim(AnalysisRole.ABSTRACT, "abstract/task"),
            _claim(AnalysisRole.INTRODUCTION, "introduction/task_application"),
            _claim(AnalysisRole.METHOD, "method/overview"),
            _claim(AnalysisRole.LIMITATION, "limitation/explanation"),
        ],
    )


def _point(point_id: str) -> AnalysisPoint:
    return AnalysisPoint(
        point_id=point_id,
        text=f"A source-attributed detail for {point_id}.",
        evidence=Evidence(kind=EvidenceKind.NOT_REPORTED),
    )


def test_v4_whole_profile_covers_four_tree_branches_and_schema() -> None:
    document = _tree_document()
    assert document.profile.roles == list(TREE_ROLES)
    assert list(ALL_ROLES) == [
        AnalysisRole.TASK,
        AnalysisRole.INPUT,
        AnalysisRole.WORKFLOW,
        AnalysisRole.OUTPUT,
        AnalysisRole.BOUNDARY,
    ]
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)

    sparse = document.model_dump(mode="json")
    sparse["claims"].pop()
    # The branch remains in the observable tree even when the source offers no
    # defensible factual claim for that section.
    sparse_document = AnalysisDocument.model_validate(sparse)
    assert sparse_document.profile.roles == list(TREE_ROLES)
    jsonschema.validate(sparse_document.model_dump(mode="json"), IR_SCHEMA)


@pytest.mark.parametrize("invalid_vault_name", ["../other", " test", "test ", "te\x00st"])
def test_v4_reader_projection_schema_keeps_pdf_span_identity_separate(
    invalid_vault_name: str,
) -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["reader"] = {"kind": "zotflow_library", "vault_name": "test"}
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)

    bad = document.model_dump(mode="json")
    bad["reader"]["vault_name"] = invalid_vault_name
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(bad)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, IR_SCHEMA)


def test_v4_zotflow_reader_accepts_host_vault_id_and_rejects_malformed_ids() -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["reader"] = {"kind": "zotflow_library", "vault_id": "0123456789abcdef"}
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)

    for invalid_id in ("test", "0123456789abcdeg", "0123456789ABCDEF"):
        bad = document.model_dump(mode="json")
        bad["reader"]["vault_id"] = invalid_id
        with pytest.raises(ValidationError):
            AnalysisDocument.model_validate(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, IR_SCHEMA)

    ambiguous = document.model_dump(mode="json")
    ambiguous["reader"]["vault_name"] = "test"
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(ambiguous)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(ambiguous, IR_SCHEMA)


def test_new_v4_commit_keeps_analysis_bundle_in_one_paper_folder() -> None:
    document = _tree_document()
    good_paths = AnalysisCanonicalPaths(
        markdown="World Models/resources/papers/v-jepa-2/V-JEPA 2分析.md",
        canvas="World Models/resources/papers/v-jepa-2/V-JEPA 2解析树.canvas",
        sidecar="World Models/resources/papers/v-jepa-2/V-JEPA 2分析.analysis.json",
    )

    def request(paths: AnalysisCanonicalPaths) -> AnalysisCommitRequest:
        return AnalysisCommitRequest(
            commit_id="paper-folder-contract",
            batch_id="paper-folder-batch",
            item_id="paper-folder-item",
            source_state=AnalysisState.VALIDATED,
            resource_id="paper:v-jepa-2",
            note_stem="V-JEPA 2分析",
            document=document,
            paths=paths,
            base_revisions={path: None for path in paths.as_list()},
            relations=[KnowledgeRelation(
                from_id="paper:v-jepa-2",
                relation="has-analysis",
                to_id=document.artifact_id,
            )],
        )

    assert request(good_paths).paths == good_paths
    flat_paths = AnalysisCanonicalPaths(
        markdown="World Models/V-JEPA 2分析.md",
        canvas="World Models/V-JEPA 2解析树.canvas",
        sidecar="World Models/V-JEPA 2分析.analysis.json",
    )
    with pytest.raises(ValidationError, match="folder"):
        request(flat_paths)
    rootless_paths = AnalysisCanonicalPaths(
        markdown="resources/papers/v-jepa-2/V-JEPA 2分析.md",
        canvas="resources/papers/v-jepa-2/V-JEPA 2解析树.canvas",
        sidecar="resources/papers/v-jepa-2/V-JEPA 2分析.analysis.json",
    )
    assert request(rootless_paths).paths == rootless_paths
    shallow_paths = AnalysisCanonicalPaths(
        markdown="papers/v-jepa-2/V-JEPA 2分析.md",
        canvas="papers/v-jepa-2/V-JEPA 2解析树.canvas",
        sidecar="papers/v-jepa-2/V-JEPA 2分析.analysis.json",
    )
    with pytest.raises(ValidationError, match="Field resources/papers"):
        request(shallow_paths)
    split_paths = good_paths.model_copy(update={
        "canvas": "World Models/resources/papers/other/V-JEPA 2解析树.canvas"
    })
    with pytest.raises(ValidationError, match="paper folder"):
        request(split_paths)


@pytest.mark.parametrize(
    ("role", "path", "allowed_point"),
    [
        (AnalysisRole.ABSTRACT, "abstract/previous_methods/datid-3d", "challenge-1"),
        (AnalysisRole.ABSTRACT, "abstract/insight", "motivation"),
        (AnalysisRole.ABSTRACT, "abstract/contributions/contribution-1", "summary"),
        (AnalysisRole.ABSTRACT, "abstract/experiment/robot-control", "finding-1"),
        (AnalysisRole.INTRODUCTION, "introduction/previous_methods/challenge-1", "technical-reason"),
        (AnalysisRole.INTRODUCTION, "introduction/our_pipeline/contributions/contribution-1", "how"),
        (AnalysisRole.METHOD, "method/modules/module-1", "why-it-works"),
        (AnalysisRole.LIMITATION, "limitation/explanation/camera", "reason-1"),
    ],
)
def test_v4_accepts_only_defined_tree_paths_and_point_slots(
    role: AnalysisRole, path: str, allowed_point: str
) -> None:
    profile = AnalysisProfile(
        kind=ProfileKind.FOCUSED,
        framework="reference_tree",
        roles=[role],
    )
    document = AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:focused-tree",
        paper_title="Focused tree",
        language="en",
        profile=profile,
        claims=[_claim(role, path, points=[_point(allowed_point)])],
    )
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)

    bad = document.model_dump(mode="json")
    bad["claims"][0]["points"][0]["point_id"] = "invented-slot"
    with pytest.raises(ValidationError, match="point_id is outside"):
        AnalysisDocument.model_validate(bad)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, IR_SCHEMA)


@pytest.mark.parametrize(
    "bad_path",
    [
        "abstract/unknown",
        "abstract/contributions/Unstable Name",
        "abstract/contributions/-leading",
        "introduction/our_pipeline/challenge",
        "method/modules/module-1/extra",
        "limitation/experiment",
    ],
)
def test_v4_rejects_paths_outside_original_framework(bad_path: str) -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["claims"][0]["outline_path"] = bad_path
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)


def test_v4_rejects_duplicate_or_misclassified_outline_paths() -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["claims"].append({**payload["claims"][0], "claim_id": "duplicate-path"})
    with pytest.raises(ValidationError, match="outline_path values must be unique"):
        AnalysisDocument.model_validate(payload)

    mismatch = _tree_document().model_dump(mode="json")
    mismatch["claims"][0]["outline_path"] = "method/overview"
    with pytest.raises(ValidationError, match="must start with its claim role"):
        AnalysisDocument.model_validate(mismatch)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(mismatch, IR_SCHEMA)


def test_v4_semantic_budget_counts_editable_claim_and_grouped_detail_nodes() -> None:
    with pytest.raises(ValidationError, match="exceeds 40 generated semantic"):
        _tree_document(
            claims=[
                _claim(
                    AnalysisRole.ABSTRACT,
                    f"abstract/contributions/contribution-{index}",
                    claim_id=f"contribution-{index}",
                    points=[_point("summary")],
                )
                for index in range(1, 20)
            ] + [
                _claim(AnalysisRole.INTRODUCTION, "introduction/task_application"),
                _claim(AnalysisRole.METHOD, "method/overview"),
                _claim(AnalysisRole.LIMITATION, "limitation/explanation"),
            ]
        )


def test_v4_schema_and_model_agree_on_40_claim_boundary() -> None:
    claims = [
        _claim(
            AnalysisRole.ABSTRACT,
            f"abstract/contributions/contribution-{index}",
            claim_id=f"contribution-{index}",
        )
        for index in range(1, 41)
    ]
    document = _tree_document(claims=claims)
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)
    payload = document.model_dump(mode="json")
    payload["claims"].append(
        _claim(
            AnalysisRole.ABSTRACT,
            "abstract/contributions/contribution-41",
            claim_id="contribution-41",
        ).model_dump(mode="json")
    )
    with pytest.raises(ValidationError, match="exceeds 40 generated semantic"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)


def test_v4_schema_and_model_reject_fourth_abstract_challenge() -> None:
    payload = _tree_document(
        claims=[
            _claim(
                AnalysisRole.ABSTRACT,
                "abstract/previous_methods/datid-3d",
                points=[_point("challenge-3")],
            )
        ]
    ).model_dump(mode="json")
    payload["claims"][0]["points"][0]["point_id"] = "challenge-4"
    with pytest.raises(ValidationError, match="point_id is outside"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)


@pytest.mark.parametrize(
    ("role", "path", "overflow_point"),
    [
        (AnalysisRole.ABSTRACT, "abstract/experiment/robot-control", "finding-5"),
        (AnalysisRole.LIMITATION, "limitation/explanation/camera", "reason-5"),
    ],
)
def test_v4_repeated_result_and_limitation_details_stay_bounded(
    role: AnalysisRole, path: str, overflow_point: str
) -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["claims"] = [
        _claim(role, path, points=[_point(overflow_point.replace("-5", "-4"))]).model_dump(mode="json")
    ]
    payload["claims"][0]["points"][0]["point_id"] = overflow_point
    with pytest.raises(ValidationError, match="point_id is outside"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)


def test_v4_schema_and_model_reject_heading_injected_into_claim_body() -> None:
    payload = _tree_document().model_dump(mode="json")
    payload["claims"][0]["body"] = "Ordinary explanation.\n### Corresponding Challenge"
    payload["claims"][0]["canvas_summary"] = "Ordinary explanation."
    with pytest.raises(ValidationError, match="cannot inject framework headings"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)


@pytest.mark.parametrize("note_stem", ["Analysis|broken", "Analysis\ncontinued"])
def test_batch_rejects_broken_reference_backlink_filename(note_stem: str) -> None:
    with pytest.raises(ValidationError, match="plain filename stem"):
        AnalysisBatchItem(
            item_id="reference-tree",
            zotero_item_key="ABCD1234",
            note_stem=note_stem,
            document=_tree_document(),
        )


def test_v4_requires_explicit_language_framework_and_source_spans() -> None:
    payload = _tree_document().model_dump(mode="json")
    payload.pop("language")
    with pytest.raises(ValidationError, match="explicit analysis language"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)

    payload = _tree_document().model_dump(mode="json")
    payload["profile"]["framework"] = "legacy"
    with pytest.raises(ValidationError):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)

    payload = _tree_document().model_dump(mode="json")
    payload["claims"][0]["evidence"] = Evidence(
        kind=EvidenceKind.AUTHOR_STATED,
        anchor="Abstract",
    ).model_dump(mode="json")
    with pytest.raises(ValidationError, match="source span"):
        AnalysisDocument.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, IR_SCHEMA)

    source = ZoteroPdfSpan(
        library_type="personal",
        library_id="17685951",
        attachment_key="QR4ZU2S9",
        content_hash="md5:" + "a" * 32,
        page_index=0,
    )
    payload["claims"][0]["evidence"]["source_spans"] = [source.model_dump(mode="json")]
    document = AnalysisDocument.model_validate(payload)
    jsonschema.validate(document.model_dump(mode="json"), IR_SCHEMA)


def test_legacy_document_keeps_five_roles_and_rejects_tree_fields() -> None:
    legacy = AnalysisDocument(
        schema_version=1,
        artifact_id="analysis:paper:legacy",
        paper_title="Legacy paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body="Legacy explanation.",
                evidence=Evidence(kind=EvidenceKind.NOT_REPORTED),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in ALL_ROLES
        ],
    )
    assert legacy.profile.roles == list(ALL_ROLES)
    assert legacy.language == "zh"
    jsonschema.validate(legacy.model_dump(mode="json"), IR_SCHEMA)

    with_tree_path = legacy.model_dump(mode="json")
    with_tree_path["claims"][0]["outline_path"] = "abstract/task"
    with pytest.raises(ValidationError, match="legacy claims cannot carry"):
        AnalysisDocument.model_validate(with_tree_path)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(with_tree_path, IR_SCHEMA)


def test_baseline_node_cap_is_versioned() -> None:
    document = _tree_document()
    ids = [f"{index:016x}" for index in range(41)]
    claims = {
        claim.claim_id: AnalysisBaselineClaim(
            role=claim.role,
            markdown_sha256="a" * 64,
            canvas_node_id=ids[index],
            canvas_text_sha256="b" * 64,
        )
        for index, claim in enumerate(document.claims)
    }
    baseline = AnalysisBaseline(
        artifact_id=document.artifact_id,
        note_stem="Reference analysis",
        document=document,
        markdown_sha256="c" * 64,
        canvas_sha256="d" * 64,
        claims=claims,
        generated_node_ids=ids,
        generated_edge_ids=[],
    )
    BASELINE_VALIDATOR.validate(baseline.model_dump(mode="json"))

    payload = baseline.model_dump(mode="json")
    payload["generated_node_ids"].extend(f"{index:016x}" for index in range(41, 97))
    with pytest.raises(ValidationError, match="more than 96"):
        AnalysisBaseline.model_validate(payload)
    with pytest.raises(jsonschema.ValidationError):
        BASELINE_VALIDATOR.validate(payload)
