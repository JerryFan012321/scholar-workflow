"""Vault discovery reads only Hub-governed frontmatter, never free Markdown."""
from __future__ import annotations

from datetime import datetime, timezone

from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
    HubTopic,
)
from scholar_workflow.hub.vault import VaultCatalogProvider


def _base() -> HubCatalog:
    return HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[HubResource(resource_id="paper:one", kind="paper")],
        topics=[HubTopic(topic_id="world-models", name="世界模型", resource_ids=["paper:one"])],
        artifacts=[],
    )


def test_scans_only_managed_frontmatter_and_keeps_human_body_out_of_catalog(tmp_path):
    managed = tmp_path / "世界模型" / "analysis.md"
    managed.parent.mkdir()
    managed.write_text(
        "---\n"
        "title: 人工标题\n"
        "sw_schema: 1\n"
        "sw_kind: paper-analysis\n"
        "sw_catalog_id: analysis:paper-one\n"
        "sw_topic_id: world-models\n"
        "sw_resource_id: paper:one\n"
        "sw_revision: sha256:abc\n"
        "---\n"
        "# 人类正文\n\n这里可以自由编辑。\n",
        encoding="utf-8",
    )
    (tmp_path / "自由笔记.md").write_text(
        "# looks like paper-analysis but has no contract\n", encoding="utf-8"
    )

    catalog = VaultCatalogProvider(StaticCatalogProvider(_base()), tmp_path).load()

    assert [artifact.artifact_id for artifact in catalog.artifacts] == [
        "analysis:paper-one"
    ]
    artifact = catalog.artifacts[0]
    assert artifact.vault_path == "世界模型/analysis.md"
    assert artifact.resource_id == "paper:one"
    assert artifact.topic_id == "world-models"
    serialized = catalog.model_dump_json()
    assert "人类正文" not in serialized
    assert "人工标题" not in serialized


def test_dangling_managed_relation_is_visible_diagnostic_not_fake_authority(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\n"
        "sw_schema: 1\n"
        "sw_kind: reading-note\n"
        "sw_catalog_id: note:orphan\n"
        "sw_resource_id: paper:missing\n"
        "---\nbody\n",
        encoding="utf-8",
    )

    catalog = VaultCatalogProvider(StaticCatalogProvider(_base()), tmp_path).load()

    assert catalog.artifacts[0].resource_id is None
    assert any(row.code == "dangling-vault-resource" for row in catalog.diagnostics)
    assert {resource.resource_id for resource in catalog.resources} == {"paper:one"}


def test_unique_vault_declaration_updates_stale_snapshot_path_after_manual_rename(tmp_path):
    renamed = tmp_path / "世界模型" / "人工重命名.md"
    renamed.parent.mkdir()
    renamed.write_text(
        "---\n"
        "sw_schema: 1\n"
        "sw_kind: paper-analysis\n"
        "sw_catalog_id: analysis:paper-one\n"
        "sw_resource_id: paper:one\n"
        "---\n"
        "# 人工正文\n",
        encoding="utf-8",
    )
    base = _base()
    base = HubCatalog(
        generated_at=base.generated_at,
        resources=base.resources,
        topics=base.topics,
        artifacts=[
            HubArtifact(
                artifact_id="analysis:paper-one",
                kind=ArtifactKind.PAPER_ANALYSIS,
                format=ArtifactFormat.MARKDOWN,
                vault_path="世界模型/旧名字.md",
                resource_id="paper:one",
            )
        ],
    )

    catalog = VaultCatalogProvider(StaticCatalogProvider(base), tmp_path).load()

    assert catalog.artifacts[0].vault_path == "世界模型/人工重命名.md"
    assert not any(
        row.code == "duplicate-vault-artifact-id" for row in catalog.diagnostics
    )


def test_unknown_hub_frontmatter_field_is_diagnostic_but_human_yaml_is_allowed(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\n"
        "title: 人工字段继续允许\n"
        "sw_schema: 1\n"
        "sw_kind: reading-note\n"
        "sw_catalog_id: note:unknown-field\n"
        "sw_future_guess: forbidden\n"
        "---\n"
        "正文\n",
        encoding="utf-8",
    )

    catalog = VaultCatalogProvider(StaticCatalogProvider(_base()), tmp_path).load()

    assert catalog.artifacts == []
    assert any(
        row.code == "unknown-vault-managed-field" for row in catalog.diagnostics
    )


def test_invalid_managed_declaration_masks_same_snapshot_artifact(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(
        "---\n"
        "sw_schema: 1\n"
        "sw_kind: reading-note\n"
        "sw_catalog_id: note:invalid\n"
        "sw_future_guess: forbidden\n"
        "---\n正文\n",
        encoding="utf-8",
    )
    base = _base()
    base = HubCatalog(
        generated_at=base.generated_at,
        resources=base.resources,
        topics=base.topics,
        artifacts=[
            HubArtifact(
                artifact_id="note:invalid",
                kind=ArtifactKind.READING_NOTE,
                format=ArtifactFormat.MARKDOWN,
                vault_path="note.md",
            )
        ],
    )

    catalog = VaultCatalogProvider(StaticCatalogProvider(base), tmp_path).load()

    assert catalog.artifacts == []
    assert any(
        row.code == "unknown-vault-managed-field"
        for row in catalog.diagnostics
    )
