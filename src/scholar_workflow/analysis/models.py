"""Public models for versioned paper-analysis artifacts and batches."""

from __future__ import annotations

import re
from enum import StrEnum
from itertools import pairwise
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from scholar_workflow.knowledge.models import (
    ATOMIC_RESOURCE_KINDS as ATOMIC_RESOURCE_KINDS,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    CoreDocumentKind as CoreDocumentKind,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeAtomicResource as KnowledgeAtomicResource,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeCoreDocument as KnowledgeCoreDocument,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeManifest as KnowledgeManifest,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeProjection as KnowledgeProjection,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeRelation as KnowledgeRelation,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    KnowledgeSupportingDocument as KnowledgeSupportingDocument,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    SupportingDocumentKind as SupportingDocumentKind,  # noqa: PLC0414 -- compatibility export
)
from scholar_workflow.knowledge.models import (
    _validate_vault_path as _validate_vault_path,  # noqa: PLC0414 -- compatibility export
)


class AnalysisRole(StrEnum):
    TASK = "task"
    INPUT = "input"
    WORKFLOW = "workflow"
    OUTPUT = "output"
    BOUNDARY = "boundary"
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    METHOD = "method"
    EXPERIMENTS = "experiments"
    LIMITATION = "limitation"


ALL_ROLES = (
    AnalysisRole.TASK,
    AnalysisRole.INPUT,
    AnalysisRole.WORKFLOW,
    AnalysisRole.OUTPUT,
    AnalysisRole.BOUNDARY,
)
TREE_ROLES = (
    AnalysisRole.ABSTRACT,
    AnalysisRole.INTRODUCTION,
    AnalysisRole.METHOD,
    AnalysisRole.LIMITATION,
)
FIVE_TREE_ROLES = (
    AnalysisRole.ABSTRACT,
    AnalysisRole.INTRODUCTION,
    AnalysisRole.METHOD,
    AnalysisRole.EXPERIMENTS,
    AnalysisRole.LIMITATION,
)

_OUTLINE_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_REFERENCE_TREE_PATHS = (
    (re.compile(r"^abstract/task$"), frozenset()),
    (re.compile(rf"^abstract/previous_methods/{_OUTLINE_SLUG}$"), None),
    (re.compile(r"^abstract/insight$"), frozenset({"motivation", "advantage"})),
    (re.compile(rf"^abstract/contributions/{_OUTLINE_SLUG}$"), frozenset({"summary", "advantage"})),
    (re.compile(r"^abstract/experiment$"), frozenset()),
    (
        re.compile(rf"^abstract/experiment/{_OUTLINE_SLUG}$"),
        frozenset(f"finding-{index}" for index in range(1, 5)),
    ),
    (re.compile(r"^introduction/task_application$"), frozenset()),
    (
        re.compile(rf"^introduction/previous_methods/{_OUTLINE_SLUG}$"),
        frozenset({"previous-method", "limitation", "technical-reason"}),
    ),
    (re.compile(r"^introduction/our_pipeline/insight$"), frozenset()),
    (
        re.compile(rf"^introduction/our_pipeline/contributions/{_OUTLINE_SLUG}$"),
        frozenset({"purpose", "how", "advantage"}),
    ),
    (re.compile(r"^method/overview$"), frozenset()),
    (
        re.compile(rf"^method/modules/{_OUTLINE_SLUG}$"),
        frozenset({"motivation", "method", "why-it-works", "technical-advantage"}),
    ),
    (re.compile(r"^limitation/explanation$"), frozenset()),
    (
        re.compile(rf"^limitation/explanation/{_OUTLINE_SLUG}$"),
        frozenset(f"reason-{index}" for index in range(1, 5)),
    ),
)


def reference_tree_point_slots(path: str) -> frozenset[str] | None:
    """Return allowed point IDs for a known tree path, or None for unknown paths.

    The reference image has three numbered previous-method challenges. Keep
    that bounded so a single editable detail card cannot become a tall scroll.
    """
    for pattern, slots in _REFERENCE_TREE_PATHS:
        if pattern.fullmatch(path):
            return slots if slots is not None else frozenset(
                f"challenge-{index}" for index in range(1, 4)
            )
    return None


