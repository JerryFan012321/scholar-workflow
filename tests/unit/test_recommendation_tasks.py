"""Task binding preserves project prose and refuses unsafe or ambiguous routes."""
from __future__ import annotations

import json
import uuid

import pytest

from scholar_workflow.research.models import ResearchError
from scholar_workflow.research.recommendations.project_tasks import ProjectTasks
from scholar_workflow.research.recommendations.store import RecommendationStore


@pytest.fixture
def binding(tmp_path):
    store = RecommendationStore(tmp_path / "recommendations/test")
    root = tmp_path / "project"
    root.mkdir()
    return ProjectTasks(store, "test"), root, str(uuid.uuid4())


def files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_binding_preserves_existing_documents_and_needs_no_instruction_topology(binding):
    tasks, root, thread = binding
    relative = ".agents/context/recommendations/evaluation"
    directory = root / relative
    directory.mkdir(parents=True)
    (root / "AGENT.md").write_text("# Existing instruction entry\nKeep this file.\n")
    (root / "project-layout.json").write_text("not a layout declaration\n")
    (directory / "context.md").write_text("# Human context\nThe selected task's actual scope.\n")
    (directory / "recommended.md").write_text("# Human history\nKeep earlier recommendations and reasons.\n")
    before = files(root)
    task = tasks.bind(root, "evaluation", "Evaluation research", thread)
    repeated = tasks.bind(root, "evaluation", "Evaluation research", thread)
    assert repeated == task
    assert task["schema_version"] == 2
    assert task["context_file"] == relative + "/context.md"
    assert task["recommended_file"] == relative + "/recommended.md"
    assert files(root) == before
    assert "checkpoint_file" not in task and "feedback_file" not in task
    assert not (root / "AGENTS.md").exists()


def test_new_binding_leaves_only_two_project_files(binding):
    tasks, root, thread = binding
    tasks.bind(root, "evaluation", "Evaluation research", thread)
    assert set(files(root)) == {
        ".agents/context/recommendations/evaluation/context.md",
        ".agents/context/recommendations/evaluation/recommended.md",
    }


@pytest.mark.parametrize("name", ["context.md", "recommended.md"])
@pytest.mark.parametrize("attack", ["symlink", "hardlink"])
def test_binding_refuses_unsafe_existing_documents(binding, tmp_path, name, attack):
    tasks, root, thread = binding
    directory = root / ".agents/context/recommendations/evaluation"
    directory.mkdir(parents=True)
    original = tmp_path / "outside.md"
    original.write_text("# Human original\nNever overwrite this content.\n")
    target = directory / name
    if attack == "symlink":
        target.symlink_to(original)
    else:
        target.hardlink_to(original)
    with pytest.raises(ResearchError):
        tasks.bind(root, "evaluation", "Evaluation research", thread)
    assert original.read_text() == "# Human original\nNever overwrite this content.\n"
    assert not tasks.list()["tasks"]


@pytest.mark.parametrize("directory", [".agents", ".agents/context", ".agents/context/recommendations/evaluation"])
def test_binding_does_not_follow_project_directory_symlinks(binding, tmp_path, directory):
    tasks, root, thread = binding
    outside = tmp_path / "outside"
    outside.mkdir()
    target = root / directory
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ResearchError):
        tasks.bind(root, "evaluation", "Evaluation research", thread)
    assert not list(outside.iterdir())
    assert not tasks.list()["tasks"]


def test_thread_change_requires_current_revision_and_preserves_documents(binding):
    tasks, root, thread = binding
    task = tasks.bind(root, "evaluation", "Evaluation research", thread)
    before = files(root)
    next_thread = str(uuid.uuid4())
    with pytest.raises(ResearchError):
        tasks.bind(root, "evaluation", "Evaluation research", next_thread)
    changed = tasks.bind(root, "evaluation", "Evaluation research", next_thread,
                         expected_revision=task["revision"])
    assert changed["thread_id"] == next_thread
    assert changed["revision"] == task["revision"] + 1
    with pytest.raises(ResearchError):
        tasks.bind(root, "evaluation", "Evaluation research", thread,
                   expected_revision=task["revision"])
    assert files(root) == before


def test_same_producer_cannot_silently_move_to_another_root(binding, tmp_path):
    tasks, root, thread = binding
    task = tasks.bind(root, "evaluation", "Evaluation research", thread)
    other = tmp_path / "other-project"
    other.mkdir()
    with pytest.raises(ResearchError):
        tasks.bind(other, "evaluation", "Evaluation research", thread)
    assert not list(other.iterdir())
    assert tasks.guide("evaluation")["task"] == task
    assert tasks.guide("evaluation")["project_root"] == str(root)


@pytest.mark.parametrize("producer", ["../outside", "a/b", "..", "/absolute"])
def test_binding_rejects_path_like_producer_without_project_writes(binding, producer):
    tasks, root, thread = binding
    with pytest.raises(ResearchError):
        tasks.bind(root, producer, "Evaluation research", thread)
    assert not list(root.iterdir())
    assert not tasks.list()["tasks"]


def test_legacy_task_stays_listable_but_is_not_silently_adopted(binding):
    tasks, root, thread = binding
    legacy = {"schema_version": 1, "project_id": "legacy-project", "producer_id": "evaluation",
              "title": "Legacy task", "revision": 1, "context_file": "legacy/CONTEXT.md",
              "feedback_file": "legacy/feedback.jsonl", "checkpoint_file": "legacy/state.json"}
    with tasks.store._database(write=True) as database:
        database.execute("INSERT INTO recommendation_tasks VALUES(?,?,?)",
                         ("evaluation", "legacy-project", json.dumps(legacy)))
    assert tasks.list()["tasks"] == [legacy]
    with pytest.raises(ResearchError):
        tasks.guide("evaluation", include_context=True)
    with pytest.raises(ResearchError):
        tasks.bind(root, "evaluation", "Evaluation research", thread, expected_revision=1)
    assert tasks.list()["tasks"] == [legacy]
    assert not list(root.iterdir())
