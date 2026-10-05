"""Apply explicit KnowledgeChangeSet records to one authoritative snapshot.

The snapshot is the durable provider declaration plus its rebuildable HubCatalog
projection.  Applying a change never scans the Vault, Markdown, projects, or the
host PATH.  One locked, atomic replacement commits the manifest, catalog, and
receipt together.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from scholar_workflow.analysis.models import (
    AnalysisCommitRequest,
    KnowledgeArtifactChange,
    KnowledgeChangeSet,
)
from scholar_workflow.knowledge.catalog_models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
)
from scholar_workflow.knowledge.models import (
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
    KnowledgeSupportingDocument,
    SupportingDocumentKind,
    _validate_vault_path,
)
from scholar_workflow.models import ResourceKind

_SNAPSHOT_NAME = "knowledge-provider.snapshot.json"
_LOCK_NAME = ".knowledge-provider.apply.lock"
_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
_RESERVED_CONTROL_PLANE_NAMESPACES = frozenset({"project", "projects", "tool", "tools"})
_VISIBLE_ARTIFACTS = {
    "analysis_markdown": (
        SupportingDocumentKind.ANALYSIS,
        ArtifactKind.PAPER_ANALYSIS,
        ArtifactFormat.MARKDOWN,
    ),
    "analysis_canvas": (
        SupportingDocumentKind.ANALYSIS_CANVAS,
        ArtifactKind.ANALYSIS_CANVAS,
        ArtifactFormat.CANVAS,
    ),
}


class KnowledgeApplyError(RuntimeError):
    """Base error for provider snapshot application."""


class KnowledgeApplyConflict(KnowledgeApplyError):
    """The change does not match the current provider revision or identity."""


class KnowledgeApplySafetyError(KnowledgeApplyError):
    """The provider state boundary cannot be used safely."""


class KnowledgeApplyReceipt(BaseModel):
    """Stable result of one successfully applied semantic change."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    receipt_id: str = Field(pattern=r"^knowledge-apply:[0-9a-f]{64}$")
    change_id: str = Field(pattern=r"^change:[0-9a-f]{64}$")
    change_fingerprint: str = Field(pattern=_HASH_PATTERN)
    source_receipt: str = Field(min_length=1, max_length=256)
    before_catalog_revision: str = Field(pattern=_HASH_PATTERN)
    after_catalog_revision: str = Field(pattern=_HASH_PATTERN)
    applied_at: AwareDatetime
    applied_artifact_ids: list[str]

    @model_validator(mode="after")
    def validate_artifact_ids(self) -> Self:
        if self.applied_artifact_ids != sorted(set(self.applied_artifact_ids)):
            raise ValueError("applied_artifact_ids must be sorted and unique")
        semantic = self.model_dump(
            mode="json",
            exclude={"schema_version", "receipt_id", "applied_at"},
        )
        expected = "knowledge-apply:" + _hash_payload(semantic).removeprefix("sha256:")
        if self.receipt_id != expected:
            raise ValueError("knowledge apply receipt ID does not match its content")
        return self


class KnowledgeVaultBinding(BaseModel):
    """Host-local filesystem identity of the Vault owning a provider snapshot."""

    model_config = ConfigDict(extra="forbid")

    root_path: str = Field(min_length=1)
    device: int = Field(ge=0)
    inode: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_root_path(self) -> Self:
        if not os.path.isabs(self.root_path) or os.path.normpath(self.root_path) != self.root_path:
            raise ValueError("Vault binding path must be an absolute normalized path")
        return self