def complete_tree_point_slots(path: str, point_ids: list[str]) -> frozenset[str] | None:
    """Version-5 slots, without treating the example image's counts as limits."""
    fixed = {
        "method/overview": frozenset({"task-io", "steps"}),
        "introduction/demos_application": frozenset(),
    }
    if path in fixed:
        return fixed[path]
    if re.fullmatch(rf"experiments/ablation/{_OUTLINE_SLUG}", path):
        return frozenset({"components", "design-choices"})
    numbered = (
        (rf"abstract/previous_methods/{_OUTLINE_SLUG}", "challenge"),
        (rf"abstract/experiment/{_OUTLINE_SLUG}", "finding"),
        (rf"experiments/comparison/{_OUTLINE_SLUG}", "finding"),
        (rf"limitation/explanation/{_OUTLINE_SLUG}", "reason"),
    )
    for pattern, prefix in numbered:
        if re.fullmatch(pattern, path):
            return frozenset(
                point_id for point_id in point_ids
                if re.fullmatch(rf"{prefix}-[1-9][0-9]*", point_id)
            )
    return reference_tree_point_slots(path)


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


QuoteEmphasis = list[Annotated[str, Field(
    strict=True, min_length=1, max_length=1600, pattern=r"^\S(?:[\s\S]*\S)?$"
)]]


def _validate_quote_emphasis(quote: str | None, fragments: list[str]) -> None:
    """Validate literal spans, without certifying their scientific support."""
    if not fragments:
        return
    if quote is None or not quote.strip():
        raise ValueError("quote_emphasis requires a nonblank original quote")
    intervals: list[tuple[int, int]] = []
    for fragment in fragments:
        start = quote.find(fragment)
        if start < 0 or quote.find(fragment, start + 1) != -1:
            raise ValueError("quote_emphasis fragments must occur exactly once in the original quote")
        intervals.append((start, start + len(fragment)))
    intervals.sort()
    if any(left[1] > right[0] for left, right in pairwise(intervals)):
        raise ValueError("quote_emphasis fragments must not overlap or repeat")


class ZoteroPdfSpan(BaseModel):
    """Stable attachment identity and one verifiable PDF page or annotation."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["zotero_pdf"] = "zotero_pdf"
    library_type: Literal["personal", "group"]
    library_id: str = Field(pattern=r"^[0-9]+$")
    attachment_key: str = Field(pattern=r"^[A-Z0-9]{8}$")
    content_hash: str = Field(pattern=r"^(?:md5:[0-9a-f]{32}|sha256:[0-9a-f]{64})$")
    page_index: int = Field(ge=0)
    page_label: str | None = Field(default=None, min_length=1, max_length=64)
    annotation_key: str | None = Field(default=None, pattern=r"^[A-Z0-9]{8}$")
    section: str | None = Field(default=None, min_length=1, max_length=160)
    quote: str | None = Field(default=None, min_length=1, max_length=1600)
    quote_emphasis: QuoteEmphasis = Field(
        default_factory=list, max_length=8, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def validate_quote_emphasis(self) -> ZoteroPdfSpan:
        _validate_quote_emphasis(self.quote, self.quote_emphasis)
        return self


class VaultMarkdownSpan(BaseModel):
    """Portable note identity plus one explicit Obsidian block locator."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["vault_markdown"] = "vault_markdown"
    source_id: UUID
    artifact_id: str = Field(min_length=1, max_length=240, pattern=r"^[^\s]+$")
    vault_path: str = Field(min_length=4, max_length=512)
    block_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
    quote: str | None = Field(
        default=None, min_length=1, max_length=1600, exclude_if=lambda value: value is None
    )
    quote_emphasis: QuoteEmphasis = Field(
        default_factory=list, max_length=8, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def validate_quote_emphasis(self) -> VaultMarkdownSpan:
        _validate_quote_emphasis(self.quote, self.quote_emphasis)
        return self

    @field_validator("vault_path")
    @classmethod
    def validate_vault_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or not value.endswith(".md")
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(char in value for char in "\\#|[]\r\n")
        ):
            raise ValueError("vault_path must be a safe relative Markdown path")
        return value


