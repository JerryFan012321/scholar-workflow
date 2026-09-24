from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import yaml

import scholar_workflow.hub.field_migration as migration_module
from scholar_workflow.adapters.zotero_local import (
    ZoteroAttachmentLocator,
    ZoteroLocalError,
)
from scholar_workflow.hub.field_migration import (
    FieldMigrationError,
    FieldMigrationService,
    ZoteroPdfLinkResolver,
)
from scholar_workflow.hub.fields import FieldService, KnowledgeSourceRegistry

_OLD = "http://127.0.0.1:23128/open/paper/ABCD2345"
_NEW = "zotero://open-pdf/library/items/ABCD2345"


def _fixture_pdf(key: str) -> str:
    assert key == "ABCD2345"
    return _NEW


class _FakeZotero:
    def __init__(self, item: dict | None, *, error: str | None = None) -> None:
        self.item = item
        self.error = error
        self.locator_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get_item(self, _key: str) -> dict:
        if self.error:
            raise ZoteroLocalError(self.error)
        assert self.item is not None
        return self.item

    def resolve_attachment_locator(self, key: str) -> ZoteroAttachmentLocator:
        self.locator_calls += 1
        return ZoteroAttachmentLocator(
            attachment_key=key,
            library_id="7",
            content_hash="sha256:fixture",
            path=Path("/fixture.pdf"),
            filename="fixture.pdf",
        )


def _zotero_item(**data_overrides: str) -> dict:
    data = {
        "key": "ABCD2345",
        "itemType": "attachment",
        "contentType": "application/pdf",
        "linkMode": "imported_file",
    }
    data.update(data_overrides)
    return {
        "key": "ABCD2345",
        "library": {"type": "user", "id": 7},
        "data": data,
    }


def test_zotero_link_resolver_requires_user_pdf_and_live_locator() -> None:
    adapter = _FakeZotero(_zotero_item())
    resolver = ZoteroPdfLinkResolver(adapter_factory=lambda: adapter)
    assert resolver("ABCD2345") == _NEW
    assert adapter.locator_calls == 1


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({**_zotero_item(), "library": {"type": "group", "id": 7}}, "user library"),
        (_zotero_item(itemType="journalArticle"), "not an attachment"),
        (_zotero_item(contentType="text/html"), "not a confirmed PDF"),
        (_zotero_item(linkMode="linked_url"), "link mode is unsupported"),
        ({**_zotero_item(), "key": "ZZZZ2345"}, "identity does not match"),
    ],
)
def test_zotero_link_resolver_rejects_unsupported_item_without_locator(
    item: dict, expected: str
) -> None:
    adapter = _FakeZotero(item)
    with pytest.raises(FieldMigrationError, match=expected):
        ZoteroPdfLinkResolver(adapter_factory=lambda: adapter)("ABCD2345")
    assert adapter.locator_calls == 0


def test_zotero_link_resolver_rejects_missing_item() -> None:
    adapter = _FakeZotero(None, error="HTTP 404")
    with pytest.raises(FieldMigrationError, match="HTTP 404"):
        ZoteroPdfLinkResolver(adapter_factory=lambda: adapter)("ABCD2345")
    assert adapter.locator_calls == 0


