"""Acknowledge metadata-only editor saves without replacing knowledge content."""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    apply_knowledge_change_set,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.commit import (
    AnalysisCommitConflict,
    AnalysisCommitSafetyError,
    _assert_v4_provider_preconditions,
    _commit_lock,
    _existing_root,
    _json_bytes,
    _path_directory_identity,
    _plan_existing_analysis_update,
    _read_target_regular,
    _registered_v4_provider,
    _request_fingerprint,
    _sha256_bytes,
)
from scholar_workflow.analysis.models import (
    AnalysisBaseline,
    AnalysisCommitRequest,
    KnowledgeChangeSet,
)
from scholar_workflow.canvas import CanvasValidationError, validate_canvas_payload
from scholar_workflow.knowledge.fields import KnowledgeSourceRegistry


def _metadata_graph(payload: bytes) -> dict:
    try:
        graph = json.loads(payload)
        validate_canvas_payload(graph)
    except (ValueError, CanvasValidationError) as exc:
        raise AnalysisCommitSafetyError(f"invalid editor Canvas: {exc}") from exc
    if graph.get("metadata", {}).get("frontmatter") != {}:
        raise AnalysisCommitSafetyError("only newly added empty editor frontmatter is supported")
    return graph


def acknowledge_canvas_metadata(
    *, vault_root: Path, request: AnalysisCommitRequest,
    source_registry: KnowledgeSourceRegistry,
) -> dict:
    """CAS-record an additive editor metadata save; do not write any Vault file."""
    if request.document.schema_version not in {4, 5} or any(
        value is None for value in request.base_revisions.values()
    ):
        raise AnalysisCommitSafetyError("metadata acknowledgement requires an existing v4/v5 pair")
    root = _existing_root(vault_root, label="Vault root")
    identity = _path_directory_identity(root)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        canvas = _metadata_graph(_read_target_regular(root, descriptor, request.paths.canvas))
    finally:
        os.close(descriptor)
    original_graph = {key: value for key, value in canvas.items() if key != "metadata"}
    original_hash = _sha256_bytes(_json_bytes(original_graph))
    current_hash = request.base_revisions[request.paths.canvas]
    semantic = {
        "source_receipt": "canvas-metadata:" + _request_fingerprint(request),
        "base_catalog_revision": request.base_catalog_revision,
        "upsert_artifacts": [{
            "artifact_id": request.document.artifact_id + ":canvas",
            "resource_id": request.resource_id,
            "kind": "analysis_canvas",
            "vault_path": request.paths.canvas,
            "sha256": current_hash,
        }],
        "upsert_relations": [], "upsert_projections": [],
        "expected_base_hashes": {request.paths.canvas: original_hash},
    }
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    change = KnowledgeChangeSet.model_validate({
        **semantic, "change_id": "change:" + sha256(encoded.encode()).hexdigest(),
    })
    with _registered_v4_provider(source_registry, root, request) as (provider, source_id):
        with ExitStack() as locks:
            def verify(snapshot: KnowledgeProviderSnapshot) -> None:
                binding = snapshot.vault_binding
                if binding is None or (
                    Path(binding.root_path) != root
                    or (binding.device, binding.inode) != identity
                ):
                    raise AnalysisCommitSafetyError("metadata provider belongs to another Vault")
                vault_fd = locks.enter_context(_commit_lock(root, identity))
                contents = {
                    path: _read_target_regular(root, vault_fd, path)
                    for path in request.paths.as_list()
                }
                if any(_sha256_bytes(value) != request.base_revisions[path]
                       for path, value in contents.items()):
                    raise AnalysisCommitConflict("metadata acknowledgement base changed")
                current_graph = _metadata_graph(contents[request.paths.canvas])
                stripped = {k: v for k, v in current_graph.items() if k != "metadata"}
                if _sha256_bytes(_json_bytes(stripped)) != original_hash:
                    raise AnalysisCommitConflict("Canvas graph changed during metadata acknowledgement")
                prior = any(row.change_id == change.change_id for row in snapshot.receipts)
                bases = dict(request.base_revisions)
                bases[request.paths.canvas] = current_hash if prior else original_hash
                check = request.model_copy(update={
                    "base_revisions": bases,
                    "base_catalog_revision": snapshot.catalog.revision if prior else request.base_catalog_revision,
                    "base_snapshot_revision": snapshot.snapshot_revision if prior else request.base_snapshot_revision,
                })
                _assert_v4_provider_preconditions(check, snapshot)
                try:
                    baseline = AnalysisBaseline.model_validate_json(contents[request.paths.sidecar])
                except ValueError as exc:
                    raise AnalysisCommitSafetyError("metadata baseline is invalid") from exc
                if baseline.artifact_id != request.document.artifact_id:
                    raise AnalysisCommitSafetyError("metadata baseline identity differs from the request")
                _plan_existing_analysis_update(
                    root, vault_fd, request.model_copy(update={"document": baseline.document}),
                )

            receipt = apply_knowledge_change_set(
                state_root=provider, change_set=change, before_apply=verify,
            )
        snapshot = load_knowledge_provider_snapshot(provider)
        next_request = request.model_copy(update={
            "base_catalog_revision": snapshot.catalog.revision,
            "base_snapshot_revision": snapshot.snapshot_revision,
        })
        _assert_v4_provider_preconditions(next_request, snapshot)
        return {
            "schema_version": 1, "source_id": source_id, "metadata_only": True,
            "canonical_written": False, "files": request.base_revisions,
            "provider_receipt": receipt.model_dump(mode="json"),
            "next_request": next_request.model_dump(mode="json"),
        }
