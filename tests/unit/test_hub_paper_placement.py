"""Synthetic, zero-write review of one joint Field/provider paper placement."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    apply_knowledge_change_set,
    initialize_knowledge_provider_snapshot,
    load_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.commit import _canonical_payloads
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
    KnowledgeAtomicResource,
    KnowledgeChangeSet,
    KnowledgeManifest,
    KnowledgeProjection,
    KnowledgeRelation,
    ProfileKind,
    ZoteroPdfSpan,
)
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.hub.fields import (
    FieldDefinition,
    FieldManifest,
    FieldNavigationGroup,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.hub.paper_placement import PaperPlacementError, plan_v4_paper_placement
from scholar_workflow.models import ResourceKind

SOURCE_ID = "0374b783-02c8-4230-b789-d5c321b432ba"
FIELD_ID = "62f9a02e-c91c-475c-86ca-f0bd19353c12"
OLD_NOTE = "field/paper_assets/Paper.md"
NEW_NOTE = "field/resources/papers/paper/Paper.md"
OLD_MD = "field/Legacy分析.md"
OLD_CANVAS = "field/Legacy解析树.canvas"


@dataclass
class Fixture:
    vault: Path
    registry: KnowledgeSourceRegistry
    provider: Path
    field: FieldDefinition
    revised: FieldDefinition
    request: AnalysisCommitRequest
    bundle: object
    baseline: object
    reviewed_files: dict[str, bytes]
    legacy: dict[str, str | None]
    rewrites: dict[str, dict[str, str]]

    def plan(self):
        return plan_v4_paper_placement(
            self.registry,
            source_id=SOURCE_ID,
            field_id=FIELD_ID,
            request=self.request,
            bundle=self.bundle,
            baseline=self.baseline,
            reviewed_files=self.reviewed_files,
            paper_note_source=OLD_NOTE,
            paper_note_destination=NEW_NOTE,
            preserved_legacy_sources=self.legacy,
            proposed_field=self.revised,
            link_rewrites=self.rewrites,
        )


def _hash(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()


def _document(*, test_vault_reader: bool = False) -> AnalysisDocument:
    return AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:fixture",
        paper_title="Fixture Paper",
        language="en",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        reader=(
            AnalysisReader(kind="zotflow_library", vault_name="test")
            if test_vault_reader
            else AnalysisReader(kind="zotero_native")
        ),
        claims=[
            AnalysisClaim(
                claim_id="task",
                role=AnalysisRole.ABSTRACT,
                outline_path="abstract/task",
                title="Task",
                body="A readable paper task.",
                evidence=Evidence(
                    kind=EvidenceKind.AUTHOR_STATED,
                    anchor="Abstract",
                    source_spans=[
                        ZoteroPdfSpan(
                            library_type="personal",
                            library_id="1",
                            attachment_key="ABCDEFGH",
                            content_hash="sha256:" + "a" * 64,
                            page_index=0,
                        )
                    ],
                ),
            )
        ],
    )


def _fixture(tmp_path: Path, *, bound: bool = True, test_vault_reader: bool = False) -> Fixture:
    vault = tmp_path / "vault"
    world = vault / "field"
    (vault / ".obsidian").mkdir(parents=True)
    (world / "paper_assets").mkdir(parents=True)
    (world / "paper_assets" / "Paper.md").write_text("# Paper\n\nOwner note.\n", encoding="utf-8")
    (world / "00-Home.md").write_text(
        "# Field\n\n[Paper](paper_assets/Paper.md)\n", encoding="utf-8"
    )
    (world / "Legacy分析.md").write_text(
        "---\nsw_kind: paper-analysis\n---\n# Old analysis\n", encoding="utf-8"
    )
    (world / "Legacy解析树.canvas").write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    field = FieldDefinition(
        field_id=FIELD_ID,
        title="Field",
        relative_root="field",
        home="00-Home.md",
        navigation=[FieldNavigationGroup(label="Papers", items=["paper_assets/Paper.md"])],
    )
    revised = field.model_copy(
        update={
            "navigation": [
                FieldNavigationGroup(label="Papers", items=["resources/papers/paper/Paper.md"])
            ]
        }
    )
    state_dir = vault / ".scholar-workflow"
    state_dir.mkdir()
    (state_dir / "fields.yml").write_text(
        yaml.safe_dump(
            FieldManifest(source_id=SOURCE_ID, fields=[field]).model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    registry = KnowledgeSourceRegistry(tmp_path / "host" / "sources.json")
    registry.save(
        KnowledgeSourceRegistryDocument(
            folders=[
                FolderRegistration(
                    folder_id="fixture-vault", root=vault, capabilities=["read", "write"]
                )
            ],
            sources=[KnowledgeSourceRegistration(source_id=SOURCE_ID, folder_id="fixture-vault")],
        )
    )
    provider = registry.path.parent / "knowledge-providers" / SOURCE_ID
    provider.mkdir(parents=True)
    snapshot = initialize_knowledge_provider_snapshot(
        state_root=provider,
        vault_root=vault if bound else None,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id="paper:fixture",
                    kind=ResourceKind.PAPER,
                    title="Fixture Paper",
                    markdown_path=OLD_NOTE,
                )
            ]
        ),
        catalog=HubCatalog(
            generated_at=datetime(2026, 9, 29, tzinfo=UTC),
            resources=[
                HubResource(
                    resource_id="paper:fixture",
                    kind=ResourceKind.PAPER,
                    title="Fixture Paper",
                    zotero=ZoteroLink(item_key="ABCDEFGH"),
                )
            ],
        ),
    )
    document = _document(test_vault_reader=test_vault_reader)
    bundle, baseline = render_analysis_projection(document, note_stem="Paper分析")
    paths = AnalysisCanonicalPaths(
        markdown="field/resources/papers/paper/Paper分析.md",
        canvas="field/resources/papers/paper/Paper解析树.canvas",
        sidecar="field/resources/papers/paper/Paper分析.analysis.json",
    )
    request = AnalysisCommitRequest(
        commit_id="fixture-placement",
        batch_id="fixture-batch",
        item_id="fixture-item",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:fixture",
        note_stem="Paper分析",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        base_catalog_revision=snapshot.catalog.revision,
        base_snapshot_revision=snapshot.snapshot_revision,
        zotero_item_key="ABCDEFGH",
        relations=[
            KnowledgeRelation(
                from_id="paper:fixture",
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
    )
    return Fixture(
        vault,
        registry,
        provider,
        field,
        revised,
        request,
        bundle,
        baseline,
        _canonical_payloads(request, bundle, baseline),
        {
            OLD_MD: _hash((world / "Legacy分析.md").read_bytes()),
            OLD_CANVAS: _hash((world / "Legacy解析树.canvas").read_bytes()),
        },
        {"00-Home.md": {"paper_assets/Paper.md": "resources/papers/paper/Paper.md"}},
    )


def test_joint_placement_plan_binds_both_manifests_files_and_links_without_writes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = {
        str(path.relative_to(tmp_path)): (path.read_bytes(), path.stat().st_ino)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    plan = fixture.plan()
    assert plan == fixture.plan()
    assert plan.conflicts == ()
    assert plan.plan_digest.startswith("sha256:")
    assert "paper_assets/Paper.md" in plan.provider_manifest_diff
    assert "resources/papers/paper/Paper.md" in plan.provider_manifest_diff
    assert "Paper分析.md" in plan.provider_manifest_diff
    assert "resources/papers/paper/Paper.md" in plan.field_manifest_diff
    assert len(plan.provider_artifacts) == 3
    assert [(row.path, row.kind) for row in plan.files if row.kind == "preserved-v2-original"] == [
        ("field/Legacy分析.analysis.json", "preserved-v2-original"),
        (OLD_MD, "preserved-v2-original"),
        (OLD_CANVAS, "preserved-v2-original"),
    ]
    assert plan.link_rewrites[0].occurrences == 1
    assert "paper_assets/Paper.md" in plan.link_rewrites[0].diff
    assert [row.path for row in plan.directories] == [
        "field/resources",
        "field/resources/papers",
        "field/resources/papers/paper",
    ]
    assert not (fixture.vault / NEW_NOTE).exists()
    after = {
        str(path.relative_to(tmp_path)): (path.read_bytes(), path.stat().st_ino)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "fault", ["source", "provider", "owner", "owner-path", "target", "old-byte", "nav"]
)
def test_joint_placement_rejects_stale_or_unowned_input(tmp_path: Path, fault: str) -> None:
    fixture = _fixture(tmp_path, bound=fault != "provider")
    if fault == "source":
        fixture.registry.save(KnowledgeSourceRegistryDocument())
    elif fault == "owner":
        (fixture.vault / OLD_NOTE).unlink()
    elif fault == "owner-path":
        fixture.request = fixture.request.model_copy(update={"resource_id": "paper:other"})
    elif fault == "target":
        target = fixture.vault / NEW_NOTE
        target.parent.mkdir(parents=True)
        target.write_text("# Collision", encoding="utf-8")
    elif fault == "old-byte":
        (fixture.vault / OLD_MD).write_text("Changed", encoding="utf-8")
    elif fault == "nav":
        fixture.revised = fixture.field
    with pytest.raises(PaperPlacementError):
        fixture.plan()


def test_joint_placement_rejects_test_vault_candidate_links(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, test_vault_reader=True)
    assert "vault=test" in fixture.bundle.markdown
    with pytest.raises(PaperPlacementError, match="vault=test"):
        fixture.plan()


def test_joint_placement_flags_old_hub_links_in_preserved_bytes(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    old = fixture.vault / OLD_MD
    old.write_text(
        old.read_text(encoding="utf-8") + "[old](http://127.0.0.1:23128/open/paper/ABCDEFGH)\n",
        encoding="utf-8",
    )
    fixture.legacy[OLD_MD] = _hash(old.read_bytes())
    plan = fixture.plan()
    assert plan.conflicts == (f"preserved v2 source retains old Hub URL: {OLD_MD}",)


def test_joint_placement_digest_changes_with_candidate_and_navigation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    first = fixture.plan()
    changed_document = fixture.request.document.model_copy(deep=True)
    changed_document.claims[0].body = "A revised but conformant paper task."
    fixture.bundle, fixture.baseline = render_analysis_projection(
        changed_document, note_stem="Paper分析"
    )
    fixture.request = fixture.request.model_copy(update={"document": changed_document})
    fixture.reviewed_files = _canonical_payloads(
        fixture.request, fixture.bundle, fixture.baseline
    )
    candidate_change = fixture.plan()
    assert candidate_change.plan_digest != first.plan_digest
    assert (
        candidate_change.proposed_provider_graph_sha256
        != first.proposed_provider_graph_sha256
    )
    home = fixture.vault / "field" / "00-Home.md"
    home.write_text(home.read_text(encoding="utf-8") + "\nExtra context.\n", encoding="utf-8")
    assert fixture.plan().plan_digest != candidate_change.plan_digest
    assert os.stat(fixture.vault / OLD_MD).st_ino == next(
        row.before_inode for row in first.files if row.path == OLD_MD
    )


def test_joint_placement_flags_unreviewed_navigation_reference(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.rewrites = {}
    plan = fixture.plan()
    assert plan.conflicts == ("unreviewed navigation references old paper note: field/00-Home.md",)


def test_joint_placement_rejects_symlinked_destination_parent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    target_parent = fixture.vault / "field" / "resources"
    target_parent.symlink_to(fixture.vault / "field" / "paper_assets", target_is_directory=True)
    with pytest.raises(PaperPlacementError):
        fixture.plan()


def test_joint_placement_flags_preserved_v2_navigation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.field.navigation.append(FieldNavigationGroup(label="Old", items=["Legacy分析.md"]))
    manifest_path = fixture.vault / ".scholar-workflow" / "fields.yml"
    manifest_path.write_text(
        yaml.safe_dump(
            FieldManifest(source_id=SOURCE_ID, fields=[fixture.field]).model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fixture.revised.navigation.append(FieldNavigationGroup(label="Old", items=["Legacy分析.md"]))
    plan = fixture.plan()
    assert plan.conflicts == ("preserved v2 originals remain in Field navigation: Legacy分析.md",)


def test_joint_placement_rejects_unrelated_navigation_rewrite(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture.rewrites = {"00-Home.md": {"paper_assets/Paper.md": "an unrelated target"}}
    with pytest.raises(PaperPlacementError, match="does not bind"):
        fixture.plan()


def _store_snapshot(fixture: Fixture, data: dict) -> KnowledgeProviderSnapshot:
    data["snapshot_revision"] = ""
    data["catalog"]["revision"] = ""
    snapshot = KnowledgeProviderSnapshot.model_validate(data)
    (fixture.provider / "knowledge-provider.snapshot.json").write_text(
        snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    fixture.request = fixture.request.model_copy(
        update={
            "base_snapshot_revision": snapshot.snapshot_revision,
            "base_catalog_revision": snapshot.catalog.revision,
        }
    )
    return snapshot


def test_proposed_provider_graph_is_complete_review_only_and_preserves_history(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    snapshot = load_knowledge_provider_snapshot(fixture.provider)
    # Obtain actual prior receipt history from an isolated provider operation.
    semantic = {
        "source_receipt": "analysis-commit:prior-fixture",
        "base_catalog_revision": snapshot.catalog.revision,
        "upsert_artifacts": [
            {
                "artifact_id": "analysis:prior",
                "resource_id": "paper:fixture",
                "kind": "analysis_markdown",
                "vault_path": OLD_MD,
                "sha256": fixture.legacy[OLD_MD],
            }
        ],
        "upsert_relations": [],
        "upsert_projections": [],
        "expected_base_hashes": {OLD_MD: None},
    }
    change_hash = _hash(
        json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    apply_knowledge_change_set(
        state_root=fixture.provider,
        change_set=KnowledgeChangeSet(
            change_id="change:" + change_hash.removeprefix("sha256:"), **semantic
        ),
        clock=lambda: datetime(2026, 9, 29, tzinfo=UTC),
    )
    snapshot = load_knowledge_provider_snapshot(fixture.provider)
    fixture.request = fixture.request.model_copy(
        update={
            "base_snapshot_revision": snapshot.snapshot_revision,
            "base_catalog_revision": snapshot.catalog.revision,
            "projections": [
                KnowledgeProjection(
                    projection_id="projection:fixture",
                    kind="obsidian",
                    target_id=fixture.request.document.artifact_id,
                )
            ],
        }
    )
    before = (fixture.provider / "knowledge-provider.snapshot.json").read_bytes()
    plan = fixture.plan()
    graph = plan.proposed_provider_graph
    assert graph.kind == "proposed-provider-graph"
    assert graph.requires_joint_receipt is True
    assert graph.is_persistable_snapshot is False
    assert graph.before_receipts == snapshot.receipts
    assert len(graph.before_receipts) == 1
    assert graph.before_receipts[-1].after_catalog_revision == snapshot.catalog.revision
    assert graph.catalog.revision != snapshot.catalog.revision
    assert "snapshot_revision" not in graph.model_dump()
    assert graph.manifest.atomic_resources[0].markdown_path == NEW_NOTE
    assert snapshot.manifest.atomic_resources[0].markdown_path == OLD_NOTE
    assert graph.relations == fixture.request.relations
    assert graph.projections == fixture.request.projections
    assert set(graph.catalog.resources[0].artifact_ids) == {
        fixture.request.document.artifact_id,
        fixture.request.document.artifact_id + ":canvas",
        "analysis:prior",
    }
    assert graph.catalog.resources[0].zotero.item_key == fixture.request.zotero_item_key
    assert len(graph.artifacts) == 4
    assert len(graph.catalog.artifacts) == 3
    assert next(row for row in graph.artifacts if row.artifact_id == "analysis:prior") == (
        snapshot.artifacts[0]
    )
    for artifact in graph.artifacts:
        if artifact.artifact_id != "analysis:prior":
            assert artifact.sha256 == _hash(fixture.reviewed_files[artifact.vault_path])
        visible = next(
            (row for row in graph.catalog.artifacts if row.artifact_id == artifact.artifact_id),
            None,
        )
        if artifact.kind == "analysis_sidecar":
            assert visible is None
        else:
            assert visible.vault_path == artifact.vault_path
            assert visible.revision == artifact.sha256
            assert visible.resource_id == artifact.resource_id
    encoded = (
        json.dumps(graph.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    ).encode()
    assert plan.proposed_provider_graph_sha256 == _hash(encoded)
    assert "projection:fixture" in plan.proposed_provider_graph_diff
    assert NEW_NOTE in plan.proposed_provider_graph_diff
    assert (fixture.provider / "knowledge-provider.snapshot.json").read_bytes() == before
    assert plan == fixture.plan()
    with pytest.raises(ValueError):
        KnowledgeProviderSnapshot.model_validate(graph.model_dump(mode="json"))


@pytest.mark.parametrize(
    "collision", ["artifact-id", "sidecar-id", "path", "folder", "folder-support"]
)
def test_proposed_provider_graph_rejects_identity_and_path_collisions(
    tmp_path: Path, collision: str
) -> None:
    fixture = _fixture(tmp_path)
    data = load_knowledge_provider_snapshot(fixture.provider).model_dump(mode="json")
    if collision == "folder":
        data["manifest"]["atomic_resources"].append(
            {
                "resource_id": "paper:other",
                "kind": "paper",
                "title": "Other paper",
                "markdown_path": "field/resources/papers/paper/Other.md",
            }
        )
        data["catalog"]["resources"].append(
            HubResource(resource_id="paper:other", kind=ResourceKind.PAPER).model_dump(mode="json")
        )
    else:
        data["manifest"]["supporting_documents"].append(
            {
                "document_id": (
                    fixture.request.document.artifact_id
                    + (":sidecar" if collision == "sidecar-id" else "")
                    if collision != "path"
                    else "note:other"
                ),
                "kind": "reading_note",
                "title": "Other note",
                "vault_path": (
                    fixture.request.paths.markdown
                    if collision == "path"
                    else (
                        "field/resources/papers/paper/Other.md"
                        if collision == "folder-support"
                        else "field/Other.md"
                    )
                ),
                "owner_id": "paper:fixture",
            }
        )
    _store_snapshot(fixture, data)
    with pytest.raises(PaperPlacementError, match="already|collides"):
        fixture.plan()


@pytest.mark.parametrize("fault", ["zotero", "missing-zotero", "snapshot", "catalog", "owner-note"])
def test_proposed_provider_graph_rejects_stale_or_mismatched_authority(
    tmp_path: Path, fault: str
) -> None:
    fixture = _fixture(tmp_path)
    if fault in {"owner-note", "missing-zotero"}:
        data = load_knowledge_provider_snapshot(fixture.provider).model_dump(mode="json")
        if fault == "owner-note":
            data["manifest"]["atomic_resources"][0]["markdown_path"] = "field/Other.md"
        else:
            data["catalog"]["resources"][0]["zotero"]["item_key"] = None
            fixture.request = fixture.request.model_copy(update={"zotero_item_key": None})
        _store_snapshot(fixture, data)
    else:
        updates = {
            "zotero": {"zotero_item_key": "HGFEDCBA"},
            "snapshot": {"base_snapshot_revision": "sha256:" + "0" * 64},
            "catalog": {"base_catalog_revision": "sha256:" + "0" * 64},
        }
        fixture.request = fixture.request.model_copy(update=updates[fault])
    with pytest.raises(PaperPlacementError):
        fixture.plan()


@pytest.mark.parametrize("kind", ["relation", "projection"])
def test_proposed_provider_graph_rejects_unknown_relation_or_projection(
    tmp_path: Path, kind: str
) -> None:
    fixture = _fixture(tmp_path)
    if kind == "relation":
        fixture.request.relations.append(
            KnowledgeRelation(from_id="paper:fixture", relation="cites", to_id="paper:missing")
        )
    else:
        fixture.request.projections.append(
            KnowledgeProjection(projection_id="missing", kind="obsidian", target_id="missing")
        )
    with pytest.raises(PaperPlacementError, match="explicit Knowledge"):
        fixture.plan()


def test_joint_placement_requires_existing_preserved_sidecar_in_review(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    sidecar = fixture.vault / "field/Legacy分析.analysis.json"
    sidecar.write_text('{"historical":true}', encoding="utf-8")
    with pytest.raises(PaperPlacementError, match="sidecar is missing from review"):
        fixture.plan()
    fixture.legacy["field/Legacy分析.analysis.json"] = _hash(sidecar.read_bytes())
    plan = fixture.plan()
    row = next(row for row in plan.files if row.path == "field/Legacy分析.analysis.json")
    assert row.before_sha256 == row.after_sha256 == fixture.legacy[row.path]


def test_joint_placement_detects_preserved_sidecar_created_during_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scholar_workflow.hub import paper_placement

    fixture = _fixture(tmp_path)
    original = paper_placement._proposed_provider_graph

    def create_sidecar(*args, **kwargs):
        (fixture.vault / "field/Legacy分析.analysis.json").write_text("{}", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(paper_placement, "_proposed_provider_graph", create_sidecar)
    with pytest.raises(PaperPlacementError, match="source changed during review"):
        fixture.plan()


def test_proposed_provider_graph_rejects_snapshot_bytes_changed_during_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scholar_workflow.hub import paper_placement

    fixture = _fixture(tmp_path)
    original = paper_placement._proposed_provider_graph

    def rewrite_snapshot(*args, **kwargs):
        # Same semantic revision, different exact bytes: full snapshot CAS still applies.
        path = fixture.provider / "knowledge-provider.snapshot.json"
        data = json.loads(path.read_bytes())
        data["catalog"]["generated_at"] = "2026-09-30T00:00:00Z"
        path.write_text(json.dumps(data), encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(paper_placement, "_proposed_provider_graph", rewrite_snapshot)
    with pytest.raises(PaperPlacementError, match="Source or provider identity changed"):
        fixture.plan()
