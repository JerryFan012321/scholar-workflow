from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scholar_workflow.analysis.audit import (
    audit_analysis_batch_store,
    audit_analysis_pairs,
    audit_knowledge_manifest,
)
from scholar_workflow.analysis.batch import AnalysisBatchStore
from scholar_workflow.analysis.commit import commit_analysis_bundle
from scholar_workflow.analysis.models import (
    AnalysisAuditTarget,
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeAuditManifest,
    KnowledgeAuditObject,
    ProfileKind,
)
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import render_analysis_projection


def _document() -> AnalysisDocument:
    return AnalysisDocument(
        artifact_id="analysis:paper:audit",
        paper_title="Audit Paper",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value} content.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 1"),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in AnalysisRole
        ],
    )


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_analysis_audit_is_read_only_and_reuses_hard_conformance(tmp_path: Path) -> None:
    document = _document()
    bundle = render_analysis(document, note_stem="Audit分析")
    topic = tmp_path / "topic"
    topic.mkdir()
    (topic / "Audit分析.md").write_text(bundle.markdown, encoding="utf-8")
    (topic / "Audit解析树.canvas").write_text(
        json.dumps(bundle.canvas, ensure_ascii=False), encoding="utf-8"
    )
    target = AnalysisAuditTarget(
        item_id="audit-paper",
        note_stem="Audit分析",
        markdown_path="topic/Audit分析.md",
        canvas_path="topic/Audit解析树.canvas",
        document=document,
    )
    before = _hash_tree(tmp_path)

    report = audit_analysis_pairs(tmp_path, [target])

    assert report.ok
    assert report.checked_item_ids == ["audit-paper"]
    assert report.findings == []
    assert _hash_tree(tmp_path) == before


def test_analysis_audit_reports_drift_without_repairing_it(tmp_path: Path) -> None:
    document = _document()
    bundle = render_analysis(document, note_stem="Audit分析")
    topic = tmp_path / "topic"
    topic.mkdir()
    (topic / "Audit分析.md").write_text(bundle.markdown, encoding="utf-8")
    canvas = {"nodes": [dict(node) for node in bundle.canvas["nodes"]], "edges": bundle.canvas["edges"]}
    claim = next(node for node in canvas["nodes"] if "sw-analysis-claim" in node["text"])
    claim["text"] = claim["text"].replace("[[Audit分析#", "[[Wrong#")
    canvas_path = topic / "Audit解析树.canvas"
    canvas_path.write_text(json.dumps(canvas, ensure_ascii=False), encoding="utf-8")
    target = AnalysisAuditTarget(
        item_id="audit-paper",
        note_stem="Audit分析",
        markdown_path="topic/Audit分析.md",
        canvas_path="topic/Audit解析树.canvas",
        document=document,
    )
    before = _hash_tree(tmp_path)

    report = audit_analysis_pairs(tmp_path, [target])

    assert not report.ok
    assert "missing-evidence-backlink" in {finding.code for finding in report.findings}
    assert _hash_tree(tmp_path) == before


def test_analysis_audit_rejects_symlink_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "linked.md").symlink_to(outside)
    target = AnalysisAuditTarget(
        item_id="audit-paper",
        note_stem="Audit分析",
        markdown_path="linked.md",
        canvas_path="missing.canvas",
        document=_document(),
    )

    report = audit_analysis_pairs(tmp_path, [target])

    assert report.findings[0].code == "analysis-audit-read-failed"
    assert "symlink" in report.findings[0].message


def test_batch_audit_reports_failed_stage_residue(tmp_path: Path) -> None:
    store = AnalysisBatchStore(tmp_path / "analysis.db")
    item = AnalysisBatchItem(
        item_id="queued-item",
        zotero_item_key="ABCD1234",
        note_stem="Audit分析",
        document=_document(),
    )
    request = AnalysisBatchRequest(batch_id="audit-batch", items=[item])
    store.ensure_batch(request)
    store.ensure_item(request.batch_id, item)
    store.update_item(
        request.batch_id,
        item.item_id,
        AnalysisState.FAILED,
        stage_path=str(tmp_path / "residue"),
    )

    report = audit_analysis_batch_store(store)

    assert not report.ok
    assert [finding.code for finding in report.findings] == ["failed-stage-residue"]


