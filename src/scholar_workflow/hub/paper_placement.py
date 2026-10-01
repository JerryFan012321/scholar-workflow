"""Read-only review plan for one IR v4 paper folder placement.

This module deliberately has no apply or recovery function. A digest binds a
proposal to observed filesystem identities; it is not approval, a backup, or
authority to write either the Vault or the Knowledge provider snapshot.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from difflib import unified_diff
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from scholar_workflow.analysis.apply_changes import (
    KnowledgeApplyError,
    KnowledgeProviderSnapshot,
    KnowledgeVaultBinding,
    ProviderReceipt,
    _apply_catalog,
    _merge_projections,
    _merge_relations,
    _read_snapshot,
    _reject_control_plane_identity,
    _validate_catalog_projection,
)
from scholar_workflow.analysis.commit import _canonical_payloads
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisCommitRequest,
    KnowledgeArtifactChange,
)
from scholar_workflow.knowledge.models import (
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
    KnowledgeSupportingDocument,
    SupportingDocumentKind,
)
from scholar_workflow.analysis.rendering import AnalysisBundle
from scholar_workflow.hub.field_migration import _has_legacy_hub_reference, _managed_paths
from scholar_workflow.hub.field_transaction import (
    _MANIFEST,
    FieldTransactionError,
    _directory_plan,
    _has_analysis_identity,
    _has_analysis_sidecar,
    _hash,
    _identity,
    _read_target,
)
from scholar_workflow.knowledge.fields import (
    FieldDefinition,
    FieldManifest,
    FieldRegistryError,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
    _assert_field_owned_markdown,
    _open_directory_chain,
    _read_regular_at,
    _safe_relative,
)
from scholar_workflow.knowledge.catalog_models import HubCatalog
from scholar_workflow.models import ResourceKind

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_FILE = 8 * 1024 * 1024
_MAX_DIFF = 1024 * 1024


class PaperPlacementError(ValueError):
    """A reviewed placement cannot be planned from these exact inputs."""


class ProposedProviderGraph(BaseModel):
    """Review-only graph, deliberately not a persistable provider snapshot.

    Existing receipts describe the before state. A future joint transaction
    must supply its own receipt contract before this graph can be published.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["proposed-provider-graph"] = "proposed-provider-graph"
    requires_joint_receipt: Literal[True] = True
    is_persistable_snapshot: Literal[False] = False
    vault_binding: KnowledgeVaultBinding
    manifest: KnowledgeManifest
    artifacts: list[KnowledgeArtifactChange]
    relations: list[KnowledgeRelation]
    projections: list[KnowledgeProjection]
    catalog: HubCatalog
    before_receipts: list[ProviderReceipt]


@dataclass(frozen=True)
class PaperPlacementFile:
    path: str
    kind: str
    before_sha256: str | None
    before_device: int | None
    before_inode: int | None
    after_sha256: str | None


@dataclass(frozen=True)
class PaperPlacementDirectory:
    path: str
    before_device: int | None
    before_inode: int | None


@dataclass(frozen=True)
class PaperPlacementLinkRewrite:
    path: str
    old_text: str
    new_text: str
    occurrences: int
    diff: str


@dataclass(frozen=True)
class PaperPlacementPlan:
    plan_digest: str
    source_id: str
    field_id: str
    resource_id: str
    vault_root: str
    vault_device: int
    vault_inode: int
    provider_state_root: str
    provider_device: int
    provider_inode: int
    provider_snapshot_revision: str
    provider_snapshot_sha256: str
    provider_snapshot_device: int
    provider_snapshot_inode: int
    registry_sha256: str
    registry_device: int
    registry_inode: int
    field_manifest_diff: str
    provider_manifest_diff: str
    files: tuple[PaperPlacementFile, ...]
    directories: tuple[PaperPlacementDirectory, ...]
    link_rewrites: tuple[PaperPlacementLinkRewrite, ...]
    provider_artifacts: tuple[KnowledgeArtifactChange, ...]
    proposed_provider_graph: ProposedProviderGraph
    proposed_provider_graph_sha256: str
    proposed_provider_graph_diff: str
    conflicts: tuple[str, ...]


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PaperPlacementError("reviewed JSON candidate has duplicate keys")
        result[key] = value
    return result


