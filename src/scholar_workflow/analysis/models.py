"""Public models for versioned paper-analysis artifacts and batches."""
from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from scholar_workflow.models import ResourceKind


class AnalysisRole(StrEnum):
    TASK = "task"
    INPUT = "input"
    WORKFLOW = "workflow"
    OUTPUT = "output"
    BOUNDARY = "boundary"


ALL_ROLES = tuple(AnalysisRole)


class ProfileKind(StrEnum):
    WHOLE = "whole"
    FOCUSED = "focused"


class EvidenceKind(StrEnum):
    AUTHOR_STATED = "author_stated"
    ANALYSIS_INFERENCE = "analysis_inference"
    NOT_REPORTED = "not_reported"
    UNVERIFIABLE = "unverifiable"
    NOT_APPLICABLE = "not_applicable"


class AnalysisState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATED = "validated"
    REPAIRED = "repaired"
    FAILED = "failed"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    anchor: str | None = Field(default=None, min_length=1, max_length=512)
    detail: str | None = Field(default=None, min_length=1, max_length=2048)

    @model_validator(mode="after")
    def validate_support(self) -> Evidence:
        if self.kind is EvidenceKind.AUTHOR_STATED and not self.anchor:
            raise ValueError("author_stated evidence requires an anchor")
        if self.kind in {
            EvidenceKind.ANALYSIS_INFERENCE,
            EvidenceKind.UNVERIFIABLE,
            EvidenceKind.NOT_APPLICABLE,
        } and not self.detail:
            raise ValueError(f"{self.kind.value} evidence requires detail")
        return self


class AnalysisProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ProfileKind
    roles: list[AnalysisRole] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_roles(self) -> AnalysisProfile:
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("profile roles must be unique")
        if self.kind is ProfileKind.WHOLE:
            if self.roles and set(self.roles) != set(ALL_ROLES):
                raise ValueError("whole profile must declare all five roles or omit roles")
            self.roles = list(ALL_ROLES)
        elif not self.roles:
            raise ValueError("focused profile must declare at least one role")
        return self


class AnalysisClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    role: AnalysisRole
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20_000)
    evidence: Evidence
    order: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_workflow_order(self) -> AnalysisClaim:
        if self.role is AnalysisRole.WORKFLOW and self.order is None:
            raise ValueError("workflow claims require an order")
        if self.role is not AnalysisRole.WORKFLOW and self.order is not None:
            raise ValueError("only workflow claims may carry an order")
        if self.role is AnalysisRole.WORKFLOW:
            title = self.title.casefold()
            forbidden = (
                "对应挑战",
                "对应贡献",
                "corresponding challenge",
                "corresponding contribution",
            )
            if any(term in title for term in forbidden):
                raise ValueError("workflow titles cannot invent challenge/contribution nodes")
        return self


class AnalysisDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    artifact_id: str = Field(pattern=r"^analysis:[^\s]+$")
    paper_title: str = Field(min_length=1, max_length=1000)
    profile: AnalysisProfile
    claims: list[AnalysisClaim] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_projection(self) -> AnalysisDocument:
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")

        covered = {claim.role for claim in self.claims}
        expected = set(self.profile.roles)
        if self.profile.kind is ProfileKind.WHOLE and covered != set(ALL_ROLES):
            missing = sorted(role.value for role in set(ALL_ROLES) - covered)
            raise ValueError(f"whole profile must cover all five roles; missing: {missing}")
        if self.profile.kind is ProfileKind.FOCUSED:
            outside = covered - expected
            missing = expected - covered
            if outside:
                names = sorted(role.value for role in outside)
                raise ValueError(f"claims outside the focused profile: {names}")
            if missing:
                names = sorted(role.value for role in missing)
                raise ValueError(f"focused profile has no claims for declared roles: {names}")

        workflow_orders = sorted(
            claim.order for claim in self.claims if claim.role is AnalysisRole.WORKFLOW
        )
        if workflow_orders and workflow_orders != list(range(1, len(workflow_orders) + 1)):
            raise ValueError("workflow order must be unique and contiguous from 1")

        generated_semantic_nodes = 1 + len(covered) + len(self.claims)
        if generated_semantic_nodes > 40:
            raise ValueError(
                "analysis projection exceeds 40 semantic Canvas nodes "
                "(limit: 40 generated semantic Canvas nodes)"
            )
        return self


