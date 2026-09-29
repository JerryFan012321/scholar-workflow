"""Pure bootstrap graphs for a first-time, jointly reviewed Field migration."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scholar_workflow.analysis.apply_changes import (
    KnowledgeVaultBinding,
    prepare_joint_paper_placement,
)
from scholar_workflow.analysis.models import (
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisReader,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeCoreDocument,
    ProfileKind,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.hub.fields import FieldDefinition, FieldNavigationGroup
from scholar_workflow.hub.models import HubResource, ZoteroLink
from scholar_workflow.hub.paper_foldering import (
    PaperFolderRelocation,
    plan_paper_foldering,
)
from scholar_workflow.hub.provider_bootstrap import (
    ProviderBootstrapError,
    build_bootstrap_provider_base,
    build_bootstrap_provider_graphs,
)
from scholar_workflow.models import ResourceKind

FIELD_ID = "62f9a02e-c91c-475c-86ca-f0bd19353c12"
GENERATED_AT = datetime(2026, 9, 29, tzinfo=UTC)
KEY_DIGITS = "23456789"


@dataclass
class Case:
    vault: Path
    field: FieldDefinition
    plan: object
    papers: list[HubResource]
    cores: list[KnowledgeCoreDocument]
    binding: KnowledgeVaultBinding

    @property
    def base_kwargs(self) -> dict[str, object]:
        return {
            "field": self.plan.proposed_field,
            "paper_plan": self.plan,
            "verified_papers": self.papers,
            "reviewed_source_note_paths": [move.old_path for move in self.plan.moves],
            "core_documents": self.cores,
            "vault_binding": self.binding,
            "generated_at": GENERATED_AT,
        }

    def analysis_kwargs(self) -> dict[str, object]:
        base = build_bootstrap_provider_base(**self.base_kwargs)
        paths = AnalysisCanonicalPaths(
            markdown="field/resources/papers/paper-0/Paper0分析.md",
            canvas="field/resources/papers/paper-0/Paper0解析树.canvas",
            sidecar="field/resources/papers/paper-0/Paper0分析.analysis.json",
        )
        document = AnalysisDocument(
            schema_version=4,
            artifact_id="analysis:paper:fixture-0",
            paper_title="Fixture Paper 0",
            language="en",
            profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
            reader=AnalysisReader(kind="zotero_native"),
            claims=[
                AnalysisClaim(
                    claim_id="task",
                    role=AnalysisRole.ABSTRACT,
                    outline_path="abstract/task",
                    title="Task",
                    body="A readable task.",
                    evidence=Evidence(
                        kind=EvidenceKind.AUTHOR_STATED,
                        anchor="Abstract",
                        source_spans=[
                            ZoteroPdfSpan(
                                library_type="personal",
                                library_id="1",
                                attachment_key=self.papers[0].zotero.attachment_key,
                                content_hash="sha256:" + "a" * 64,
                                page_index=0,
                            )
                        ],
                    ),
                )
            ],
        )
        bundle, baseline = render_analysis_projection(document, note_stem="Paper0分析")
        request = AnalysisCommitRequest(
            commit_id="bootstrap-fixture",
            batch_id="bootstrap-batch",
            item_id="bootstrap-item",
            source_state=AnalysisState.VALIDATED,
            resource_id=self.papers[0].resource_id,
            note_stem="Paper0分析",
            document=document,
            paths=paths,
            base_revisions={path: None for path in paths.as_list()},
            base_snapshot_revision=base.snapshot_revision,
            base_catalog_revision=base.catalog.revision,
            zotero_item_key=self.papers[0].zotero.item_key,
            relations=[
                {
                    "from_id": self.papers[0].resource_id,
                    "relation": "has-analysis",
                    "to_id": document.artifact_id,
                }
            ],
        )
        return {**self.base_kwargs, "request": request, "bundle": bundle, "baseline": baseline}


def _key(prefix: str, index: int) -> str:
    return prefix * 6 + KEY_DIGITS[index // 8] + KEY_DIGITS[index % 8]


def _case(tmp_path: Path, *, count: int = 2, missing: bool = False) -> Case:
    vault = tmp_path / "vault"
    field_root = vault / "field"
    paper_root = field_root / "paper_assets"
    paper_root.mkdir(parents=True)
    (field_root / "00-Home.md").write_text("# Home\n", encoding="utf-8")
    papers = []
    relocations = []
    nav = []
    for index in range(count):
        note = f"Paper{index}.md"
        (paper_root / note).write_text(f"# Fixture Paper {index}\n", encoding="utf-8")
        nav.append(f"paper_assets/{note}")
        relocations.append(
            PaperFolderRelocation(
                source_note=f"paper_assets/{note}",
                resource_id=f"paper:fixture-{index}",
                destination_note=f"resources/papers/paper-{index}/{note}",
            )
        )
        papers.append(
            HubResource(
                resource_id=f"paper:fixture-{index}",
                kind=ResourceKind.PAPER,
                title=f"Fixture Paper {index}",
                zotero=ZoteroLink(
                    item_key=_key("A", index),
                    attachment_key=_key("B", index),
                ),
            )
        )
    if missing:
        nav.append("paper_assets/Missing.md")
    field = FieldDefinition(
        field_id=FIELD_ID,
        title="Fixture Field",
        relative_root="field",
        home="00-Home.md",
        navigation=[FieldNavigationGroup(label="Papers", items=nav)],
    )
    plan = plan_paper_foldering(vault_root=vault, field=field, relocations=relocations)
    info = vault.stat()
    return Case(
        vault=vault,
        field=field,
        plan=plan,
        papers=papers,
        cores=[
            KnowledgeCoreDocument(
                document_id="core:fixture-home",
                kind="catalog",
                title="Fixture Field",
                markdown_path="field/00-Home.md",
            )
        ],
        binding=KnowledgeVaultBinding(root_path=str(vault), device=info.st_dev, inode=info.st_ino),
    )


def _files(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (
            hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_ino
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def test_bootstrap_all_39_papers_and_analysis_triple_without_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case(tmp_path, count=39)
    inputs = case.analysis_kwargs()
    before = _files(case.vault)
    def reject_io(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider bootstrap performed filesystem IO")

    monkeypatch.setattr(os, "open", reject_io)
    result = build_bootstrap_provider_graphs(**inputs)
    assert _files(case.vault) == before
    assert len(result.base.manifest.atomic_resources) == 39
    assert len(result.after.manifest.atomic_resources) == 39
    assert len(result.base.catalog.resources) == 39
    assert len(result.after.catalog.resources) == 39
    assert result.base.receipts == result.after.receipts == []
    assert result.base.artifacts == []
    assert len(result.after.artifacts) == 3
    assert len(result.after.catalog.artifacts) == 2
    assert result.base.manifest.atomic_resources[0].markdown_path.startswith(
        "field/paper_assets/"
    )
    assert all(
        row.markdown_path.startswith("field/resources/papers/")
        for row in result.after.manifest.atomic_resources
    )
    assert result.base.snapshot_revision != result.after.snapshot_revision
    assert result.base.catalog.revision != result.after.catalog.revision
    selected_move = case.plan.moves[0]
    selected_preparation = prepare_joint_paper_placement(
        snapshot=result.base,
        request=inputs["request"],
        vault_binding=case.binding,
        transaction_id="comparison-only",
        plan_digest=case.plan.plan_digest,
        source_note_path=selected_move.old_path,
        destination_note_path=selected_move.new_path,
        note_sha256=selected_move.after_sha256,
        new_artifacts=result.after.artifacts,
    )
    assert result.after.artifacts == list(selected_preparation.artifacts)
    assert result.after.relations == list(selected_preparation.relations)
    assert result.after.projections == list(selected_preparation.projections)
    assert result.after.catalog == selected_preparation.catalog
    assert result.after.manifest.supporting_documents == (
        selected_preparation.manifest.supporting_documents
    )


def test_bootstrap_rejects_missing_duplicate_and_unreviewed_paper_identity(tmp_path: Path) -> None:
    case = _case(tmp_path)
    inputs = case.base_kwargs
    with pytest.raises(ProviderBootstrapError, match="cover every move"):
        build_bootstrap_provider_base(**{**inputs, "verified_papers": case.papers[:1]})
    with pytest.raises(ProviderBootstrapError, match="unique"):
        build_bootstrap_provider_base(
            **{
                **inputs,
                "verified_papers": [
                    case.papers[0],
                    case.papers[1].model_copy(
                        update={"zotero": case.papers[0].zotero.model_copy(deep=True)}
                    ),
                ],
            }
        )
    with pytest.raises(ProviderBootstrapError, match="reviewed flat-note inventory"):
        build_bootstrap_provider_base(
            **{**inputs, "reviewed_source_note_paths": [case.plan.moves[0].old_path]}
        )
    with pytest.raises(ProviderBootstrapError, match="invalid Zotero key"):
        build_bootstrap_provider_base(
            **{
                **inputs,
                "verified_papers": [
                    case.papers[0].model_copy(
                        update={"zotero": case.papers[0].zotero.model_copy(
                            update={"attachment_key": "INVALID!"}
                        )}
                    ),
                    case.papers[1],
                ],
            }
        )
    with pytest.raises(ProviderBootstrapError, match="two Zotero keys"):
        build_bootstrap_provider_base(
            **{
                **inputs,
                "verified_papers": [
                    case.papers[0].model_copy(
                        update={"zotero": ZoteroLink(item_key=case.papers[0].zotero.item_key)}
                    ),
                    case.papers[1],
                ],
            }
        )


def test_missing_navigation_requires_exact_reviewed_removal(tmp_path: Path) -> None:
    case = _case(tmp_path, missing=True)
    with pytest.raises(ProviderBootstrapError, match="explicit removal"):
        build_bootstrap_provider_base(**case.base_kwargs)
    revised = case.plan.proposed_field.model_copy(deep=True)
    revised.navigation[0].items.remove("paper_assets/Missing.md")
    base = build_bootstrap_provider_base(
        **{
            **case.base_kwargs,
            "field": revised,
            "explicitly_removed_navigation_targets": ["paper_assets/Missing.md"],
        }
    )
    assert len(base.catalog.resources) == 2
    with pytest.raises(ProviderBootstrapError, match="navigation changed"):
        build_bootstrap_provider_base(
            **{
                **case.base_kwargs,
                "field": case.plan.proposed_field,
                "explicitly_removed_navigation_targets": ["paper_assets/Missing.md"],
            }
        )


def test_bootstrap_rejects_stale_revision_wrong_pdf_and_external_core(tmp_path: Path) -> None:
    case = _case(tmp_path)
    inputs = case.analysis_kwargs()
    request = inputs["request"]
    with pytest.raises(ProviderBootstrapError, match="virtual base"):
        build_bootstrap_provider_graphs(
            **{
                **inputs,
                "request": request.model_copy(update={"base_snapshot_revision": "sha256:" + "0" * 64}),
            }
        )
    wrong_document = request.document.model_copy(deep=True)
    wrong_document.claims[0].evidence.source_spans[0].attachment_key = "CCCCCCCC"
    with pytest.raises(ProviderBootstrapError, match="verified attachment"):
        build_bootstrap_provider_graphs(
            **{
                **inputs,
                "request": request.model_copy(update={"document": wrong_document}),
            }
        )
    wrong_item = request.model_copy(update={"zotero_item_key": "CCCCCCCC"})
    with pytest.raises(ProviderBootstrapError, match="verified Zotero row"):
        build_bootstrap_provider_graphs(**{**inputs, "request": wrong_item})
    with pytest.raises(ProviderBootstrapError, match="outside the selected Field"):
        build_bootstrap_provider_base(
            **{
                **case.base_kwargs,
                "core_documents": [
                    case.cores[0].model_copy(update={"markdown_path": "other/00-Home.md"})
                ],
            }
        )