def test_weekly_knowledge_audit_reports_explicit_inventory_drift_read_only(
    tmp_path: Path,
) -> None:
    topic = tmp_path / "topic"
    topic.mkdir()
    note = topic / "Paper.md"
    note.write_text(
        "# Paper\n\n{{ unresolved }}\nhttp://127.0.0.1:23128/pdf/ABC\n",
        encoding="utf-8",
    )
    support = topic / "Paper分析.md"
    support.write_text("# Analysis\n", encoding="utf-8")
    (topic / "Empty.txt").write_text("", encoding="utf-8")
    unlisted = topic / "Unlisted.md"
    unlisted.write_text("http://127.0.0.1:23128/not-audit-scope\n", encoding="utf-8")
    catalog = topic / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "revision": "sha256:" + "1" * 64,
                "resources": [
                    {"resource_id": "paper:other", "artifact_ids": ["missing:artifact"]},
                    {"resource_id": "paper:other", "artifact_ids": []},
                ],
                "artifacts": [
                    {"artifact_id": "analysis:other", "resource_id": "paper:missing"}
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = KnowledgeAuditManifest(
        objects=[
            KnowledgeAuditObject(
                object_id="paper:audit",
                object_class="atomic_resource",
                kind="paper",
                vault_path="topic/Paper.md",
                catalog_kind="resource",
            ),
            KnowledgeAuditObject(
                object_id="analysis:audit",
                object_class="supporting_document",
                kind="paper",
                vault_path="topic/Paper分析.md",
                owner_id="missing:owner",
                catalog_kind="resource",
            ),
            KnowledgeAuditObject(
                object_id="paper:audit",
                object_class="core_document",
                kind="catalog",
                vault_path="topic/Paper分析.md",
            ),
            KnowledgeAuditObject(
                object_id="doc:empty",
                object_class="atomic_resource",
                kind="technical_document",
                vault_path="topic/Empty.txt",
            ),
            KnowledgeAuditObject(
                object_id="analysis:other",
                object_class="supporting_document",
                kind="analysis",
                vault_path="topic/Paper分析.md",
                owner_id="paper:audit",
                catalog_kind="artifact",
            ),
        ],
        catalog_path="topic/catalog.json",
        expected_catalog_revision="sha256:" + "2" * 64,
    )
    before = _hash_tree(tmp_path)

    report = audit_knowledge_manifest(tmp_path, manifest)

    codes = {finding.code for finding in report.findings}
    assert {
        "duplicate-knowledge-id",
        "duplicate-knowledge-path",
        "knowledge-kind-role-mismatch",
        "orphan-supporting-document",
        "knowledge-catalog-kind-mismatch",
        "unresolved-template-marker",
        "raw-23128-url",
        "human-readable-markdown-required",
        "empty-human-readable-document",
        "catalog-duplicate-id",
        "catalog-revision-drift",
        "catalog-projection-drift",
        "catalog-orphan-relation",
    } <= codes
    assert all("Unlisted" not in finding.path for finding in report.findings)
    assert _hash_tree(tmp_path) == before


def test_weekly_knowledge_audit_accepts_clean_explicit_manifest(tmp_path: Path) -> None:
    topic = tmp_path / "topic"
    topic.mkdir()
    (topic / "Paper.md").write_text("# Human-readable paper\n", encoding="utf-8")
    (topic / "Analysis.md").write_text("# Human-readable analysis\n", encoding="utf-8")
    (topic / "catalog.json").write_text(
        json.dumps(
            {
                "revision": "sha256:" + "3" * 64,
                "resources": [
                    {
                        "resource_id": "paper:audit",
                        "kind": "paper",
                        "artifact_ids": ["analysis:audit"],
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "analysis:audit",
                        "kind": "paper-analysis",
                        "vault_path": "topic/Analysis.md",
                        "resource_id": "paper:audit",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = KnowledgeAuditManifest(
        objects=[
            KnowledgeAuditObject(
                object_id="paper:audit",
                object_class="atomic_resource",
                kind="paper",
                vault_path="topic/Paper.md",
                catalog_kind="resource",
            ),
            KnowledgeAuditObject(
                object_id="analysis:audit",
                object_class="supporting_document",
                kind="analysis",
                vault_path="topic/Analysis.md",
                owner_id="paper:audit",
                catalog_kind="artifact",
            ),
        ],
        catalog_path="topic/catalog.json",
        expected_catalog_revision="sha256:" + "3" * 64,
    )

    report = audit_knowledge_manifest(tmp_path, manifest)

    assert report.ok
    assert report.findings == []


def test_weekly_audit_reads_catalog_only_from_explicit_catalog_root(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Paper.md").write_text("# Paper\n", encoding="utf-8")
    catalog_root = tmp_path / "state"
    catalog_root.mkdir()
    (catalog_root / "catalog.json").write_text(
        json.dumps(
            {
                "revision": "sha256:" + "4" * 64,
                "resources": [
                    {"resource_id": "paper:audit", "kind": "paper", "artifact_ids": []}
                ],
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    manifest = KnowledgeAuditManifest(
        objects=[
            KnowledgeAuditObject(
                object_id="paper:audit",
                object_class="atomic_resource",
                kind="paper",
                vault_path="Paper.md",
                catalog_kind="resource",
            )
        ],
        catalog_path="catalog.json",
        expected_catalog_revision="sha256:" + "4" * 64,
    )

    report = audit_knowledge_manifest(
        vault,
        manifest,
        catalog_root=catalog_root,
    )

    assert report.ok


def test_weekly_audit_requires_and_verifies_sidecar_and_commit_receipt(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / "topic").mkdir(parents=True)
    state = tmp_path / "state"
    document = _document()
    bundle, baseline = render_analysis_projection(document, note_stem="Audit分析")
    paths = AnalysisCanonicalPaths(
        markdown="topic/Audit分析.md",
        canvas="topic/Audit解析树.canvas",
        sidecar="topic/Audit分析.analysis.json",
    )
    request = AnalysisCommitRequest(
        commit_id="audit-commit",
        batch_id="audit-batch",
        item_id="audit-paper",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:audit",
        note_stem="Audit分析",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
    )
    commit_analysis_bundle(
        vault_root=vault,
        state_root=state,
        request=request,
        bundle=bundle,
        baseline=baseline,
    )
    target = AnalysisAuditTarget(
        item_id="audit-paper",
        note_stem="Audit分析",
        markdown_path=paths.markdown,
        canvas_path=paths.canvas,
        sidecar_path=paths.sidecar,
        receipt_path="analysis-commits/receipts/audit-commit.json",
        document=document,
    )
    manifest = KnowledgeAuditManifest(analysis_targets=[target])
    before_vault = _hash_tree(vault)
    before_state = _hash_tree(state)

    report = audit_knowledge_manifest(
        vault,
        manifest,
        commit_state_root=state,
    )

    assert report.ok
    assert _hash_tree(vault) == before_vault
    assert _hash_tree(state) == before_state

    (vault / paths.sidecar).write_text("{}", encoding="utf-8")
    drift = audit_knowledge_manifest(
        vault,
        manifest,
        commit_state_root=state,
    )
    assert {finding.code for finding in drift.findings} >= {
        "analysis-sidecar-drift",
        "analysis-receipt-drift",
    }

    untracked = target.model_copy(
        update={"sidecar_path": None, "receipt_path": None}
    )
    missing = audit_knowledge_manifest(
        vault,
        KnowledgeAuditManifest(analysis_targets=[untracked]),
        commit_state_root=state,
    )
    assert {finding.code for finding in missing.findings} >= {
        "analysis-sidecar-untracked",
        "analysis-receipt-untracked",
    }


def test_weekly_audit_reports_malformed_catalog_arrays_without_crashing(
    tmp_path: Path,
) -> None:
    (tmp_path / "catalog.json").write_text(
        json.dumps({"revision": "sha256:" + "5" * 64, "resources": None}),
        encoding="utf-8",
    )
    manifest = KnowledgeAuditManifest(catalog_path="catalog.json")

    report = audit_knowledge_manifest(tmp_path, manifest)

    assert [finding.code for finding in report.findings].count("catalog-invalid") == 2
