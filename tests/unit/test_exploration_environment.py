"""Environment boundaries are independent of workspace names and browser ports."""

import json

import pytest

from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment


def _context(tmp_path):
    vault = tmp_path / "test-vault"
    vault.mkdir()
    return vault, ExplorerEnvironment("test", tmp_path / "test-state", (vault,))


def test_test_environment_requires_explicit_state_and_root(tmp_path):
    with pytest.raises(ExplorationError, match="explicit"):
        ExplorerEnvironment("test")
    with pytest.raises(ExplorationError, match="explicit"):
        ExplorerEnvironment("test", tmp_path / "state")


def test_test_environment_does_not_inherit_ambient_production_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "production"))
    vault, context = _context(tmp_path)
    assert context.registry_path == tmp_path / "test-state/hub/sources.json"
    context.check_registry()
    assert context.check_root(vault) == vault
    assert not context.state_root.exists()


def test_test_environment_rejects_production_home(tmp_path):
    from scholar_workflow.config import DEFAULT_HOME

    vault = tmp_path / "test-vault"
    vault.mkdir()
    with pytest.raises(ExplorationError, match="production"):
        ExplorerEnvironment("test", DEFAULT_HOME, (vault,))


def test_test_environment_rejects_outside_roots_and_symlinks(tmp_path):
    vault, context = _context(tmp_path)
    outside = tmp_path / "production-vault"
    outside.mkdir()
    with pytest.raises(ExplorationError, match="test"):
        context.check_root(outside)
    (vault / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExplorationError, match="symlink"):
        context.check_root(vault / "escape")


def test_test_environment_rechecks_registered_folders(tmp_path):
    vault, context = _context(tmp_path)
    outside = tmp_path / "other-vault"
    outside.mkdir()
    context.registry_path.parent.mkdir(parents=True)
    document = {"schema_version": 1, "sources": [], "folders": [
        {"folder_id": "selected", "root": str(vault), "capabilities": ["read"]},
    ]}
    context.registry_path.write_text(json.dumps(document))
    context.check_registry()
    before = context.registry_path.read_bytes()
    document["folders"].append({"folder_id": "outside", "root": str(outside)})
    context.registry_path.write_text(json.dumps(document))
    with pytest.raises(ExplorationError, match="test"):
        context.check_registry()
    assert context.registry_path.read_bytes() != before


def test_test_environment_rejects_registry_parent_symlink(tmp_path):
    _vault, context = _context(tmp_path)
    context.state_root.mkdir()
    outside = tmp_path / "other-state"
    outside.mkdir()
    (context.state_root / "hub").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExplorationError, match="symlink"):
        context.check_registry()


def test_public_environment_identity_contains_no_paths(tmp_path):
    vault, context = _context(tmp_path)
    info = context.public_info(vault)
    assert info["mode"] == "test"
    assert info["root_name"] == "test-vault"
    assert info["version"]
    assert str(tmp_path) not in json.dumps(info)


def test_personal_environment_can_connect_different_selected_vaults(tmp_path, monkeypatch):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("SCHOLAR_WORKFLOW_HOME", str(tmp_path / "personal-state"))
    context = ExplorerEnvironment()
    assert context.registry_path == tmp_path / "personal-state/hub/sources.json"
    assert context.check_root(first) == first
    assert context.check_root(second) == second
    assert not context.is_test
