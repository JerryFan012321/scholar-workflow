from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import initialize_knowledge_provider_snapshot
from scholar_workflow.analysis.models import (
    ALL_ROLES,
    AnalysisBatchItem,
    AnalysisBatchRequest,
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
    KnowledgeAuditManifest,
    KnowledgeAuditObject,
    KnowledgeManifest,
    KnowledgeRelation,
    ProfileKind,
    ZoteroPdfSpan,
)
from scholar_workflow.cli import main
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
from scholar_workflow.models import ResourceKind

_V4_SOURCE_ID = "00000000-0000-4000-8000-000000000041"
_V4_FIELD_ID = "00000000-0000-4000-8000-000000000042"


def _register_v4_source(state_home: Path, vault: Path) -> Path:
    registry = KnowledgeSourceRegistry(state_home / "hub" / "sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(
            folder_id="analysis-vault",
            root=vault,
            capabilities=["read", "write"],
        )],
        sources=[KnowledgeSourceRegistration(
            source_id=_V4_SOURCE_ID,
            folder_id="analysis-vault",
        )],
    ))
    manifest = FieldManifest(
        source_id=_V4_SOURCE_ID,
        fields=[FieldDefinition(
            field_id=_V4_FIELD_ID,
            title="Analysis field",
            relative_root="field",
            home="home.md",
            navigation=[FieldNavigationGroup(label="Entry", items=["home.md"])],
        )],
    )
    (vault / ".scholar-workflow").mkdir()
    (vault / ".scholar-workflow" / "fields.yml").write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    (vault / "field" / "home.md").write_text("# Analysis field\n", encoding="utf-8")
    return registry.path.parent / "knowledge-providers" / _V4_SOURCE_ID


def _request(batch_id: str, *, body_suffix: str = "") -> AnalysisBatchRequest:
    document = AnalysisDocument(
        schema_version=1,
        artifact_id="analysis:paper:cli-test",
        paper_title="CLI Test",
        profile=AnalysisProfile(kind=ProfileKind.WHOLE),
        claims=[
            AnalysisClaim(
                claim_id=role.value,
                role=role,
                title=role.value,
                body=f"Readable {role.value} content{body_suffix}.",
                evidence=Evidence(kind=EvidenceKind.AUTHOR_STATED, anchor="Section 1"),
                order=1 if role is AnalysisRole.WORKFLOW else None,
            )
            for role in ALL_ROLES
        ],
    )
    return AnalysisBatchRequest(
        batch_id=batch_id,
        items=[
            AnalysisBatchItem(
                item_id="paper-one",
                zotero_item_key="ABCD1234",
                note_stem="CLI Test分析",
                document=document,
            )
        ],
    )


def _write_request(path: Path, request: AnalysisBatchRequest) -> None:
    path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")