class JointPaperPlacementReceipt(BaseModel):
    """Provider member of a committed, recoverable Provider/Field transaction.

    This receipt is durable only with the snapshot that contains it. It is not
    proof that the enclosing Field journal has completed or that a backup exists.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    kind: Literal["joint-paper-placement"] = "joint-paper-placement"
    receipt_id: str = Field(pattern=r"^knowledge-placement:[0-9a-f]{64}$")
    change_id: str = Field(pattern=r"^placement:[0-9a-f]{64}$")
    transaction_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    plan_digest: str = Field(pattern=_HASH_PATTERN)
    before_snapshot_revision: str = Field(pattern=_HASH_PATTERN)
    before_catalog_revision: str = Field(pattern=_HASH_PATTERN)
    after_catalog_revision: str = Field(pattern=_HASH_PATTERN)
    resource_id: str = Field(min_length=1, max_length=256)
    zotero_item_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    source_note_path: str
    destination_note_path: str
    note_sha256: str = Field(pattern=_HASH_PATTERN)
    applied_artifact_ids: list[str] = Field(min_length=3, max_length=3)
    applied_at: AwareDatetime

    @model_validator(mode="after")
    def validate_placement(self) -> Self:
        for path in (self.source_note_path, self.destination_note_path):
            _validate_vault_path(path, suffix=".md")
        if self.source_note_path == self.destination_note_path:
            raise ValueError("joint placement requires a distinct owner note destination")
        if self.applied_artifact_ids != sorted(set(self.applied_artifact_ids)):
            raise ValueError("applied_artifact_ids must be sorted and unique")
        semantic = self.model_dump(
            mode="json", exclude={"schema_version", "receipt_id", "change_id", "applied_at"}
        )
        fingerprint = _hash_payload(semantic).removeprefix("sha256:")
        if self.change_id != f"placement:{fingerprint}" or (
            self.receipt_id != f"knowledge-placement:{fingerprint}"
        ):
            raise ValueError("joint placement receipt IDs do not match its content")
        return self


ProviderReceipt = KnowledgeApplyReceipt | JointPaperPlacementReceipt


class KnowledgeProviderSnapshot(BaseModel):
    """One authoritative provider manifest and its derived catalog snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    snapshot_revision: str = Field(default="", pattern=r"^(?:|sha256:[0-9a-f]{64})$")
    vault_binding: KnowledgeVaultBinding | None = None
    manifest: KnowledgeManifest
    artifacts: list[KnowledgeArtifactChange] = Field(default_factory=list)
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    projections: list[KnowledgeProjection] = Field(default_factory=list)
    catalog: HubCatalog
    receipts: list[ProviderReceipt] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_provider_graph(self) -> Self:
        for resource in self.manifest.atomic_resources:
            _reject_control_plane_identity(resource.resource_id)
        for document in self.manifest.core_documents:
            _reject_control_plane_identity(document.document_id)
        for document in self.manifest.supporting_documents:
            _reject_control_plane_identity(document.document_id)
            _reject_control_plane_identity(document.owner_id)
        atomic_ids = {item.resource_id for item in self.manifest.atomic_resources}
        core_ids = {item.document_id for item in self.manifest.core_documents}
        supporting = {
            item.document_id: item for item in self.manifest.supporting_documents
        }
        primary_ids = atomic_ids | core_ids
        manifest_path_owners = {
            **{
                item.markdown_path: item.resource_id
                for item in self.manifest.atomic_resources
            },
            **{
                item.markdown_path: item.document_id
                for item in self.manifest.core_documents
            },
            **{
                item.vault_path: item.document_id
                for item in self.manifest.supporting_documents
            },
        }
        artifacts = _unique_by(self.artifacts, "artifact_id", "provider artifact")
        artifact_paths = _unique_by(self.artifacts, "vault_path", "provider artifact path")
        if len(artifact_paths) != len(artifacts):
            raise ValueError("provider artifact paths must be globally unique")

        for artifact in artifacts.values():
            _reject_control_plane_identity(artifact.artifact_id)
            _reject_control_plane_identity(artifact.resource_id)
            if artifact.artifact_id in primary_ids:
                raise ValueError(
                    f"provider artifact collides with a primary Knowledge ID: "
                    f"{artifact.artifact_id}"
                )
            if artifact.resource_id not in atomic_ids:
                raise ValueError(
                    f"provider artifact owner is not an atomic resource: {artifact.artifact_id}"
                )
            visible = _VISIBLE_ARTIFACTS.get(artifact.kind)
            path_owner = manifest_path_owners.get(artifact.vault_path)
            if visible is None:
                if artifact.artifact_id in supporting or path_owner is not None:
                    raise ValueError(
                        f"provider sidecar collides with a declared Knowledge object: "
                        f"{artifact.artifact_id}"
                    )
                continue
            expected_support_kind, _, _ = visible
            declaration = supporting.get(artifact.artifact_id)
            if declaration is None or (
                declaration.kind is not expected_support_kind
                or declaration.owner_id != artifact.resource_id
                or declaration.vault_path != artifact.vault_path
            ):
                raise ValueError(
                    f"visible artifact declaration differs from its owner manifest: "
                    f"{artifact.artifact_id}"
                )
            if path_owner != artifact.artifact_id:
                raise ValueError(
                    f"visible provider artifact path has another manifest owner: "
                    f"{artifact.artifact_id}"
                )

        known_ids = atomic_ids | core_ids | set(supporting) | set(artifacts)
        relation_keys: set[tuple[str, str, str]] = set()
        for relation in self.relations:
            key = (relation.from_id, relation.relation, relation.to_id)
            if key in relation_keys:
                raise ValueError("duplicate provider relation")
            relation_keys.add(key)
            _validate_relation(relation, known_ids=known_ids, artifacts=artifacts)

        projection_ids: set[str] = set()
        for projection in self.projections:
            if projection.projection_id in projection_ids:
                raise ValueError("projection_id must be globally unique")
            projection_ids.add(projection.projection_id)
            _validate_projection(projection, known_ids=known_ids)

        receipt_ids: set[str] = set()
        change_ids: set[str] = set()
        artifact_ids = set(artifacts)
        previous_after_revision: str | None = None
        for receipt in self.receipts:
            if receipt.receipt_id in receipt_ids or receipt.change_id in change_ids:
                raise ValueError("provider receipts must have unique receipt and change IDs")
            if (
                previous_after_revision is not None
                and receipt.before_catalog_revision != previous_after_revision
            ):
                raise ValueError("provider receipt catalog revisions must form one chain")
            unknown = set(receipt.applied_artifact_ids) - artifact_ids
            if unknown:
                raise ValueError(
                    f"provider receipt references unknown artifacts: {sorted(unknown)}"
                )
            if isinstance(receipt, JointPaperPlacementReceipt):
                owner = next(
                    (row for row in self.catalog.resources if row.resource_id == receipt.resource_id),
                    None,
                )
                if owner is None or owner.kind is not ResourceKind.PAPER or (
                    owner.zotero.item_key != receipt.zotero_item_key
                ) or any(
                    artifacts[value].resource_id != receipt.resource_id
                    for value in receipt.applied_artifact_ids
                ):
                    raise ValueError("joint placement receipt has a different PAPER owner")
            receipt_ids.add(receipt.receipt_id)
            change_ids.add(receipt.change_id)
            previous_after_revision = receipt.after_catalog_revision
        if (
            previous_after_revision is not None
            and previous_after_revision != self.catalog.revision
        ):
            raise ValueError("latest provider receipt does not match catalog revision")

        _validate_catalog_projection(self)
        computed = self.compute_revision()
        if self.snapshot_revision and self.snapshot_revision != computed:
            raise ValueError("provider snapshot revision does not match its contents")
        self.snapshot_revision = computed
        return self

    def compute_revision(self) -> str:
        """Return a semantic revision independent of timestamps and list ordering."""
        payload = {
            "manifest": self.manifest.model_dump(mode="json"),
            "artifacts": sorted(
                (item.model_dump(mode="json") for item in self.artifacts),
                key=lambda row: row["artifact_id"],
            ),
            "relations": sorted(
                (item.model_dump(mode="json") for item in self.relations),
                key=lambda row: (row["from_id"], row["relation"], row["to_id"]),
            ),
            "projections": sorted(
                (item.model_dump(mode="json") for item in self.projections),
                key=lambda row: row["projection_id"],
            ),
            "catalog_revision": self.catalog.revision,
            "receipts": sorted(
                (
                    item.model_dump(mode="json", exclude={"applied_at"})
                    for item in self.receipts
                ),
                key=lambda row: row["change_id"],
            ),
        }
        if self.vault_binding is not None:
            payload["vault_binding"] = self.vault_binding.model_dump(mode="json")
        return _hash_payload(payload)


FaultInjector = Callable[[str], None]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PreparedJointPaperPlacement:
    """Prospective graph only; never persist this as a provider snapshot.

    The enclosing journal owns filesystem conformance, registration, writer
    pause, source/destination CAS, and recovery. Preparation reads no files.
    """

    request: AnalysisCommitRequest
    vault_binding: KnowledgeVaultBinding
    transaction_id: str
    plan_digest: str
    source_note_path: str
    destination_note_path: str
    note_sha256: str
    new_artifacts: tuple[KnowledgeArtifactChange, ...]
    before_snapshot_revision: str
    before_catalog_revision: str
    after_catalog_revision: str
    manifest: KnowledgeManifest
    artifacts: tuple[KnowledgeArtifactChange, ...]
    relations: tuple[KnowledgeRelation, ...]
    projections: tuple[KnowledgeProjection, ...]
    catalog: HubCatalog


