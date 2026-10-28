"""Vault connection checks use selected synthetic directories and private state only."""
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from scholar_workflow.knowledge.exploration import ExplorationError
from scholar_workflow.knowledge.fields import FieldRegistryCommitUncertain, KnowledgeSourceRegistry
from scholar_workflow.workflows.vault_connections import VaultConnectionService


@pytest.fixture
def selected(tmp_path):
    vault = tmp_path / "selected"
    vault.mkdir()
    (vault / "Notes.md").write_text("# Notes\nHuman text.\n", encoding="utf-8")
    private = tmp_path / "private"

    def checked(path):
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_dir():
            raise ExplorationError("Selected root is unavailable", 7)
        if candidate != vault and vault not in candidate.parents:
            raise ExplorationError("Selected root is outside test scope", 7)
        return candidate

    env = SimpleNamespace(registry_path=private / "hub" / "sources.json", is_test=True,
                          check_root=checked)
    picker = SimpleNamespace(choose=lambda: vault)
    service = VaultConnectionService(env, picker=picker)
    return SimpleNamespace(root=vault, state=private, env=env, picker=picker, service=service)


def test_preview_does_not_write_or_invent_paper_identity(selected):
    report = selected.service.choose()
    assert report["can_connect"] is True
    assert report["layers"]["readable"]["status"] == "available"
    assert report["layers"]["referenceable"]["status"] == "needs-registration"
    assert report["documents"] == ["Notes.md"]
    assert report["fields"] == []
    assert not selected.state.exists()
    assert not (selected.root / ".scholar-workflow").exists()
    assert str(selected.root) not in str(report)


def test_plain_vault_connects_read_only_and_preserves_original(selected):
    original = (selected.root / "Notes.md").read_bytes()
    report = selected.service.choose()
    result = selected.service.connect(report["candidate_id"], report["revision"])
    assert result["status"] == "connected"
    document = KnowledgeSourceRegistry(selected.env.registry_path).load_document()
    assert len(document.folders) == 1
    assert document.folders[0].capabilities == ["read"]
    assert document.sources == []
    assert (selected.root / "Notes.md").read_bytes() == original
    assert not (selected.root / ".scholar-workflow").exists()
    assert str(selected.root) not in str(result)
    entries = selected.service.list_connections()["connections"]
    assert len(entries) == 1
    assert selected.service.documents(entries[0]["connection_id"])["documents"][0]["relative_path"] == "Notes.md"
    assert selected.service.preview_document(entries[0]["connection_id"], "Notes.md")["text"].endswith("Human text.\n")


def test_personal_mode_connects_multiple_selected_vaults_with_isolated_state(tmp_path):
    from scholar_workflow.knowledge.exploration_environment import ExplorerEnvironment

    first, second = tmp_path / "First Vault", tmp_path / "Second Vault"
    first.mkdir()
    second.mkdir()
    for root in (first, second):
        (root / "Notes.md").write_text("# Preserve original notes\n", encoding="utf-8")
    context = ExplorerEnvironment("personal", tmp_path / "personal-synthetic-state")
    picker = SimpleNamespace(choose=lambda: first)
    service = VaultConnectionService(context, picker)
    for root in (first, second):
        picker.choose = lambda root=root: root
        preview = service.choose()
        assert service.connect(preview["candidate_id"], preview["revision"])["status"] == "connected"
    document = KnowledgeSourceRegistry(context.registry_path).load_document()
    assert {folder.root for folder in document.folders} == {first, second}
    assert all(folder.capabilities == ["read"] for folder in document.folders)
    assert document.sources == []
    assert all((root / "Notes.md").read_text() == "# Preserve original notes\n" for root in (first, second))


def test_existing_manifest_attaches_identity_without_provider_initialization(selected):
    state = selected.root / ".scholar-workflow"
    state.mkdir()
    manifest = {"schema_version": 1, "source_id": "11111111-1111-4111-8111-111111111111",
                "fields": [{"field_id": "22222222-2222-4222-8222-222222222222",
                            "title": "Existing", "relative_root": ".", "home": "Notes.md", "navigation": []}]}
    path = state / "fields.yml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    original = path.read_bytes()
    report = selected.service.choose()
    assert report["fields"][0]["title"] == "Existing"
    result = selected.service.connect(report["candidate_id"], report["revision"])
    registry = KnowledgeSourceRegistry(selected.env.registry_path).load_document()
    assert registry.sources[0].source_id == manifest["source_id"]
    assert registry.sources[0].capabilities == ["read"]
    assert path.read_bytes() == original
    assert not (state / "knowledge-provider.snapshot.json").exists()
    assert result["connection"]["source_id"] == manifest["source_id"]