class AnalysisBaselineClaim(BaseModel):
    """Hashes and Canvas identity for one generated claim projection."""

    model_config = ConfigDict(extra="forbid")

    role: AnalysisRole
    markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canvas_node_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    canvas_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AnalysisBaseline(BaseModel):
    """Trusted sidecar binding an IR to the exact generated artifact pair."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    artifact_id: str = Field(pattern=r"^analysis:[^\s]+$")
    note_stem: str = Field(min_length=1, max_length=240)
    document: AnalysisDocument
    markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canvas_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claims: dict[str, AnalysisBaselineClaim]
    generated_node_ids: list[str]
    generated_edge_ids: list[str]

    @model_validator(mode="after")
    def validate_identity(self) -> AnalysisBaseline:
        if self.artifact_id != self.document.artifact_id:
            raise ValueError("baseline artifact_id must match its embedded analysis IR")
        expected = {claim.claim_id for claim in self.document.claims}
        if set(self.claims) != expected:
            raise ValueError("baseline claim map must exactly match its embedded analysis IR")
        if len(self.generated_node_ids) != len(set(self.generated_node_ids)):
            raise ValueError("baseline generated_node_ids must be unique")
        if len(self.generated_edge_ids) != len(set(self.generated_edge_ids)):
            raise ValueError("baseline generated_edge_ids must be unique")
        if len(self.generated_node_ids) > 40:
            raise ValueError("baseline cannot own more than 40 generated semantic nodes")
        claim_node_ids = {claim.canvas_node_id for claim in self.claims.values()}
        if not claim_node_ids.issubset(set(self.generated_node_ids)):
            raise ValueError("baseline claim nodes must belong to the generated Canvas subgraph")
        return self


class ConformanceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,95}$")
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"
    repairable: bool = True


class ConformanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    ok: bool
    findings: list[ConformanceFinding] = Field(default_factory=list)


class AnalysisBatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    zotero_item_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    note_stem: str = Field(min_length=1, max_length=240)
    document: AnalysisDocument

    @model_validator(mode="after")
    def validate_note_stem(self) -> AnalysisBatchItem:
        if any(token in self.note_stem for token in ("/", "\\", "#", "^", "[", "]")):
            raise ValueError("note_stem must be a plain filename stem")
        return self


class AnalysisBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    batch_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    items: list[AnalysisBatchItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> AnalysisBatchRequest:
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("batch item_id values must be unique")
        zotero_keys = [item.zotero_item_key for item in self.items]
        if len(zotero_keys) != len(set(zotero_keys)):
            raise ValueError("batch zotero_item_key values must be unique")
        return self


class AnalysisItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    state: AnalysisState
    repair_count: int = Field(ge=0, le=1)
    diagnostics: list[ConformanceFinding] = Field(default_factory=list)
    stage_path: str | None = None


class AnalysisBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    batch_id: str
    state: Literal["completed", "partial", "failed"]
    items: list[AnalysisItemResult]


class AnalysisAuditTarget(BaseModel):
    """One manifest-resolved pair supplied to the read-only audit engine."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    note_stem: str = Field(min_length=1, max_length=240)
    markdown_path: str
    canvas_path: str
    sidecar_path: str | None = None
    receipt_path: str | None = None
    document: AnalysisDocument

    @model_validator(mode="after")
    def validate_paths(self) -> AnalysisAuditTarget:
        for field, value, suffix in (
            ("markdown_path", self.markdown_path, ".md"),
            ("canvas_path", self.canvas_path, ".canvas"),
        ):
            path = PurePosixPath(value)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in value
                or value != path.as_posix()
                or not value.endswith(suffix)
            ):
                raise ValueError(f"{field} must be a safe Vault-relative {suffix} path")
        for field, value in (
            ("sidecar_path", self.sidecar_path),
            ("receipt_path", self.receipt_path),
        ):
            if value is None:
                continue
            try:
                _validate_vault_path(value, suffix=".json")
            except ValueError as exc:
                raise ValueError(
                    f"{field} must be a safe root-relative .json path"
                ) from exc
        if any(token in self.note_stem for token in ("/", "\\", "#", "^", "[", "]")):
            raise ValueError("note_stem must be a plain filename stem")
        return self


class AnalysisAuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    ok: bool
    checked_item_ids: list[str]
    findings: list[ConformanceFinding] = Field(default_factory=list)


ATOMIC_RESOURCE_KINDS = (
    ResourceKind.PAPER,
    ResourceKind.TECHNICAL_DOCUMENT,
    ResourceKind.BLOG_POST,
)


class CoreDocumentKind(StrEnum):
    """Human-authored documents that organize a knowledge context."""

    CHARTER = "charter"
    SURVEY = "survey"
    CATALOG = "catalog"


class SupportingDocumentKind(StrEnum):
    """Documents that must remain attached to an atomic resource or context."""

    ANALYSIS = "analysis"
    ANALYSIS_CANVAS = "analysis_canvas"
    ANNOTATIONS = "annotations"
    READING_NOTE = "reading_note"
    ATTACHMENT = "attachment"


def _validate_vault_path(value: str, *, suffix: str | None = None) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in value
        or value != path.as_posix()
        or (suffix is not None and not value.endswith(suffix))
    ):
        expected = f" ending in {suffix}" if suffix else ""
        raise ValueError(f"path must be a safe Vault-relative POSIX path{expected}")
    return value


class KnowledgeAtomicResource(BaseModel):
    """A paper, technical document, or blog with its own human-readable note."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(min_length=1, max_length=256)
    kind: Literal[
        ResourceKind.PAPER,
        ResourceKind.TECHNICAL_DOCUMENT,
        ResourceKind.BLOG_POST,
    ]
    title: str = Field(min_length=1, max_length=1000)
    markdown_path: str

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeAtomicResource:
        self.markdown_path = _validate_vault_path(self.markdown_path, suffix=".md")
        return self


class KnowledgeCoreDocument(BaseModel):
    """A charter, synthesis, or directory document anchoring a context."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    kind: CoreDocumentKind
    title: str = Field(min_length=1, max_length=1000)
    markdown_path: str

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeCoreDocument:
        self.markdown_path = _validate_vault_path(self.markdown_path, suffix=".md")
        return self


class KnowledgeSupportingDocument(BaseModel):
    """A subordinate artifact that cannot be represented as an atomic resource."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    kind: SupportingDocumentKind
    title: str = Field(min_length=1, max_length=1000)
    vault_path: str
    owner_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeSupportingDocument:
        if self.kind is SupportingDocumentKind.ANALYSIS_CANVAS:
            expected_suffix = ".canvas"
        elif self.kind in {
            SupportingDocumentKind.ANALYSIS,
            SupportingDocumentKind.ANNOTATIONS,
            SupportingDocumentKind.READING_NOTE,
        }:
            expected_suffix = ".md"
        else:
            expected_suffix = None
        self.vault_path = _validate_vault_path(self.vault_path, suffix=expected_suffix)
        return self


class KnowledgeManifest(BaseModel):
    """Explicit Knowledge System inventory; it never discovers objects from prose."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    atomic_resources: list[KnowledgeAtomicResource] = Field(default_factory=list)
    core_documents: list[KnowledgeCoreDocument] = Field(default_factory=list)
    supporting_documents: list[KnowledgeSupportingDocument] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> KnowledgeManifest:
        primary_ids = {
            resource.resource_id for resource in self.atomic_resources
        } | {document.document_id for document in self.core_documents}
        all_ids = [resource.resource_id for resource in self.atomic_resources]
        all_ids.extend(document.document_id for document in self.core_documents)
        all_ids.extend(document.document_id for document in self.supporting_documents)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("knowledge object IDs must be globally unique")

        paths = [resource.markdown_path for resource in self.atomic_resources]
        paths.extend(document.markdown_path for document in self.core_documents)
        paths.extend(document.vault_path for document in self.supporting_documents)
        if len(paths) != len(set(paths)):
            raise ValueError("knowledge object paths must be globally unique")

        orphaned = sorted(
            document.document_id
            for document in self.supporting_documents
            if document.owner_id not in primary_ids
        )
        if orphaned:
            raise ValueError(f"supporting documents require an atomic/context owner: {orphaned}")
        return self


