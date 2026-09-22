from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import (
    initialize_knowledge_provider_snapshot,
)
from scholar_workflow.analysis.models import (
    KnowledgeArtifactChange,
    KnowledgeAtomicResource,
    KnowledgeChangeSet,
    KnowledgeManifest,
)
from scholar_workflow.cli import main
from scholar_workflow.hub.models import HubCatalog, HubResource
from scholar_workflow.models import ResourceKind


def _state_and_change(tmp_path: Path) -> tuple[Path, Path]:
    state = tmp_path / "provider"
    state.mkdir()
    catalog = HubCatalog(
        generated_at=datetime(2026, 9, 22, tzinfo=UTC),
        resources=[HubResource(resource_id="paper:cli", kind=ResourceKind.PAPER)],
    )
    initialize_knowledge_provider_snapshot(
        state_root=state,
        manifest=KnowledgeManifest(
            atomic_resources=[
                KnowledgeAtomicResource(
                    resource_id="paper:cli",
                    kind=ResourceKind.PAPER,
                    title="CLI Paper",
                    markdown_path="papers/CLI.md",
                )
            ]
        ),
        catalog=catalog,
    )
    artifacts = [
        KnowledgeArtifactChange(
            artifact_id="analysis:paper:cli",
            resource_id="paper:cli",
            kind="analysis_markdown",
            vault_path="papers/CLI分析.md",
            sha256="sha256:" + "1" * 64,
        ),
        KnowledgeArtifactChange(
            artifact_id="analysis:paper:cli:canvas",
            resource_id="paper:cli",
            kind="analysis_canvas",
            vault_path="papers/CLI解析树.canvas",
            sha256="sha256:" + "2" * 64,
        ),
        KnowledgeArtifactChange(
            artifact_id="analysis:paper:cli:sidecar",
            resource_id="paper:cli",
            kind="analysis_sidecar",
            vault_path="papers/CLI分析.analysis.json",
            sha256="sha256:" + "3" * 64,
        ),
    ]
    semantic = {
        "source_receipt": "analysis-commit:cli",
        "base_catalog_revision": catalog.revision,
        "upsert_artifacts": [item.model_dump(mode="json") for item in artifacts],
        "upsert_relations": [],
        "upsert_projections": [],
        "expected_base_hashes": {item.vault_path: None for item in artifacts},
    }
    encoded = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    change = KnowledgeChangeSet(
        change_id="change:" + hashlib.sha256(encoded).hexdigest(),
        **semantic,
    )
    change_path = tmp_path / "change.json"
    change_path.write_text(change.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return state, change_path


def test_apply_change_set_cli_returns_stable_receipt_on_replay(tmp_path: Path) -> None:
    state, change_path = _state_and_change(tmp_path)
    args = [
        "analysis",
        "apply-change-set",
        "--change-set",
        str(change_path),
        "--provider-state-root",
        str(state),
    ]
    runner = CliRunner()

    first = runner.invoke(main, args)
    replay = runner.invoke(main, args)

    assert first.exit_code == 0, first.output
    assert replay.exit_code == 0, replay.output
    assert json.loads(first.output) == json.loads(replay.output)
    assert len(json.loads(first.output)["applied_artifact_ids"]) == 3


def test_apply_change_set_cli_maps_stale_revision_to_identity_conflict(
    tmp_path: Path,
) -> None:
    state, change_path = _state_and_change(tmp_path)
    payload = json.loads(change_path.read_text(encoding="utf-8"))
    payload["base_catalog_revision"] = "sha256:" + "9" * 64
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {"schema_version", "change_id"}
    }
    encoded = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    payload["change_id"] = "change:" + hashlib.sha256(encoded).hexdigest()
    change_path.write_text(json.dumps(payload), encoding="utf-8")

    result = CliRunner().invoke(
        main,
        [
            "analysis",
            "apply-change-set",
            "--change-set",
            str(change_path),
            "--provider-state-root",
            str(state),
        ],
    )

    assert result.exit_code == 5
    assert "base catalog revision changed" in result.output