def test_old_format_is_local_diagnosis_not_read_blocker(selected):
    (selected.root / "Old.md").write_text("---\nsw_kind: paper-analysis\n---\nhttp://127.0.0.1:23128/open/paper/ABCD2345", encoding="utf-8")
    report = selected.service.choose()
    assert report["can_connect"] is True
    assert any(issue["code"] == "legacy-link" for issue in report["issues"])
    preview = selected.service.preview_adjustments(report["candidate_id"])
    assert preview["candidate_id"] == report["candidate_id"]
    assert any(change["path"] == "Old.md" for change in preview["changes"])
    assert not selected.state.exists()


def test_stale_registry_or_changed_content_rejects_connection(selected):
    report = selected.service.choose()
    (selected.root / "Notes.md").write_text("Changed", encoding="utf-8")
    with pytest.raises(ExplorationError, match="changed"):
        selected.service.connect(report["candidate_id"], report["revision"])
    assert not selected.state.exists()


def test_exact_repeat_reuses_existing_connection(selected):
    first = selected.service.choose()
    selected.service.connect(first["candidate_id"], first["revision"])
    original = selected.env.registry_path.read_bytes()
    again = selected.service.choose()
    assert selected.service.connect(again["candidate_id"], again["revision"])["status"] == "unchanged"
    assert selected.env.registry_path.read_bytes() == original


def test_symlink_assets_are_ignored_and_never_previewed(selected, tmp_path):
    (selected.root / "Escaped.md").symlink_to(tmp_path / "outside.md")
    report = selected.service.choose()
    assert "Escaped.md" not in report["documents"]
    result = selected.service.connect(report["candidate_id"], report["revision"])
    with pytest.raises(ExplorationError):
        selected.service.preview_document(result["connection"]["connection_id"], "Escaped.md")


def test_hidden_config_is_never_read_or_listed(selected):
    hidden = selected.root / ".obsidian"
    hidden.mkdir()
    (hidden / "secret.md").write_text("do not read", encoding="utf-8")
    report = selected.service.choose()
    assert report["documents"] == ["Notes.md"]
    assert "do not read" not in str(report)


def test_outside_test_root_is_rejected_before_inventory(selected, tmp_path):
    other = tmp_path / "outside"
    other.mkdir()
    selected.picker.choose = lambda: other
    with pytest.raises(ExplorationError):
        selected.service.choose()


def test_document_traversal_rejected(selected):
    report = selected.service.choose()
    result = selected.service.connect(report["candidate_id"], report["revision"])
    for relative in ("../outside.md", "/etc/passwd", ".obsidian/secret.md", "Notes.md/../Notes.md"):
        with pytest.raises(ExplorationError):
            selected.service.preview_document(result["connection"]["connection_id"], relative)


def test_root_swap_after_preview_is_rejected(selected):
    report = selected.service.choose()
    moved = selected.root.with_name("moved")
    selected.root.rename(moved)
    selected.root.mkdir()
    (selected.root / "Notes.md").write_text("Replacement", encoding="utf-8")
    with pytest.raises(ExplorationError, match="changed"):
        selected.service.connect(report["candidate_id"], report["revision"])


def test_invalid_manifest_does_not_prevent_read_only_connection(selected):
    state = selected.root / ".scholar-workflow"
    state.mkdir()
    (state / "fields.yml").write_text("invalid: manifest", encoding="utf-8")
    report = selected.service.choose()
    assert report["can_connect"] is True
    assert report["layers"]["referenceable"]["status"] == "needs-review"
    assert any(issue["code"] == "invalid-manifest" for issue in report["issues"])
    selected.service.connect(report["candidate_id"], report["revision"])
    assert KnowledgeSourceRegistry(selected.env.registry_path).load_document().sources == []


def test_uncertain_publication_is_recoverable_and_requires_fresh_inspection(selected, monkeypatch):
    report = selected.service.choose()
    original = selected.service.registry._save_locked

    def published_then_uncertain(*args, **kwargs):
        original(*args, **kwargs)
        raise FieldRegistryCommitUncertain("Synthetic post-publication durability failure")

    monkeypatch.setattr(selected.service.registry, "_save_locked", published_then_uncertain)
    with pytest.raises(ExplorationError, match="may have completed") as failure:
        selected.service.connect(report["candidate_id"], report["revision"])
    assert failure.value.code == 6
    assert report["candidate_id"] in selected.service._candidates
    assert len(selected.service.registry.load_document().folders) == 1
    with pytest.raises(ExplorationError, match="changed"):
        selected.service.connect(report["candidate_id"], report["revision"])
    fresh = selected.service.choose()
    assert selected.service.connect(fresh["candidate_id"], fresh["revision"])["status"] == "unchanged"
    assert (selected.root / "Notes.md").read_text(encoding="utf-8") == "# Notes\nHuman text.\n"
