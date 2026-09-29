"""Provider preparation is pure; only a joint coordinator can publish its payload."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from scholar_workflow.analysis.apply_changes import (
    JointPaperPlacementReceipt,
    KnowledgeApplyConflict,
    KnowledgeApplySafetyError,
    KnowledgeProviderSnapshot,
    KnowledgeVaultBinding,
    _make_receipt,
    apply_knowledge_change_set,
    finalize_joint_paper_placement,
    prepare_joint_paper_placement,
)
from scholar_workflow.analysis.models import (
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeChangeSet,
    KnowledgeManifest,
    KnowledgeRelation,
    ProfileKind,
    ZoteroPdfSpan,
)
from scholar_workflow.hub.models import HubArtifact, HubAsset, HubCatalog, HubResource, ZoteroLink
from scholar_workflow.models import ResourceKind

NOW = datetime(2026, 9, 29, tzinfo=UTC)
OLD_NOTE = "field/paper_assets/Paper.md"
NEW_NOTE = "field/resources/papers/paper/Paper.md"
HASH = "sha256:" + "a" * 64


def _inputs():
    binding = KnowledgeVaultBinding(root_path="/synthetic-vault", device=1, inode=42)
    catalog = HubCatalog(
        generated_at=NOW,
        resources=[HubResource(
            resource_id="paper:fixture", kind=ResourceKind.PAPER,
            zotero=ZoteroLink(item_key="ABCDEFGH"),
        )],
    )
    legacy_change = KnowledgeChangeSet(
        change_id="change:" + "1" * 64, source_receipt="fixture-history",
        base_catalog_revision=catalog.revision, upsert_artifacts=[], expected_base_hashes={},
    )
    historical = _make_receipt(
        legacy_change, fingerprint=HASH, before_revision=catalog.revision,
        after_revision=catalog.revision, applied_at=NOW,
    )
    snapshot = KnowledgeProviderSnapshot(
        vault_binding=binding,
        manifest=KnowledgeManifest(atomic_resources=[KnowledgeAtomicResource(
            resource_id="paper:fixture", kind=ResourceKind.PAPER, title="Paper",
            markdown_path=OLD_NOTE,
        )]),
        catalog=catalog, receipts=[historical],
    )
    document = AnalysisDocument(
        schema_version=4, artifact_id="analysis:paper:fixture", paper_title="Paper",
        language="en", profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        claims=[AnalysisClaim(
            claim_id="task", role=AnalysisRole.ABSTRACT, outline_path="abstract/task",
            title="Task", body="A synthetic task.",
            evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Abstract", source_spans=[
                ZoteroPdfSpan(library_type="personal", library_id="1", attachment_key="12345678",
                              content_hash=HASH, page_index=0),
            ]),
        )],
    )
    paths = AnalysisCanonicalPaths(
        markdown="field/resources/papers/paper/Analysis.md",
        canvas="field/resources/papers/paper/Analysis.canvas",
        sidecar="field/resources/papers/paper/Analysis.analysis.json",
    )
    request = AnalysisCommitRequest(
        commit_id="placement", batch_id="batch", item_id="item",
        source_state=AnalysisState.VALIDATED, resource_id="paper:fixture",
        note_stem="Analysis", document=document, paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        base_catalog_revision=catalog.revision, base_snapshot_revision=snapshot.snapshot_revision,
        zotero_item_key="ABCDEFGH",
        relations=[KnowledgeRelation(from_id="paper:fixture", relation="has-analysis",
                                     to_id=document.artifact_id)],
    )
    artifacts = [KnowledgeArtifactChange(
        artifact_id=document.artifact_id + suffix, resource_id=request.resource_id,
        kind=kind, vault_path=path, sha256=HASH,
    ) for suffix, kind, path in zip(
        ("", ":canvas", ":sidecar"),
        ("analysis_markdown", "analysis_canvas", "analysis_sidecar"), paths.as_list(), strict=True,
    )]
    return {
        "snapshot": snapshot, "request": request, "vault_binding": binding,
        "transaction_id": "world-models-1", "plan_digest": HASH,
        "source_note_path": OLD_NOTE, "destination_note_path": NEW_NOTE, "note_sha256": HASH,
        "new_artifacts": artifacts,
    }


def test_preparation_is_prospective_and_finalizer_preserves_receipts(monkeypatch):
    values = _inputs()
    before = values["snapshot"].model_dump_json()

    def no_io(*args, **kwargs):
        raise AssertionError("pure provider preparation must never perform IO")

    monkeypatch.setattr("os.open", no_io)
    prepared = prepare_joint_paper_placement(**values)
    assert not hasattr(prepared, "receipt")
    assert not hasattr(prepared, "payload")
    assert prepared.manifest.atomic_resources[0].markdown_path == NEW_NOTE
    after = finalize_joint_paper_placement(
        prepared, current_snapshot=values["snapshot"], committed_at=NOW,
    )
    assert values["snapshot"].model_dump_json() == before
    assert after.snapshot.receipts[:-1] == values["snapshot"].receipts
    assert isinstance(after.snapshot.receipts[-1], JointPaperPlacementReceipt)
    assert after.before_snapshot_revision == values["snapshot"].snapshot_revision
    assert after.after_snapshot_revision != after.before_snapshot_revision
    assert KnowledgeProviderSnapshot.model_validate_json(after.payload) == after.snapshot


@pytest.mark.parametrize("case", ["snapshot", "vault", "owner", "key", "source", "path", "artifact"])
def test_preparation_rejects_stale_or_wrong_ownership(case):
    values = _inputs()
    if case == "snapshot":
        values["request"].base_snapshot_revision = HASH
    elif case == "vault":
        values["vault_binding"] = KnowledgeVaultBinding(root_path="/other", device=1, inode=43)
    elif case == "owner":
        values["new_artifacts"][0].resource_id = "paper:other"
    elif case == "key":
        values["request"].zotero_item_key = "87654321"
    elif case == "source":
        values["source_note_path"] = "field/wrong.md"
    elif case == "path":
        values["destination_note_path"] = values["request"].paths.markdown
    else:
        values["new_artifacts"][0].artifact_id = "analysis:other"
    with pytest.raises(KnowledgeApplyConflict):
        prepare_joint_paper_placement(**values)


def test_finalizer_rejects_intervening_full_snapshot_change():
    values = _inputs()
    prepared = prepare_joint_paper_placement(**values)
    raw = values["snapshot"].model_dump(mode="json")
    raw["snapshot_revision"] = ""
    raw["manifest"]["atomic_resources"][0]["title"] = "Concurrent title update"
    changed = KnowledgeProviderSnapshot.model_validate(raw)
    assert changed.catalog.revision == values["snapshot"].catalog.revision
    with pytest.raises(KnowledgeApplyConflict, match="full provider snapshot"):
        finalize_joint_paper_placement(prepared, current_snapshot=changed, committed_at=NOW)


def test_finalizer_rejects_mutated_prospective_graph_and_naive_clock():
    values = _inputs()
    prepared = prepare_joint_paper_placement(**values)
    with pytest.raises(KnowledgeApplySafetyError, match="aware"):
        finalize_joint_paper_placement(
            prepared, current_snapshot=values["snapshot"], committed_at=NOW.replace(tzinfo=None),
        )
    prepared.manifest.atomic_resources[0].title = "Unreviewed title"
    with pytest.raises(KnowledgeApplyConflict, match="changed after preparation"):
        finalize_joint_paper_placement(prepared, current_snapshot=values["snapshot"], committed_at=NOW)


def test_new_receipt_snapshot_matches_published_schema():
    values = _inputs()
    result = finalize_joint_paper_placement(
        prepare_joint_paper_placement(**values), current_snapshot=values["snapshot"], committed_at=NOW,
    )
    root = Path(__file__).resolve().parents[2] / "contracts"
    registry = Registry()
    for path in root.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        registry = registry.with_resource(
            "https://scholar-workflow.local/contracts/" + path.name, Resource.from_contents(schema),
        )
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    schema = json.loads((root / "knowledge-provider-snapshot.schema.json").read_text())
    jsonschema.Draft202012Validator(schema, registry=registry).validate(json.loads(result.payload))


def test_committed_placement_cannot_be_reused_as_new_transaction():
    values = _inputs()
    result = finalize_joint_paper_placement(
        prepare_joint_paper_placement(**values), current_snapshot=values["snapshot"], committed_at=NOW,
    )
    values["snapshot"] = result.snapshot
    values["request"].base_snapshot_revision = result.snapshot.snapshot_revision
    values["request"].base_catalog_revision = result.snapshot.catalog.revision
    with pytest.raises(KnowledgeApplyConflict, match="already committed"):
        prepare_joint_paper_placement(**values)


@pytest.mark.parametrize("collision", ["id", "path", "folder"])
def test_preparation_rejects_existing_provider_ownership(collision):
    values = _inputs()
    raw = values["snapshot"].model_dump(mode="json")
    raw["snapshot_revision"] = ""
    other = {
        "resource_id": "paper:other", "kind": "paper", "title": "Other",
        "markdown_path": "field/Other.md",
    }
    if collision == "id":
        other["resource_id"] = values["request"].document.artifact_id
    elif collision == "path":
        other["markdown_path"] = NEW_NOTE
    else:
        other["markdown_path"] = "field/resources/papers/paper/Other.md"
    raw["manifest"]["atomic_resources"].append(other)
    raw["catalog"]["resources"].append(HubResource(
        resource_id=other["resource_id"], kind=ResourceKind.PAPER,
    ).model_dump(mode="json"))
    raw["catalog"]["revision"] = ""
    raw["receipts"] = []
    snapshot = KnowledgeProviderSnapshot.model_validate(raw)
    values["snapshot"] = snapshot
    values["request"].base_catalog_revision = snapshot.catalog.revision
    values["request"].base_snapshot_revision = snapshot.snapshot_revision
    with pytest.raises(KnowledgeApplyConflict, match="already|belongs"):
        prepare_joint_paper_placement(**values)


def test_ordinary_provider_apply_continues_after_joint_receipt(tmp_path):
    import hashlib

    values = _inputs()
    result = finalize_joint_paper_placement(
        prepare_joint_paper_placement(**values), current_snapshot=values["snapshot"], committed_at=NOW,
    )
    state = tmp_path / "provider"
    state.mkdir()
    (state / "knowledge-provider.snapshot.json").write_bytes(result.payload)
    semantic = {
        "source_receipt": "analysis-commit:later", "base_catalog_revision": result.snapshot.catalog.revision,
        "upsert_artifacts": [], "upsert_relations": [], "upsert_projections": [],
        "expected_base_hashes": {},
    }
    digest = hashlib.sha256(json.dumps(
        semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    change = KnowledgeChangeSet(change_id=f"change:{digest}", **semantic)
    receipt = apply_knowledge_change_set(state_root=state, change_set=change, clock=lambda: NOW)
    loaded = KnowledgeProviderSnapshot.model_validate_json(
        (state / "knowledge-provider.snapshot.json").read_bytes(),
    )
    assert loaded.receipts == [*result.snapshot.receipts, receipt]


@pytest.mark.parametrize("kind", ["core", "support", "provider-sidecar", "catalog-asset"])
def test_new_paper_folder_rejects_all_foreign_managed_paths(kind):
    values = _inputs()
    raw = values["snapshot"].model_dump(mode="json")
    raw["snapshot_revision"] = ""
    raw["receipts"] = []
    raw["manifest"]["atomic_resources"].append({
        "resource_id": "paper:other", "kind": "paper", "title": "Other",
        "markdown_path": "field/Other.md",
    })
    raw["catalog"]["resources"].append(HubResource(
        resource_id="paper:other", kind=ResourceKind.PAPER,
    ).model_dump(mode="json"))
    path = "field/resources/papers/paper/nested/Other.md"
    if kind == "core":
        raw["manifest"]["core_documents"].append({
            "document_id": "context:other", "kind": "catalog", "title": "Other",
            "markdown_path": path,
        })
    elif kind == "support":
        raw["manifest"]["supporting_documents"].append({
            "document_id": "note:other", "kind": "reading_note", "title": "Other",
            "owner_id": "paper:other", "vault_path": path,
        })
    elif kind == "provider-sidecar":
        raw["artifacts"].append(KnowledgeArtifactChange(
            artifact_id="analysis:other:sidecar", resource_id="paper:other",
            kind="analysis_sidecar", vault_path=path + ".json", sha256=HASH,
        ).model_dump(mode="json"))
    else:
        artifact_id = "analysis:other"
        artifact_path = "field/Other-analysis.md"
        raw["manifest"]["supporting_documents"].append({
            "document_id": artifact_id, "kind": "analysis", "title": "Other",
            "owner_id": "paper:other", "vault_path": artifact_path,
        })
        raw["artifacts"].append(KnowledgeArtifactChange(
            artifact_id=artifact_id, resource_id="paper:other", kind="analysis_markdown",
            vault_path=artifact_path, sha256=HASH,
        ).model_dump(mode="json"))
        raw["catalog"]["artifacts"].append(HubArtifact(
            artifact_id=artifact_id, kind="paper-analysis", format="markdown",
            vault_path=artifact_path, resource_id="paper:other", revision=HASH,
        ).model_dump(mode="json"))
        raw["catalog"]["resources"][-1]["artifact_ids"] = [artifact_id]
        raw["catalog"]["assets"].append(HubAsset(
            asset_id="asset:other", owner_artifact_ids=[artifact_id], vault_path=path + ".png",
            display_name="Other.png", media_type="image/png", size=1, sha256=HASH, role="embed",
        ).model_dump(mode="json"))
    raw["catalog"]["revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(raw)
    values["snapshot"] = snapshot
    values["request"].base_snapshot_revision = snapshot.snapshot_revision
    values["request"].base_catalog_revision = snapshot.catalog.revision
    with pytest.raises(KnowledgeApplyConflict, match="folder belongs to another"):
        prepare_joint_paper_placement(**values)


@pytest.mark.parametrize("path", [
    "../outside.md", "field/../outside.md", "field/nested/../../outside.md",
    "./note.md", "field/./note.md", "/outside.md", "field//note.md",
    "field\\note.md", "field/note.md\n",
])
def test_joint_receipt_schema_rejects_unsafe_note_paths(path):
    root = Path(__file__).resolve().parents[2] / "contracts"
    schema = json.loads((root / "knowledge-provider-snapshot.schema.json").read_text())
    validator = jsonschema.Draft202012Validator({"$ref": "#/$defs/vaultMarkdownPath", "$defs": schema["$defs"]})
    assert not validator.is_valid(path)


@pytest.mark.parametrize("path", ["Note.md", "field/notes/Note.md", "field/.notes/Note.md", "目录/论文.md"])
def test_joint_receipt_schema_accepts_canonical_note_paths(path):
    root = Path(__file__).resolve().parents[2] / "contracts"
    schema = json.loads((root / "knowledge-provider-snapshot.schema.json").read_text())
    validator = jsonschema.Draft202012Validator({"$ref": "#/$defs/vaultMarkdownPath", "$defs": schema["$defs"]})
    assert validator.is_valid(path)