@dataclass(frozen=True)
class FinalizedJointPaperPlacement:
    """Validated commit payload; becomes durable only when the journal publishes it."""

    before_snapshot_revision: str
    after_snapshot_revision: str
    snapshot: KnowledgeProviderSnapshot
    payload: bytes
    receipt: JointPaperPlacementReceipt


def prepare_joint_paper_placement(
    *,
    snapshot: KnowledgeProviderSnapshot,
    request: AnalysisCommitRequest,
    vault_binding: KnowledgeVaultBinding,
    transaction_id: str,
    plan_digest: str,
    source_note_path: str,
    destination_note_path: str,
    note_sha256: str,
    new_artifacts: list[KnowledgeArtifactChange] | tuple[KnowledgeArtifactChange, ...],
) -> PreparedJointPaperPlacement:
    """Prepare an additive v4 graph and one PAPER note move without disk writes.

    The caller supplies artifacts whose exact bytes passed bundle conformance.
    This function validates provider identity and graph ownership, not the files.
    Prior artifacts, relations, projections, and receipts cannot be removed here.
    """
    try:
        snapshot = KnowledgeProviderSnapshot.model_validate(snapshot.model_dump(mode="json"))
        request = AnalysisCommitRequest.model_validate(request.model_dump(mode="json"))
        if request.document.schema_version != 4:
            raise ValueError("joint placement requires IR v4")
        if request.base_snapshot_revision != snapshot.snapshot_revision:
            raise ValueError("full provider snapshot revision changed")
        if request.base_catalog_revision != snapshot.catalog.revision:
            raise ValueError("provider catalog revision changed")
        if snapshot.vault_binding is None or snapshot.vault_binding != vault_binding:
            raise ValueError("provider Vault binding differs from the registered Vault")
        if any(isinstance(row, JointPaperPlacementReceipt) and
               row.transaction_id == transaction_id for row in snapshot.receipts):
            raise ValueError("joint transaction ID is already committed")
        for path in (source_note_path, destination_note_path):
            _validate_vault_path(path, suffix=".md")
        if source_note_path == destination_note_path:
            raise ValueError("joint placement requires a distinct owner note destination")
        if PurePosixPath(destination_note_path).parent != PurePosixPath(request.paths.markdown).parent:
            raise ValueError("owner note must share the new analysis paper folder")
        owner = next(
            (row for row in snapshot.manifest.atomic_resources
             if row.resource_id == request.resource_id), None
        )
        catalog_owner = next(
            (row for row in snapshot.catalog.resources if row.resource_id == request.resource_id),
            None,
        )
        if owner is None or owner.kind is not ResourceKind.PAPER or (
            owner.markdown_path != source_note_path
        ) or catalog_owner is None or catalog_owner.kind is not ResourceKind.PAPER or (
            not request.zotero_item_key or catalog_owner.zotero.item_key != request.zotero_item_key
        ):
            raise ValueError("joint placement has no matching PAPER owner and Zotero key")
        incoming = [KnowledgeArtifactChange.model_validate(row.model_dump(mode="json"))
                    for row in new_artifacts]
        stem = request.document.artifact_id
        expected = {
            stem: ("analysis_markdown", request.paths.markdown),
            f"{stem}:canvas": ("analysis_canvas", request.paths.canvas),
            f"{stem}:sidecar": ("analysis_sidecar", request.paths.sidecar),
        }
        if len(incoming) != 3 or {row.artifact_id for row in incoming} != set(expected):
            raise ValueError("joint placement requires exactly the v4 artifact triple")
        if any(row.resource_id != request.resource_id or
               (row.kind, row.vault_path) != expected[row.artifact_id] for row in incoming):
            raise ValueError("joint placement artifacts differ from the v4 request")
        if any(value is not None for value in request.base_revisions.values()):
            raise ValueError("joint placement may only create new analysis artifacts")
        existing_ids = _known_knowledge_ids(snapshot.manifest, snapshot.artifacts)
        if existing_ids.intersection(expected):
            raise ValueError("joint placement artifact identity is already declared")
        existing_paths = {
            *(row.markdown_path for row in snapshot.manifest.atomic_resources),
            *(row.markdown_path for row in snapshot.manifest.core_documents),
            *(row.vault_path for row in snapshot.manifest.supporting_documents),
            *(row.vault_path for row in snapshot.artifacts),
            *(row.vault_path for row in snapshot.catalog.assets),
        }
        target_paths = {destination_note_path, *request.paths.as_list()}
        if len(target_paths) != 4 or target_paths.intersection(existing_paths):
            raise ValueError("joint placement target path already has an owner")
        target_folder = PurePosixPath(destination_note_path).parent
        managed_owners = [
            *((row.markdown_path, {row.resource_id}) for row in snapshot.manifest.atomic_resources),
            *((row.markdown_path, {row.document_id}) for row in snapshot.manifest.core_documents),
            *((row.vault_path, {row.owner_id}) for row in snapshot.manifest.supporting_documents),
            *((row.vault_path, {row.resource_id}) for row in snapshot.artifacts),
            *((row.vault_path, {row.resource_id or row.topic_id}) for row in snapshot.catalog.artifacts),
        ]
        catalog_artifacts = {row.artifact_id: row for row in snapshot.catalog.artifacts}
        for asset in snapshot.catalog.assets:
            asset_owners = {
                catalog_artifacts[value].resource_id or catalog_artifacts[value].topic_id
                if value in catalog_artifacts else None
                for value in asset.owner_artifact_ids
            }
            managed_owners.append((asset.vault_path, asset_owners))
        if any(
            PurePosixPath(path).is_relative_to(target_folder)
            and owners != {request.resource_id}
            for path, owners in managed_owners
        ):
            raise ValueError("joint placement paper folder belongs to another resource")
        # Reuse the additive artifact validator, then apply the explicitly reviewed note move.
        change = KnowledgeChangeSet(
            change_id="change:" + "0" * 64,
            source_receipt=f"joint-field:{transaction_id}",
            base_catalog_revision=snapshot.catalog.revision,
            upsert_artifacts=incoming,
            expected_base_hashes={row.vault_path: None for row in incoming},
        )
        manifest, artifacts = _apply_artifacts(snapshot, change)
        for row in manifest.supporting_documents:
            if row.document_id == stem:
                row.title = f"{request.document.paper_title} analysis"
            elif row.document_id == f"{stem}:canvas":
                row.title = f"{request.document.paper_title} analysis Canvas"
        for row in manifest.atomic_resources:
            if row.resource_id == request.resource_id:
                row.markdown_path = destination_note_path
        manifest = KnowledgeManifest.model_validate(manifest.model_dump(mode="json"))
        known_ids = _known_knowledge_ids(manifest, artifacts)
        relations = _merge_relations(
            snapshot.relations, request.relations, known_ids=known_ids,
            artifacts={row.artifact_id: row for row in artifacts},
        )
        projections = _merge_projections(
            snapshot.projections, request.projections, known_ids=known_ids,
        )
        catalog = _apply_catalog(
            snapshot.catalog, manifest=manifest, artifacts=artifacts,
            changed=incoming, generated_at=snapshot.catalog.generated_at,
        )
        # Validate the complete prospective graph without inventing an applied receipt.
        KnowledgeProviderSnapshot(
            vault_binding=vault_binding, manifest=manifest, artifacts=artifacts,
            relations=relations, projections=projections, catalog=catalog,
        )
        prepared = PreparedJointPaperPlacement(
            request=request, vault_binding=vault_binding.model_copy(deep=True),
            transaction_id=transaction_id, plan_digest=plan_digest,
            source_note_path=source_note_path, destination_note_path=destination_note_path,
            note_sha256=note_sha256, new_artifacts=tuple(incoming),
            before_snapshot_revision=snapshot.snapshot_revision,
            before_catalog_revision=snapshot.catalog.revision,
            after_catalog_revision=catalog.revision,
            manifest=manifest, artifacts=tuple(artifacts), relations=tuple(relations),
            projections=tuple(projections), catalog=catalog,
        )
        # Validate receipt-shaped identifiers without creating an applied receipt.
        if not transaction_id or len(transaction_id) > 128 or any(
            not (char.isascii() and (char.isalnum() or char in "_-"))
            for char in transaction_id
        ) or not transaction_id[0].isalnum():
            raise ValueError("invalid joint transaction ID")
        if any(len(value) != 71 or not value.startswith("sha256:") or any(
            char not in "0123456789abcdef" for char in value[7:]
        ) for value in (plan_digest, note_sha256)):
            raise ValueError("joint placement hashes must use sha256:<hex>")
        return prepared
    except (ValueError, ValidationError) as exc:
        raise KnowledgeApplyConflict(str(exc)) from None


