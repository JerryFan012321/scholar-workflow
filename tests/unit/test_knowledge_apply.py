from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from scholar_workflow.analysis.apply_changes import (
    KnowledgeApplyConflict,
    KnowledgeApplyReceipt,
    KnowledgeApplySafetyError,
    KnowledgeProviderSnapshot,
    KnowledgeSnapshotCatalogProvider,
    apply_knowledge_change_set,
    initialize_knowledge_provider_snapshot,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.models import (
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeChangeSet,
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
)
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
)
from scholar_workflow.hub.server import start_hub_server
from scholar_workflow.models import ResourceKind

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 22, tzinfo=UTC)
HASHES = {
    "markdown": "sha256:" + "1" * 64,
    "canvas": "sha256:" + "2" * 64,
    "sidecar": "sha256:" + "3" * 64,
}


def _manifest() -> KnowledgeManifest:
    return KnowledgeManifest(
        atomic_resources=[
            KnowledgeAtomicResource(
                resource_id="paper:jepa",
                kind=ResourceKind.PAPER,
                title="JEPA",
                markdown_path="topics/jepa/JEPA.md",
            )
        ]
    )


def _catalog() -> HubCatalog:
    return HubCatalog(
        generated_at=NOW,
        resources=[
            HubResource(
                resource_id="paper:jepa",
                kind=ResourceKind.PAPER,
                title="JEPA",
            )
        ],
    )


