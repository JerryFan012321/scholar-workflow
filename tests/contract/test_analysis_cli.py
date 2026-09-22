from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from scholar_workflow.analysis.models import (
    AnalysisBatchItem,
    AnalysisBatchRequest,
    AnalysisCanonicalPaths,
    AnalysisClaim,
    AnalysisCommitRequest,
    AnalysisDocument,
    AnalysisProfile,
    AnalysisRole,
    AnalysisState,
    Evidence,
    EvidenceKind,
    KnowledgeAuditManifest,
    KnowledgeAuditObject,
    KnowledgeRelation,
    ProfileKind,
)
from scholar_workflow.cli import main


def _request(batch_id: str, *, body_suffix: str = "") -> AnalysisBatchRequest:
    document = AnalysisDocument(
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
            for role in AnalysisRole
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
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["state"] == "committed"
    assert (vault / paths.markdown).is_file()
    assert (vault / paths.canvas).is_file()
    assert (vault / paths.sidecar).is_file()


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