def finalize_joint_paper_placement(
    prepared: PreparedJointPaperPlacement,
    *,
    current_snapshot: KnowledgeProviderSnapshot,
    committed_at: datetime,
) -> FinalizedJointPaperPlacement:
    """Encode the provider commit member after the joint coordinator reacquires CAS.

    No writes occur here. The coordinator must journal these exact bytes before
    replacing any member, publish the provider last, and conditionally recover all
    members on failure. Only that publication makes the enclosed receipt durable.
    """
    checked = prepare_joint_paper_placement(
        snapshot=current_snapshot, request=prepared.request,
        vault_binding=prepared.vault_binding, transaction_id=prepared.transaction_id,
        plan_digest=prepared.plan_digest, source_note_path=prepared.source_note_path,
        destination_note_path=prepared.destination_note_path, note_sha256=prepared.note_sha256,
        new_artifacts=prepared.new_artifacts,
    )
    if checked != prepared:
        raise KnowledgeApplyConflict("prospective joint placement changed after preparation")
    if committed_at.utcoffset() is None:
        raise KnowledgeApplySafetyError("joint commit clock must return an aware datetime")
    semantic = {
        "kind": "joint-paper-placement", "transaction_id": prepared.transaction_id,
        "plan_digest": prepared.plan_digest,
        "before_snapshot_revision": prepared.before_snapshot_revision,
        "before_catalog_revision": prepared.before_catalog_revision,
        "after_catalog_revision": prepared.after_catalog_revision,
        "resource_id": prepared.request.resource_id,
        "zotero_item_key": prepared.request.zotero_item_key,
        "source_note_path": prepared.source_note_path,
        "destination_note_path": prepared.destination_note_path,
        "note_sha256": prepared.note_sha256,
        "applied_artifact_ids": sorted(row.artifact_id for row in prepared.new_artifacts),
    }
    digest = _hash_payload(semantic).removeprefix("sha256:")
    receipt = JointPaperPlacementReceipt(
        **semantic, receipt_id=f"knowledge-placement:{digest}", change_id=f"placement:{digest}",
        applied_at=committed_at,
    )
    catalog = prepared.catalog.model_copy(deep=True)
    catalog.generated_at = committed_at
    after = KnowledgeProviderSnapshot(
        vault_binding=prepared.vault_binding, manifest=prepared.manifest,
        artifacts=list(prepared.artifacts), relations=list(prepared.relations),
        projections=list(prepared.projections), catalog=catalog,
        receipts=[*current_snapshot.receipts, receipt],
    )
    return FinalizedJointPaperPlacement(
        before_snapshot_revision=prepared.before_snapshot_revision,
        after_snapshot_revision=after.snapshot_revision,
        snapshot=after, payload=_json_bytes(after.model_dump(mode="json")), receipt=receipt,
    )


class KnowledgeSnapshotCatalogProvider:
    """Read the derived HubCatalog from an atomic Knowledge provider snapshot."""

    def __init__(self, state_root: Path) -> None:
        self.state_root = Path(state_root)

    def load(self) -> HubCatalog:
        return load_knowledge_provider_snapshot(self.state_root).catalog


