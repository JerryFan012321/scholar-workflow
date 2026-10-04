from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from scholar_workflow.adapters.obsidian_registry import (
    ZotFlowError,
    resolve_obsidian_reader,
    resolve_obsidian_vault_id,
)
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import (
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.workflows.knowledge_open import open_document

VAULT_ID = "1111111111111111"
SOURCE_ID = "11111111-1111-4111-8111-111111111111"


def fixture(tmp_path: Path):
    vault = tmp_path / "Vault"
    source = vault / "Chosen Field"
    source.mkdir(parents=True)
    (source / "Analysis #1.md").write_text("# Analysis\n")
    (source / "Tree.canvas").write_text('{"nodes":[],"edges":[]}')
    config = tmp_path / "obsidian.json"
    config.write_text(json.dumps({"vaults": {VAULT_ID: {"path": str(vault)}}}))
    registry = KnowledgeSourceRegistry(tmp_path / "state/hub/sources.json")
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(folder_id="selected", root=source, capabilities=["read"])],
        sources=[KnowledgeSourceRegistration(source_id=SOURCE_ID, folder_id="selected")],
    ))
    return vault, source, config, registry


def test_subdirectory_reader_does_not_become_file_authority(tmp_path: Path):
    vault, source, config, registry = fixture(tmp_path)
    binding = resolve_obsidian_reader(source, config_path=config)
    assert binding.vault_id == VAULT_ID
    assert binding.vault_root == vault
    assert binding.source_root == source
    assert registry.resolve(SOURCE_ID, capability="read") == source
    with pytest.raises(RuntimeError):
        registry.resolve(SOURCE_ID, capability="write")
    with pytest.raises(ZotFlowError, match="missing or ambiguous"):
        resolve_obsidian_vault_id(source, config_path=config)
    assert resolve_obsidian_vault_id(vault, config_path=config) == VAULT_ID


@pytest.mark.parametrize("kind", ["missing", "duplicate", "nested", "symlink", "permissions", "fifo"])
def test_unsafe_or_ambiguous_reader_refuses(tmp_path: Path, kind: str):
    vault, source, config, _registry = fixture(tmp_path)
    if kind == "missing":
        config.write_text('{"vaults":{}}')
    elif kind in {"duplicate", "nested"}:
        config.write_text(json.dumps({"vaults": {
            VAULT_ID: {"path": str(vault)},
            "2222222222222222": {"path": str(vault if kind == "duplicate" else source)},
        }}))
    elif kind == "symlink":
        config.unlink()
        config.symlink_to(source / "Analysis #1.md")
    elif kind == "permissions":
        config.chmod(0o666)
    else:
        import os
        config.unlink()
        os.mkfifo(config)
    with pytest.raises(ZotFlowError):
        resolve_obsidian_reader(source, config_path=config)


@pytest.mark.parametrize("name", ["Analysis #1.md", "Tree.canvas"])
def test_native_open_is_encoded_read_only_and_scoped(tmp_path: Path, name: str):
    vault, source, config, registry = fixture(tmp_path)
    before = registry.path.read_bytes(), (source / name).read_bytes()
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        assert kwargs["shell"] is False
        return SimpleNamespace(returncode=0, stderr="")

    result = open_document(registry, SOURCE_ID, name, config_path=config, runner=runner)
    assert result["status"] == "open-requested"
    assert result["source_relative_path"] == name
    assert result["human_assessment"] == "pending"
    query = parse_qs(urlsplit(calls[0][1]).query)
    assert "Chosen%20Field%2F" in calls[0][1]
    assert "+" not in calls[0][1]
    assert calls[0][0] == "/usr/bin/open"
    assert query == {"vault": [VAULT_ID], "file": [f"Chosen Field/{name}"]}
    assert registry.path.read_bytes() == before[0]
    assert (source / name).read_bytes() == before[1]
    assert registry.resolve(SOURCE_ID, capability="read") != vault


@pytest.mark.parametrize("name", ["../Outside.md", "/Outside.md", "a/../b.md", "a\\b.md",
                                 ".obsidian/settings.md", "missing.md", "", "Chosen Field",
                                 "analysis.baseline.json", "https://example.com/x.md"])
def test_invalid_open_never_launches(tmp_path: Path, name: str):
    _vault, _source, config, registry = fixture(tmp_path)
    calls = []
    with pytest.raises((ValueError, RuntimeError)):
        open_document(registry, SOURCE_ID, name, config_path=config,
                      runner=lambda *args, **kwargs: calls.append(args))
    assert not calls


def test_symlink_open_refuses(tmp_path: Path):
    vault, source, config, registry = fixture(tmp_path)
    (vault / "Outside.md").write_text("outside")
    (source / "Escape.md").symlink_to(vault / "Outside.md")
    with pytest.raises(RuntimeError):
        open_document(registry, SOURCE_ID, "Escape.md", config_path=config)


def test_symlink_directory_open_refuses(tmp_path: Path):
    vault, source, config, registry = fixture(tmp_path)
    (vault / "Outside.md").write_text("outside")
    (source / "linked").symlink_to(vault, target_is_directory=True)
    with pytest.raises(RuntimeError):
        open_document(registry, SOURCE_ID, "linked/Outside.md", config_path=config)


@pytest.mark.parametrize("change", ["source-disabled", "read-revoked"])
def test_disabled_or_unreadable_source_refuses(tmp_path: Path, change: str):
    _vault, _source, config, registry = fixture(tmp_path)
    document = registry.load_document()
    if change == "source-disabled":
        document.sources[0].enabled = False
    else:
        document.folders[0].capabilities = ["write"]
    registry.save(document)
    with pytest.raises(RuntimeError):
        open_document(registry, SOURCE_ID, "Tree.canvas", config_path=config)


def test_unregistered_source_refuses(tmp_path: Path):
    _vault, _source, config, registry = fixture(tmp_path)
    with pytest.raises(RuntimeError):
        open_document(registry, "22222222-2222-4222-8222-222222222222", "Tree.canvas",
                      config_path=config)


def test_cli_reader_and_open_use_existing_authority(tmp_path: Path, monkeypatch):
    _vault, source, config, registry = fixture(tmp_path)
    import scholar_workflow.adapters.obsidian_registry as identity
    import scholar_workflow.workflows.knowledge_open as opening

    original = identity.resolve_obsidian_reader
    monkeypatch.setattr(opening, "resolve_obsidian_reader",
                        lambda root: original(root, config_path=config))
    calls = []
    monkeypatch.setattr(opening.subprocess, "run",
                        lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0))
    runner = CliRunner()
    env = {"SCHOLAR_WORKFLOW_HOME": str(registry.path.parent.parent)}
    result = runner.invoke(main, ["knowledge", "reader", SOURCE_ID, "--format", "json"], env=env)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["source_root"] == str(source)
    assert not calls
    result = runner.invoke(main, ["knowledge", "open", SOURCE_ID, "Tree.canvas", "--language", "zh"], env=env)
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert "待人工" in result.output
