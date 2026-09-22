from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
from referencing import Registry, Resource

from scholar_workflow.analysis.models import (
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitFile,
    AnalysisCommitReceipt,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    CoreDocumentKind,
    Evidence,
    EvidenceKind,
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeAuditManifest,
    KnowledgeAuditObject,
    KnowledgeChangeSet,
    KnowledgeCoreDocument,
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
    KnowledgeSupportingDocument,
    ProfileKind,
    SupportingDocumentKind,
)
from scholar_workflow.models import ResourceKind

ROOT = Path(__file__).resolve().parents[2]


def _manifest() -> KnowledgeManifest:
    return KnowledgeManifest(
        atomic_resources=[
            KnowledgeAtomicResource(
                resource_id="paper:jepa",
                kind=ResourceKind.PAPER,
                title="JEPA",
                markdown_path="topics/jepa/JEPA.md",
            ),
            KnowledgeAtomicResource(
                resource_id="doc:runtime",
                kind=ResourceKind.TECHNICAL_DOCUMENT,
                title="Runtime Notes",
                markdown_path="topics/runtime/Runtime.md",
            ),
            KnowledgeAtomicResource(
                resource_id="blog:example",
                kind=ResourceKind.BLOG_POST,
                title="A Blog",
                markdown_path="topics/blog/A Blog.md",
            ),
        ],
        core_documents=[
            KnowledgeCoreDocument(
                document_id="context:world-models",
                kind=CoreDocumentKind.CATALOG,
                title="World Models",
                markdown_path="topics/world-models/README.md",
            )
        ],
        supporting_documents=[
            KnowledgeSupportingDocument(
                document_id="analysis:paper:jepa",
                kind=SupportingDocumentKind.ANALYSIS,
                title="JEPA analysis",
                vault_path="topics/jepa/JEPA分析.md",
                owner_id="paper:jepa",
            )
        ],
    )


def test_knowledge_manifest_distinguishes_atomic_core_and_supporting_objects() -> None:
    manifest = _manifest()

    assert {item.kind for item in manifest.atomic_resources} == {
        ResourceKind.PAPER,
        ResourceKind.TECHNICAL_DOCUMENT,
        ResourceKind.BLOG_POST,
    }
    assert manifest.supporting_documents[0].owner_id == "paper:jepa"


def test_supporting_document_cannot_impersonate_an_atomic_resource() -> None:
    with pytest.raises(ValidationError):
        KnowledgeSupportingDocument(
            document_id="paper:fake",
            kind="paper",
            title="Not a paper",
            vault_path="fake.md",
            owner_id="paper:jepa",
        )

    payload = _manifest().model_dump(mode="json")
    payload["supporting_documents"][0]["owner_id"] = "missing:owner"
    with pytest.raises(ValidationError, match="require an atomic/context owner"):
        KnowledgeManifest.model_validate(payload)


def test_knowledge_manifest_preserves_legacy_ids_but_requires_global_uniqueness() -> None:
    payload = _manifest().model_dump(mode="json")
    payload["core_documents"][0]["document_id"] = "paper:jepa"

    with pytest.raises(ValidationError, match="globally unique"):
        KnowledgeManifest.model_validate(payload)


def test_checked_in_knowledge_manifest_schema_accepts_runtime_model() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "knowledge-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )

    jsonschema.validate(_manifest().model_dump(mode="json"), schema)


def _analysis_document() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:contract",
        paper_title="Contract Paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value}.",
                evidence=Evidence(
                    kind=EvidenceKind.AUTHOR_STATED,
                    anchor="Section 1",
                ),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in AnalysisRole
        ],
    )


def test_checked_in_commit_and_change_schemas_accept_runtime_models() -> None:
    document = _analysis_document()
    paths = AnalysisCanonicalPaths(
        markdown="topic/Contract分析.md",
        canvas="topic/Contract解析树.canvas",
        sidecar="topic/Contract分析.analysis.json",
    )
    relation = KnowledgeRelation(
        from_id="paper:contract",
        relation="has-analysis",
        to_id=document.artifact_id,
    )
    projection = KnowledgeProjection(
        projection_id="projection:contract",
        kind="obsidian",
        target_id=document.artifact_id,
    )
    request = AnalysisCommitRequest(
        commit_id="contract-commit",
        batch_id="contract-batch",
        item_id="paper-one",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:contract",
        note_stem="Contract分析",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        relations=[relation],
        projections=[projection],
    )
    digest = "sha256:" + "1" * 64
    change = KnowledgeChangeSet(
        change_id="change:" + "2" * 64,
        source_receipt="analysis-commit:contract-commit",
        upsert_artifacts=[
            KnowledgeArtifactChange(
                artifact_id=artifact_id,
                resource_id=request.resource_id,
                kind=kind,
                vault_path=path,
                sha256=digest,
            )
            for artifact_id, kind, path in (
                (document.artifact_id, "analysis_markdown", paths.markdown),
                (f"{document.artifact_id}:canvas", "analysis_canvas", paths.canvas),
                (f"{document.artifact_id}:sidecar", "analysis_sidecar", paths.sidecar),
            )
        ],
        upsert_relations=[relation],
        upsert_projections=[projection],
        expected_base_hashes=request.base_revisions,
    )
    receipt = AnalysisCommitReceipt(
        commit_id=request.commit_id,
        request_fingerprint="sha256:" + "3" * 64,
        artifact_id=document.artifact_id,
        committed_at="2026-09-22T00:00:00+00:00",
        files=[
            AnalysisCommitFile(
                path=path,
                after_sha256=digest,
                action="created",
            )
            for path in paths.as_list()
        ],
        change_set=change,
    )

    filenames = (
        "analysis-ir.schema.json",
        "knowledge-change-set.schema.json",
        "analysis-commit-request.schema.json",
        "analysis-commit-receipt.schema.json",
    )
    schemas = {
        filename: json.loads((ROOT / "contracts" / filename).read_text(encoding="utf-8"))
        for filename in filenames
    }
    registry = Registry()
    for schema in schemas.values():
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))

    jsonschema.Draft202012Validator(
        schemas["analysis-commit-request.schema.json"],
        registry=registry,
    ).validate(request.model_dump(mode="json"))
    jsonschema.Draft202012Validator(
        schemas["knowledge-change-set.schema.json"],
        registry=registry,
    ).validate(change.model_dump(mode="json"))
    jsonschema.Draft202012Validator(
        schemas["analysis-commit-receipt.schema.json"],
        registry=registry,
    ).validate(receipt.model_dump(mode="json"))


def test_checked_in_audit_manifest_schema_accepts_explicit_inventory() -> None:
    manifest = KnowledgeAuditManifest(
        objects=[
            KnowledgeAuditObject(
                object_id="paper:contract",
                object_class="atomic_resource",
                kind="paper",
                vault_path="topic/Paper.md",
                catalog_kind="resource",
            )
        ],
        catalog_path="state/catalog.json",
        expected_catalog_revision="sha256:" + "4" * 64,
    )
    analysis_schema = json.loads(
        (ROOT / "contracts" / "analysis-ir.schema.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        (ROOT / "contracts" / "knowledge-audit-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )
    registry = Registry().with_resource(
        analysis_schema["$id"],
        Resource.from_contents(analysis_schema),
    )

    jsonschema.Draft202012Validator(schema, registry=registry).validate(
        manifest.model_dump(mode="json")
    )