def initialize_knowledge_provider_snapshot(
    *,
    state_root: Path,
    vault_root: Path | None = None,
    manifest: KnowledgeManifest,
    catalog: HubCatalog,
    artifacts: list[KnowledgeArtifactChange] | None = None,
    relations: list[KnowledgeRelation] | None = None,
    projections: list[KnowledgeProjection] | None = None,
) -> KnowledgeProviderSnapshot:
    """Create a provider snapshot once; an existing state is never overwritten."""
    snapshot = KnowledgeProviderSnapshot(
        vault_binding=_vault_binding_for_root(vault_root) if vault_root is not None else None,
        manifest=manifest,
        artifacts=artifacts or [],
        relations=relations or [],
        projections=projections or [],
        catalog=catalog,
    )
    payload = _json_bytes(snapshot.model_dump(mode="json"))
    with _locked_state_root(state_root) as root:
        root.ensure_current()
        if _entry_exists(root.fd, _SNAPSHOT_NAME):
            raise KnowledgeApplyConflict("knowledge provider snapshot already exists")
        _atomic_create(root.fd, _SNAPSHOT_NAME, payload)
        root.ensure_current()
    return snapshot


def load_knowledge_provider_snapshot(state_root: Path) -> KnowledgeProviderSnapshot:
    """Load and fully validate the explicit provider snapshot without discovery."""
    with _open_state_root(state_root) as root:
        root.ensure_current()
        snapshot, _, _ = _read_snapshot(root.fd)
        root.ensure_current()
    return snapshot


def apply_knowledge_change_set(
    *,
    state_root: Path,
    change_set: KnowledgeChangeSet,
    clock: Clock | None = None,
    fault_inject: FaultInjector | None = None,
    before_apply: Callable[[KnowledgeProviderSnapshot], None] | None = None,
) -> KnowledgeApplyReceipt:
    """CAS-apply one explicit change and atomically persist its receipt.

    Replaying identical content returns the original receipt even after later
    changes.  Reusing a change ID for other content or presenting a stale catalog
    revision fails closed.
    """
    _verify_change_identity(change_set)
    fingerprint = _change_fingerprint(change_set)
    with _locked_state_root(state_root) as root:
        root.ensure_current()
        snapshot, before_bytes, before_identity = _read_snapshot(root.fd)
        if before_apply is not None:
            before_apply(snapshot)
        prior = next(
            (item for item in snapshot.receipts if item.change_id == change_set.change_id),
            None,
        )
        if prior is not None:
            if prior.change_fingerprint != fingerprint:
                raise KnowledgeApplyConflict("change_id was reused for different content")
            _verify_replay_postconditions(snapshot, change_set, prior)
            return prior

        if change_set.base_catalog_revision is None:
            raise KnowledgeApplyConflict("base_catalog_revision is required for provider apply")
        if change_set.base_catalog_revision != snapshot.catalog.revision:
            raise KnowledgeApplyConflict("base catalog revision changed; refusing to apply")

        applied_at = (clock or _utc_now)()
        if applied_at.utcoffset() is None:
            raise KnowledgeApplySafetyError("apply clock must return an aware datetime")
        try:
            manifest, artifacts = _apply_artifacts(snapshot, change_set)
            known_ids = _known_knowledge_ids(manifest, artifacts)
            relations = _merge_relations(
                snapshot.relations,
                change_set.upsert_relations,
                known_ids=known_ids,
                artifacts={item.artifact_id: item for item in artifacts},
            )
            projections = _merge_projections(
                snapshot.projections,
                change_set.upsert_projections,
                known_ids=known_ids,
            )
            catalog = _apply_catalog(
                snapshot.catalog,
                manifest=manifest,
                artifacts=artifacts,
                changed=change_set.upsert_artifacts,
                generated_at=applied_at,
            )
            receipt = _make_receipt(
                change_set,
                fingerprint=fingerprint,
                before_revision=snapshot.catalog.revision,
                after_revision=catalog.revision,
                applied_at=applied_at,
            )
            updated = KnowledgeProviderSnapshot(
                vault_binding=snapshot.vault_binding,
                manifest=manifest,
                artifacts=artifacts,
                relations=relations,
                projections=projections,
                catalog=catalog,
                receipts=[*snapshot.receipts, receipt],
            )
        except (ValidationError, ValueError) as exc:
            raise KnowledgeApplyConflict(str(exc)) from None
        payload = _json_bytes(updated.model_dump(mode="json"))
        if fault_inject is not None:
            fault_inject("before-snapshot-replace")
        root.ensure_current()
        _atomic_replace_if_unchanged(
            root.fd,
            _SNAPSHOT_NAME,
            payload,
            expected_bytes=before_bytes,
            expected_identity=before_identity,
        )
        root.ensure_current()
        if fault_inject is not None:
            fault_inject("after-snapshot-replace")
        root.ensure_current()
        return receipt


def _apply_artifacts(
    snapshot: KnowledgeProviderSnapshot,
    change_set: KnowledgeChangeSet,
) -> tuple[KnowledgeManifest, list[KnowledgeArtifactChange]]:
    incoming = _unique_by(
        change_set.upsert_artifacts,
        "artifact_id",
        "change-set artifact",
    )
    incoming_paths = _unique_by(
        change_set.upsert_artifacts,
        "vault_path",
        "change-set artifact path",
    )
    if len(incoming_paths) != len(incoming):
        raise KnowledgeApplyConflict("change-set artifact paths must be unique")
    expected_paths = {item.vault_path for item in change_set.upsert_artifacts}
    if set(change_set.expected_base_hashes) != expected_paths:
        raise KnowledgeApplyConflict(
            "expected_base_hashes must exactly cover changed artifact paths"
        )

    atomic_ids = {item.resource_id for item in snapshot.manifest.atomic_resources}
    current = {item.artifact_id: item for item in snapshot.artifacts}
    paths = {item.vault_path: item.artifact_id for item in snapshot.artifacts}
    for artifact in incoming.values():
        _reject_control_plane_identity(artifact.artifact_id)
        _reject_control_plane_identity(artifact.resource_id)
        if artifact.resource_id not in atomic_ids:
            raise KnowledgeApplyConflict(
                f"artifact owner is not an explicit atomic resource: {artifact.resource_id}"
            )
        existing = current.get(artifact.artifact_id)
        expected_hash = change_set.expected_base_hashes[artifact.vault_path]
        if existing is None:
            if expected_hash is not None:
                raise KnowledgeApplyConflict(
                    f"new artifact requires a null base hash: {artifact.artifact_id}"
                )
            occupied = paths.get(artifact.vault_path)
            if occupied is not None:
                raise KnowledgeApplyConflict(
                    f"artifact path already belongs to another ID: {occupied}"
                )
        else:
            immutable = (existing.resource_id, existing.kind, existing.vault_path)
            proposed = (artifact.resource_id, artifact.kind, artifact.vault_path)
            if immutable != proposed:
                raise KnowledgeApplyConflict(
                    f"artifact immutable identity changed: {artifact.artifact_id}"
                )
            if expected_hash != existing.sha256:
                raise KnowledgeApplyConflict(
                    f"artifact base hash changed: {artifact.artifact_id}"
                )
        current[artifact.artifact_id] = artifact
        paths[artifact.vault_path] = artifact.artifact_id

    manifest = snapshot.manifest.model_copy(deep=True)
    support = {item.document_id: item for item in manifest.supporting_documents}
    for artifact in incoming.values():
        visible = _VISIBLE_ARTIFACTS.get(artifact.kind)
        if visible is None:
            continue
        support_kind, _, _ = visible
        declaration = support.get(artifact.artifact_id)
        if declaration is None:
            support[artifact.artifact_id] = KnowledgeSupportingDocument(
                document_id=artifact.artifact_id,
                kind=support_kind,
                title=artifact.artifact_id,
                vault_path=artifact.vault_path,
                owner_id=artifact.resource_id,
            )
            continue
        if (
            declaration.kind is not support_kind
            or declaration.vault_path != artifact.vault_path
            or declaration.owner_id != artifact.resource_id
        ):
            raise KnowledgeApplyConflict(
                f"artifact owner manifest conflicts with change: {artifact.artifact_id}"
            )
    manifest.supporting_documents = sorted(
        support.values(),
        key=lambda item: item.document_id,
    )
    manifest = KnowledgeManifest.model_validate(manifest.model_dump(mode="json"))
    return manifest, sorted(current.values(), key=lambda item: item.artifact_id)


