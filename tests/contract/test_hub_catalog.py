"""Contract tests for the canonical HubCatalog interface.

The catalog is a rebuildable index shared by the Web Hub, Obsidian projector,
and Notion projector.  It is deliberately not another knowledge database.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
import jsonschema
from pydantic import ValidationError

from scholar_workflow.hub.models import (
    AssetRole,
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubAsset,
    HubCatalog,
    HubResource,
    HubTopic,
)


NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def _catalog(
    *,
    artifact_path: str = "世界模型/01-Paperlist.md",
    with_asset: bool = False,
) -> HubCatalog:
    artifact = HubArtifact(
        artifact_id="topic:world-models:paper-list",
        kind=ArtifactKind.PAPER_LIST,
        format=ArtifactFormat.MARKDOWN,
        vault_path=artifact_path,
        topic_id="world-models",
    )
    resource = HubResource(
        resource_id="paper:arxiv:2301.04104",
        kind="paper",
        title="A paper",
        authors=["A. Author"],
        topic_ids=["world-models", "robot-learning"],
        artifact_ids=[artifact.artifact_id],
    )
    assets = []
    if with_asset:
        assets.append(
            HubAsset(
                asset_id="asset:figure-one",
                owner_artifact_ids=[artifact.artifact_id],
                vault_path="attachments/paper-list-a1b2c3d4/方法概览.png",
                display_name="方法概览.png",
                media_type="image/png",
                size=9,
                sha256="sha256:" + "a" * 64,
                role=AssetRole.EMBED,
            )
        )
    return HubCatalog(
        generated_at=NOW,
        resources=[resource],
        topics=[
            HubTopic(
                topic_id="world-models",
                name="世界模型",
                resource_ids=[resource.resource_id],
                artifact_ids=[artifact.artifact_id],
            ),
            HubTopic(
                topic_id="robot-learning",
                name="机器人学习",
                resource_ids=[resource.resource_id],
            ),
        ],
        artifacts=[artifact],
        assets=assets,
    )


def test_one_resource_can_be_placed_in_multiple_topics():
    catalog = _catalog()
    assert catalog.resources[0].topic_ids == ["world-models", "robot-learning"]
    assert catalog.revision.startswith("sha256:")


@pytest.mark.parametrize(
    "bad_path",
    ["/tmp/paper.md", "../paper.md", "topic/../../paper.md", r"topic\\paper.md"],
)
def test_artifact_path_must_be_vault_relative_posix(bad_path):
    with pytest.raises(ValidationError):
        _catalog(artifact_path=bad_path)


def test_duplicate_and_dangling_ids_are_rejected():
    valid = _catalog()
    duplicate = valid.model_dump()
    duplicate["resources"].append(duplicate["resources"][0])
    with pytest.raises(ValidationError, match="duplicate resource_id"):
        HubCatalog.model_validate(duplicate)

    dangling = valid.model_dump()
    dangling["topics"][0]["resource_ids"] = ["paper:missing"]
    with pytest.raises(ValidationError, match="unknown resource"):
        HubCatalog.model_validate(dangling)


def test_asset_identity_path_and_owners_are_strict():
    valid = _catalog(with_asset=True)

    dangling = valid.model_dump()
    dangling["assets"][0]["owner_artifact_ids"] = ["artifact:missing"]
    dangling["revision"] = ""
    with pytest.raises(ValidationError, match="unknown artifact"):
        HubCatalog.model_validate(dangling)

    duplicate_path = valid.model_dump()
    duplicate = dict(duplicate_path["assets"][0])
    duplicate["asset_id"] = "asset:figure-two"
    duplicate_path["assets"].append(duplicate)
    duplicate_path["revision"] = ""
    with pytest.raises(ValidationError, match="duplicate asset vault_path"):
        HubCatalog.model_validate(duplicate_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vault_path", "/tmp/figure.png"),
        ("vault_path", "../figure.png"),
        ("display_name", "nested/figure.png"),
        ("media_type", "not a mime"),
        ("sha256", "abc123"),
        ("owner_artifact_ids", []),
    ],
)
def test_asset_fields_reject_nonportable_or_ambiguous_values(field, value):
    payload = _catalog(with_asset=True).model_dump()
    payload["assets"][0][field] = value
    payload["revision"] = ""
    with pytest.raises(ValidationError):
        HubCatalog.model_validate(payload)


def test_revision_is_stable_across_generated_time_and_top_level_order():
    first = _catalog(with_asset=True)
    payload = first.model_dump()
    payload["generated_at"] = datetime(2030, 1, 1, tzinfo=timezone.utc)
    payload["topics"] = list(reversed(payload["topics"]))
    payload["assets"][0]["owner_artifact_ids"] = list(
        reversed(payload["assets"][0]["owner_artifact_ids"])
    )
    payload["revision"] = ""
    second = HubCatalog.model_validate(payload)
    assert second.revision == first.revision


def test_catalog_serialization_never_contains_action_targets():
    payload = _catalog().model_dump(mode="json")
    text = str(payload)
    assert "command" not in text
    assert "action_id" not in text
    assert "/Users/" not in text


def test_checked_in_json_schema_accepts_the_runtime_model():
    schema = json.loads(
        (Path(__file__).parents[2] / "contracts" / "hub-catalog.schema.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.validate(_catalog(with_asset=True).model_dump(mode="json"), schema)


@pytest.mark.parametrize("bad_path", ["/tmp/a.png", "../a.png", "a/../b.png", r"a\b.png"])
def test_checked_in_json_schema_rejects_unsafe_asset_paths(bad_path):
    schema = json.loads(
        (Path(__file__).parents[2] / "contracts" / "hub-catalog.schema.json")
        .read_text(encoding="utf-8")
    )
    payload = _catalog(with_asset=True).model_dump(mode="json")
    payload["assets"][0]["vault_path"] = bad_path
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)