SourceSpan = Annotated[ZoteroPdfSpan | VaultMarkdownSpan, Field(discriminator="kind")]


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    anchor: str | None = Field(default=None, min_length=1, max_length=512)
    detail: str | None = Field(default=None, min_length=1, max_length=2048)
    source_spans: list[SourceSpan] = Field(
        default_factory=list, max_length=8, exclude_if=lambda value: not value
    )

    @model_validator(mode="after")
    def validate_support(self) -> Evidence:
        if any(span.quote_emphasis for span in self.source_spans) and self.kind not in {
            EvidenceKind.AUTHOR_STATED, EvidenceKind.ANALYSIS_INFERENCE,
        }:
            raise ValueError("quote_emphasis requires author_stated or analysis_inference evidence")
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
    framework: Literal["legacy", "reference_tree", "reference_tree_v5"] = "legacy"
    markdown_quotes: bool = Field(default=False, strict=True, exclude_if=lambda value: not value)
    markdown_folded_quotes: bool = Field(
        default=False, strict=True, exclude_if=lambda value: not value,
    )
    markdown_source_images: bool = Field(
        default=False, strict=True, exclude_if=lambda value: not value,
    )
    canvas_unique_sources: bool = Field(
        default=False, strict=True, exclude_if=lambda value: not value,
    )
    canvas_note_path: str | None = Field(
        default=None, min_length=4, max_length=512, exclude_if=lambda value: value is None,
    )

    @field_validator("canvas_note_path", mode="before")
    @classmethod
    def validate_canvas_note_path(cls, value: object) -> str:
        if not isinstance(value, str) or value.strip() != value:
            raise ValueError("Canvas companion path must be a plain relative Markdown path")
        _validate_vault_path(value, suffix=".md")
        if any(char in value for char in ":#^|[]") or any(
            ord(char) < 32 or ord(char) == 127 for char in value
        ):
            raise ValueError("Canvas companion path cannot contain link syntax or control characters")
        return value

    @model_validator(mode="after")
    def validate_roles(self) -> AnalysisProfile:
        if self.markdown_folded_quotes and (
            not self.markdown_quotes or self.framework not in {"reference_tree", "reference_tree_v5"}
        ):
            raise ValueError("Folded Markdown quotations require displayed reference-tree quotations")
        if self.markdown_source_images and self.framework != "reference_tree_v5":
            raise ValueError("Markdown source images require the v5 framework")
        if self.canvas_note_path is not None and self.framework != "reference_tree_v5":
            raise ValueError("Explicit Canvas companion paths require the v5 framework")
        if self.canvas_unique_sources and self.framework != "reference_tree_v5":
            raise ValueError("Unique Canvas sources require the v5 framework")
        if self.markdown_quotes and self.framework not in {"reference_tree", "reference_tree_v5"}:
            raise ValueError("Markdown quotations require the reference_tree framework")
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("profile roles must be unique")
        allowed_roles = (
            FIVE_TREE_ROLES if self.framework == "reference_tree_v5"
            else TREE_ROLES if self.framework == "reference_tree" else ALL_ROLES
        )
        if self.kind is ProfileKind.WHOLE:
            if self.roles and set(self.roles) != set(allowed_roles):
                raise ValueError("whole profile must declare all framework roles or omit roles")
            self.roles = list(allowed_roles)
        elif not self.roles:
            raise ValueError("focused profile must declare at least one role")
        elif not set(self.roles).issubset(allowed_roles):
            raise ValueError("focused profile roles must belong to its framework")
        return self