def _candidate_bytes(
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
    reviewed_files: Mapping[str, bytes],
) -> dict[str, bytes]:
    # Conformance checks the semantic bundle; the supplied raw bytes remain authoritative.
    _canonical_payloads(request, bundle, baseline)
    paths = request.paths.as_list()
    if set(reviewed_files) != set(paths) or any(
        not isinstance(reviewed_files[path], bytes) for path in paths
    ):
        raise PaperPlacementError("reviewed v4 triple must provide exact bytes for all three paths")
    payloads = {path: reviewed_files[path] for path in paths}
    if sum(map(len, payloads.values())) > 32 * 1024 * 1024 or any(
        len(content) > _MAX_FILE for content in payloads.values()
    ):
        raise PaperPlacementError("v4 analysis candidate exceeds review size limit")
    try:
        markdown = payloads[request.paths.markdown].decode("utf-8")
        canvas = json.loads(
            payloads[request.paths.canvas], object_pairs_hook=_unique_json_object
        )
        sidecar_json = json.loads(
            payloads[request.paths.sidecar], object_pairs_hook=_unique_json_object
        )
        sidecar = AnalysisBaseline.model_validate(sidecar_json)
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise PaperPlacementError("reviewed v4 triple is not valid UTF-8/JSON") from exc
    if (
        markdown != bundle.markdown
        or canvas != bundle.canvas
        or sidecar.model_dump(mode="json") != baseline.model_dump(mode="json")
    ):
        raise PaperPlacementError("reviewed v4 bytes differ from the conformant bundle")
    return payloads


def _diff(before: bytes, after: bytes, name: str) -> str:
    try:
        old = before.decode("utf-8").splitlines(keepends=True)
        new = after.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise PaperPlacementError(f"reviewed text is not UTF-8: {name}") from exc
    result = "".join(unified_diff(old, new, fromfile=f"before/{name}", tofile=f"after/{name}"))
    if len(result.encode("utf-8")) > _MAX_DIFF:
        raise PaperPlacementError(f"review diff is too large: {name}")
    return result


def _read_regular_absolute(path: Path) -> tuple[bytes, os.stat_result]:
    descriptor = _open_directory_chain(path.parent)
    try:
        return _read_regular_at(descriptor, path.name, limit=_MAX_FILE)
    finally:
        os.close(descriptor)


def _file_row(
    path: str,
    kind: str,
    before: tuple[bytes, os.stat_result] | None,
    after: bytes | None,
) -> PaperPlacementFile:
    return PaperPlacementFile(
        path,
        kind,
        None if before is None else _hash(before[0]),
        None if before is None else before[1].st_dev,
        None if before is None else before[1].st_ino,
        None if after is None else _hash(after),
    )


def _field_path(field: FieldDefinition, path: str) -> str:
    safe = _safe_relative(path)
    if safe != path:
        raise PaperPlacementError("paper placement path is not canonical")
    parts = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    relative = PurePosixPath(*parts, *PurePosixPath(safe).parts).as_posix()
    if relative == "." or any(part.startswith(".") for part in PurePosixPath(safe).parts):
        raise PaperPlacementError("paper placement path is hidden or unsafe")
    return relative


def _within_field(field: FieldDefinition, path: str) -> str:
    safe = _safe_relative(path)
    if safe != path:
        raise PaperPlacementError("paper placement path is not canonical")
    prefix = () if field.relative_root == "." else PurePosixPath(field.relative_root).parts
    parts = PurePosixPath(safe).parts
    if parts[: len(prefix)] != prefix or len(parts) <= len(prefix):
        raise PaperPlacementError(f"paper placement path escaped its Field: {path}")
    if any(part.startswith(".") for part in parts[len(prefix) :]):
        raise PaperPlacementError(f"paper placement path is hidden: {path}")
    return PurePosixPath(*parts[len(prefix) :]).as_posix()