def _change_id(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "change:" + hashlib.sha256(encoded).hexdigest()


def _semantic_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _change(
    base_revision: str,
    *,
    stem: str = "analysis:paper:jepa",
    hashes: dict[str, str] | None = None,
    expected: dict[str, str | None] | None = None,
    relations: list[KnowledgeRelation] | None = None,
    projections: list[KnowledgeProjection] | None = None,
) -> KnowledgeChangeSet:
    revisions = hashes or HASHES
    artifacts = [
        KnowledgeArtifactChange(
            artifact_id=stem,
            resource_id="paper:jepa",
            kind="analysis_markdown",
            vault_path="topics/jepa/JEPA分析.md",
            sha256=revisions["markdown"],
        ),
        KnowledgeArtifactChange(
            artifact_id=f"{stem}:canvas",
            resource_id="paper:jepa",
            kind="analysis_canvas",
            vault_path="topics/jepa/JEPA解析树.canvas",
            sha256=revisions["canvas"],
        ),
        KnowledgeArtifactChange(
            artifact_id=f"{stem}:sidecar",
            resource_id="paper:jepa",
            kind="analysis_sidecar",
            vault_path="topics/jepa/JEPA分析.analysis.json",
            sha256=revisions["sidecar"],
        ),
    ]
    relation_rows = relations
    if relation_rows is None:
        relation_rows = [
            KnowledgeRelation(
                from_id="paper:jepa",
                relation="has-analysis",
                to_id=stem,
            )
        ]
    projection_rows = projections
    if projection_rows is None:
        projection_rows = [
            KnowledgeProjection(
                projection_id="projection:jepa-analysis",
                kind="obsidian",
                target_id=stem,
            )
        ]
    base_hashes = expected
    if base_hashes is None:
        base_hashes = {item.vault_path: None for item in artifacts}
    semantic: dict[str, object] = {
        "source_receipt": "analysis-commit:jepa-one",
        "base_catalog_revision": base_revision,
        "upsert_artifacts": [item.model_dump(mode="json") for item in artifacts],
        "upsert_relations": [item.model_dump(mode="json") for item in relation_rows],
        "upsert_projections": [item.model_dump(mode="json") for item in projection_rows],
        "expected_base_hashes": base_hashes,
    }
    return KnowledgeChangeSet(change_id=_change_id(semantic), **semantic)


def _initialize(tmp_path: Path) -> Path:
    state = tmp_path / "provider"
    state.mkdir()
    initialize_knowledge_provider_snapshot(
        state_root=state,
        manifest=_manifest(),
        catalog=_catalog(),
    )
    return state


def test_apply_updates_manifest_and_catalog_as_one_idempotent_snapshot(
    tmp_path: Path,
) -> None:
    state = _initialize(tmp_path)
    base = load_knowledge_provider_snapshot(state)
    change = _change(base.catalog.revision)

    first = apply_knowledge_change_set(
        state_root=state,
        change_set=change,
        clock=lambda: NOW,
    )
    snapshot_path = state / "knowledge-provider.snapshot.json"
    committed_bytes = snapshot_path.read_bytes()
    replay = apply_knowledge_change_set(
        state_root=state,
        change_set=change,
        clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
    )
    snapshot = load_knowledge_provider_snapshot(state)

    assert replay == first
    assert snapshot_path.read_bytes() == committed_bytes
    assert {item.document_id for item in snapshot.manifest.supporting_documents} == {
        "analysis:paper:jepa",
        "analysis:paper:jepa:canvas",
    }
    assert {item.artifact_id for item in snapshot.artifacts} == {
        "analysis:paper:jepa",
        "analysis:paper:jepa:canvas",
        "analysis:paper:jepa:sidecar",
    }
    assert {item.artifact_id for item in snapshot.catalog.artifacts} == {
        "analysis:paper:jepa",
        "analysis:paper:jepa:canvas",
    }
    assert snapshot.catalog.resources[0].artifact_ids == [
        "analysis:paper:jepa",
        "analysis:paper:jepa:canvas",
    ]
    assert snapshot.relations == change.upsert_relations
    assert snapshot.projections == change.upsert_projections
    assert KnowledgeSnapshotCatalogProvider(state).load() == snapshot.catalog


def test_change_id_reuse_and_stale_catalog_revision_fail_without_writes(
    tmp_path: Path,
) -> None:
    state = _initialize(tmp_path)
    base = load_knowledge_provider_snapshot(state)
    first = _change(base.catalog.revision)
    apply_knowledge_change_set(state_root=state, change_set=first, clock=lambda: NOW)
    snapshot_path = state / "knowledge-provider.snapshot.json"
    committed = snapshot_path.read_bytes()

    forged = first.model_copy(deep=True)
    forged.upsert_artifacts[0].sha256 = "sha256:" + "9" * 64
    with pytest.raises(KnowledgeApplyConflict, match="change_id does not match"):
        apply_knowledge_change_set(state_root=state, change_set=forged)

    stale = _change(
        base.catalog.revision,
        hashes={
            "markdown": "sha256:" + "4" * 64,
            "canvas": "sha256:" + "5" * 64,
            "sidecar": "sha256:" + "6" * 64,
        },
        expected={
            "topics/jepa/JEPA分析.md": HASHES["markdown"],
            "topics/jepa/JEPA解析树.canvas": HASHES["canvas"],
            "topics/jepa/JEPA分析.analysis.json": HASHES["sidecar"],
        },
    )
    with pytest.raises(KnowledgeApplyConflict, match="base catalog revision changed"):
        apply_knowledge_change_set(state_root=state, change_set=stale)
    assert snapshot_path.read_bytes() == committed


def test_fault_before_replace_is_zero_write_and_fault_after_replace_replays(
    tmp_path: Path,
) -> None:
    state = _initialize(tmp_path)
    snapshot_path = state / "knowledge-provider.snapshot.json"
    before = snapshot_path.read_bytes()
    change = _change(load_knowledge_provider_snapshot(state).catalog.revision)

    def fail_before(point: str) -> None:
        if point == "before-snapshot-replace":
            raise RuntimeError("before replace")

    with pytest.raises(RuntimeError, match="before replace"):
        apply_knowledge_change_set(
            state_root=state,
            change_set=change,
            fault_inject=fail_before,
        )
    assert snapshot_path.read_bytes() == before

    def fail_after(point: str) -> None:
        if point == "after-snapshot-replace":
            raise RuntimeError("after replace")

    with pytest.raises(RuntimeError, match="after replace"):
        apply_knowledge_change_set(
            state_root=state,
            change_set=change,
            clock=lambda: NOW,
            fault_inject=fail_after,
        )
    replay = apply_knowledge_change_set(state_root=state, change_set=change)
    assert replay == load_knowledge_provider_snapshot(state).receipts[0]


def test_apply_enforces_owner_relation_and_project_tool_boundaries(tmp_path: Path) -> None:
    state = _initialize(tmp_path)
    base = load_knowledge_provider_snapshot(state)
    snapshot_path = state / "knowledge-provider.snapshot.json"
    before = snapshot_path.read_bytes()

    bad_owner = _change(base.catalog.revision)
    bad_owner.upsert_artifacts[0].resource_id = "paper:missing"
    semantic = bad_owner.model_dump(mode="json", exclude={"schema_version", "change_id"})
    bad_owner.change_id = _change_id(semantic)
    with pytest.raises(KnowledgeApplyConflict, match="not an explicit atomic resource"):
        apply_knowledge_change_set(state_root=state, change_set=bad_owner)

    project_relation = _change(
        base.catalog.revision,
        relations=[
            KnowledgeRelation(
                from_id="paper:jepa",
                relation="related-to",
                to_id="project:forbidden",
            )
        ],
        projections=[],
    )
    with pytest.raises(KnowledgeApplyConflict, match="Projects and Tools"):
        apply_knowledge_change_set(state_root=state, change_set=project_relation)

    project_projection = _change(
        base.catalog.revision,
        relations=[],
        projections=[
            KnowledgeProjection(
                projection_id="projection:project",
                kind="project",
                target_id="paper:jepa",
            )
        ],
    )
    with pytest.raises(KnowledgeApplyConflict, match="Projects and Tools"):
        apply_knowledge_change_set(state_root=state, change_set=project_projection)
    assert snapshot_path.read_bytes() == before


def test_existing_artifact_update_requires_content_hash_cas(tmp_path: Path) -> None:
    state = _initialize(tmp_path)
    first = _change(load_knowledge_provider_snapshot(state).catalog.revision)
    apply_knowledge_change_set(state_root=state, change_set=first, clock=lambda: NOW)
    current = load_knowledge_provider_snapshot(state)
    updated_hashes = {
        "markdown": "sha256:" + "4" * 64,
        "canvas": "sha256:" + "5" * 64,
        "sidecar": "sha256:" + "6" * 64,
    }
    expected = {item.vault_path: item.sha256 for item in current.artifacts}
    update = _change(
        current.catalog.revision,
        hashes=updated_hashes,
        expected=expected,
    )

    receipt = apply_knowledge_change_set(
        state_root=state,
        change_set=update,
        clock=lambda: datetime(2026, 9, 23, tzinfo=UTC),
    )
    snapshot = load_knowledge_provider_snapshot(state)

    assert receipt.before_catalog_revision == current.catalog.revision
    assert {item.sha256 for item in snapshot.artifacts} == set(updated_hashes.values())
    assert {item.revision for item in snapshot.catalog.artifacts} == {
        updated_hashes["markdown"],
        updated_hashes["canvas"],
    }
    assert len(snapshot.receipts) == 2


def test_checked_in_provider_schemas_accept_runtime_snapshot(tmp_path: Path) -> None:
    state = _initialize(tmp_path)
    change = _change(load_knowledge_provider_snapshot(state).catalog.revision)
    receipt = apply_knowledge_change_set(
        state_root=state,
        change_set=change,
        clock=lambda: NOW,
    )
    snapshot = load_knowledge_provider_snapshot(state)
    names = (
        "hub-catalog.schema.json",
        "knowledge-manifest.schema.json",
        "knowledge-change-set.schema.json",
        "knowledge-apply-receipt.schema.json",
        "knowledge-provider-snapshot.schema.json",
    )
    schemas = {
        name: json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        for name in names
    }
    registry = Registry()
    for name, schema in schemas.items():
        resource = Resource.from_contents(schema)
        registry = registry.with_resource(schema["$id"], resource)
        if name == "hub-catalog.schema.json":
            registry = registry.with_resource(
                "https://scholar-workflow.local/contracts/hub-catalog.schema.json",
                resource,
            )

    jsonschema.Draft202012Validator(
        schemas["knowledge-apply-receipt.schema.json"],
        registry=registry,
    ).validate(receipt.model_dump(mode="json"))
    jsonschema.Draft202012Validator(
        schemas["knowledge-provider-snapshot.schema.json"],
        registry=registry,
    ).validate(snapshot.model_dump(mode="json"))
    assert KnowledgeProviderSnapshot.model_validate_json(
        (state / "knowledge-provider.snapshot.json").read_text(encoding="utf-8")
    ) == snapshot


def test_replay_rejects_receipt_without_applied_change(tmp_path: Path) -> None:
    state = _initialize(tmp_path)
    snapshot = load_knowledge_provider_snapshot(state)
    change = _change(snapshot.catalog.revision)
    fingerprint = _semantic_hash(change.model_dump(mode="json"))
    receipt_semantic: dict[str, object] = {
        "change_id": change.change_id,
        "change_fingerprint": fingerprint,
        "source_receipt": change.source_receipt,
        "before_catalog_revision": snapshot.catalog.revision,
        "after_catalog_revision": snapshot.catalog.revision,
        "applied_artifact_ids": [],
    }
    receipt = KnowledgeApplyReceipt(
        receipt_id=(
            "knowledge-apply:"
            + _semantic_hash(receipt_semantic).removeprefix("sha256:")
        ),
        applied_at=NOW,
        **receipt_semantic,
    )
    forged = snapshot.model_dump(mode="json")
    forged["snapshot_revision"] = ""
    forged["receipts"] = [receipt.model_dump(mode="json")]
    persisted = KnowledgeProviderSnapshot.model_validate(forged)
    (state / "knowledge-provider.snapshot.json").write_text(
        json.dumps(persisted.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeApplySafetyError, match="does not match"):
        apply_knowledge_change_set(state_root=state, change_set=change)


def test_apply_rejects_state_root_rename_swap(tmp_path: Path) -> None:
    state = _initialize(tmp_path)
    before = (state / "knowledge-provider.snapshot.json").read_bytes()
    moved = tmp_path / "provider-moved"
    change = _change(load_knowledge_provider_snapshot(state).catalog.revision)

    def swap_root(point: str) -> None:
        if point == "before-snapshot-replace":
            state.rename(moved)
            state.mkdir()

    with pytest.raises(KnowledgeApplySafetyError, match="binding changed"):
        apply_knowledge_change_set(
            state_root=state,
            change_set=change,
            fault_inject=swap_root,
        )

    assert not (state / "knowledge-provider.snapshot.json").exists()
    assert (moved / "knowledge-provider.snapshot.json").read_bytes() == before


def test_apply_does_not_report_success_if_state_root_moves_after_replace(
    tmp_path: Path,
) -> None:
    state = _initialize(tmp_path)
    moved = tmp_path / "provider-moved"
    change = _change(load_knowledge_provider_snapshot(state).catalog.revision)

    def swap_root(point: str) -> None:
        if point == "after-snapshot-replace":
            state.rename(moved)
            state.mkdir()

    with pytest.raises(KnowledgeApplySafetyError, match="binding changed"):
        apply_knowledge_change_set(
            state_root=state,
            change_set=change,
            clock=lambda: NOW,
            fault_inject=swap_root,
        )

    assert not (state / "knowledge-provider.snapshot.json").exists()
    assert load_knowledge_provider_snapshot(moved).receipts


def test_provider_rejects_undeclared_catalog_objects_and_control_plane_ids(
    tmp_path: Path,
) -> None:
    missing_resource = HubCatalog(generated_at=NOW)
    with pytest.raises(ValueError, match="exactly match"):
        initialize_knowledge_provider_snapshot(
            state_root=tmp_path,
            manifest=_manifest(),
            catalog=missing_resource,
        )

    extra_resource = _catalog().model_copy(deep=True)
    extra_resource.resources.append(
        HubResource(
            resource_id="technical:undeclared",
            kind=ResourceKind.TECHNICAL_DOCUMENT,
            title="Undeclared",
        )
    )
    extra_resource.revision = ""
    with pytest.raises(ValueError, match="exactly match"):
        initialize_knowledge_provider_snapshot(
            state_root=tmp_path,
            manifest=_manifest(),
            catalog=extra_resource,
        )

    extra_artifact = _catalog().model_copy(deep=True)
    extra_artifact.artifacts.append(
        HubArtifact(
            artifact_id="analysis:undeclared",
            kind=ArtifactKind.PAPER_ANALYSIS,
            format=ArtifactFormat.MARKDOWN,
            vault_path="topics/jepa/undeclared.md",
            resource_id="paper:jepa",
        )
    )
    extra_artifact.resources[0].artifact_ids.append("analysis:undeclared")
    extra_artifact.revision = ""
    with pytest.raises(ValueError, match="exactly match"):
        initialize_knowledge_provider_snapshot(
            state_root=tmp_path,
            manifest=_manifest(),
            catalog=extra_artifact,
        )

    bad_manifest = _manifest().model_copy(deep=True)
    bad_manifest.atomic_resources[0].resource_id = "project:forbidden"
    bad_catalog = _catalog().model_copy(deep=True)
    bad_catalog.resources[0].resource_id = "project:forbidden"
    bad_catalog.revision = ""
    with pytest.raises(ValueError, match="Projects and Tools"):
        initialize_knowledge_provider_snapshot(
            state_root=tmp_path,
            manifest=bad_manifest,
            catalog=bad_catalog,
        )

    colliding_sidecar = KnowledgeArtifactChange(
        artifact_id="paper:jepa",
        resource_id="paper:jepa",
        kind="analysis_sidecar",
        vault_path="topics/jepa/JEPA.md",
        sha256=HASHES["sidecar"],
    )
    with pytest.raises(ValueError, match="collides"):
        initialize_knowledge_provider_snapshot(
            state_root=tmp_path,
            manifest=_manifest(),
            catalog=_catalog(),
            artifacts=[colliding_sidecar],
        )


def test_default_hub_uses_authoritative_provider_snapshot_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    state = home / "knowledge-provider"
    state.mkdir(parents=True)
    initialize_knowledge_provider_snapshot(
        state_root=state,
        manifest=_manifest(),
        catalog=_catalog(),
    )
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(home))

    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        owner_mode="headless",
    )
    try:
        assert isinstance(
            server.runtime.catalog_provider,
            KnowledgeSnapshotCatalogProvider,
        )
        assert server.runtime.catalog_provider.load() == _catalog()
        assert server.runtime.catalog_path == state / "knowledge-provider.snapshot.json"
    finally:
        server.server_close()
