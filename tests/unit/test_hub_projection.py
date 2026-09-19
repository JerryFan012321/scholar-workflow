"""Pure projection tests: structured literature input -> canonical HubCatalog."""
from __future__ import annotations

from datetime import datetime, timezone

from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.workflows.hub_projection import (
    build_topic_catalog_patch,
    merge_catalog_patch,
)


def _doc(topic_id: str, topic: str) -> dict:
    return {
        "generated_at": "2026-09-18T00:00:00Z",
        "topic_id": topic_id,
        "topic": topic,
        "paper_list": [
            {
                "resource_id": "arxiv:2301.04104",
                "title": "Mastering Diverse Domains through World Models",
                "authors": ["Danijar Hafner"],
                "year": 2023,
                "venue": "arXiv",
                "importance": "milestone",
                "zotero_key": "S6LZUS6S",
                "attachment_key": "ABCD2345",
                "arxiv": "2301.04104",
                "asset_note": "paper_assets/2023-Hafner-DreamerV3.md",
                "classified": True,
            }
        ],
        "tree": {
            "name": topic,
            "kind": "topic",
            "children": [
                {
                    "name": "general world-model learning",
                    "kind": "task",
                    "papers": ["arxiv:2301.04104"],
                }
            ],
        },
    }


def _empty() -> HubCatalog:
    return HubCatalog(
        generated_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        resources=[], topics=[], artifacts=[],
    )


def test_patch_contains_relationships_but_no_markdown_body():
    patch = build_topic_catalog_patch(
        _doc("world-models", "世界模型"),
        root="世界模型",
        port=23128,
        filename="02-世界模型文献树.md",
        paperlist_only=False,
    )

    assert patch.topics[0].topic_id == "world-models"
    assert patch.resources[0].topic_ids == ["world-models"]
    assert {artifact.kind.value for artifact in patch.artifacts} == {
        "literature-tree", "paper-hub"
    }
    assert "```mermaid" not in patch.model_dump_json()
    assert all(not artifact.vault_path.startswith("/") for artifact in patch.artifacts)


def test_merge_allows_one_paper_in_multiple_topics():
    world = build_topic_catalog_patch(
        _doc("world-models", "世界模型"), "世界模型", 23128,
        "01-Paperlist.md", paperlist_only=True,
    )
    robot = build_topic_catalog_patch(
        _doc("robot-learning", "机器人学习"), "机器人学习", 23128,
        "01-Paperlist.md", paperlist_only=True,
    )

    merged = merge_catalog_patch(merge_catalog_patch(_empty(), world), robot)

    assert len(merged.resources) == 1
    assert set(merged.resources[0].topic_ids) == {"world-models", "robot-learning"}
    assert len([
        artifact for artifact in merged.artifacts
        if artifact.kind.value == "paper-hub"
    ]) == 2
    assert {topic.topic_id for topic in merged.topics} == {
        "world-models", "robot-learning"
    }


def test_tree_and_paper_list_are_two_human_readable_artifacts_for_one_topic():
    doc = _doc("world-models", "世界模型")
    paper_list = build_topic_catalog_patch(
        doc, "世界模型", 23128, "01-Paperlist.md", paperlist_only=True,
    )
    tree = build_topic_catalog_patch(
        doc, "世界模型", 23128, "02-世界模型文献树.md", paperlist_only=False,
    )

    merged = merge_catalog_patch(merge_catalog_patch(_empty(), paper_list), tree)
    kinds = {artifact.kind.value for artifact in merged.artifacts}
    assert "paper-list" in kinds
    assert "literature-tree" in kinds
    assert "paper-hub" in kinds
    topic = next(topic for topic in merged.topics if topic.topic_id == "world-models")
    assert set(topic.artifact_ids) == {artifact.artifact_id for artifact in merged.artifacts}