def _merge_relations(
    current: list[KnowledgeRelation],
    incoming: list[KnowledgeRelation],
    *,
    known_ids: set[str],
    artifacts: dict[str, KnowledgeArtifactChange],
) -> list[KnowledgeRelation]:
    merged: dict[tuple[str, str, str], KnowledgeRelation] = {}
    for relation in [*current, *incoming]:
        _validate_relation(relation, known_ids=known_ids, artifacts=artifacts)
        merged[(relation.from_id, relation.relation, relation.to_id)] = relation
    return [merged[key] for key in sorted(merged)]


def _merge_projections(
    current: list[KnowledgeProjection],
    incoming: list[KnowledgeProjection],
    *,
    known_ids: set[str],
) -> list[KnowledgeProjection]:
    merged = {item.projection_id: item for item in current}
    for projection in incoming:
        _validate_projection(projection, known_ids=known_ids)
        existing = merged.get(projection.projection_id)
        if existing is not None and existing != projection:
            raise KnowledgeApplyConflict(
                f"projection immutable identity changed: {projection.projection_id}"
            )
        merged[projection.projection_id] = projection
    return [merged[key] for key in sorted(merged)]


def _apply_catalog(
    catalog: HubCatalog,
    *,
    manifest: KnowledgeManifest,
    artifacts: list[KnowledgeArtifactChange],
    changed: list[KnowledgeArtifactChange],
    generated_at: datetime,
) -> HubCatalog:
    result = catalog.model_copy(deep=True)
    resources = {item.resource_id: item for item in result.resources}
    manifest_resources = {item.resource_id: item for item in manifest.atomic_resources}
    catalog_artifacts = {item.artifact_id: item for item in result.artifacts}
    provider_artifacts = {item.artifact_id: item for item in artifacts}

    for artifact in sorted(changed, key=lambda item: item.artifact_id):
        resource = resources.get(artifact.resource_id)
        declaration = manifest_resources.get(artifact.resource_id)
        if resource is None or declaration is None:
            raise KnowledgeApplyConflict(
                f"catalog has no explicit artifact owner: {artifact.resource_id}"
            )
        if resource.kind != declaration.kind:
            raise KnowledgeApplyConflict(
                f"catalog resource kind conflicts with manifest: {artifact.resource_id}"
            )
        visible = _VISIBLE_ARTIFACTS.get(artifact.kind)
        if visible is None:
            if artifact.artifact_id in catalog_artifacts:
                raise KnowledgeApplyConflict("analysis sidecars cannot enter knowledge_catalog")
            continue
        _, artifact_kind, artifact_format = visible
        proposed = HubArtifact(
            artifact_id=artifact.artifact_id,
            kind=artifact_kind,
            format=artifact_format,
            vault_path=artifact.vault_path,
            resource_id=artifact.resource_id,
            revision=artifact.sha256,
        )
        existing = catalog_artifacts.get(artifact.artifact_id)
        if existing is not None:
            immutable = existing.model_dump(
                mode="json",
                exclude={"revision"},
            )
            proposed_immutable = proposed.model_dump(
                mode="json",
                exclude={"revision"},
            )
            if immutable != proposed_immutable:
                raise KnowledgeApplyConflict(
                    f"catalog artifact identity conflicts with provider manifest: "
                    f"{artifact.artifact_id}"
                )
            index = next(
                index
                for index, item in enumerate(result.artifacts)
                if item.artifact_id == artifact.artifact_id
            )
            result.artifacts[index] = proposed
        else:
            result.artifacts.append(proposed)
        catalog_artifacts[artifact.artifact_id] = proposed
        resource.artifact_ids = sorted(set(resource.artifact_ids) | {artifact.artifact_id})

    result.generated_at = generated_at
    result.revision = ""
    rebuilt = HubCatalog.model_validate(result.model_dump(mode="json"))
    for artifact_id, declaration in provider_artifacts.items():
        visible = _VISIBLE_ARTIFACTS.get(declaration.kind)
        projected = next(
            (item for item in rebuilt.artifacts if item.artifact_id == artifact_id),
            None,
        )
        if visible is None:
            if projected is not None:
                raise KnowledgeApplyConflict("analysis sidecars cannot enter knowledge_catalog")
            continue
        if projected is None or projected.revision != declaration.sha256:
            raise KnowledgeApplyConflict(
                f"catalog projection is incomplete for artifact: {artifact_id}"
            )
    return rebuilt


def _make_receipt(
    change_set: KnowledgeChangeSet,
    *,
    fingerprint: str,
    before_revision: str,
    after_revision: str,
    applied_at: datetime,
) -> KnowledgeApplyReceipt:
    semantic = {
        "change_id": change_set.change_id,
        "change_fingerprint": fingerprint,
        "source_receipt": change_set.source_receipt,
        "before_catalog_revision": before_revision,
        "after_catalog_revision": after_revision,
        "applied_artifact_ids": sorted(
            item.artifact_id for item in change_set.upsert_artifacts
        ),
    }
    receipt_hash = _hash_payload(semantic).removeprefix("sha256:")
    return KnowledgeApplyReceipt(
        receipt_id=f"knowledge-apply:{receipt_hash}",
        applied_at=applied_at,
        **semantic,
    )