def _manifest_after(
    snapshot: KnowledgeProviderSnapshot,
    request: AnalysisCommitRequest,
    old_note: str,
    new_note: str,
) -> KnowledgeManifest:
    owner = next(
        (
            row
            for row in snapshot.manifest.atomic_resources
            if row.resource_id == request.resource_id
        ),
        None,
    )
    if owner is None or owner.kind is not ResourceKind.PAPER or owner.markdown_path != old_note:
        raise PaperPlacementError("provider has no unique PAPER owner at the proposed source note")
    if PurePosixPath(new_note).parent != PurePosixPath(request.paths.markdown).parent:
        raise PaperPlacementError("PAPER owner note is not in the candidate analysis folder")
    existing_ids = {row.artifact_id for row in snapshot.artifacts}
    artifact_ids = (
        request.document.artifact_id,
        f"{request.document.artifact_id}:canvas",
        f"{request.document.artifact_id}:sidecar",
    )
    if existing_ids.intersection(artifact_ids):
        raise PaperPlacementError(
            "existing provider analysis artifacts need a separate relocation review"
        )
    existing_knowledge_ids = {
        *(row.resource_id for row in snapshot.manifest.atomic_resources),
        *(row.document_id for row in snapshot.manifest.core_documents),
        *(row.document_id for row in snapshot.manifest.supporting_documents),
    }
    if existing_knowledge_ids.intersection(artifact_ids):
        raise PaperPlacementError("new analysis artifact identity is already declared")
    for artifact_id in artifact_ids:
        _reject_control_plane_identity(artifact_id)
    paths = request.paths.as_list()
    if new_note in paths:
        raise PaperPlacementError("PAPER owner note overlaps a candidate analysis file")
    existing_paths = {
        *(row.markdown_path for row in snapshot.manifest.atomic_resources),
        *(row.markdown_path for row in snapshot.manifest.core_documents),
        *(row.vault_path for row in snapshot.manifest.supporting_documents),
        *(row.vault_path for row in snapshot.artifacts),
        *(row.vault_path for row in snapshot.catalog.assets),
    }
    if new_note in existing_paths or set(paths).intersection(existing_paths):
        raise PaperPlacementError("new paper folder collides with a provider-owned path")
    new_folder = PurePosixPath(new_note).parent.as_posix()
    if any(
        path == new_folder or path.startswith(new_folder + "/")
        for path in existing_paths
    ):
        raise PaperPlacementError("new paper folder already contains a provider-owned path")
    manifest_data = snapshot.manifest.model_dump(mode="json")
    for row in manifest_data["atomic_resources"]:
        if row["resource_id"] == request.resource_id:
            row["markdown_path"] = new_note
    manifest_data["supporting_documents"].extend(
        [
            KnowledgeSupportingDocument(
                document_id=artifact_ids[0],
                kind=SupportingDocumentKind.ANALYSIS,
                title=f"{request.document.paper_title} analysis",
                vault_path=paths[0],
                owner_id=request.resource_id,
            ).model_dump(mode="json"),
            KnowledgeSupportingDocument(
                document_id=artifact_ids[1],
                kind=SupportingDocumentKind.ANALYSIS_CANVAS,
                title=f"{request.document.paper_title} analysis Canvas",
                vault_path=paths[1],
                owner_id=request.resource_id,
            ).model_dump(mode="json"),
        ]
    )
    try:
        manifest = KnowledgeManifest.model_validate(manifest_data)
    except ValueError as exc:
        raise PaperPlacementError("proposed provider manifest is invalid") from exc
    return manifest


def _proposed_provider_graph(
    snapshot: KnowledgeProviderSnapshot,
    request: AnalysisCommitRequest,
    manifest: KnowledgeManifest,
    artifacts: tuple[KnowledgeArtifactChange, ...],
) -> ProposedProviderGraph:
    """Compute a complete graph without inventing an applied receipt."""
    combined = sorted([*snapshot.artifacts, *artifacts], key=lambda row: row.artifact_id)
    known_ids = {
        *(row.resource_id for row in manifest.atomic_resources),
        *(row.document_id for row in manifest.core_documents),
        *(row.document_id for row in manifest.supporting_documents),
        *(row.artifact_id for row in combined),
    }
    graph = ProposedProviderGraph(
        vault_binding=snapshot.vault_binding,
        manifest=manifest,
        artifacts=combined,
        relations=_merge_relations(
            snapshot.relations,
            request.relations,
            known_ids=known_ids,
            artifacts={row.artifact_id: row for row in combined},
        ),
        projections=_merge_projections(
            snapshot.projections, request.projections, known_ids=known_ids
        ),
        catalog=_apply_catalog(
            snapshot.catalog,
            manifest=manifest,
            artifacts=combined,
            changed=list(artifacts),
            # Review is deterministic and does not claim a new application time.
            generated_at=snapshot.catalog.generated_at,
        ),
        before_receipts=snapshot.receipts,
    )
    # This validator uses only graph fields, not snapshot revisions or receipts.
    # Historical receipts remain above as before-state evidence, never rewritten.
    _validate_catalog_projection(graph)
    return graph


