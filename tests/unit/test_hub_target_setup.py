"""Prepared isolated fixtures for the system-selected execution folder flow."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scholar_workflow.hub.directory import ProjectRegistry
from scholar_workflow.hub.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.routing import (
    ExecutionTarget,
    ExecutionTargetError,
    ExecutionTargetRegistry,
    ExecutionTargetRegistryDocument,
)
from scholar_workflow.hub.target_setup import ExecutionFolderSetup


def _registries(tmp_path: Path):
    state = tmp_path / "state"
    sources = KnowledgeSourceRegistry(state / "sources.json")
    targets = ExecutionTargetRegistry(
        state / "targets.json",
        project_registry=ProjectRegistry(state / "projects.json"),
        source_registry=sources,
    )
    return sources, targets


def _working_folder(tmp_path: Path) -> Path:
    working = tmp_path / "isolated-working-folder"
    working.mkdir()
    return working


def test_folder_preview_and_confirmation_expose_only_safe_metadata(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    setup = ExecutionFolderSetup(sources, targets)

    preview = setup.preview(working)
    assert preview["title"] == working.name
    assert preview["kind"] == "folder"
    assert preview["capabilities"] == ["codex"]
    assert preview["requires_confirmation"] is True
    assert set(preview) == {
        "candidate_token", "title", "kind", "capabilities", "requires_confirmation",
    }
    assert str(working) not in json.dumps(preview)
    assert sources.load_document().folders == []
    assert targets.load().targets == []

    result = setup.confirm(preview["candidate_token"])
    assert result["title"] == working.name
    assert result["kind"] == "folder"
    assert str(working) not in json.dumps(result)
    assert "root" not in result and "cwd" not in result
    assert len(sources.load_document().folders) == 1
    assert len(targets.load().targets) == 1
    resolved = targets.resolve(result["target_id"], capability="codex")
    assert resolved.cwd == working.resolve()

    with pytest.raises(ExecutionTargetError, match="expired"):
        setup.confirm(preview["candidate_token"])
    assert len(targets.load().targets) == 1


@pytest.mark.parametrize("selection", ["root", "home", "symlink", "relative"])
def test_folder_preview_rejects_broad_or_untrusted_roots(tmp_path, monkeypatch, selection):
    sources, targets = _registries(tmp_path)
    setup = ExecutionFolderSetup(sources, targets)
    working = _working_folder(tmp_path)
    simulated_home = tmp_path / "simulated-home"
    simulated_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: simulated_home)
    link = tmp_path / "selected-link"
    link.symlink_to(working, target_is_directory=True)
    selected = {
        "root": Path(working.anchor),
        "home": simulated_home,
        "symlink": link,
        "relative": Path("relative-working-folder"),
    }[selection]

    with pytest.raises(ExecutionTargetError, match="specific working folder|non-symlink"):
        setup.preview(selected)
    assert sources.load_document().folders == []
    assert targets.load().targets == []


def test_confirmation_rejects_replaced_folder_identity(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    setup = ExecutionFolderSetup(sources, targets)
    preview = setup.preview(working)
    original = tmp_path / "original-folder"
    working.rename(original)
    working.mkdir()

    with pytest.raises(ExecutionTargetError, match="Selected folder changed"):
        setup.confirm(preview["candidate_token"])
    assert sources.load_document().folders == []
    assert targets.load().targets == []
    assert original.is_dir()


@pytest.mark.parametrize("changed_registry", ["sources", "targets"])
def test_confirmation_rejects_stale_registry_revision(tmp_path, changed_registry):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    setup = ExecutionFolderSetup(sources, targets)
    preview = setup.preview(working)
    if changed_registry == "sources":
        sources.save(KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
            folder_id="other-folder", root=working, capabilities=["read"],
        )]))
    else:
        targets.save(ExecutionTargetRegistryDocument(targets=[ExecutionTarget(
            target_id="other-target", kind="folder",
            registered_root_id="other-folder", capabilities=["codex"],
        )]))
    source_before = sources.load_document().model_dump(mode="json")
    target_before = targets.load().model_dump(mode="json")

    with pytest.raises(ExecutionTargetError, match="registrations changed"):
        setup.confirm(preview["candidate_token"])
    assert sources.load_document().model_dump(mode="json") == source_before
    assert targets.load().model_dump(mode="json") == target_before


def test_failed_target_cas_restores_prior_folder_registration(tmp_path, monkeypatch):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    sources.save(KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
        folder_id="existing-folder", root=working, capabilities=["read"],
    )]))
    sources_before = sources.load_document().model_dump(mode="json")
    setup = ExecutionFolderSetup(sources, targets)
    preview = setup.preview(working)

    def reject_target_save(_document, *, expected_revision):
        assert expected_revision == "absent"
        assert "codex" in sources.load_document().folders[0].capabilities
        raise ExecutionTargetError("execution target registry changed after preview")

    monkeypatch.setattr(targets, "save", reject_target_save)
    with pytest.raises(ExecutionTargetError, match="changed after preview"):
        setup.confirm(preview["candidate_token"])
    assert sources.load_document().model_dump(mode="json") == sources_before
    assert targets.load().targets == []
    assert working.is_dir()


def test_confirmation_does_not_reenable_disabled_folder(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    sources.save(KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
        folder_id="disabled-folder", root=working, enabled=False,
        capabilities=["read", "codex"],
    )]))
    previous_revision = sources.revision()
    setup = ExecutionFolderSetup(sources, targets)
    preview = setup.preview(working)

    with pytest.raises(ExecutionTargetError, match="registered folder is disabled"):
        setup.confirm(preview["candidate_token"])
    assert sources.revision() == previous_revision
    assert sources.load_document().folders[0].enabled is False
    assert targets.load().targets == []


def test_folder_candidate_expiry_has_no_registration_side_effect(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    elapsed = [100.0]
    setup = ExecutionFolderSetup(sources, targets, ttl_seconds=10, clock=lambda: elapsed[0])
    preview = setup.preview(working)
    elapsed[0] = 111.0

    with pytest.raises(ExecutionTargetError, match="expired"):
        setup.confirm(preview["candidate_token"])
    assert sources.load_document().folders == []
    assert targets.load().targets == []


def test_confirmation_reuses_existing_target_without_duplicate_alias(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    sources.save(KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
        folder_id="existing-folder", root=working, capabilities=["read", "codex"],
    )]))
    targets.save(ExecutionTargetRegistryDocument(targets=[ExecutionTarget(
        target_id="existing-target", kind="folder",
        registered_root_id="existing-folder", capabilities=["codex"],
    )]))
    setup = ExecutionFolderSetup(sources, targets)

    result = setup.confirm(setup.preview(working)["candidate_token"])
    assert result["target_id"] == "existing-target"
    assert len(sources.load_document().folders) == 1
    assert len(targets.load().targets) == 1


def test_selecting_vault_root_does_not_reuse_a_field_scoped_target(tmp_path):
    sources, targets = _registries(tmp_path)
    working = _working_folder(tmp_path)
    field_root = working / "field"
    field_root.mkdir()
    source_id = "f0784bc9-aa47-49b8-9c54-4b364789a472"
    field_id = "ab0e1a99-f20d-4a41-8b13-56f04d7f0221"
    (working / ".scholar-workflow").mkdir()
    (working / ".scholar-workflow" / "fields.yml").write_text(json.dumps({
        "schema_version": 1, "source_id": source_id,
        "fields": [{"field_id": field_id, "title": "Isolated Field",
                    "relative_root": "field", "home": "home.md", "navigation": []}],
    }), encoding="utf-8")
    sources.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(
            folder_id="existing-vault", root=working, capabilities=["read", "codex"],
        )],
        sources=[KnowledgeSourceRegistration(
            source_id=source_id, folder_id="existing-vault", capabilities=["read"],
        )],
    ))
    targets.save(ExecutionTargetRegistryDocument(targets=[ExecutionTarget(
        target_id="existing-field-target", kind="vault",
        registered_root_id="existing-vault", source_id=source_id, field_id=field_id,
        capabilities=["codex"],
    )]))
    setup = ExecutionFolderSetup(sources, targets)

    result = setup.confirm(setup.preview(working)["candidate_token"])
    assert result["target_id"] != "existing-field-target"
    assert result["kind"] == "folder"
    assert result["field_id"] is None
    assert targets.resolve(result["target_id"], capability="codex").cwd == working.resolve()
    assert targets.resolve("existing-field-target", capability="codex").cwd == field_root.resolve()
    assert len(targets.load().targets) == 2