def _verify_replay_postconditions(
    snapshot: KnowledgeProviderSnapshot,
    change_set: KnowledgeChangeSet,
    receipt: KnowledgeApplyReceipt,
) -> None:
    expected_ids = sorted(item.artifact_id for item in change_set.upsert_artifacts)
    if (
        receipt.source_receipt != change_set.source_receipt
        or receipt.applied_artifact_ids != expected_ids
    ):
        raise KnowledgeApplySafetyError(
            "stored provider receipt does not match the replayed change"
        )

    current_artifacts = {item.artifact_id: item for item in snapshot.artifacts}
    for requested in change_set.upsert_artifacts:
        current = current_artifacts.get(requested.artifact_id)
        if current is None or (
            current.resource_id,
            current.kind,
            current.vault_path,
        ) != (
            requested.resource_id,
            requested.kind,
            requested.vault_path,
        ):
            raise KnowledgeApplySafetyError(
                "stored provider receipt has no matching applied artifact"
            )

    relation_keys = {
        (item.from_id, item.relation, item.to_id) for item in snapshot.relations
    }
    if any(
        (item.from_id, item.relation, item.to_id) not in relation_keys
        for item in change_set.upsert_relations
    ):
        raise KnowledgeApplySafetyError(
            "stored provider receipt has no matching applied relation"
        )
    projections = {item.projection_id: item for item in snapshot.projections}
    if any(
        projections.get(item.projection_id) != item
        for item in change_set.upsert_projections
    ):
        raise KnowledgeApplySafetyError(
            "stored provider receipt has no matching applied projection"
        )


def _validate_catalog_projection(snapshot: KnowledgeProviderSnapshot) -> None:
    resources = {item.resource_id: item for item in snapshot.catalog.resources}
    catalog_artifacts = {item.artifact_id: item for item in snapshot.catalog.artifacts}
    manifest_resources = {
        item.resource_id: item for item in snapshot.manifest.atomic_resources
    }
    visible_artifacts = {
        item.artifact_id: item
        for item in snapshot.artifacts
        if item.kind in _VISIBLE_ARTIFACTS
    }
    if set(resources) != set(manifest_resources):
        raise ValueError(
            "catalog resources must exactly match explicit provider atomic resources"
        )
    if set(catalog_artifacts) != set(visible_artifacts):
        raise ValueError(
            "catalog artifacts must exactly match visible provider artifacts"
        )
    expected_owner_artifacts: dict[str, set[str]] = {
        resource_id: set() for resource_id in manifest_resources
    }
    for artifact in visible_artifacts.values():
        expected_owner_artifacts[artifact.resource_id].add(artifact.artifact_id)
    for resource_id, resource in resources.items():
        if set(resource.artifact_ids) != expected_owner_artifacts[resource_id]:
            raise ValueError(
                f"catalog resource artifact list differs from provider: {resource_id}"
            )

    for value in resources:
        _reject_control_plane_identity(value)
    for topic in snapshot.catalog.topics:
        _reject_control_plane_identity(topic.topic_id)
    for value in catalog_artifacts:
        _reject_control_plane_identity(value)
    for asset in snapshot.catalog.assets:
        _reject_control_plane_identity(asset.asset_id)
    for artifact in snapshot.artifacts:
        owner = resources.get(artifact.resource_id)
        declaration = manifest_resources.get(artifact.resource_id)
        if owner is None or declaration is None or owner.kind != declaration.kind:
            raise ValueError(
                f"catalog owner differs from provider manifest: {artifact.resource_id}"
            )
        visible = _VISIBLE_ARTIFACTS.get(artifact.kind)
        projected = catalog_artifacts.get(artifact.artifact_id)
        if visible is None:
            if projected is not None:
                raise ValueError("analysis sidecars cannot enter knowledge_catalog")
            continue
        _, kind, artifact_format = visible
        if projected is None or (
            projected.kind is not kind
            or projected.format is not artifact_format
            or projected.vault_path != artifact.vault_path
            or projected.resource_id != artifact.resource_id
            or projected.revision != artifact.sha256
            or artifact.artifact_id not in owner.artifact_ids
        ):
            raise ValueError(
                f"catalog projection differs from provider artifact: {artifact.artifact_id}"
            )


def _validate_relation(
    relation: KnowledgeRelation,
    *,
    known_ids: set[str],
    artifacts: dict[str, KnowledgeArtifactChange],
) -> None:
    _reject_control_plane_identity(relation.from_id)
    _reject_control_plane_identity(relation.to_id)
    if relation.from_id not in known_ids or relation.to_id not in known_ids:
        raise ValueError("knowledge relations may reference only explicit Knowledge IDs")
    if relation.relation == "has-analysis":
        target = artifacts.get(relation.to_id)
        if (
            target is None
            or target.kind != "analysis_markdown"
            or target.resource_id != relation.from_id
        ):
            raise ValueError("has-analysis must bind an analysis to its declared owner")


def _validate_projection(
    projection: KnowledgeProjection,
    *,
    known_ids: set[str],
) -> None:
    _reject_control_plane_identity(projection.projection_id)
    _reject_control_plane_identity(projection.target_id)
    if projection.kind.casefold() in _RESERVED_CONTROL_PLANE_NAMESPACES:
        raise ValueError("Projects and Tools cannot be Knowledge projections")
    if projection.target_id not in known_ids:
        raise ValueError("knowledge projections require an explicit Knowledge target")


def _known_knowledge_ids(
    manifest: KnowledgeManifest,
    artifacts: list[KnowledgeArtifactChange],
) -> set[str]:
    identifiers = {item.resource_id for item in manifest.atomic_resources}
    identifiers.update(item.document_id for item in manifest.core_documents)
    identifiers.update(item.document_id for item in manifest.supporting_documents)
    identifiers.update(item.artifact_id for item in artifacts)
    return identifiers


def _reject_control_plane_identity(value: str) -> None:
    namespace = value.split(":", 1)[0].split("/", 1)[0].casefold()
    if namespace in _RESERVED_CONTROL_PLANE_NAMESPACES:
        raise ValueError("Projects and Tools cannot enter a Knowledge provider snapshot")


