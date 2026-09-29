"""Build an unpersisted Knowledge provider graph for first-time Field enrollment.

All paper identities and source paths are explicit caller-reviewed inputs. This
module does no discovery, filesystem IO, registration, or publication. In
particular, the returned ``base`` is a *virtual* pre-move graph, not evidence
that a provider snapshot has ever existed on disk. The joint Field transaction
must separately bind current bytes, pause external writers, journal every
member, and conditionally recover failures.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from scholar_workflow.analysis.apply_changes import (
    KnowledgeApplyError,
    KnowledgeProviderSnapshot,
    KnowledgeVaultBinding,
    prepare_joint_paper_placement,
)
from scholar_workflow.analysis.commit import _canonical_payloads
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisCommitRequest,
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeCoreDocument,
    KnowledgeManifest,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.hub.fields import FieldDefinition
from scholar_workflow.hub.models import HubCatalog, HubResource
from scholar_workflow.hub.paper_foldering import PaperFolderingPlan
from scholar_workflow.models import ResourceKind


class ProviderBootstrapError(ValueError):
    """The explicit bootstrap inputs cannot form one complete provider graph."""


@dataclass(frozen=True)
class BootstrapProviderGraphs:
    """Virtual pre-move graph and prospective post-move graph; neither is durable."""

    base: KnowledgeProviderSnapshot
    after: KnowledgeProviderSnapshot


def _field_relative(field: FieldDefinition, path: str) -> str:
    parts = PurePosixPath(path).parts
    prefix = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    if (
        not path
        or PurePosixPath(path).is_absolute()
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or parts[: len(prefix)] != prefix
        or len(parts) <= len(prefix)
        or any(part.startswith(".") for part in parts[len(prefix) :])
    ):
        raise ProviderBootstrapError(f"path is outside the selected Field: {path}")
    return PurePosixPath(*parts[len(prefix) :]).as_posix()


def _validate_field_and_navigation(
    field: FieldDefinition,
    plan: PaperFolderingPlan,
    *,
    moved_paths: set[str],
    core_paths: set[str],
    explicitly_removed_navigation_targets: Sequence[str],
) -> None:
    proposed = plan.proposed_field
    if (field.field_id, field.title, field.relative_root) != (
        proposed.field_id, proposed.title, proposed.relative_root
    ) or field.home != proposed.home:
        raise ProviderBootstrapError("final Field identity, root, title, or home differs from plan")
    removed = list(explicitly_removed_navigation_targets)
    if len(removed) != len(set(removed)) or set(removed) != set(plan.missing_navigation_targets):
        raise ProviderBootstrapError(
            "every missing navigation target requires an explicit removal decision"
        )
    if field.home in removed:
        raise ProviderBootstrapError("missing Field home requires a reviewed replacement")
    if len(field.navigation) != len(proposed.navigation):
        raise ProviderBootstrapError("final Field navigation groups differ from plan")
    for before, after in zip(proposed.navigation, field.navigation, strict=True):
        if before.label != after.label or after.items != [
            path for path in before.items if path not in removed
        ]:
            raise ProviderBootstrapError("final Field navigation changed beyond explicit removals")
    navigation = {field.home, *(path for group in field.navigation for path in group.items)}
    expected = moved_paths | core_paths
    if navigation != expected or field.home not in core_paths:
        raise ProviderBootstrapError(
            "Field navigation must cover exactly the declared papers and core documents"
        )


def build_bootstrap_provider_base(
    *,
    field: FieldDefinition,
    paper_plan: PaperFolderingPlan,
    verified_papers: Sequence[HubResource],
    reviewed_source_note_paths: Sequence[str],
    core_documents: Sequence[KnowledgeCoreDocument],
    vault_binding: KnowledgeVaultBinding,
    generated_at: datetime,
    explicitly_removed_navigation_targets: Sequence[str] = (),
) -> KnowledgeProviderSnapshot:
    """Validate all declared papers and return the unpersisted pre-move graph.

    The caller must verify paper/title/Zotero identities with the authoritative
    provider and separately review the complete flat-note inventory. This
    function verifies their *agreement*, but cannot prove the external facts.
    """
    try:
        field = FieldDefinition.model_validate(field.model_dump(mode="json"))
        if not isinstance(paper_plan, PaperFolderingPlan):
            raise ProviderBootstrapError("paper foldering plan has an unexpected type")
        vault_binding = KnowledgeVaultBinding.model_validate(
            vault_binding.model_dump(mode="json")
        )
        papers = [HubResource.model_validate(row.model_dump(mode="json"))
                  for row in verified_papers]
        cores = [KnowledgeCoreDocument.model_validate(row.model_dump(mode="json"))
                 for row in core_documents]
        if generated_at.utcoffset() is None:
            raise ProviderBootstrapError("catalog generation time must be timezone-aware")
        if not paper_plan.read_only or paper_plan.recovery_is_verified_backup:
            raise ProviderBootstrapError("bootstrap requires a read-only foldering proposal")
        if paper_plan.field_id != field.field_id:
            raise ProviderBootstrapError("paper foldering plan belongs to another Field")
        if (
            str(paper_plan.vault_root), paper_plan.vault_device, paper_plan.vault_inode
        ) != (
            vault_binding.root_path, vault_binding.device, vault_binding.inode
        ):
            raise ProviderBootstrapError("foldering plan and Vault binding differ")
        moves = {row.resource_id: row for row in paper_plan.moves}
        if not moves or len(moves) != len(paper_plan.moves):
            raise ProviderBootstrapError("paper moves are empty or duplicate resource IDs")
        if len(papers) != len(moves) or {row.resource_id for row in papers} != set(moves):
            raise ProviderBootstrapError("verified paper identities must cover every move once")
        if len({row.resource_id for row in papers}) != len(papers):
            raise ProviderBootstrapError("verified paper identities contain duplicates")
        old_paths = [row.old_path for row in paper_plan.moves]
        if (
            len(reviewed_source_note_paths) != len(set(reviewed_source_note_paths))
            or set(reviewed_source_note_paths) != set(old_paths)
        ):
            raise ProviderBootstrapError("reviewed flat-note inventory differs from paper moves")
        if len({row.zotero.item_key for row in papers}) != len(papers) or len({
            row.zotero.attachment_key for row in papers
        }) != len(papers):
            raise ProviderBootstrapError("Zotero item and attachment keys must be unique")
        for row in papers:
            if (
                row.kind is not ResourceKind.PAPER
                or not row.title
                or not row.zotero.item_key
                or not row.zotero.attachment_key
                or row.artifact_ids
                or row.topic_ids
            ):
                raise ProviderBootstrapError(
                    "each paper needs a title, two Zotero keys, and no undeclared graph refs"
                )
        if len({row.old_path for row in paper_plan.moves}) != len(paper_plan.moves) or len({
            row.new_path for row in paper_plan.moves
        }) != len(paper_plan.moves) or len({
            row.stable_segment.casefold() for row in paper_plan.moves
        }) != len(paper_plan.moves):
            raise ProviderBootstrapError("paper moves reuse a source, destination, or segment")
        move_documents = {
            (row.source_path, row.output_path): row for row in paper_plan.documents
        }
        if len(move_documents) != len(paper_plan.documents):
            raise ProviderBootstrapError("foldering candidate documents contain duplicates")
        moved_relative_paths: set[str] = set()
        for move in paper_plan.moves:
            old = _field_relative(field, move.old_path)
            new = _field_relative(field, move.new_path)
            if PurePosixPath(new).parts != (
                "resources", "papers", move.stable_segment,
                PurePosixPath(new).name,
            ) or PurePosixPath(old).parent != PurePosixPath("paper_assets"):
                raise ProviderBootstrapError("paper move is not an owned flat-to-folder relocation")
            document = move_documents.get((move.old_path, move.new_path))
            if document is None or (
                document.before_sha256 != move.before_sha256
                or document.after_sha256 != move.after_sha256
                or document.before_device != move.before_device
                or document.before_inode != move.before_inode
                or "sha256:" + hashlib.sha256(document.after_bytes).hexdigest()
                != document.after_sha256
            ):
                raise ProviderBootstrapError("paper move lacks its exact candidate document")
            moved_relative_paths.add(new)
        if len(cores) != len({row.document_id for row in cores}) or len(cores) != len({
            row.markdown_path for row in cores
        }):
            raise ProviderBootstrapError("core document identities or paths are duplicated")
        core_relative_paths = {
            _field_relative(field, row.markdown_path) for row in cores
        }
        if len(core_relative_paths) != len(cores):
            raise ProviderBootstrapError("core document paths are duplicated")
        _validate_field_and_navigation(
            field,
            paper_plan,
            moved_paths=moved_relative_paths,
            core_paths=core_relative_paths,
            explicitly_removed_navigation_targets=explicitly_removed_navigation_targets,
        )
        manifest = KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id=row.resource_id,
                    kind=ResourceKind.PAPER,
                    title=row.title,
                    markdown_path=moves[row.resource_id].old_path,
                )
                for row in sorted(papers, key=lambda item: item.resource_id)
            ],
            core_documents=sorted(cores, key=lambda row: row.document_id),
        )
        catalog = HubCatalog(
            generated_at=generated_at,
            resources=sorted((row.model_copy(deep=True) for row in papers),
                             key=lambda item: item.resource_id),
        )
        return KnowledgeProviderSnapshot(
            vault_binding=vault_binding,
            manifest=manifest,
            catalog=catalog,
            receipts=[],
        )
    except ProviderBootstrapError:
        raise
    except (KnowledgeApplyError, TypeError, ValueError) as exc:
        raise ProviderBootstrapError(str(exc)) from exc


def build_bootstrap_provider_graphs(
    *,
    field: FieldDefinition,
    paper_plan: PaperFolderingPlan,
    verified_papers: Sequence[HubResource],
    reviewed_source_note_paths: Sequence[str],
    core_documents: Sequence[KnowledgeCoreDocument],
    vault_binding: KnowledgeVaultBinding,
    generated_at: datetime,
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
    explicitly_removed_navigation_targets: Sequence[str] = (),
) -> BootstrapProviderGraphs:
    """Project every note move plus one new conformant v4 analysis triple."""
    base = build_bootstrap_provider_base(
        field=field,
        paper_plan=paper_plan,
        verified_papers=verified_papers,
        reviewed_source_note_paths=reviewed_source_note_paths,
        core_documents=core_documents,
        vault_binding=vault_binding,
        generated_at=generated_at,
        explicitly_removed_navigation_targets=explicitly_removed_navigation_targets,
    )
    try:
        request = AnalysisCommitRequest.model_validate(request.model_dump(mode="json"))
        if request.document.schema_version != 4 or any(
            value is not None for value in request.base_revisions.values()
        ):
            raise ProviderBootstrapError("bootstrap requires a new IR v4 analysis triple")
        if (request.base_snapshot_revision, request.base_catalog_revision) != (
            base.snapshot_revision, base.catalog.revision
        ):
            raise ProviderBootstrapError("analysis request does not bind the virtual base graph")
        analyzed = next(
            (row for row in base.catalog.resources if row.resource_id == request.resource_id),
            None,
        )
        if analyzed is None or (
            request.zotero_item_key != analyzed.zotero.item_key
            or request.document.paper_title != analyzed.title
        ):
            raise ProviderBootstrapError("analyzed paper identity differs from verified Zotero row")
        move = next(row for row in paper_plan.moves if row.resource_id == request.resource_id)
        if PurePosixPath(move.new_path).parent != PurePosixPath(request.paths.markdown).parent:
            raise ProviderBootstrapError("analysis triple must share its owner paper folder")
        if request.document.reader.kind == "zotflow_library" and (
            request.document.reader.vault_id is None
        ):
            raise ProviderBootstrapError("formal ZotFlow v4 projection requires a Vault ID")
        spans = [
            span
            for claim in request.document.claims
            for evidence in [claim.evidence, *(point.evidence for point in claim.points)]
            for span in evidence.source_spans
            if isinstance(span, ZoteroPdfSpan)
        ]
        if not spans or any(
            span.attachment_key != analyzed.zotero.attachment_key for span in spans
        ):
            raise ProviderBootstrapError("v4 PDF evidence differs from the verified attachment")
        payloads = _canonical_payloads(request, bundle, baseline)
        stem = request.document.artifact_id
        declarations = [
            (stem, "analysis_markdown", request.paths.markdown),
            (f"{stem}:canvas", "analysis_canvas", request.paths.canvas),
            (f"{stem}:sidecar", "analysis_sidecar", request.paths.sidecar),
        ]
        artifacts = [
            KnowledgeArtifactChange(
                artifact_id=artifact_id,
                resource_id=request.resource_id,
                kind=kind,
                vault_path=path,
                sha256="sha256:" + hashlib.sha256(payloads[path]).hexdigest(),
            )
            for artifact_id, kind, path in declarations
        ]
        prepared = prepare_joint_paper_placement(
            snapshot=base,
            request=request,
            vault_binding=vault_binding,
            transaction_id="bootstrap-graph-only",
            plan_digest=paper_plan.plan_digest,
            source_note_path=move.old_path,
            destination_note_path=move.new_path,
            note_sha256=move.after_sha256,
            new_artifacts=artifacts,
        )
        manifest_data = prepared.manifest.model_dump(mode="json")
        moved = {row.resource_id: row.new_path for row in paper_plan.moves}
        for resource in manifest_data["atomic_resources"]:
            resource["markdown_path"] = moved[resource["resource_id"]]
        after_manifest = KnowledgeManifest.model_validate(manifest_data)
        after = KnowledgeProviderSnapshot(
            vault_binding=vault_binding,
            manifest=after_manifest,
            artifacts=list(prepared.artifacts),
            relations=list(prepared.relations),
            projections=list(prepared.projections),
            catalog=prepared.catalog,
            receipts=[],
        )
        return BootstrapProviderGraphs(base=base, after=after)
    except ProviderBootstrapError:
        raise
    except (KnowledgeApplyError, TypeError, ValueError) as exc:
        raise ProviderBootstrapError(str(exc)) from exc


def build_bootstrap_provider_after(
    *,
    field: FieldDefinition,
    paper_plan: PaperFolderingPlan,
    verified_papers: Sequence[HubResource],
    reviewed_source_note_paths: Sequence[str],
    core_documents: Sequence[KnowledgeCoreDocument],
    vault_binding: KnowledgeVaultBinding,
    generated_at: datetime,
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
    explicitly_removed_navigation_targets: Sequence[str] = (),
) -> KnowledgeProviderSnapshot:
    """Return only the prospective graph for a joint coordinator's after member."""
    return build_bootstrap_provider_graphs(
        field=field,
        paper_plan=paper_plan,
        verified_papers=verified_papers,
        reviewed_source_note_paths=reviewed_source_note_paths,
        core_documents=core_documents,
        vault_binding=vault_binding,
        generated_at=generated_at,
        request=request,
        bundle=bundle,
        baseline=baseline,
        explicitly_removed_navigation_targets=explicitly_removed_navigation_targets,
    ).after


__all__ = [
    "BootstrapProviderGraphs",
    "ProviderBootstrapError",
    "build_bootstrap_provider_after",
    "build_bootstrap_provider_base",
    "build_bootstrap_provider_graphs",
]