class AnalysisCanonicalPaths(BaseModel):
    """The three canonical files committed as one recoverable analysis bundle."""

    model_config = ConfigDict(extra="forbid")

    markdown: str
    canvas: str
    sidecar: str

    @model_validator(mode="after")
    def validate_paths(self) -> AnalysisCanonicalPaths:
        self.markdown = _validate_vault_path(self.markdown, suffix=".md")
        self.canvas = _validate_vault_path(self.canvas, suffix=".canvas")
        self.sidecar = _validate_vault_path(self.sidecar, suffix=".json")
        values = [self.markdown, self.canvas, self.sidecar]
        if len(values) != len(set(values)):
            raise ValueError("canonical analysis paths must be distinct")
        return self

    def as_list(self) -> list[str]:
        return [self.markdown, self.canvas, self.sidecar]


class KnowledgeRelation(BaseModel):
    """One explicitly supplied relation; no relation is inferred from note text."""

    model_config = ConfigDict(extra="forbid")

    from_id: str = Field(min_length=1, max_length=256)
    relation: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    to_id: str = Field(min_length=1, max_length=256)


class KnowledgeProjection(BaseModel):
    """One explicitly supplied projection identity, never an executable URL."""

    model_config = ConfigDict(extra="forbid")

    projection_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    target_id: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def reject_urls(self) -> KnowledgeProjection:
        if "://" in self.projection_id or "://" in self.target_id:
            raise ValueError("projection identities cannot be URLs")
        return self


class AnalysisCommitRequest(BaseModel):
    """CAS inputs for committing one validated or repaired staged bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    commit_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    batch_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    item_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    source_state: Literal[AnalysisState.VALIDATED, AnalysisState.REPAIRED]
    resource_id: str = Field(min_length=1, max_length=256)
    note_stem: str = Field(min_length=1, max_length=240)
    document: AnalysisDocument
    paths: AnalysisCanonicalPaths
    base_revisions: dict[str, str | None]
    base_catalog_revision: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    projections: list[KnowledgeProjection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_commit_contract(self) -> AnalysisCommitRequest:
        if any(token in self.note_stem for token in ("/", "\\", "#", "^", "[", "]")):
            raise ValueError("note_stem must be a plain filename stem")
        expected_paths = set(self.paths.as_list())
        if set(self.base_revisions) != expected_paths:
            raise ValueError("base_revisions must exactly cover all canonical paths")
        for revision in self.base_revisions.values():
            if revision is not None and not _is_prefixed_sha256(revision):
                raise ValueError("base revisions must use sha256:<hex> or null")
        if len(self.relations) != len(
            {(item.from_id, item.relation, item.to_id) for item in self.relations}
        ):
            raise ValueError("duplicate explicit knowledge relation")
        if len(self.projections) != len(
            {(item.projection_id, item.kind, item.target_id) for item in self.projections}
        ):
            raise ValueError("duplicate explicit knowledge projection")
        return self


class KnowledgeArtifactChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1, max_length=256)
    resource_id: str = Field(min_length=1, max_length=256)
    kind: Literal["analysis_markdown", "analysis_canvas", "analysis_sidecar"]
    vault_path: str
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeArtifactChange:
        self.vault_path = _validate_vault_path(self.vault_path)
        return self


class KnowledgeChangeSet(BaseModel):
    """Idempotent semantic delta derived only from explicit commit inputs."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    change_id: str = Field(pattern=r"^change:[0-9a-f]{64}$")
    source_receipt: str = Field(min_length=1, max_length=256)
    base_catalog_revision: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    upsert_artifacts: list[KnowledgeArtifactChange]
    upsert_relations: list[KnowledgeRelation] = Field(default_factory=list)
    upsert_projections: list[KnowledgeProjection] = Field(default_factory=list)
    expected_base_hashes: dict[str, str | None]


class AnalysisCommitFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    before_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    after_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    action: Literal["created", "replaced", "unchanged"]

    @model_validator(mode="after")
    def validate_path(self) -> AnalysisCommitFile:
        self.path = _validate_vault_path(self.path)
        return self


class AnalysisCommitReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    commit_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    artifact_id: str = Field(pattern=r"^analysis:[^\s]+$")
    state: Literal["committed"] = "committed"
    committed_at: AwareDatetime
    files: list[AnalysisCommitFile] = Field(min_length=3, max_length=3)
    change_set: KnowledgeChangeSet

    @model_validator(mode="after")
    def validate_receipt(self) -> AnalysisCommitReceipt:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("commit receipt file paths must be unique")

        for item in self.files:
            if item.action == "created" and item.before_sha256 is not None:
                raise ValueError("created receipt files cannot have a before revision")
            if item.action == "replaced" and (
                item.before_sha256 is None or item.before_sha256 == item.after_sha256
            ):
                raise ValueError(
                    "replaced receipt files require distinct before and after revisions"
                )
            if item.action == "unchanged" and item.before_sha256 != item.after_sha256:
                raise ValueError("unchanged receipt files require equal revisions")

        if self.change_set.source_receipt != f"analysis-commit:{self.commit_id}":
            raise ValueError("change set source_receipt must bind the commit_id")
        if self.change_set.expected_base_hashes != {
            item.path: item.before_sha256 for item in self.files
        }:
            raise ValueError("change set base hashes must match receipt before revisions")

        expected_artifacts = {
            "analysis_markdown": self.artifact_id,
            "analysis_canvas": f"{self.artifact_id}:canvas",
            "analysis_sidecar": f"{self.artifact_id}:sidecar",
        }
        artifacts = self.change_set.upsert_artifacts
        if len(artifacts) != 3 or {item.kind for item in artifacts} != set(
            expected_artifacts
        ):
            raise ValueError("commit receipt requires exactly three analysis artifacts")
        files_by_path = {item.path: item for item in self.files}
        for artifact in artifacts:
            record = files_by_path.get(artifact.vault_path)
            if (
                artifact.artifact_id != expected_artifacts[artifact.kind]
                or record is None
                or artifact.sha256 != record.after_sha256
            ):
                raise ValueError("change set artifacts must match committed file revisions")
        return self


class KnowledgeAuditObject(BaseModel):
    """Relaxed inventory row so a read-only audit can report model drift."""

    model_config = ConfigDict(extra="forbid")

    object_id: str = Field(min_length=1, max_length=256)
    object_class: Literal["atomic_resource", "core_document", "supporting_document"]
    kind: str = Field(min_length=1, max_length=64)
    vault_path: str
    owner_id: str | None = Field(default=None, min_length=1, max_length=256)
    catalog_kind: Literal["resource", "artifact"] | None = None

    @model_validator(mode="after")
    def validate_path(self) -> KnowledgeAuditObject:
        self.vault_path = _validate_vault_path(self.vault_path)
        return self


class KnowledgeAuditManifest(BaseModel):
    """Explicit roots and identities for a no-discovery weekly audit."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    objects: list[KnowledgeAuditObject] = Field(default_factory=list)
    analysis_targets: list[AnalysisAuditTarget] = Field(default_factory=list)
    catalog_path: str | None = None
    expected_catalog_revision: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_catalog_path(self) -> KnowledgeAuditManifest:
        if self.catalog_path is not None:
            self.catalog_path = _validate_vault_path(self.catalog_path, suffix=".json")
        if self.expected_catalog_revision is not None and self.catalog_path is None:
            raise ValueError("expected_catalog_revision requires catalog_path")
        return self


def _is_prefixed_sha256(value: str) -> bool:
    if not value.startswith("sha256:") or len(value) != 71:
        return False
    return all(char in "0123456789abcdef" for char in value[7:])