def _unique_by(rows: list[Any], field: str, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        value = str(getattr(row, field))
        if value in result:
            raise ValueError(f"duplicate {label}: {value}")
        result[value] = row
    return result


def _verify_change_identity(change_set: KnowledgeChangeSet) -> None:
    payload = change_set.model_dump(
        mode="json",
        exclude={"schema_version", "change_id"},
    )
    expected = "change:" + _hash_payload(payload).removeprefix("sha256:")
    if change_set.change_id != expected:
        raise KnowledgeApplyConflict("change_id does not match change-set content")


def _change_fingerprint(change_set: KnowledgeChangeSet) -> str:
    return _hash_payload(change_set.model_dump(mode="json"))


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _StateRootBinding:
    path: Path
    fd: int
    device: int
    inode: int

    def ensure_current(self) -> None:
        try:
            path_info = os.stat(self.path, follow_symlinks=False)
            fd_info = os.fstat(self.fd)
        except OSError as exc:
            raise KnowledgeApplySafetyError(
                f"knowledge provider state root binding changed: {exc}"
            ) from exc
        if (
            not stat.S_ISDIR(path_info.st_mode)
            or not stat.S_ISDIR(fd_info.st_mode)
            or (path_info.st_dev, path_info.st_ino) != (self.device, self.inode)
            or (fd_info.st_dev, fd_info.st_ino) != (self.device, self.inode)
        ):
            raise KnowledgeApplySafetyError(
                "knowledge provider state root binding changed during operation"
            )


@contextmanager
def _open_state_root(state_root: Path) -> Iterator[_StateRootBinding]:
    path = Path(os.path.abspath(state_root))
    root_fd: int | None = None
    try:
        if path.is_symlink():
            raise KnowledgeApplySafetyError("knowledge provider state root cannot be a symlink")
        if not path.is_dir():
            raise KnowledgeApplySafetyError("knowledge provider state root must be a directory")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        root_fd = os.open(path, flags)
        info = os.fstat(root_fd)
        binding = _StateRootBinding(
            path=path,
            fd=root_fd,
            device=info.st_dev,
            inode=info.st_ino,
        )
        binding.ensure_current()
    except (OSError, RuntimeError) as exc:
        if root_fd is not None:
            os.close(root_fd)
        if isinstance(exc, KnowledgeApplySafetyError):
            raise
        raise KnowledgeApplySafetyError(f"cannot open knowledge provider state root: {exc}") from exc
    try:
        yield binding
    finally:
        os.close(root_fd)


def _vault_binding_for_root(vault_root: Path) -> KnowledgeVaultBinding:
    path = Path(os.path.abspath(vault_root))
    try:
        for component in (path, *path.parents):
            if not stat.S_ISDIR(os.lstat(component).st_mode):
                raise KnowledgeApplySafetyError(
                    "Vault binding root cannot traverse a symlink or non-directory"
                )
        with _open_state_root(path) as root:
            root.ensure_current()
            return KnowledgeVaultBinding(
                root_path=str(root.path),
                device=root.device,
                inode=root.inode,
            )
    except OSError as exc:
        raise KnowledgeApplySafetyError(f"Vault binding root is unavailable: {exc}") from exc


@contextmanager
def _locked_state_root(state_root: Path) -> Iterator[_StateRootBinding]:
    with _open_state_root(state_root) as root:
        flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_fd: int | None = None
        try:
            lock_fd = os.open(_LOCK_NAME, flags, 0o600, dir_fd=root.fd)
            if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                raise KnowledgeApplySafetyError("knowledge provider lock is not a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            root.ensure_current()
        except (OSError, KnowledgeApplySafetyError) as exc:
            if lock_fd is not None:
                os.close(lock_fd)
            if isinstance(exc, KnowledgeApplySafetyError):
                raise
            raise KnowledgeApplySafetyError(
                f"cannot lock knowledge provider state: {exc}"
            ) from exc
        try:
            yield root
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def _read_snapshot(root_fd: int) -> tuple[KnowledgeProviderSnapshot, bytes, tuple[int, ...]]:
    try:
        payload, identity = _read_regular_entry(root_fd, _SNAPSHOT_NAME)
        snapshot = KnowledgeProviderSnapshot.model_validate_json(payload)
    except FileNotFoundError as exc:
        raise KnowledgeApplySafetyError("knowledge provider snapshot does not exist") from exc
    except (UnicodeDecodeError, ValidationError, ValueError) as exc:
        raise KnowledgeApplySafetyError(f"invalid knowledge provider snapshot: {exc}") from exc
    return snapshot, payload, identity


def _read_regular_entry(root_fd: int, name: str) -> tuple[bytes, tuple[int, ...]]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_fd = os.open(name, flags, dir_fd=root_fd)
    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise KnowledgeApplySafetyError(f"provider state entry is not regular: {name}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), _identity(info)
    finally:
        os.close(file_fd)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _entry_exists(root_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _write_temp(root_fd: int, payload: bytes) -> str:
    name = f".{_SNAPSHOT_NAME}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    file_fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(file_fd, view)
            view = view[written:]
        os.fsync(file_fd)
    except BaseException:
        os.close(file_fd)
        try:
            os.unlink(name, dir_fd=root_fd)
        except FileNotFoundError:
            pass
        raise
    else:
        os.close(file_fd)
    return name


def _atomic_create(root_fd: int, name: str, payload: bytes) -> None:
    temporary = _write_temp(root_fd, payload)
    try:
        os.link(
            temporary,
            name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
            follow_symlinks=False,
        )
        os.fsync(root_fd)
    except FileExistsError as exc:
        raise KnowledgeApplyConflict("knowledge provider snapshot already exists") from exc
    finally:
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except FileNotFoundError:
            pass


def _atomic_replace_if_unchanged(
    root_fd: int,
    name: str,
    payload: bytes,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, ...],
) -> None:
    temporary = _write_temp(root_fd, payload)
    try:
        current_bytes, current_identity = _read_regular_entry(root_fd, name)
        if current_identity != expected_identity or current_bytes != expected_bytes:
            raise KnowledgeApplyConflict(
                "provider snapshot changed outside the apply lock; refusing to replace"
            )
        os.replace(
            temporary,
            name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
        os.fsync(root_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=root_fd)
        except FileNotFoundError:
            pass