def _registered_vault(tmp_path: Path) -> tuple[Path, KnowledgeSourceRegistry, str, str]:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    world = vault / "世界模型"
    world.mkdir()
    (world / "00-领域入口.md").write_text(
        f"# World Models\n\n[paper]({_OLD})\n\nPreserved prose.\n",
        encoding="utf-8",
    )
    (world / "JEPA.md").write_text(f"JEPA {_OLD}\n", encoding="utf-8")
    other = vault / "3DGS"
    other.mkdir()
    (other / "00-领域入口.md").write_text(f"# Sibling\n\n{_OLD}\n", encoding="utf-8")
    (vault / "unmapped-top.md").write_text(f"# Outside\n\n{_OLD}\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "state" / "sources.json")
    service = FieldService(registry)
    world_preview = service.preview(vault)
    world_candidate = next(row for row in world_preview.fields if row.title == "世界模型")
    service.confirm(world_preview.candidate_token, world_candidate.field_id)
    other_preview = service.preview(vault)
    other_candidate = next(row for row in other_preview.fields if row.title == "3DGS")
    manifest = service.confirm(other_preview.candidate_token, other_candidate.field_id)
    world_id = next(row.field_id for row in manifest.fields if row.title == "世界模型")
    other_id = next(row.field_id for row in manifest.fields if row.title == "3DGS")
    return vault, registry, world_id, other_id


def test_field_migration_plan_is_read_only_then_replaces_only_managed_links(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    (world / "unmapped.md").write_text("Do not change this prose.\n", encoding="utf-8")
    (world / "tree.canvas").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "0123456789abcdef",
                        "type": "link",
                        "x": 0,
                        "y": 0,
                        "width": 300,
                        "height": 150,
                        "url": _OLD,
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    world_entry = next(row for row in manifest["fields"] if row["field_id"] == world_id)
    world_entry["navigation"][1]["items"].append("tree.canvas")
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    recovery_root = tmp_path / "recovery-state"
    migrator = FieldMigrationService(
        registry, state_root=recovery_root, link_resolver=_fixture_pdf
    )
    before_world = (world / "00-领域入口.md").read_bytes()
    before_sibling = (vault / "3DGS" / "00-领域入口.md").read_bytes()
    before_outside = (vault / "unmapped-top.md").read_bytes()

    plan = migrator.plan(manifest["source_id"], world_id)

    assert not recovery_root.exists()
    assert (world / "00-领域入口.md").read_bytes() == before_world
    assert plan.conflicts == ()
    assert plan.template_normalization == "manual-review-required"
    assert plan.unmapped_files == ("unmapped.md",)
    assert sum(change.occurrences for change in plan.link_changes) == 3
    assert set(plan.managed_files) == {"00-领域入口.md", "JEPA.md", "tree.canvas"}
    with pytest.raises(FieldMigrationError, match="not approved"):
        migrator.apply(plan.plan_token, approved_digest="wrong digest")

    plan = migrator.plan(manifest["source_id"], world_id)
    result = migrator.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert result.changed_files == ("00-领域入口.md", "JEPA.md", "tree.canvas")
    assert result.replaced_links == 3
    assert result.recovery_is_verified_backup is False
    assert (world / "00-领域入口.md").read_text(encoding="utf-8") == (
        "# World Models\n\n[paper](" + _NEW + ")\n\nPreserved prose.\n"
    )
    assert (
        json.loads((world / "tree.canvas").read_text(encoding="utf-8"))["nodes"][0]["url"] == _NEW
    )
    assert (world / "unmapped.md").read_text(encoding="utf-8") == ("Do not change this prose.\n")
    assert (vault / "3DGS" / "00-领域入口.md").read_bytes() == before_sibling
    assert (vault / "unmapped-top.md").read_bytes() == before_outside
    with zipfile.ZipFile(result.recovery_snapshot) as bundle:
        metadata = json.loads(bundle.read("recovery.json"))
        assert metadata["verified_backup"] is False
        assert bundle.read("original/世界模型/00-领域入口.md") == before_world
        assert "original/3DGS/00-领域入口.md" not in bundle.namelist()


def test_field_migration_refuses_concurrent_edit_without_snapshot(tmp_path: Path) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id
    plan = service.plan(source_id, world_id)
    document = vault / "世界模型" / "JEPA.md"
    document.write_text("New user edit\n", encoding="utf-8")

    with pytest.raises(FieldMigrationError, match="changed after preview"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert document.read_text(encoding="utf-8") == "New user edit\n"
    assert not (tmp_path / "recovery").exists()


def test_field_migration_blocks_legacy_links_in_unmapped_field_files(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    orphan = world / "unmapped.md"
    orphan.write_text(f"Unmapped {_OLD}\n", encoding="utf-8")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert plan.unmapped_files == ("unmapped.md",)
    assert len(plan.unresolved_legacy_links) == 1
    assert plan.unresolved_legacy_links[0].relative_path == "unmapped.md"
    assert any("Unmapped Field files still contain" in item for item in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert orphan.read_text(encoding="utf-8") == f"Unmapped {_OLD}\n"
    assert not (tmp_path / "recovery").exists()


def test_field_migration_rolls_back_only_selected_field_after_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id
    plan = service.plan(source_id, world_id)
    home = vault / "世界模型" / "00-领域入口.md"
    jepa = vault / "世界模型" / "JEPA.md"
    sibling = vault / "3DGS" / "00-领域入口.md"
    originals = (home.read_bytes(), jepa.read_bytes(), sibling.read_bytes())
    original_replace = migration_module._replace_at
    calls = 0

    def fail_once_on_second(source: str, destination: str, parent_fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second-file failure")
        original_replace(source, destination, parent_fd)

    monkeypatch.setattr(migration_module, "_replace_at", fail_once_on_second)

    with pytest.raises(FieldMigrationError, match="rolled back"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert (home.read_bytes(), jepa.read_bytes(), sibling.read_bytes()) == originals
    snapshots = list((tmp_path / "recovery").rglob("*.zip"))
    assert len(snapshots) == 1


def test_field_migration_does_not_rewrite_sibling_field(tmp_path: Path) -> None:
    vault, registry, world_id, other_id = _registered_vault(tmp_path)
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id
    sibling = vault / "3DGS" / "00-领域入口.md"
    sibling_before = sibling.read_bytes()
    plan = service.plan(source_id, world_id)

    assert all("3DGS" not in change.relative_path for change in plan.link_changes)
    assert other_id != world_id
    service.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert sibling.read_bytes() == sibling_before
    assert _OLD in sibling.read_text(encoding="utf-8")


def test_field_migration_rejects_recovery_directory_inside_vault_without_creating_it(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    recovery = vault / "unregistered-recovery"
    service = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)
    source_id = FieldService._load_manifest(vault).source_id
    plan = service.plan(source_id, world_id)

    with pytest.raises(FieldMigrationError, match="outside the Vault"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert not recovery.exists()
    assert _OLD in (vault / "世界模型" / "00-领域入口.md").read_text(encoding="utf-8")


def test_field_migration_checks_each_distinct_key_once_and_blocks_unverified_key(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    calls: list[str] = []

    def offline(key: str) -> str:
        calls.append(key)
        raise FieldMigrationError("Zotero Local API is unavailable")

    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=offline
    )
    source_id = FieldService._load_manifest(vault).source_id
    plan = service.plan(source_id, world_id)

    assert calls == ["ABCD2345"]
    assert any("ABCD2345" in conflict and "unavailable" in conflict for conflict in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert not (tmp_path / "recovery").exists()


def test_field_migration_reverifies_zotero_before_creating_snapshot(tmp_path: Path) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    calls = 0

    def available_then_offline(key: str) -> str:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise FieldMigrationError("Zotero Local API is unavailable")
        return _fixture_pdf(key)

    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=available_then_offline
    )
    plan = service.plan(source_id, world_id)
    assert not plan.conflicts

    with pytest.raises(FieldMigrationError, match="cannot be reverified"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert calls == 2
    assert not (tmp_path / "recovery").exists()
    assert _OLD in (vault / "世界模型" / "JEPA.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "legacy_url",
    [
        _OLD + "/",
        "http://127.0.0.1:23128/hub/item?key=ABCD2345",
        "http://localhost:23128/open/paper/ABCD2345",
        "http://[::1]:23128/open/paper/ABCD2345",
    ],
)
def test_field_migration_rejects_unknown_old_hub_url_shapes(
    tmp_path: Path, legacy_url: str
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    document = vault / "世界模型" / "JEPA.md"
    document.write_text(f"Legacy {legacy_url}\n", encoding="utf-8")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert any("unrecognized legacy Hub URL in managed file" in item for item in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert document.read_text(encoding="utf-8") == f"Legacy {legacy_url}\n"
    assert not (tmp_path / "recovery").exists()


def test_field_migration_detects_json_escaped_old_hub_url(tmp_path: Path) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    canvas = world / "tree.canvas"
    canvas.write_text(
        '{"nodes":[{"id":"n","type":"link","x":0,"y":0,"width":200,'
        '"height":100,"url":"http:\\/\\/127\\u002e0\\u002e0\\u002e1:23128/'
        'open/paper/ABCD2345"}],"edges":[]}',
        encoding="utf-8",
    )
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    world_entry = next(row for row in manifest["fields"] if row["field_id"] == world_id)
    world_entry["navigation"][1]["items"].append("tree.canvas")
    manifest_path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert any("unrecognized legacy Hub URL in managed file: tree.canvas" in item
               for item in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)


def test_field_migration_fails_closed_when_inventory_cannot_be_walked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    def failing_walk(_top, *, followlinks, onerror):
        assert followlinks is False
        onerror(PermissionError("injected unreadable directory"))
        yield from ()

    monkeypatch.setattr(migration_module.os, "walk", failing_walk)
    with pytest.raises(FieldMigrationError, match="directory traversal failed"):
        service.plan(source_id, world_id)
    assert not (tmp_path / "recovery").exists()


@pytest.mark.parametrize("suffix", [".txt", ".html", ".json", ".yml", ".yaml", ".ipynb"])
def test_field_migration_checks_unmanaged_text_files_for_old_hub_urls(
    tmp_path: Path, suffix: str
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    extra = vault / "世界模型" / f"notes{suffix}"
    if suffix in {".json", ".ipynb"}:
        extra.write_text(json.dumps({"source": [_OLD]}), encoding="utf-8")
    else:
        extra.write_text(f"reference: {_OLD}\n", encoding="utf-8")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert f"notes{suffix}" in plan.unmapped_files
    assert any("Unmapped Field files still contain" in item for item in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)
    assert extra.exists()
    assert not (tmp_path / "recovery").exists()


def test_field_migration_rejects_unreadable_text_but_ignores_binary_attachments(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    (world / "figure.png").write_bytes(b"\x89PNG\r\n" + _OLD.encode())
    unreadable = world / "notes.txt"
    unreadable.write_bytes(b"\xff\xfe\x00")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    with pytest.raises(FieldMigrationError, match="not UTF-8"):
        service.plan(source_id, world_id)
    assert not (tmp_path / "recovery").exists()

    unreadable.unlink()
    plan = service.plan(source_id, world_id)
    assert plan.conflicts == ()
    assert "figure.png" not in plan.unmapped_files


def test_field_migration_ignores_other_fields_and_hidden_state_text(tmp_path: Path) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    (world / ".obsidian").mkdir()
    (world / ".obsidian" / "legacy.txt").write_text(_OLD, encoding="utf-8")
    (vault / "3DGS" / "legacy.txt").write_text(_OLD, encoding="utf-8")
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert plan.conflicts == ()
    assert "legacy.txt" not in plan.unmapped_files
