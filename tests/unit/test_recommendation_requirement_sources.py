"""Source ownership is explicit version metadata, without guessing legacy intent."""

from __future__ import annotations

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.source_catalog import SourceCatalog
from scholar_workflow.research.recommendations.store import RecommendationStore


def save(store, requirement_id="synthetic-requirement", expected_revision=0, **changes):
    fields = {
        "requirement_id": requirement_id,
        "title": "Synthetic source requirement",
        "content": "只整理这个来源中与当前研究相关的材料。",
        "enabled": True,
        "expected_revision": expected_revision,
        "updated_by": {"kind": "human", "name": "Synthetic author"},
    }
    return store.save_requirement(**{**fields, **changes})


def test_new_requirement_binds_only_to_explicit_source_and_filter_keeps_disabled(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    bound = save(store, source_id="alphaxiv", enabled=False)
    other = save(store, requirement_id="other-source", source_id="hf-daily")
    assert bound["source_id"] == "alphaxiv"
    assert store.list_requirements(source_id="alphaxiv") == {"items": [bound]}
    assert store.list_requirements(source_id="hf-daily") == {"items": [other]}
    assert len(store.list_requirements()["items"]) == 2


def test_unassigned_legacy_requirement_is_preserved_and_never_guessed(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    original = save(store)
    assert "source_id" not in original
    assert store.list_requirements(source_id="alphaxiv")["items"] == []
    assert store.list_requirements(source_id="hf-daily")["items"] == []
    revised = save(store, expected_revision=1, content="Old client edits a legacy note.")
    assert "source_id" not in revised
    assert store.get_requirement(original["requirement_id"], revision=1) == original


def test_old_client_edit_preserves_current_binding_and_explicit_move_preserves_history(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    first = save(store, source_id="alphaxiv")
    second = save(store, expected_revision=1, content="Edit without providing source_id.")
    assert second["source_id"] == "alphaxiv"
    third = save(store, expected_revision=2, source_id="hf-daily")
    assert third["source_id"] == "hf-daily"
    assert store.get_requirement(first["requirement_id"], revision=1) == first
    assert store.get_requirement(first["requirement_id"], revision=2) == second
    assert store.list_requirements(source_id="alphaxiv")["items"] == []
    assert store.list_requirements(source_id="hf-daily")["items"] == [third]


@pytest.mark.parametrize("source_id", ["unknown-source", "", "private/path"])
def test_unknown_source_cannot_be_saved_or_silently_listed_empty(tmp_path, source_id):
    store = RecommendationStore(tmp_path / "state")
    with pytest.raises(ResearchError):
        save(store, source_id=source_id)
    with pytest.raises(ResearchError):
        store.list_requirements(source_id=source_id)
    assert store.list_requirements()["items"] == []


def test_registered_custom_source_is_usable_without_a_platform_enum(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    SourceCatalog(store).register(
        {
            "source_id": "selected-lab",
            "name": "Synthetic lab",
            "purpose": "Selected announcements",
            "status": "available",
            "interfaces": [{"kind": "feed", "url": "https://example.org/feed.xml"}],
            "capabilities": ["releases"],
        },
        expected_revision=0,
    )
    requirement = save(store, source_id="selected-lab")
    assert store.list_requirements(source_id="selected-lab")["items"] == [requirement]


def test_stale_source_reassignment_cannot_overwrite_current_owner(tmp_path):
    store = RecommendationStore(tmp_path / "state")
    first = save(store, source_id="alphaxiv")
    with pytest.raises(ResearchError) as failure:
        save(store, expected_revision=0, source_id="hf-daily")
    assert failure.value.exit_code == 5
    assert store.get_requirement(first["requirement_id"]) == first
