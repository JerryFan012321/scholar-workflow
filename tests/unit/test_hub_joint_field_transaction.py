"""The joint coordinator must bind first enrollment and provider publication."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

import scholar_workflow.hub.joint_field_transaction as joint_module
from scholar_workflow.analysis.apply_changes import (
    KnowledgeProviderSnapshot,
    KnowledgeVaultBinding,
    load_knowledge_provider_snapshot,
    prepare_joint_paper_placement,
)
from scholar_workflow.analysis.commit import _canonical_payloads
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
    KnowledgeManifest,
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
from scholar_workflow.hub.joint_field_transaction import (
    JointFieldTransactionError,
    JointFieldTransactionService,
)
from scholar_workflow.hub.models import HubCatalog, HubResource, ZoteroLink
from scholar_workflow.hub.paper_foldering import (
    PaperFolderRelocation,
    plan_paper_foldering,
)
from scholar_workflow.models import ResourceKind

SOURCE_ID = "0374b783-02c8-4230-b789-d5c321b432ba"
FIELD_ID = "62f9a02e-c91c-475c-86ca-f0bd19353c12"
OLD_NOTE = "field/paper_assets/Paper.md"
NEW_NOTE = "field/resources/papers/paper/Paper.md"


def _foldering(vault: Path, *moves: tuple[str, str, str]):
    before = FieldDefinition(
        field_id=FIELD_ID,
        title="Field",
        relative_root="field",
        home="00-Home.md",
        navigation=[
            FieldNavigationGroup(
                label="Papers",
                items=[source.removeprefix("field/") for source, _resource, _target in moves],
            )
        ],
    )
    return plan_paper_foldering(
        vault_root=vault,
        field=before,
        relocations=[
            PaperFolderRelocation(
                source_note=source.removeprefix("field/"),
                resource_id=resource,
                destination_note=target.removeprefix("field/"),
            )
            for source, resource, target in moves
        ],
    )


def _fixture(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "field" / "paper_assets").mkdir(parents=True)
    (vault / "field" / "paper_assets" / "Paper.md").write_text(
        "# Paper\n\nOwner note.\n", encoding="utf-8"
    )
    (vault / "field" / "00-Home.md").write_text(
        "# Field\n\n[Paper](paper_assets/Paper.md)\n", encoding="utf-8"
    )
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    state = tmp_path / "recovery"
    state.mkdir(mode=0o700)
    registry = KnowledgeSourceRegistry(host / "sources.json")
    service = JointFieldTransactionService(registry, state)
    field = FieldDefinition(
        field_id=FIELD_ID,
        title="Field",
        relative_root="field",
        home="00-Home.md",
        navigation=[
            FieldNavigationGroup(label="Papers", items=["resources/papers/paper/Paper.md"])
        ],
    )
    manifest = FieldManifest(source_id=SOURCE_ID, fields=[field])
    registration = KnowledgeSourceRegistryDocument(
        folders=[
            FolderRegistration(
                folder_id="fixture-vault", root=vault, capabilities=["read", "write"]
            )
        ],
        sources=[
            KnowledgeSourceRegistration(
                source_id=SOURCE_ID, folder_id="fixture-vault", capabilities=["read", "write"]
            )
        ],
    )
    info = os.stat(vault)
    provider_base = KnowledgeProviderSnapshot(
        vault_binding=KnowledgeVaultBinding(
            root_path=str(vault), device=info.st_dev, inode=info.st_ino
        ),
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
    document = AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:fixture",
        paper_title="Fixture Paper",
        language="en",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
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
    bundle, baseline = render_analysis_projection(document, note_stem="Paper分析")
    paths = AnalysisCanonicalPaths(
        markdown="field/resources/papers/paper/Paper分析.md",
        canvas="field/resources/papers/paper/Paper解析树.canvas",
        sidecar="field/resources/papers/paper/Paper分析.analysis.json",
    )
    request = AnalysisCommitRequest(
        commit_id="joint-fixture",
        batch_id="fixture-batch",
        item_id="fixture-item",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:fixture",
        note_stem="Paper分析",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        base_catalog_revision=provider_base.catalog.revision,
        base_snapshot_revision=provider_base.snapshot_revision,
        zotero_item_key="ABCDEFGH",
        relations=[
            KnowledgeRelation(
                from_id="paper:fixture",
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
    )
    payloads = _canonical_payloads(request, bundle, baseline)
    artifacts = [
        KnowledgeArtifactChange(
            artifact_id=document.artifact_id + suffix,
            resource_id="paper:fixture",
            kind=kind,
            vault_path=path,
            sha256="sha256:" + hashlib.sha256(payloads[path]).hexdigest(),
        )
        for suffix, kind, path in (
            ("", "analysis_markdown", paths.markdown),
            (":canvas", "analysis_canvas", paths.canvas),
            (":sidecar", "analysis_sidecar", paths.sidecar),
        )
    ]
    prepared = prepare_joint_paper_placement(
        snapshot=provider_base,
        request=request,
        vault_binding=provider_base.vault_binding,
        transaction_id="fixture-joint-1",
        plan_digest="sha256:" + "0" * 64,
        source_note_path=OLD_NOTE,
        destination_note_path=NEW_NOTE,
        note_sha256="sha256:" + hashlib.sha256((vault / OLD_NOTE).read_bytes()).hexdigest(),
        new_artifacts=artifacts,
    )
    bootstrap_after = KnowledgeProviderSnapshot(
        vault_binding=provider_base.vault_binding,
        manifest=prepared.manifest,
        artifacts=list(prepared.artifacts),
        relations=list(prepared.relations),
        projections=list(prepared.projections),
        catalog=prepared.catalog,
    )
    kwargs = {
        "vault_root": vault,
        "source_id": SOURCE_ID,
        "field_id": FIELD_ID,
        "registry_after": registration,
        "manifest_after": manifest,
        "provider_base": provider_base,
        "request": request,
        "bundle": bundle,
        "baseline": baseline,
        "source_note_path": OLD_NOTE,
        "destination_note_path": NEW_NOTE,
        "reviewed_files": {
            "field/00-Home.md": (b"# Field\n\n[Paper](resources/papers/paper/Paper.md)\n")
        },
        "preserved_paths": {},
        "required_existing_documents": {
            OLD_NOTE: "sha256:" + hashlib.sha256((vault / OLD_NOTE).read_bytes()).hexdigest()
        },
        "transaction_id": "fixture-joint-1",
        "bootstrap_provider_after": bootstrap_after,
        "paper_foldering_plan": _foldering(vault, (OLD_NOTE, "paper:fixture", NEW_NOTE)),
    }
    return vault, registry, service, kwargs


def test_first_enrollment_plan_is_zero_write_and_apply_is_joint(tmp_path: Path) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    assert plan.provider_before is None
    assert not registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()
    assert not (registry.path.parent / "knowledge-providers").exists()
    assert plan.plan_digest.startswith("sha256:")
    assert "provider_after_catalog" in plan.preview
    assert "before/field/00-Home.md" in plan.preview
    assert "paper_assets/Paper.md" in plan.preview
    with pytest.raises(JointFieldTransactionError, match="paused"):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=False)
    with pytest.raises(JointFieldTransactionError, match="approved"):
        service.apply(plan, approved_digest="sha256:" + "0" * 64, external_writers_paused=True)
    result = service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert result.recovery_is_verified_backup is False
    assert result.recovery_record.exists()
    assert not (vault / OLD_NOTE).exists()
    assert (vault / NEW_NOTE).read_text() == "# Paper\n\nOwner note.\n"
    assert (vault / kwargs["request"].paths.canvas).exists()
    assert (
        FieldManifest.model_validate(
            yaml.safe_load((vault / ".scholar-workflow" / "fields.yml").read_text())
        ).source_id
        == SOURCE_ID
    )
    assert registry.resolve(SOURCE_ID, capability="write") == vault
    provider = load_knowledge_provider_snapshot(
        registry.path.parent / "knowledge-providers" / SOURCE_ID
    )
    assert provider.snapshot_revision == result.provider_snapshot_revision
    assert provider.manifest.atomic_resources[0].markdown_path == NEW_NOTE
    assert provider.receipts == []  # bootstrap is not a forged prior apply receipt
    assert service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True).outcome == (
        "nothing-to-recover"
    )


def test_stale_owner_note_aborts_without_publication(tmp_path: Path) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    (vault / OLD_NOTE).write_text("External edit", encoding="utf-8")
    with pytest.raises(JointFieldTransactionError, match="changed after preview"):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert not registry.path.exists()
    assert not (
        registry.path.parent
        / "knowledge-providers"
        / SOURCE_ID
        / "knowledge-provider.snapshot.json"
    ).exists()


def test_unreviewed_old_link_and_missing_navigation_fail_closed(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    (vault / "field" / "Extra.md").write_text(
        "[old](http://127.0.0.1:23128/open/paper/ABCDEFGH)", encoding="utf-8"
    )
    with pytest.raises(JointFieldTransactionError, match="unreviewed old Hub URL"):
        service.plan(**kwargs)
    (vault / "field" / "Extra.md").unlink()
    kwargs["manifest_after"].fields[0].navigation[0].items.append("Missing.md")
    with pytest.raises(JointFieldTransactionError, match="reviewed paper-foldering navigation"):
        service.plan(**kwargs)


def test_omitted_navigation_rewrite_cannot_leave_deleted_note_link(tmp_path: Path) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    kwargs["reviewed_files"] = {}
    with pytest.raises(JointFieldTransactionError, match="omitted or changed"):
        service.plan(**kwargs)
    assert not registry.path.exists()
    assert (vault / OLD_NOTE).exists()


def test_new_unlisted_field_entry_invalidates_approved_plan(tmp_path: Path) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    (vault / "field" / "Extra.md").write_text("# External", encoding="utf-8")
    with pytest.raises(JointFieldTransactionError, match="Field inventory changed"):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert not registry.path.exists()
    assert (vault / OLD_NOTE).exists()


def test_field_entry_created_during_staging_aborts_before_commit_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._stage_file
    injected = False

    def concurrent_writer(*args, **options):
        nonlocal injected
        result = original(*args, **options)
        if not injected:
            injected = True
            (vault / "field" / "External.md").write_text("# New", encoding="utf-8")
        return result

    monkeypatch.setattr(joint_module, "_stage_file", concurrent_writer)
    with pytest.raises(JointFieldTransactionError, match="Field inventory changed"):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert not registry.path.exists()
    assert (vault / OLD_NOTE).exists()
    assert (vault / "field" / "External.md").read_text(encoding="utf-8") == "# New"
    assert service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True).outcome == (
        "nothing-to-recover"
    )


def test_hard_kill_while_staging_has_durable_prepare_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._stage_file

    def kill_after_stage(*args, **options):
        original(*args, **options)
        raise SystemExit("simulated kill after fsynced stage")

    monkeypatch.setattr(joint_module, "_stage_file", kill_after_stage)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    monkeypatch.setattr(joint_module, "_stage_file", original)
    assert not registry.path.exists()
    pending = service._journal_dir(SOURCE_ID, FIELD_ID) / "pending.json"
    assert pending.exists()
    assert '"phase":"prepare"' in pending.read_text(encoding="utf-8")
    recovered = service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert recovered.outcome == "rolled-back"
    assert (vault / OLD_NOTE).exists()
    assert not (vault / NEW_NOTE).exists()
    assert not list(vault.rglob(".scholar-joint-*.tmp"))


def test_hard_kill_before_directory_receipt_requires_manual_ownership_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._directory_chain_create

    def kill_before_receipt(*args, **options):
        created = original(*args, **options)
        if created:
            raise SystemExit("simulated kill before directory receipt")
        return created

    monkeypatch.setattr(joint_module, "_directory_chain_create", kill_before_receipt)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    monkeypatch.setattr(joint_module, "_directory_chain_create", original)
    assert not registry.path.exists()
    assert (vault / "field" / "resources").exists()
    with pytest.raises(JointFieldTransactionError, match="manual ownership review"):
        service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert (vault / "field" / "resources").exists()
    assert (service._journal_dir(SOURCE_ID, FIELD_ID) / "pending.json").exists()
    assert (vault / OLD_NOTE).exists()


def test_unreceipted_directory_with_external_content_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._directory_chain_create

    def kill_before_receipt(*args, **options):
        created = original(*args, **options)
        if created:
            raise SystemExit("simulated kill before directory receipt")
        return created

    monkeypatch.setattr(joint_module, "_directory_chain_create", kill_before_receipt)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    monkeypatch.setattr(joint_module, "_directory_chain_create", original)
    external = vault / "field" / "resources" / "External.txt"
    external.write_text("external writer", encoding="utf-8")
    with pytest.raises(JointFieldTransactionError, match="manual ownership review"):
        service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert external.read_text(encoding="utf-8") == "external writer"
    assert (service._journal_dir(SOURCE_ID, FIELD_ID) / "pending.json").exists()


def test_external_empty_directory_after_prepare_intent_is_never_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)

    def kill_before_mkdir(*_args, **_options):
        raise SystemExit("simulated kill before engine mkdir")

    monkeypatch.setattr(joint_module, "_directory_chain_create", kill_before_mkdir)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    external = vault / "field" / "resources"
    external.mkdir(mode=0o700)
    with pytest.raises(JointFieldTransactionError, match="manual ownership review"):
        service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert external.is_dir()
    assert (service._journal_dir(SOURCE_ID, FIELD_ID) / "pending.json").exists()


def test_uppercase_flat_paper_note_is_not_silently_omitted(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    (vault / "field" / "paper_assets" / "Unreviewed.MD").write_text(
        "# Another paper", encoding="utf-8"
    )
    with pytest.raises(JointFieldTransactionError, match="flat paper asset"):
        service.plan(**kwargs)


def test_joint_plan_binds_every_reviewed_paper_foldering_document(tmp_path: Path) -> None:
    _vault, _, service, kwargs = _fixture(tmp_path)
    foldering = kwargs["paper_foldering_plan"]
    kwargs["paper_foldering_plan"] = foldering
    plan = service.plan(**kwargs)
    assert foldering.plan_digest in plan.preview
    kwargs["reviewed_files"] = {}
    with pytest.raises(JointFieldTransactionError, match="omitted or changed"):
        service.plan(**kwargs)
    kwargs["reviewed_files"] = {
        "field/00-Home.md": b"# Field\n\n[Paper](resources/papers/paper/Paper.md)\n\nExtra.\n"
    }
    with pytest.raises(JointFieldTransactionError, match="omitted or changed"):
        service.plan(**kwargs)
    kwargs["reviewed_files"] = {
        "field/00-Home.md": b"# Field\n\n[Paper](resources/papers/paper/Paper.md)\n"
    }
    kwargs["paper_foldering_plan"] = replace(
        foldering,
        moves=(replace(foldering.moves[0], resource_id="paper:tampered"),),
    )
    with pytest.raises(JointFieldTransactionError, match="review digest is inconsistent"):
        service.plan(**kwargs)


def test_hidden_flat_paper_asset_requires_disposition(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    (vault / "field" / "paper_assets" / ".private.md").write_text("# hidden")
    with pytest.raises(JointFieldTransactionError, match="hidden entry"):
        service.plan(**kwargs)


def test_first_enrollment_cannot_bypass_exact_foldering_proposal(tmp_path: Path) -> None:
    _vault, _, service, kwargs = _fixture(tmp_path)
    kwargs["paper_foldering_plan"] = None
    with pytest.raises(JointFieldTransactionError, match="exact reviewed paper-foldering"):
        service.plan(**kwargs)


def test_legacy_url_in_text_file_and_encoded_old_note_link_fail_closed(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    extra = vault / "field" / "Extra.txt"
    extra.write_text("http://127.0.0.1:23128/open/paper/ABCDEFGH", encoding="utf-8")
    with pytest.raises(JointFieldTransactionError, match="unreviewed old Hub URL"):
        service.plan(**kwargs)
    extra.unlink()
    (vault / "field" / "00-Home.md").write_text(
        "# Field\n\n[Paper](paper_assets%2FPaper.md)\n", encoding="utf-8"
    )
    kwargs["paper_foldering_plan"] = _foldering(vault, (OLD_NOTE, "paper:fixture", NEW_NOTE))
    kwargs["reviewed_files"] = {}
    with pytest.raises(JointFieldTransactionError, match="deleted paper-note path"):
        service.plan(**kwargs)


def test_interrupted_commit_rolls_forward_only_owned_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._publish_row
    counter = 0

    def crash_after_first(root: Path, row: dict[str, object]) -> None:
        nonlocal counter
        counter += 1
        if counter == 2:
            raise SystemExit("simulated process death")
        original(root, row)

    monkeypatch.setattr(joint_module, "_publish_row", crash_after_first)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    monkeypatch.setattr(joint_module, "_publish_row", original)
    assert not registry.path.exists()
    recovered = service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert recovered.outcome == "committed"
    assert recovered.recovery_record is not None
    assert (vault / NEW_NOTE).exists()
    assert registry.resolve(SOURCE_ID, capability="write") == vault


def test_recovery_refuses_external_edit_to_partially_published_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._publish_row
    counter = 0

    def crash_after_first(root: Path, row: dict[str, object]) -> None:
        nonlocal counter
        counter += 1
        if counter == 2:
            raise SystemExit("simulated process death")
        original(root, row)

    monkeypatch.setattr(joint_module, "_publish_row", crash_after_first)
    with pytest.raises(SystemExit):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    monkeypatch.setattr(joint_module, "_publish_row", original)
    home = vault / "field" / "00-Home.md"
    home.write_text("External edit after interruption", encoding="utf-8")
    with pytest.raises(JointFieldTransactionError, match="external edit"):
        service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True)
    assert home.read_text(encoding="utf-8") == "External edit after interruption"
    assert not registry.path.exists()


def test_artifact_manifest_moves_only_selected_canvas_identity(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    state = vault / ".scholar-workflow"
    state.mkdir()
    old_canvas_path = "field/Legacy.canvas"
    old_canvas = vault / old_canvas_path
    old_canvas.write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
    target = kwargs["request"].document.artifact_id + ":canvas"
    rows = [
        {
            "artifact_id": target,
            "kind": "analysis-canvas",
            "format": "canvas",
            "vault_path": old_canvas_path,
            "resource_id": "paper:fixture",
        }
    ]
    before = yaml.safe_dump({"schema_version": 1, "artifacts": rows}).encode()
    (state / "artifacts.yml").write_bytes(before)
    with pytest.raises(JointFieldTransactionError, match="Canvas identity requires"):
        service.plan(**kwargs)
    new_rows = [{**rows[0], "vault_path": kwargs["request"].paths.canvas}]
    kwargs["artifact_registry_after"] = yaml.safe_dump(
        {"schema_version": 1, "artifacts": new_rows}
    ).encode()
    with pytest.raises(JointFieldTransactionError, match="explicitly preserved"):
        service.plan(**kwargs)
    kwargs["preserved_paths"][old_canvas_path] = (
        "sha256:" + hashlib.sha256(old_canvas.read_bytes()).hexdigest()
    )
    plan = service.plan(**kwargs)
    service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert old_canvas.read_text(encoding="utf-8") == '{"nodes":[],"edges":[]}'
    after = yaml.safe_load((state / "artifacts.yml").read_text(encoding="utf-8"))
    assert after["artifacts"][0]["vault_path"] == kwargs["request"].paths.canvas


def test_in_process_publish_failure_conditionally_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    plan = service.plan(**kwargs)
    original = joint_module._publish_row
    counter = 0

    def fail_after_first(root: Path, row: dict[str, object]) -> None:
        nonlocal counter
        counter += 1
        if counter == 2:
            raise RuntimeError("injected write failure")
        original(root, row)

    monkeypatch.setattr(joint_module, "_publish_row", fail_after_first)
    with pytest.raises(JointFieldTransactionError, match="rolled back"):
        service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert (vault / OLD_NOTE).read_text(encoding="utf-8") == "# Paper\n\nOwner note.\n"
    assert not (vault / NEW_NOTE).exists()
    assert not registry.path.exists()
    assert not (
        registry.path.parent
        / "knowledge-providers"
        / SOURCE_ID
        / "knowledge-provider.snapshot.json"
    ).exists()
    assert service.recover(SOURCE_ID, FIELD_ID, external_writers_paused=True).outcome == (
        "nothing-to-recover"
    )


def test_bootstrap_moves_all_declared_paper_notes_in_same_journal(tmp_path: Path) -> None:
    vault, registry, service, kwargs = _fixture(tmp_path)
    second_old = "field/paper_assets/Other.md"
    second_new = "field/resources/papers/other/Other.md"
    (vault / second_old).write_text("# Other\n", encoding="utf-8")
    field = kwargs["manifest_after"].fields[0]
    field.navigation[0].items.append("resources/papers/other/Other.md")
    base = kwargs["provider_base"]
    manifest = base.manifest.model_copy(deep=True)
    manifest.atomic_resources.append(
        KnowledgeAtomicResource(
            resource_id="paper:other",
            kind=ResourceKind.PAPER,
            title="Other",
            markdown_path=second_old,
        )
    )
    catalog = base.catalog.model_copy(deep=True)
    catalog.revision = ""
    catalog.resources.append(
        HubResource(
            resource_id="paper:other",
            kind=ResourceKind.PAPER,
            title="Other",
            zotero=ZoteroLink(item_key="JKLMPQRS"),
        )
    )
    base = KnowledgeProviderSnapshot(
        vault_binding=base.vault_binding,
        manifest=manifest,
        catalog=catalog,
    )
    kwargs["provider_base"] = base
    request = kwargs["request"].model_copy(
        update={
            "base_catalog_revision": base.catalog.revision,
            "base_snapshot_revision": base.snapshot_revision,
        }
    )
    kwargs["request"] = request
    payloads = _canonical_payloads(request, kwargs["bundle"], kwargs["baseline"])
    artifacts = [
        KnowledgeArtifactChange(
            artifact_id=request.document.artifact_id + suffix,
            resource_id=request.resource_id,
            kind=kind,
            vault_path=path,
            sha256="sha256:" + hashlib.sha256(payloads[path]).hexdigest(),
        )
        for suffix, kind, path in (
            ("", "analysis_markdown", request.paths.markdown),
            (":canvas", "analysis_canvas", request.paths.canvas),
            (":sidecar", "analysis_sidecar", request.paths.sidecar),
        )
    ]
    prepared = prepare_joint_paper_placement(
        snapshot=base,
        request=request,
        vault_binding=base.vault_binding,
        transaction_id="fixture-joint-1",
        plan_digest="sha256:" + "0" * 64,
        source_note_path=OLD_NOTE,
        destination_note_path=NEW_NOTE,
        note_sha256="sha256:" + hashlib.sha256((vault / OLD_NOTE).read_bytes()).hexdigest(),
        new_artifacts=artifacts,
    )
    after_manifest = prepared.manifest.model_copy(deep=True)
    next(
        row for row in after_manifest.atomic_resources if row.resource_id == "paper:other"
    ).markdown_path = second_new
    kwargs["bootstrap_provider_after"] = KnowledgeProviderSnapshot(
        vault_binding=base.vault_binding,
        manifest=after_manifest,
        artifacts=list(prepared.artifacts),
        relations=list(prepared.relations),
        projections=list(prepared.projections),
        catalog=prepared.catalog,
    )
    kwargs["additional_note_relocations"] = {second_old: second_new}
    kwargs["paper_foldering_plan"] = _foldering(
        vault,
        (OLD_NOTE, "paper:fixture", NEW_NOTE),
        (second_old, "paper:other", second_new),
    )
    with pytest.raises(JointFieldTransactionError, match="inventory must equal"):
        service.plan(**kwargs)
    kwargs["required_existing_documents"][second_old] = (
        "sha256:" + hashlib.sha256((vault / second_old).read_bytes()).hexdigest()
    )
    field.navigation[0].items.remove("resources/papers/other/Other.md")
    with pytest.raises(JointFieldTransactionError, match="missing from new Field navigation"):
        service.plan(**kwargs)
    field.navigation[0].items.append("resources/papers/other/Other.md")
    plan = service.plan(**kwargs)
    result = service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    assert result.recovery_record.exists()
    assert not (vault / second_old).exists()
    assert (vault / second_new).read_text(encoding="utf-8") == "# Other\n"
    snapshot = load_knowledge_provider_snapshot(
        registry.path.parent / "knowledge-providers" / SOURCE_ID
    )
    assert (
        next(
            row for row in snapshot.manifest.atomic_resources if row.resource_id == "paper:other"
        ).markdown_path
        == second_new
    )


def test_paper_note_wikilink_rewrites_are_reviewable_and_exact(tmp_path: Path) -> None:
    vault, _, service, kwargs = _fixture(tmp_path)
    source = vault / OLD_NOTE
    source.write_text("# Paper\n\n[[Legacy分析]] and [[Legacy解析树]]\n", encoding="utf-8")
    kwargs["required_existing_documents"][OLD_NOTE] = (
        "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    )
    kwargs["paper_foldering_plan"] = _foldering(vault, (OLD_NOTE, "paper:fixture", NEW_NOTE))
    kwargs["note_link_rewrites"] = {
        OLD_NOTE: {
            "[[Legacy分析]]": "[[resources/papers/paper/Paper分析]]",
            "[[Legacy解析树]]": "[[resources/papers/paper/Paper解析树]]",
        }
    }
    plan = service.plan(**kwargs)
    assert "before/field/paper_assets/Paper.md" in plan.preview
    assert "[[Legacy分析]]" in plan.preview
    assert "[[resources/papers/paper/Paper分析]]" in plan.preview
    service.apply(plan, approved_digest=plan.plan_digest, external_writers_paused=True)
    text = (vault / NEW_NOTE).read_text(encoding="utf-8")
    assert "[[Legacy分析]]" not in text
    assert "[[resources/papers/paper/Paper分析]]" in text
