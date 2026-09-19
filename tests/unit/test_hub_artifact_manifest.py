"""Explicit artifact manifests register JSON Canvas without mutating its schema."""
from __future__ import annotations

from datetime import datetime, timezone

from scholar_workflow.hub.artifact_manifest import VaultArtifactManifestProvider
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.content import ArtifactContentStore
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
    HubTopic,
)


def _base(*, canvas: HubArtifact | None = None) -> HubCatalog:
    analysis = HubArtifact(
        artifact_id="analysis:paper-one",
        kind=ArtifactKind.PAPER_ANALYSIS,
        format=ArtifactFormat.MARKDOWN,
        vault_path="世界模型/论文分析.md",
        resource_id="paper:one",
        topic_id="world-models",
    )
    artifacts = [analysis, *([canvas] if canvas else [])]
    return HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[
            HubResource(
                resource_id="paper:one",
                kind="paper",
                topic_ids=["world-models"],
                artifact_ids=[row.artifact_id for row in artifacts],
            )
        ],
        topics=[
            HubTopic(
                topic_id="world-models",
                name="世界模型",
                resource_ids=["paper:one"],
                artifact_ids=[row.artifact_id for row in artifacts],
            )
        ],
        artifacts=artifacts,
    )


def _write_manifest(tmp_path, vault_path: str) -> None:
    directory = tmp_path / ".scholar-workflow"
    directory.mkdir(exist_ok=True)
    (directory / "artifacts.yml").write_text(
        "schema_version: 1\n"
        "artifacts:\n"
        "  - artifact_id: analysis:paper-one:canvas\n"
        "    kind: analysis-canvas\n"
        "    format: canvas\n"
        f"    vault_path: {vault_path}\n"
        "    resource_id: paper:one\n"
        "    topic_id: world-models\n"
        "    parent_id: analysis:paper-one\n",
        encoding="utf-8",
    )


def test_canvas_manifest_registers_json_canvas_without_extra_json_fields(tmp_path):
    canvas = tmp_path / "世界模型" / "论文解析树.canvas"
    canvas.parent.mkdir()
    canvas.write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    _write_manifest(tmp_path, "世界模型/论文解析树.canvas")

    provider = VaultArtifactManifestProvider(
        StaticCatalogProvider(_base()), tmp_path
    )
    catalog = provider.load()

    registered = next(
        row for row in catalog.artifacts if row.artifact_id == "analysis:paper-one:canvas"
    )
    assert registered.format == ArtifactFormat.CANVAS
    assert registered.vault_path == "世界模型/论文解析树.canvas"
    assert registered.parent_id == "analysis:paper-one"
    assert "analysis:paper-one:canvas" in catalog.resources[0].artifact_ids
    assert "analysis:paper-one:canvas" in catalog.topics[0].artifact_ids
    assert canvas.read_text(encoding="utf-8") == '{"nodes":[],"edges":[]}\n'
    content = ArtifactContentStore(tmp_path, provider).read(registered.artifact_id)
    assert content.content == '{"nodes":[],"edges":[]}\n'
    assert content.format == "canvas"


def test_canvas_manifest_updates_a_stale_snapshot_path_after_manual_manifest_edit(tmp_path):
    renamed = tmp_path / "世界模型" / "人工重命名.canvas"
    renamed.parent.mkdir()
    renamed.write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    stale = HubArtifact(
        artifact_id="analysis:paper-one:canvas",
        kind=ArtifactKind.ANALYSIS_CANVAS,
        format=ArtifactFormat.CANVAS,
        vault_path="世界模型/旧名字.canvas",
        resource_id="paper:one",
        topic_id="world-models",
        parent_id="analysis:paper-one",
    )
    _write_manifest(tmp_path, "世界模型/人工重命名.canvas")

    catalog = VaultArtifactManifestProvider(
        StaticCatalogProvider(_base(canvas=stale)), tmp_path
    ).load()

    registered = next(
        row for row in catalog.artifacts if row.artifact_id == stale.artifact_id
    )
    assert registered.vault_path == "世界模型/人工重命名.canvas"


def test_invalid_manifest_entry_masks_same_stale_snapshot_artifact(tmp_path):
    stale = HubArtifact(
        artifact_id="analysis:paper-one:canvas",
        kind=ArtifactKind.ANALYSIS_CANVAS,
        format=ArtifactFormat.CANVAS,
        vault_path="世界模型/旧名字.canvas",
        resource_id="paper:one",
        topic_id="world-models",
        parent_id="analysis:paper-one",
    )
    _write_manifest(tmp_path, "世界模型/不存在.canvas")

    catalog = VaultArtifactManifestProvider(
        StaticCatalogProvider(_base(canvas=stale)), tmp_path
    ).load()

    assert stale.artifact_id not in {row.artifact_id for row in catalog.artifacts}
    assert stale.artifact_id not in catalog.resources[0].artifact_ids
    assert stale.artifact_id not in catalog.topics[0].artifact_ids
    assert any(
        row.code == "missing-or-unsafe-vault-artifact"
        and row.entity_id == stale.artifact_id
        for row in catalog.diagnostics
    )


def test_snapshot_canvas_without_manifest_fails_closed(tmp_path):
    stale = HubArtifact(
        artifact_id="analysis:paper-one:canvas",
        kind=ArtifactKind.ANALYSIS_CANVAS,
        format=ArtifactFormat.CANVAS,
        vault_path="世界模型/旧名字.canvas",
        resource_id="paper:one",
        topic_id="world-models",
        parent_id="analysis:paper-one",
    )

    catalog = VaultArtifactManifestProvider(
        StaticCatalogProvider(_base(canvas=stale)), tmp_path
    ).load()

    assert stale.artifact_id not in {row.artifact_id for row in catalog.artifacts}
    assert any(
        row.code == "unregistered-vault-canvas"
        and row.entity_id == stale.artifact_id
        for row in catalog.diagnostics
    )