class AnalysisReader(BaseModel):
    """A display route, not source identity. Vault IDs are local to one host.

    A persisted ZotFlow projection must be re-rendered after moving hosts, once
    the destination host has resolved the registered Vault's own ID.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["zotero_native", "zotflow_library"]
    vault_name: str | None = Field(default=None, min_length=1, max_length=100)
    vault_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")

    @model_validator(mode="after")
    def validate_reader(self) -> AnalysisReader:
        if self.kind == "zotflow_library":
            if self.vault_name is None and self.vault_id is None:
                raise ValueError("zotflow_library requires a vault_id or legacy vault_name")
            if self.vault_name is not None and self.vault_id is not None:
                raise ValueError("zotflow_library must choose one Vault target")
            if self.vault_name is not None and (
                self.vault_name.strip() != self.vault_name
                or any(char in self.vault_name for char in "/\\\r\n\x00")
                or self.vault_name in {".", ".."}
            ):
                raise ValueError("zotflow_library requires a safe explicit vault_name")
        elif self.vault_name is not None or self.vault_id is not None:
            raise ValueError("zotero_native must not specify a Vault target")
        return self


class CanvasImage(BaseModel):
    """One paper-local source visual; never an arbitrary URL or paragraph crop."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["experimental_table", "process_diagram"]
    asset_id: str = Field(min_length=1, max_length=240, pattern=r"^[^\s]+$")
    image_path: str = Field(min_length=5, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pixel_width: int = Field(ge=16, le=20_000, strict=True)
    pixel_height: int = Field(ge=16, le=20_000, strict=True)
    caption: str = Field(min_length=1, max_length=120)
    source: ZoteroPdfSpan

    @field_validator("image_path")
    @classmethod
    def validate_image_path(cls, value: str) -> str:
        if (
            not value.startswith("attachments/") or not value.endswith(".png")
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(char in value for char in "\\:#|[]\r\n\x00")
            or value.strip() != value
        ):
            raise ValueError("canvas image must be a safe paper-relative attachments PNG")
        return value

    @model_validator(mode="after")
    def validate_caption_and_source(self) -> CanvasImage:
        if not self.caption.strip() or any(char in self.caption for char in "[]|<>\r\n"):
            raise ValueError("canvas image caption must be a plain nonblank single line")
        if self.source.quote is not None:
            raise ValueError("canvas images cannot carry paragraph quotations")
        return self


class AnalysisPoint(BaseModel):
    """One evidence-bearing statement inside a Canvas-sized analysis claim."""

    model_config = ConfigDict(extra="forbid")

    point_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    text: str = Field(min_length=1, max_length=5_000)
    canvas_summary: str | None = Field(default=None, min_length=1, max_length=180)
    evidence: Evidence
    canvas_image: CanvasImage | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def validate_readable_projection(self) -> AnalysisPoint:
        if not self.text.strip() or "\n" in self.text or "\r" in self.text:
            raise ValueError("point text must be a nonblank single paragraph")
        if self.canvas_summary is not None and not self.canvas_summary.strip():
            raise ValueError("point canvas_summary cannot be blank")
        if len(self.text) > 180 and self.canvas_summary is None:
            raise ValueError("point canvas_summary is required when text exceeds 180 characters")
        return self


class AnalysisClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    role: AnalysisRole
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=20_000)
    container: bool = Field(default=False, strict=True, exclude_if=lambda value: not value)
    canvas_summary: str | None = Field(default=None, min_length=1, max_length=400)
    evidence: Evidence
    canvas_image: CanvasImage | None = Field(default=None, exclude_if=lambda value: value is None)
    points: list[AnalysisPoint] = Field(default_factory=list, max_length=64, exclude_if=lambda value: not value)
    order: int | None = Field(default=None, ge=1)
    outline_path: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_workflow_order(self) -> AnalysisClaim:
        if self.canvas_summary is not None and not self.canvas_summary.strip():
            raise ValueError("canvas_summary cannot be blank")
        point_ids = [point.point_id for point in self.points]
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("point_id values must be unique within a claim")
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

    schema_version: Literal[1, 2, 3, 4, 5]
    artifact_id: str = Field(pattern=r"^analysis:[^\s]+$")
    paper_title: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "zh"] | None = None
    profile: AnalysisProfile
    reader: AnalysisReader | None = None
    capacity: Literal["expanded"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    claims: list[AnalysisClaim] = Field(min_length=1)

    @property
    def fact_node_limit(self) -> int:
        return 96 if self.schema_version == 5 and self.capacity == "expanded" else 40

    @property
    def managed_node_limit(self) -> int:
        if self.schema_version == 5 and self.capacity == "expanded":
            return 192
        return 96 if self.schema_version in {4, 5} else 40

    @model_validator(mode="after")
    def validate_projection(self) -> AnalysisDocument:
        if self.schema_version == 5 and re.search(r"!\[|<img\b", self.paper_title, re.IGNORECASE):
            raise ValueError("Canvas image embeds must use typed canvas_image, not the paper title")
        if self.capacity is not None and self.schema_version != 5:
            raise ValueError("expanded capacity is available only in IR v5")
        is_reference_tree = self.schema_version in {4, 5}
        expected_framework = (
            "reference_tree_v5" if self.schema_version == 5
            else "reference_tree" if self.schema_version == 4 else "legacy"
        )
        if self.profile.framework != expected_framework:
            raise ValueError("IR v5 requires reference_tree_v5; v4 requires reference_tree; v1-v3 require legacy")
        if self.schema_version == 5 and not self.profile.markdown_quotes:
            raise ValueError("IR v5 requires Markdown original-source quotations")
        if self.schema_version == 5 and self.reader is not None and (
            self.reader.kind == "zotflow_library" and self.reader.vault_id is None
        ):
            raise ValueError("IR v5 ZotFlow projection requires a verified vault_id")
        if is_reference_tree and self.language is None:
            raise ValueError("IR v4 requires an explicit analysis language")
        if not is_reference_tree and self.reader is not None:
            raise ValueError("reader projection is available only in IR v4")
        if not is_reference_tree and self.language is None:
            self.language = "zh"
        if self.schema_version == 1 and any(claim.points for claim in self.claims):
            raise ValueError("evidence points require analysis IR schema_version 2")
        if self.schema_version >= 3:
            all_evidence = [
                evidence
                for claim in self.claims
                for evidence in (claim.evidence, *(point.evidence for point in claim.points))
            ]
            if any(
                evidence.kind in {EvidenceKind.AUTHOR_STATED, EvidenceKind.ANALYSIS_INFERENCE}
                and not evidence.source_spans
                for evidence in all_evidence
            ):
                raise ValueError("IR v3 author claims and inferences require a source span")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")

        outline_paths: list[str] = []
        for claim in self.claims:
            if self.schema_version == 5:
                projected = [claim.title, claim.canvas_summary or claim.body]
                projected += [point.canvas_summary or point.text for point in claim.points]
                projected += [label for record in (claim, *claim.points)
                              for label in (record.evidence.anchor or "", record.evidence.detail or "")]
                if any(re.search(r"!\[|<img\b", text, re.IGNORECASE) for text in projected):
                    raise ValueError("Canvas image embeds must use typed canvas_image; Markdown crops require a plain Canvas summary")
            for record in (claim, *claim.points):
                if any(span.quote_emphasis for span in record.evidence.source_spans) and (
                    not is_reference_tree or not self.profile.markdown_quotes
                ):
                    raise ValueError("quote_emphasis requires a v4/v5 Markdown quotation projection")
                image = record.canvas_image
                if image is None:
                    continue
                if self.schema_version != 5:
                    raise ValueError("canvas images require IR v5")
                path = claim.outline_path or ""
                allowed = (
                    path.startswith(("experiments/comparison/", "experiments/ablation/"))
                    if image.kind == "experimental_table" else
                    path == "method/overview" or path.startswith("method/modules/")
                )
                if not allowed or (record is claim and claim.container):
                    raise ValueError("canvas image must supplement its corresponding experiment or method record")
                if record.evidence.kind not in {EvidenceKind.AUTHOR_STATED, EvidenceKind.ANALYSIS_INFERENCE}:
                    raise ValueError("canvas image requires a supported source record")
                identity_fields = ("library_type", "library_id", "attachment_key", "content_hash", "page_index")
                if not any(
                    isinstance(span, ZoteroPdfSpan)
                    and all(getattr(span, key) == getattr(image.source, key) for key in identity_fields)
                    for span in record.evidence.source_spans
                ):
                    raise ValueError("canvas image PDF identity and page must match its own record")
            if claim.container:
                if self.schema_version != 5:
                    raise ValueError("structural containers require IR v5")
                if (
                    claim.body != "" or claim.canvas_summary is not None
                    or claim.evidence.kind is not EvidenceKind.NOT_APPLICABLE
                    or claim.evidence.anchor is not None or claim.evidence.source_spans
                ):
                    raise ValueError("structural containers cannot carry facts, summaries or source evidence")
            elif not claim.body or (self.schema_version == 5 and not claim.body.strip()):
                raise ValueError("non-container claim body must not be blank")
            if not is_reference_tree:
                if claim.outline_path is not None:
                    raise ValueError("legacy claims cannot carry outline_path")
                continue
            path = claim.outline_path
            if path is None or not path.startswith(f"{claim.role.value}/"):
                raise ValueError("IR v4 outline_path must start with its claim role")
            if any(char in claim.title for char in "\r\n"):
                raise ValueError("IR v4 claim title must be a single line")
            if re.search(r"(?m)^#{1,6}\s", claim.body) or "sw-analysis-claim" in claim.body:
                raise ValueError("IR v4 claim body cannot inject framework headings or markers")
            for point in claim.points:
                prose = (point.text, point.canvas_summary or "")
                if any("sw-analysis-claim" in text for text in prose) or (
                    self.schema_version == 5 and any(
                        re.match(r"^ {0,3}#{1,6}(?:[ \t]|$)", text) for text in prose
                    )
                ):
                    raise ValueError(
                        f"IR v{self.schema_version} point {point.point_id} cannot inject framework headings or markers"
                    )
            if len(claim.title) > 120:
                raise ValueError("IR v4 Canvas claim title must not exceed 120 characters")
            if len(claim.body) > 180 and claim.canvas_summary is None:
                raise ValueError(
                    "IR v4 claim canvas_summary is required when body exceeds 180 characters"
                )
            if claim.canvas_summary is not None and len(claim.canvas_summary) > 180:
                raise ValueError("IR v4 claim canvas_summary must not exceed 180 characters")
            if claim.canvas_summary is not None and any(
                char in claim.canvas_summary for char in "\r\n"
            ):
                raise ValueError("IR v4 claim canvas_summary must be a single line")
            if any(
                point.canvas_summary is not None
                and any(char in point.canvas_summary for char in "\r\n")
                for point in claim.points
            ):
                raise ValueError("IR v4 point canvas_summary must be a single line")
            for evidence in (claim.evidence, *(point.evidence for point in claim.points)):
                if len(evidence.anchor or "") > 160 or len(evidence.detail or "") > 180:
                    raise ValueError("IR v4 evidence anchor/detail must be Canvas-sized")
                if any(
                    char in ((evidence.anchor or "") + (evidence.detail or ""))
                    for char in "\r\n"
                ):
                    raise ValueError("IR v4 evidence labels must be single-line")
                if len(evidence.source_spans) > 3:
                    raise ValueError("IR v4 evidence has too many inline source spans")
                if self.profile.markdown_quotes:
                    quotes = [span.quote for span in evidence.source_spans if span.quote is not None]
                    if any(not excerpt.strip() for excerpt in quotes):
                        raise ValueError("Markdown source quotations cannot be blank")
                    if evidence.kind in {
                        EvidenceKind.AUTHOR_STATED,
                        EvidenceKind.ANALYSIS_INFERENCE,
                    } and not quotes:
                        raise ValueError(
                            "Markdown source quotations require an excerpt for each supported claim/point"
                        )
            slots = (
                complete_tree_point_slots(path, [point.point_id for point in claim.points])
                if self.schema_version == 5 else reference_tree_point_slots(path)
            )
            if slots is None:
                raise ValueError(f"IR v4 outline_path is outside the reference tree: {path}")
            unexpected_points = {point.point_id for point in claim.points} - slots
            if unexpected_points:
                raise ValueError(
                    f"IR v4 point_id is outside the outline_path template: {path}"
                )
            outline_paths.append(path)
        if len(outline_paths) != len(set(outline_paths)):
            raise ValueError("IR v4 outline_path values must be unique")

        covered = {claim.role for claim in self.claims}
        expected = set(self.profile.roles)
        required_roles = (
            FIVE_TREE_ROLES if self.schema_version == 5
            else TREE_ROLES if is_reference_tree else ALL_ROLES
        )
        if not covered.issubset(required_roles):
            raise ValueError("claim roles must belong to the versioned framework")
        if (
            self.profile.kind is ProfileKind.WHOLE
            and not is_reference_tree
            and covered != set(required_roles)
        ):
            missing = sorted(role.value for role in set(required_roles) - covered)
            raise ValueError(f"whole profile must cover all framework roles; missing: {missing}")
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

        generated_semantic_nodes = (
            sum(not claim.container for claim in self.claims)
            + sum(len(claim.points) for claim in self.claims)
            if self.schema_version == 5 else
            len(self.claims) + sum(bool(claim.points) for claim in self.claims)
            if is_reference_tree
            else 1 + len(covered) + len(self.claims)
        )
        if generated_semantic_nodes > self.fact_node_limit:
            raise ValueError(
                f"analysis projection exceeds {self.fact_node_limit} generated semantic Canvas nodes "
                f"(limit: {self.fact_node_limit} generated semantic Canvas nodes)"
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
        max_generated_nodes = self.document.managed_node_limit
        if len(self.generated_node_ids) > max_generated_nodes:
            raise ValueError(
                f"baseline cannot own more than {max_generated_nodes} generated nodes"
            )
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
        if any(token in self.note_stem for token in ("/", "\\", "#", "^", "[", "]", "|", "\r", "\n")):
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
    base_snapshot_revision: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    zotero_item_key: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    projections: list[KnowledgeProjection] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_commit_contract(self) -> AnalysisCommitRequest:
        if any(token in self.note_stem for token in ("/", "\\", "#", "^", "[", "]")):
            raise ValueError("note_stem must be a plain filename stem")
        if self.document.schema_version in {4, 5}:
            parents = {
                PurePosixPath(path).parent for path in self.paths.as_list()
            }
            if len(parents) != 1:
                raise ValueError("IR v4 analysis files must share one paper folder")
            parent = next(iter(parents))
            if len(parent.parts) < 3 or parent.parts[-3:-1] != ("resources", "papers"):
                raise ValueError(
                    "IR v4 canonical paths require a Field resources/papers/<paper> folder"
                )
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
        owner_relation = (
            self.resource_id,
            "has-analysis",
            self.document.artifact_id,
        )
        if owner_relation not in {
            (item.from_id, item.relation, item.to_id) for item in self.relations
        }:
            raise ValueError(
                "commit request requires its resource has-analysis ownership relation"
            )
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
        resource_ids = {artifact.resource_id for artifact in artifacts}
        if len(resource_ids) != 1:
            raise ValueError("commit receipt artifacts must have one resource owner")
        resource_id = next(iter(resource_ids))
        if not any(
            relation.from_id == resource_id
            and relation.relation == "has-analysis"
            and relation.to_id == self.artifact_id
            for relation in self.change_set.upsert_relations
        ):
            raise ValueError(
                "commit receipt requires its resource has-analysis ownership relation"
            )
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