def plan_v4_paper_placement(
    registry: KnowledgeSourceRegistry,
    *,
    source_id: str,
    field_id: str,
    request: AnalysisCommitRequest,
    bundle: AnalysisBundle,
    baseline: AnalysisBaseline,
    reviewed_files: Mapping[str, bytes],
    paper_note_source: str,
    paper_note_destination: str,
    preserved_legacy_sources: Mapping[str, str | None],
    proposed_field: FieldDefinition,
    link_rewrites: Mapping[str, Mapping[str, str]],
) -> PaperPlacementPlan:
    """Describe one exact placement without creating a lock, journal, or file.

    All paths are Vault-relative except link-rewrite document keys, which are
    relative to the selected Field. Existing provider artifact relocation is
    intentionally excluded from this first slice.
    """
    try:
        registry_bytes, registry_meta = _read_regular_absolute(registry.path)
        if registry_meta.st_uid != os.geteuid() or registry_meta.st_nlink != 1:
            raise PaperPlacementError("Source registry is not singly linked and owned")
        registry_document = KnowledgeSourceRegistryDocument.model_validate_json(registry_bytes)
        source = next(
            (row for row in registry_document.sources if row.source_id == source_id), None
        )
        if source is None or not source.enabled or "read" not in source.capabilities:
            raise PaperPlacementError("Source is not registered and readable")
        folder = next(row for row in registry_document.folders if row.folder_id == source.folder_id)
        if not folder.enabled or "read" not in folder.capabilities:
            raise PaperPlacementError("registered Source folder is not readable")
        root = registry.resolve(source_id, capability="read")
        root_device, root_inode = _identity(root)
        manifest_current = _read_target(root, _MANIFEST)
        if manifest_current is None:
            raise PaperPlacementError("registered Source has no portable Field manifest")
        if manifest_current[1].st_uid != os.geteuid() or manifest_current[1].st_nlink != 1:
            raise PaperPlacementError("Field manifest is not singly linked and owned")
        field_manifest = FieldManifest.model_validate(yaml.safe_load(manifest_current[0]))
        if field_manifest.source_id != source_id:
            raise PaperPlacementError("Source registry and portable Field manifest disagree")
        field = next((row for row in field_manifest.fields if row.field_id == field_id), None)
        if field is None:
            raise PaperPlacementError("Field is not declared by the registered Source")
        field_root = root if field.relative_root == "." else root / field.relative_root
        field_device, field_inode = _identity(field_root)
        provider_path = registry.path.parent / "knowledge-providers" / source_id
        provider_fd = _open_directory_chain(provider_path)
        try:
            provider_info = os.fstat(provider_fd)
            snapshot, provider_bytes, provider_identity = _read_snapshot(provider_fd)
            provider_file_info = os.stat(
                "knowledge-provider.snapshot.json", dir_fd=provider_fd, follow_symlinks=False
            )
        finally:
            os.close(provider_fd)
        if provider_file_info.st_uid != os.geteuid() or provider_file_info.st_nlink != 1:
            raise PaperPlacementError("provider snapshot is not singly linked and owned")
        if len(provider_bytes) > 32 * 1024 * 1024:
            raise PaperPlacementError("provider snapshot exceeds review size limit")
        binding = snapshot.vault_binding
        if binding is None or (
            Path(binding.root_path) != root
            or (binding.device, binding.inode) != (root_device, root_inode)
        ):
            raise PaperPlacementError("provider snapshot is not bound to the registered Vault")
        if request.document.schema_version != 4:
            raise PaperPlacementError("placement requires an IR v4 analysis bundle")
        if request.base_snapshot_revision != snapshot.snapshot_revision or (
            request.base_catalog_revision != snapshot.catalog.revision
        ):
            raise PaperPlacementError("candidate analysis has a stale provider revision")
        catalog_owner = next(
            (row for row in snapshot.catalog.resources if row.resource_id == request.resource_id),
            None,
        )
        if (
            catalog_owner is None
            or catalog_owner.kind is not ResourceKind.PAPER
            or request.zotero_item_key is None
            or catalog_owner.zotero.item_key != request.zotero_item_key
        ):
            raise PaperPlacementError("candidate analysis has no matching catalog PAPER owner")
        old_note = _safe_relative(paper_note_source)
        new_note = _safe_relative(paper_note_destination)
        if old_note != paper_note_source or new_note != paper_note_destination:
            raise PaperPlacementError("PAPER owner note paths must be canonical")
        old_local = _within_field(field, old_note)
        new_local = _within_field(field, new_note)
        if old_note == new_note or not old_note.endswith(".md") or not new_note.endswith(".md"):
            raise PaperPlacementError("paper owner note needs distinct Markdown paths")
        expected_field = field.model_dump(mode="json")
        if expected_field["home"] == old_local:
            expected_field["home"] = new_local
        for group in expected_field["navigation"]:
            group["items"] = [new_local if item == old_local else item for item in group["items"]]
        if proposed_field.model_dump(mode="json") != expected_field:
            raise PaperPlacementError(
                "Field navigation proposal is not the exact paper-note substitution"
            )
        planned_manifest = FieldManifest(
            source_id=source_id,
            fields=[
                proposed_field if row.field_id == field_id else row for row in field_manifest.fields
            ],
        )
        manifest_after = yaml.safe_dump(
            planned_manifest.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        ).encode("utf-8")
        payloads = _candidate_bytes(request, bundle, baseline, reviewed_files)
        provider_manifest = _manifest_after(snapshot, request, old_note, new_note)
        if any(
            re.search(rb"(?i)vault(?:=|%3d)test(?:\b|%20|&)", payloads[path])
            for path in (request.paths.markdown, request.paths.canvas)
        ):
            raise PaperPlacementError(
                "v4 candidate still targets vault=test; re-render for the registered Source"
            )
        if request.note_stem != PurePosixPath(request.paths.markdown).stem:
            raise PaperPlacementError("candidate note stem differs from its target path")
        if any(request.base_revisions[path] is not None for path in request.paths.as_list()):
            raise PaperPlacementError("new v4 folder targets must require absence")
        files: list[PaperPlacementFile] = []
        observed: dict[str, tuple[bytes, os.stat_result] | None] = {}
        old_note_state = _read_target(root, old_note)
        if old_note_state is None:
            raise PaperPlacementError("provider PAPER owner note is missing")
        if old_note_state[1].st_uid != os.geteuid() or old_note_state[1].st_nlink != 1:
            raise PaperPlacementError("PAPER owner note is not singly linked and owned")
        _assert_field_owned_markdown(old_note_state[0])
        if _has_analysis_identity(old_note_state[0]) or _has_analysis_sidecar(root, old_note):
            raise PaperPlacementError("PAPER owner note is a managed analysis source")
        observed[old_note] = old_note_state
        files.append(_file_row(old_note, "paper-note-source", old_note_state, None))
        target_paths = [new_note, *request.paths.as_list()]
        for path in target_paths:
            _within_field(field, path)
            state = _read_target(root, path, allow_missing_parent=True)
            if state is not None:
                raise PaperPlacementError(f"new paper folder target already exists: {path}")
            observed[path] = state
        files.append(_file_row(new_note, "paper-note-destination", None, old_note_state[0]))
        for path in request.paths.as_list():
            files.append(_file_row(path, "v4-analysis-candidate", None, payloads[path]))
        if (
            len(preserved_legacy_sources) not in {2, 3}
            or sum(path.endswith(".md") for path in preserved_legacy_sources) != 1
            or sum(path.endswith(".canvas") for path in preserved_legacy_sources) != 1
            or (
                len(preserved_legacy_sources) == 3
                and sum(path.endswith(".analysis.json") for path in preserved_legacy_sources) != 1
            )
        ):
            raise PaperPlacementError("preserved v2 originals require one Markdown/Canvas pair")
        legacy_md = next(path for path in preserved_legacy_sources if path.endswith(".md"))
        legacy_canvas = next(path for path in preserved_legacy_sources if path.endswith(".canvas"))
        markdown = PurePosixPath(legacy_md)
        permitted_canvas = {
            markdown.with_suffix(".canvas").as_posix(),
            markdown.with_name(markdown.name.removesuffix("分析.md") + "解析树.canvas").as_posix(),
        }
        if legacy_canvas not in permitted_canvas:
            raise PaperPlacementError("preserved v2 Canvas is not paired with its Markdown")
        if len(preserved_legacy_sources) == 3 and (
            markdown.with_suffix(".analysis.json").as_posix() not in preserved_legacy_sources
        ):
            raise PaperPlacementError("preserved v2 sidecar is not paired with its Markdown")
        legacy_sidecar = markdown.with_suffix(".analysis.json").as_posix()
        if legacy_sidecar not in preserved_legacy_sources:
            if _read_target(root, legacy_sidecar) is not None:
                raise PaperPlacementError("existing preserved v2 sidecar is missing from review")
            # Bind absence as well, so a sidecar created during review is detected.
            observed[legacy_sidecar] = None
            files.append(_file_row(legacy_sidecar, "preserved-v2-original", None, None))
        conflicts: list[str] = []
        legacy_managed = {
            _within_field(field, path)
            for path in preserved_legacy_sources
            if path.endswith((".md", ".canvas"))
        } & set(_managed_paths(field))
        if legacy_managed:
            conflicts.append(
                "preserved v2 originals remain in Field navigation: "
                + ", ".join(sorted(legacy_managed))
            )
        for path, expected_hash in sorted(preserved_legacy_sources.items()):
            safe = _safe_relative(path)
            if safe != path:
                raise PaperPlacementError("preserved v2 source path is not canonical")
            _within_field(field, safe)
            if safe in {old_note, new_note, *request.paths.as_list()}:
                raise PaperPlacementError("preserved old source overlaps a proposed target")
            if expected_hash is not None and _HASH.fullmatch(expected_hash) is None:
                raise PaperPlacementError("preserved source hash is invalid")
            if safe.endswith((".md", ".canvas")) and expected_hash is None:
                raise PaperPlacementError("preserved v2 Markdown/Canvas must exist")
            old = _read_target(root, safe)
            if (None if old is None else _hash(old[0])) != expected_hash:
                raise PaperPlacementError(f"preserved v2 source changed: {safe}")
            if old is not None and (old[1].st_uid != os.geteuid() or old[1].st_nlink != 1):
                raise PaperPlacementError("preserved v2 source is not singly linked and owned")
            observed[safe] = old
            files.append(
                _file_row(safe, "preserved-v2-original", old, None if old is None else old[0])
            )
            if old is not None and _has_legacy_hub_reference(old[0], safe):
                conflicts.append(f"preserved v2 source retains old Hub URL: {safe}")
            if safe == legacy_md and old is not None and not _has_analysis_identity(old[0]):
                raise PaperPlacementError("preserved Markdown is not a managed v2 analysis")
        expected_managed = set(_managed_paths(field))
        rewrites: list[PaperPlacementLinkRewrite] = []
        for document, replacements in sorted(link_rewrites.items()):
            local = _safe_relative(document)
            if local != document:
                raise PaperPlacementError("link rewrite document path is not canonical")
            if local not in expected_managed or not local.endswith((".md", ".canvas")):
                raise PaperPlacementError("link rewrite document is not Field-managed")
            path = _field_path(field, local)
            if path in observed:
                raise PaperPlacementError("link rewrite overlaps another placement file")
            old = _read_target(root, path)
            if old is None:
                raise PaperPlacementError("link rewrite document is missing")
            if _has_analysis_identity(old[0]) or _has_analysis_sidecar(root, path):
                raise PaperPlacementError("managed analysis links require paired review")
            if path.endswith(".md"):
                _assert_field_owned_markdown(old[0])
            revised = old[0]
            for old_text, new_text in sorted(replacements.items()):
                if not old_text or old_text == new_text:
                    raise PaperPlacementError("link rewrite is empty or unchanged")
                if not (
                    (old_local in old_text or old_note in old_text)
                    and (new_local in new_text or new_note in new_text)
                ):
                    raise PaperPlacementError("link rewrite does not bind the paper-note move")
                count = revised.count(old_text.encode("utf-8"))
                if count == 0:
                    raise PaperPlacementError("link rewrite source text is absent")
                next_bytes = revised.replace(old_text.encode("utf-8"), new_text.encode("utf-8"))
                rewrites.append(
                    PaperPlacementLinkRewrite(
                        path, old_text, new_text, count, _diff(revised, next_bytes, path)
                    )
                )
                revised = next_bytes
            observed[path] = old
            files.append(_file_row(path, "navigation-link-rewrite", old, revised))
            if old_local.encode("utf-8") in revised or old_note.encode("utf-8") in revised:
                conflicts.append(f"navigation still references old paper note: {path}")
            if _has_legacy_hub_reference(revised, path):
                conflicts.append(f"navigation retains old Hub URL: {path}")
        for document in sorted(expected_managed):
            path = _field_path(field, document)
            if path in {old_note, *observed}:
                continue
            current = _read_target(root, path)
            if current is None:
                raise PaperPlacementError(f"Field navigation document is missing: {path}")
            if path.endswith(".md"):
                _assert_field_owned_markdown(current[0])
            observed[path] = current
            if old_local.encode("utf-8") in current[0] or old_note.encode("utf-8") in current[0]:
                conflicts.append(f"unreviewed navigation references old paper note: {path}")
            if _has_legacy_hub_reference(current[0], path):
                conflicts.append(f"unreviewed navigation retains old Hub URL: {path}")
        observed[_MANIFEST] = manifest_current
        files.append(_file_row(_MANIFEST, "field-manifest", manifest_current, manifest_after))
        directories: list[PaperPlacementDirectory] = []
        parent_parts = PurePosixPath(new_note).parent.parts
        field_depth = (
            len(PurePosixPath(field.relative_root).parts) if field.relative_root != "." else 0
        )
        for depth in range(field_depth + 1, len(parent_parts) + 1):
            path = PurePosixPath(*parent_parts[:depth]).as_posix()
            row = _directory_plan(root, path)
            directories.append(PaperPlacementDirectory(path, row.device, row.inode))
        artifact_changes = tuple(
            KnowledgeArtifactChange(
                artifact_id=artifact_id,
                resource_id=request.resource_id,
                kind=kind,
                vault_path=path,
                sha256=_hash(payloads[path]),
            )
            for artifact_id, kind, path in zip(
                (
                    request.document.artifact_id,
                    f"{request.document.artifact_id}:canvas",
                    f"{request.document.artifact_id}:sidecar",
                ),
                ("analysis_markdown", "analysis_canvas", "analysis_sidecar"),
                request.paths.as_list(),
                strict=True,
            )
        )
        proposed_graph = _proposed_provider_graph(
            snapshot, request, provider_manifest, artifact_changes
        )
        proposed_graph_bytes = _json_bytes(proposed_graph.model_dump(mode="json"))
        if len(proposed_graph_bytes) > 32 * 1024 * 1024:
            raise PaperPlacementError("proposed provider graph exceeds review size limit")
        graph_before = ProposedProviderGraph(
            vault_binding=snapshot.vault_binding,
            manifest=snapshot.manifest,
            artifacts=snapshot.artifacts,
            relations=snapshot.relations,
            projections=snapshot.projections,
            catalog=snapshot.catalog,
            before_receipts=snapshot.receipts,
        )
        graph_diff = _diff(
            _json_bytes(graph_before.model_dump(mode="json")),
            proposed_graph_bytes,
            "proposed-provider-graph",
        )
        provider_diff = _diff(
            _json_bytes(snapshot.manifest.model_dump(mode="json")),
            _json_bytes(provider_manifest.model_dump(mode="json")),
            "knowledge-provider.manifest",
        )
        field_diff = _diff(manifest_current[0], manifest_after, _MANIFEST)
        # A concurrent edit during the read-only scan must not yield a coherent-looking plan.
        for path, previous in observed.items():
            current = _read_target(root, path, allow_missing_parent=path in target_paths)
            if (
                None
                if current is None
                else (_hash(current[0]), current[1].st_dev, current[1].st_ino)
            ) != (
                None
                if previous is None
                else (_hash(previous[0]), previous[1].st_dev, previous[1].st_ino)
            ):
                raise PaperPlacementError(f"placement source changed during review: {path}")
        registry_now, registry_now_meta = _read_regular_absolute(registry.path)
        if registry_now != registry_bytes or (
            registry_now_meta.st_dev,
            registry_now_meta.st_ino,
        ) != (registry_meta.st_dev, registry_meta.st_ino):
            raise PaperPlacementError("Source registry changed during review")
        provider_fd = _open_directory_chain(provider_path)
        try:
            snapshot_now, bytes_now, identity_now = _read_snapshot(provider_fd)
            provider_now = os.fstat(provider_fd)
        finally:
            os.close(provider_fd)
        if (
            bytes_now != provider_bytes
            or identity_now != provider_identity
            or snapshot_now.snapshot_revision != snapshot.snapshot_revision
            or (provider_now.st_dev, provider_now.st_ino)
            != (provider_info.st_dev, provider_info.st_ino)
            or _identity(root) != (root_device, root_inode)
            or _identity(field_root) != (field_device, field_inode)
        ):
            raise PaperPlacementError("Source or provider identity changed during review")
        semantic = {
            "schema_version": 1,
            "source_id": source_id,
            "field_id": field_id,
            "resource_id": request.resource_id,
            "root": (str(root), root_device, root_inode),
            "field_root": (str(field_root), field_device, field_inode),
            "provider": (
                str(provider_path),
                provider_info.st_dev,
                provider_info.st_ino,
                snapshot.snapshot_revision,
                _hash(provider_bytes),
                provider_identity,
            ),
            "registry": (_hash(registry_bytes), registry_meta.st_dev, registry_meta.st_ino),
            "request": request.model_dump(mode="json"),
            "files": [asdict(row) for row in sorted(files, key=lambda row: (row.path, row.kind))],
            "directories": [asdict(row) for row in directories],
            "provider_manifest_before": snapshot.manifest.model_dump(mode="json"),
            "provider_manifest_after": provider_manifest.model_dump(mode="json"),
            "field_manifest_before": field_manifest.model_dump(mode="json"),
            "field_manifest_after": planned_manifest.model_dump(mode="json"),
            "provider_artifacts": [row.model_dump(mode="json") for row in artifact_changes],
            "proposed_provider_graph_sha256": _hash(proposed_graph_bytes),
            "link_rewrites": [asdict(row) for row in rewrites],
            "conflicts": sorted(set(conflicts)),
        }
        digest = _hash(
            json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        return PaperPlacementPlan(
            digest,
            source_id,
            field_id,
            request.resource_id,
            str(root),
            root_device,
            root_inode,
            str(provider_path),
            provider_info.st_dev,
            provider_info.st_ino,
            snapshot.snapshot_revision,
            _hash(provider_bytes),
            provider_identity[0],
            provider_identity[1],
            _hash(registry_bytes),
            registry_meta.st_dev,
            registry_meta.st_ino,
            field_diff,
            provider_diff,
            tuple(sorted(files, key=lambda row: (row.path, row.kind))),
            tuple(directories),
            tuple(rewrites),
            artifact_changes,
            proposed_graph,
            _hash(proposed_graph_bytes),
            graph_diff,
            tuple(sorted(set(conflicts))),
        )
    except (OSError, FieldRegistryError, FieldTransactionError, KnowledgeApplyError, ValueError) as exc:
        if isinstance(exc, PaperPlacementError):
            raise
        raise PaperPlacementError(f"paper placement cannot be reviewed safely: {exc}") from exc


__all__ = [
    "PaperPlacementDirectory",
    "PaperPlacementError",
    "PaperPlacementFile",
    "PaperPlacementLinkRewrite",
    "PaperPlacementPlan",
    "ProposedProviderGraph",
    "plan_v4_paper_placement",
]