def test_analysis_batch_cli_stages_only_validated_pair_and_is_idempotent(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "request.json"
    state_db = tmp_path / "analysis.db"
    stage_root = tmp_path / "stage"
    _write_request(request_path, _request("cli-batch"))
    runner = CliRunner()
    args = [
        "analysis",
        "batch-run",
        "--request",
        str(request_path),
        "--state-db",
        str(state_db),
        "--stage-root",
        str(stage_root),
    ]

    first = runner.invoke(main, args)
    second = runner.invoke(main, args)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert json.loads(first.output)["items"][0]["state"] == "validated"
    pair = stage_root / "cli-batch" / "paper-one"
    assert (pair / "analysis.md").is_file()
    assert (pair / "analysis.canvas").is_file()
    assert (pair / "analysis.baseline.json").is_file()


def test_analysis_batch_cli_rejects_batch_id_reuse_with_different_input(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    state_db = tmp_path / "analysis.db"
    stage_root = tmp_path / "stage"
    _write_request(first_path, _request("same-batch"))
    _write_request(second_path, _request("same-batch", body_suffix=" changed"))
    runner = CliRunner()
    common = ["--state-db", str(state_db), "--stage-root", str(stage_root)]

    assert runner.invoke(
        main,
        ["analysis", "batch-run", "--request", str(first_path), *common],
    ).exit_code == 0
    conflict = runner.invoke(
        main,
        ["analysis", "batch-run", "--request", str(second_path), *common],
    )

    assert conflict.exit_code == 5
    assert "different request" in conflict.output


def test_analysis_batch_audit_cli_is_read_only(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    state_db = tmp_path / "analysis.db"
    stage_root = tmp_path / "stage"
    _write_request(request_path, _request("audit-cli"))
    runner = CliRunner()
    run = runner.invoke(
        main,
        [
            "analysis",
            "batch-run",
            "--request",
            str(request_path),
            "--state-db",
            str(state_db),
            "--stage-root",
            str(stage_root),
        ],
    )
    before = state_db.read_bytes()

    audit = runner.invoke(
        main,
        ["analysis", "audit-batches", "--state-db", str(state_db)],
    )

    assert run.exit_code == 0, run.output
    assert audit.exit_code == 0, audit.output
    assert json.loads(audit.output)["ok"] is True
    assert state_db.read_bytes() == before


def test_analysis_commit_bundle_cli_requires_validated_stage_and_writes_receipt(
    tmp_path: Path,
) -> None:
    batch = _request("commit-cli")
    request_path = tmp_path / "batch.json"
    state_db = tmp_path / "analysis.db"
    stage_root = tmp_path / "stage"
    vault = tmp_path / "vault"
    (vault / "topic").mkdir(parents=True)
    _write_request(request_path, batch)
    runner = CliRunner()
    staged = runner.invoke(
        main,
        [
            "analysis",
            "batch-run",
            "--request",
            str(request_path),
            "--state-db",
            str(state_db),
            "--stage-root",
            str(stage_root),
        ],
    )
    assert staged.exit_code == 0, staged.output

    paths = AnalysisCanonicalPaths(
        markdown="topic/CLI Test分析.md",
        canvas="topic/CLI Test解析树.canvas",
        sidecar="topic/CLI Test分析.analysis.json",
    )
    commit = AnalysisCommitRequest(
        commit_id="commit-cli",
        batch_id=batch.batch_id,
        item_id=batch.items[0].item_id,
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:cli-test",
        note_stem=batch.items[0].note_stem,
        document=batch.items[0].document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        relations=[
            KnowledgeRelation(
                from_id="paper:cli-test",
                relation="has-analysis",
                to_id=batch.items[0].document.artifact_id,
            )
        ],
    )
    commit_path = tmp_path / "commit.json"
    commit_path.write_text(commit.model_dump_json(indent=2) + "\n", encoding="utf-8")
    legacy_provider = tmp_path / "legacy-provider"
    legacy_provider.mkdir()

    result = runner.invoke(
        main,
        [
            "analysis",
            "commit-bundle",
            "--request",
            str(commit_path),
            "--vault-root",
            str(vault),
            "--state-db",
            str(state_db),
            "--stage-root",
            str(stage_root),
            "--commit-state-root",
            str(tmp_path / "commit-state"),
            "--provider-state-root",
            str(legacy_provider),
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["state"] == "committed"
    assert (vault / paths.markdown).is_file()
    assert (vault / paths.canvas).is_file()
    assert (vault / paths.sidecar).is_file()


def test_analysis_commit_bundle_cli_requires_provider_manifest_for_v4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_home = tmp_path / "scholar-home"
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(state_home))
    vault_id = "0123456789abcdef"
    document = AnalysisDocument(
        schema_version=4,
        artifact_id="analysis:paper:cli-v4",
        paper_title="CLI v4",
        language="en",
        reader=AnalysisReader(kind="zotflow_library", vault_id=vault_id),
        profile=AnalysisProfile(kind=ProfileKind.WHOLE, framework="reference_tree"),
        claims=[
            AnalysisClaim(
                claim_id="task",
                role=AnalysisRole.ABSTRACT,
                outline_path="abstract/task",
                title="Task",
                body="Readable task description.",
                evidence=Evidence(
                    kind=EvidenceKind.AUTHOR_STATED,
                    anchor="Abstract",
                    source_spans=[ZoteroPdfSpan(
                        library_type="personal",
                        library_id="17685951",
                        attachment_key="QR4ZU2S9",
                        content_hash="md5:" + "a" * 32,
                        page_index=3,
                    )],
                ),
            )
        ],
    )
    batch = AnalysisBatchRequest(
        batch_id="cli-v4",
        items=[
            AnalysisBatchItem(
                item_id="paper-one",
                zotero_item_key="ABCDEFGH",
                note_stem="CLI v4 Analysis",
                document=document,
            )
        ],
    )
    batch_path = tmp_path / "batch-v4.json"
    _write_request(batch_path, batch)
    state_db = tmp_path / "analysis.db"
    stage_root = tmp_path / "stage"
    runner = CliRunner()
    staged = runner.invoke(
        main,
        [
            "analysis",
            "batch-run",
            "--request",
            str(batch_path),
            "--state-db",
            str(state_db),
            "--stage-root",
            str(stage_root),
        ],
    )
    assert staged.exit_code == 0, staged.output

    vault = tmp_path / "vault"
    (vault / "field/resources/papers/cli-v4").mkdir(parents=True)

    def resolve(root: Path) -> str:
        assert root.samefile(vault)
        return vault_id

    monkeypatch.setattr(
        "scholar_workflow.analysis.commit.resolve_obsidian_vault_id", resolve
    )
    provider = _register_v4_source(state_home, vault)
    provider.mkdir(parents=True)
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 29, tzinfo=UTC),
        resources=[
            HubResource(
                resource_id="paper:cli-v4",
                kind=ResourceKind.PAPER,
                zotero=ZoteroLink(item_key="ABCDEFGH"),
            )
        ],
    )
    snapshot = initialize_knowledge_provider_snapshot(
        state_root=provider,
        vault_root=vault,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id="paper:cli-v4",
                    kind=ResourceKind.PAPER,
                    title="CLI v4",
                    markdown_path="field/resources/papers/cli-v4/Note.md",
                )
            ]
        ),
        catalog=catalog,
    )
    paths = AnalysisCanonicalPaths(
        markdown="field/resources/papers/cli-v4/CLI v4 Analysis.md",
        canvas="field/resources/papers/cli-v4/CLI v4解析树.canvas",
        sidecar="field/resources/papers/cli-v4/CLI v4 Analysis.analysis.json",
    )
    request = AnalysisCommitRequest(
        commit_id="commit-cli-v4",
        batch_id=batch.batch_id,
        item_id="paper-one",
        source_state=AnalysisState.VALIDATED,
        resource_id="paper:cli-v4",
        note_stem="CLI v4 Analysis",
        document=document,
        paths=paths,
        base_revisions={path: None for path in paths.as_list()},
        base_catalog_revision=catalog.revision,
        base_snapshot_revision=snapshot.snapshot_revision,
        zotero_item_key="ABCDEFGH",
        relations=[
            KnowledgeRelation(
                from_id="paper:cli-v4",
                relation="has-analysis",
                to_id=document.artifact_id,
            )
        ],
    )
    commit_path = tmp_path / "commit-v4.json"
    commit_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args = [
        "analysis",
        "commit-bundle",
        "--request",
        str(commit_path),
        "--vault-root",
        str(vault),
        "--state-db",
        str(state_db),
        "--stage-root",
        str(stage_root),
        "--commit-state-root",
        str(tmp_path / "commit-state"),
    ]

    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "unregistered-home"))
    missing = runner.invoke(main, args)
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(state_home))
    wrong_request = AnalysisCommitRequest.model_validate(
        {**request.model_dump(mode="json"), "zotero_item_key": "WXYZ6789"}
    )
    wrong_path = tmp_path / "commit-v4-wrong-paper.json"
    wrong_path.write_text(wrong_request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    wrong_args = args.copy()
    wrong_args[3] = str(wrong_path)
    mismatched = runner.invoke(main, wrong_args)
    assert mismatched.exit_code != 0
    assert "staged batch Zotero item key" in mismatched.output
    assert not any((vault / path).exists() for path in paths.as_list())
    forged_provider = tmp_path / "fake-same-vault-provider"
    forged_provider.mkdir()
    (forged_provider / "knowledge-provider.snapshot.json").write_bytes(
        (provider / "knowledge-provider.snapshot.json").read_bytes()
    )
    forged = runner.invoke(main, [*args, "--provider-state-root", str(forged_provider)])
    committed = runner.invoke(main, args)

    assert missing.exit_code == 7
    assert "Source registry" in missing.output
    assert forged.exit_code == 7
    assert "--provider-state-root" in forged.output
    assert committed.exit_code == 0, committed.output
    assert all((vault / path).is_file() for path in paths.as_list())
    assert f"obsidian://zotflow?vault={vault_id}" in (
        vault / paths.markdown
    ).read_text(encoding="utf-8")


def test_analysis_audit_knowledge_cli_reports_drift_without_writes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "Paper.md"
    note.write_text("# Paper\n\n[TODO]\n", encoding="utf-8")
    manifest = KnowledgeAuditManifest(
        objects=[
            KnowledgeAuditObject(
                object_id="paper:cli",
                object_class="atomic_resource",
                kind="paper",
                vault_path="Paper.md",
            )
        ]
    )
    manifest_path = tmp_path / "audit.json"
    manifest_path.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    before = note.read_bytes()

    result = CliRunner().invoke(
        main,
        [
            "analysis",
            "audit-knowledge",
            "--manifest",
            str(manifest_path),
            "--vault-root",
            str(vault),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "unresolved-template-marker" in {
        item["code"] for item in json.loads(result.output)["findings"]
    }
    assert note.read_bytes() == before
