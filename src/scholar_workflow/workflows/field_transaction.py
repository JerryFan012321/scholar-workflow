"""Local operator entry to existing Field enrollment, CAS and journal recovery.

The reviewed request is portable between CLI processes; candidate and plan tokens
remain process-local. Apply reconstructs the candidate, recomputes the complete
core digest and refuses changed inputs before calling the original transaction.
It does not turn ordinary writes into validated analysis or enable legacy stage.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator

from scholar_workflow.analysis.legacy_cutover import (
    parse_legacy_field_proposal,
    validate_legacy_cutover,
)
from scholar_workflow.knowledge.field_transaction import (
    FieldTransactionError,
    FieldTransactionPlan,
    FieldTransactionRecovery,
    FieldTransactionResult,
    FieldTransactionService,
    _open_private_directory,
    _read_target,
)
from scholar_workflow.knowledge.fields import (
    _DIRECTORY_FLAGS,
    FieldDefinition,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
    _canonical_uuid,
)


class LocalFieldTransactionError(ValueError):
    """The explicitly selected local operation cannot be performed safely."""


def _normalized_root(value: Path) -> Path:
    """Validate every original component before removing lexical dot segments."""
    original = Path(value).expanduser()
    normalized = Path(os.path.normpath(original))
    if not original.is_absolute() or normalized == Path(normalized.anchor):
        raise LocalFieldTransactionError("an explicitly selected absolute folder is required")
    try:
        descriptor = _open_private_directory(original)
    except (FieldTransactionError, OSError) as exc:
        raise LocalFieldTransactionError("selected folder has a symlink or unsafe ancestor") from exc
    os.close(descriptor)
    return normalized


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: Path
    registered_source_id: str | None = None
    source_id: str
    field: FieldDefinition
    staged_bundle: dict[str, str] = Field(default_factory=dict)
    relocations: dict[str, str] = Field(default_factory=dict)
    link_rewrites: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("root")
    @classmethod
    def _absolute_root(cls, value: Path) -> Path:
        return _normalized_root(value)

    @field_validator("source_id", "registered_source_id")
    @classmethod
    def _source_identity(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_uuid(value, name="source_id")


class LocalFieldTransactions:
    """Reuse Field enrollment without a listener, cmux or session credential."""

    def __init__(
        self, registry: KnowledgeSourceRegistry, *, state_root: Path,
        link_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self.registry = registry
        self.state_root = Path(state_root)
        self.fields = FieldService(registry)
        self.transaction = FieldTransactionService(
            self.fields, state_root=self.state_root, link_resolver=link_resolver,
        )

    def _prepare_state_parent(self, selected_root: Path | None = None) -> None:
        """Create only the operator's state parent after approval, without links."""
        path = self.state_root.parent
        prospective = Path(os.path.normpath(self.state_root))
        selected_root = None if selected_root is None else _normalized_root(selected_root)
        if selected_root is not None and (
            prospective == selected_root or selected_root in prospective.parents
        ):
            raise LocalFieldTransactionError("recovery state must be outside the Vault")
        descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
        try:
            for part in path.parts[1:]:
                try:
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                except FileNotFoundError:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
                    try:
                        os.fsync(child)
                        os.fsync(descriptor)
                    except BaseException:
                        os.close(child)
                        raise
                os.close(descriptor)
                descriptor = child
            metadata = os.fstat(descriptor)
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                raise LocalFieldTransactionError("recovery state parent must be private")
        finally:
            os.close(descriptor)

    def _select(
        self, *, source_id: str | None, root: Path | None,
        field_root: str | None, frozen: _Request | None = None, capability: str = "write",
    ):
        if (source_id is None) == (root is None):
            raise LocalFieldTransactionError("Choose exactly one of source_id or root")
        try:
            selected_root = (
                self.registry.resolve(source_id, capability=capability)
                if source_id is not None else Path(root)
            )
            selected_root = _normalized_root(selected_root)
            if frozen is not None and selected_root != frozen.root:
                raise LocalFieldTransactionError("Registered Source moved; review a fresh plan")
            preview = self.fields.preview(selected_root)
            matches = [field for field in preview.fields
                       if field_root is None or field.relative_root == field_root]
            if len(matches) != 1:
                raise LocalFieldTransactionError(
                    "Choose exactly one unregistered Field with field_root; registered "
                    "Fields use the separate legacy-link migration workflow"
                )
            selected = matches[0]
            if source_id is not None and preview.source_id != source_id:
                raise LocalFieldTransactionError("Source manifest conflicts with registry")
            if frozen is not None:
                if preview.existing_manifest and preview.source_id != frozen.source_id:
                    raise LocalFieldTransactionError("Source identity changed; review a fresh plan")
                # Freeze identity only. Preserve the freshly inspected ownership
                # list so the core can still reject omitted original documents.
                selected = selected.model_copy(update={"field_id": frozen.field.field_id})
                original = self.fields.candidates.peek(preview.candidate_token)
                revised = preview.model_copy(update={
                    "source_id": frozen.source_id,
                    "fields": [selected if row.relative_root == selected.relative_root else row
                               for row in preview.fields],
                })
                token = self.fields.candidates.issue(
                    original.root, revised, root_identity=original.root_identity,
                    content_base_hash=original.content_base_hash,
                )
                preview = self.fields.candidates.peek(token).preview
            return selected_root, preview, selected
        except (FieldRegistryError, OSError, TypeError, ValueError) as exc:
            raise LocalFieldTransactionError(str(exc)) from exc

    def _plan(self, request: _Request) -> FieldTransactionPlan:
        _, preview, selected = self._select(
            source_id=request.registered_source_id,
            root=request.root if request.registered_source_id is None else None,
            field_root=request.field.relative_root, frozen=request,
        )
        try:
            return self.transaction.plan(
                preview.candidate_token, selected.field_id, field_definition=request.field,
                staged_bundle={name: text.encode("utf-8")
                               for name, text in request.staged_bundle.items()},
                relocations=request.relocations, link_rewrites=request.link_rewrites,
            )
        except (FieldTransactionError, FieldRegistryError, OSError, ValueError) as exc:
            raise LocalFieldTransactionError(str(exc)) from exc

    def plan(
        self, *, source_id: str | None = None, root: Path | None = None,
        field_root: str | None = None, proposal: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Inspect one explicitly selected folder or registered Source; never write."""
        selected_root, preview, selected = self._select(
            source_id=source_id, root=root, field_root=field_root,
        )
        proposed = dict(proposal or {})
        if set(proposed) - {"field", "staged_bundle", "relocations", "link_rewrites"}:
            raise LocalFieldTransactionError("Unexpected local Field proposal fields")
        request = _Request.model_validate({
            "root": selected_root, "registered_source_id": source_id,
            "source_id": preview.source_id, "field": selected, **proposed,
        })
        if request.field.relative_root != selected.relative_root:
            raise LocalFieldTransactionError("Proposed Field changed its selected root")
        plan = asdict(self._plan(request))
        plan.pop("plan_token")
        return {"schema_version": 1, "request": request.model_dump(mode="json"), "plan": plan}

    def apply(
        self, reviewed: Mapping[str, object], *, approved_digest: str,
        external_writers_paused: bool = False,
    ) -> FieldTransactionResult:
        """Recreate and CAS-apply exactly the reviewed local request."""
        if external_writers_paused is not True:
            raise LocalFieldTransactionError("external Field writers must be paused before apply")
        if set(reviewed) != {"schema_version", "request", "plan"} or reviewed["schema_version"] != 1:
            raise LocalFieldTransactionError("Invalid local Field plan document")
        request = _Request.model_validate(reviewed["request"])
        previous = reviewed["plan"]
        if not isinstance(previous, dict) or previous.get("plan_digest") != approved_digest:
            raise LocalFieldTransactionError("The exact reviewed Field digest must be approved")
        plan = self._plan(request)
        if plan.plan_digest != approved_digest:
            raise LocalFieldTransactionError("Field changed; review a fresh plan_digest")
        if plan.conflicts:
            raise LocalFieldTransactionError("Field transaction has unresolved conflicts")
        try:
            self._prepare_state_parent(request.root)
            return self.transaction.apply(
                plan.plan_token, approved_digest=approved_digest, external_writers_paused=True,
            )
        except (FieldTransactionError, FieldRegistryError, OSError) as exc:
            raise LocalFieldTransactionError(str(exc)) from exc

    def recover(
        self, source_id: str, field_id: str, *, external_writers_paused: bool = False,
    ) -> FieldTransactionRecovery:
        """Use the existing private journal, including interrupted Hub operations."""
        if external_writers_paused is not True:
            raise LocalFieldTransactionError("external Field writers must be paused before recovery")
        try:
            self._prepare_state_parent()
            return self.transaction.recover(
                source_id, field_id, external_writers_paused=True,
            )
        except (FieldTransactionError, FieldRegistryError, OSError) as exc:
            raise LocalFieldTransactionError(str(exc)) from exc

    def legacy_preview(
        self, package: Mapping[str, object], *, source_id: str | None = None,
        root: Path | None = None, field_root: str | None = None,
    ) -> dict[str, object]:
        """Read-only conservation/conformance review; this does not enable staging."""
        try:
            return self._legacy_preview(
                package, source_id=source_id, root=root, field_root=field_root,
            )
        except (FieldTransactionError, FieldRegistryError, OSError, ValueError) as exc:
            raise LocalFieldTransactionError(str(exc)) from exc

    def _legacy_preview(
        self, package: Mapping[str, object], *, source_id: str | None,
        root: Path | None, field_root: str | None,
    ) -> dict[str, object]:
        selected_root, preview, selected = self._select(
            source_id=source_id, root=root, field_root=field_root, capability="read",
        )
        proposal = parse_legacy_field_proposal(package)
        if (proposal.document.schema_version != 4
                or proposal.document.profile.framework != "reference_tree"
                or proposal.document.profile.kind.value != "whole"):
            raise LocalFieldTransactionError(
                "legacy Field cutover requires an IR v4 reference_tree whole-paper candidate"
            )
        candidate = self.fields.candidates.peek(preview.candidate_token)
        self.fields._validate_candidate(candidate)
        prefix = () if selected.relative_root == "." else PurePosixPath(selected.relative_root).parts
        sources = []
        for name in (proposal.markdown_path, proposal.canvas_path):
            relative = PurePosixPath(*prefix, *PurePosixPath(name).parts).as_posix()
            old = _read_target(selected_root, relative)
            if old is None:
                raise LocalFieldTransactionError("legacy Markdown and Canvas must already exist")
            sources.append(old[0])
        report = validate_legacy_cutover(
            sources[0], sources[1], proposal.document, proposal.bundle,
            proposal.markdown_plan, proposal.canvas_plan, note_stem=proposal.note_stem,
        )
        self.fields._validate_candidate(candidate)
        return {
            "ok": True, "ready_for_approval": report.cutover_digest is not None,
            "cutover_digest": report.cutover_digest,
            "findings": [asdict(row) for row in report.findings],
        }
