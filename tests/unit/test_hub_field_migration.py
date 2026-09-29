from __future__ import annotations

import json
import os
import stat
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
from scholar_workflow.hub.fields import FieldRegistryError, FieldService, KnowledgeSourceRegistry

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
    manifest = FieldService._load_manifest(vault)
    recovery_root = tmp_path / "recovery-state"
    migrator = FieldMigrationService(
        registry, state_root=recovery_root, link_resolver=_fixture_pdf
    )
    before_world = (world / "00-领域入口.md").read_bytes()
    before_sibling = (vault / "3DGS" / "00-领域入口.md").read_bytes()
    before_outside = (vault / "unmapped-top.md").read_bytes()

    plan = migrator.plan(manifest.source_id, world_id)

    assert not recovery_root.exists()
    assert (world / "00-领域入口.md").read_bytes() == before_world
    assert plan.conflicts == ()
    assert plan.template_normalization == "manual-review-required"
    assert plan.unmapped_files == ("unmapped.md",)
    assert sum(change.occurrences for change in plan.link_changes) == 2
    assert set(plan.managed_files) == {"00-领域入口.md", "JEPA.md"}
    with pytest.raises(FieldMigrationError, match="not approved"):
        migrator.apply(
            plan.plan_token, approved_digest="wrong digest", external_writers_paused=True
        )

    plan = migrator.plan(manifest.source_id, world_id)
    result = migrator.apply(
        plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
    )

    assert result.changed_files == ("00-领域入口.md", "JEPA.md")
    assert result.replaced_links == 2
    assert result.recovery_is_verified_backup is False
    assert (world / "00-领域入口.md").read_text(encoding="utf-8") == (
        "# World Models\n\n[paper](" + _NEW + ")\n\nPreserved prose.\n"
    )
    assert (world / "unmapped.md").read_text(encoding="utf-8") == ("Do not change this prose.\n")
    assert (vault / "3DGS" / "00-领域入口.md").read_bytes() == before_sibling
    assert (vault / "unmapped-top.md").read_bytes() == before_outside
    with zipfile.ZipFile(result.recovery_snapshot) as bundle:
        metadata = json.loads(bundle.read("recovery.json"))
        assert metadata["verified_backup"] is False
        assert bundle.read("original/世界模型/00-领域入口.md") == before_world
        assert "original/3DGS/00-领域入口.md" not in bundle.namelist()


def test_field_migration_service_requires_writer_pause_assertion(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    recovery = tmp_path / "recovery-state"
    service = FieldMigrationService(
        registry, state_root=recovery, link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id
    plan = service.plan(source_id, world_id)
    home = vault / "世界模型" / "00-领域入口.md"
    before = home.read_bytes()

    with pytest.raises(FieldMigrationError, match="writers must be paused"):
        service.apply(plan.plan_token, approved_digest=plan.plan_digest)

    assert home.read_bytes() == before
    assert not recovery.exists()
    result = service.apply(
        plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
    )
    assert "00-领域入口.md" in result.changed_files


@pytest.mark.parametrize("analysis_identity", ["marker", "sidecar", "canvas", "canonical"])
def test_field_migration_refuses_to_split_analysis_pair(
    tmp_path: Path, analysis_identity: str
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    world = vault / "世界模型"
    analysis = world / "JEPA.md"
    if analysis_identity == "marker":
        analysis.write_text(
            f"---\nsw_kind: paper-analysis\n---\n# JEPA\n{_OLD}\n",
            encoding="utf-8",
        )
    elif analysis_identity == "sidecar":
        (world / "JEPA.analysis.json").write_text("{}", encoding="utf-8")
    elif analysis_identity == "canvas":
        (world / "JEPA.canvas").write_text(
            '{"nodes": [], "edges": []}', encoding="utf-8"
        )
    else:
        analysis = analysis.rename(world / "JEPA分析.md")
        (world / "JEPA解析树.canvas").write_text(
            '{"nodes": [], "edges": []}', encoding="utf-8"
        )
        manifest_path = vault / ".scholar-workflow" / "fields.yml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        world_entry = next(row for row in manifest["fields"] if row["field_id"] == world_id)
        for group in world_entry["navigation"]:
            group["items"] = [
                "JEPA分析.md" if name == "JEPA.md" else name for name in group["items"]
            ]
        manifest_path.write_text(
            yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
        )
    original = analysis.read_bytes()
    home = (world / "00-领域入口.md").read_bytes()
    recovery_root = tmp_path / "recovery-state"
    migrator = FieldMigrationService(
        registry, state_root=recovery_root, link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = migrator.plan(source_id, world_id)

    assert any(
        "validated Field transaction" in conflict and analysis.name in conflict
        for conflict in plan.conflicts
    )
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        migrator.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
    assert analysis.read_bytes() == original
    assert (world / "00-领域入口.md").read_bytes() == home
    assert not recovery_root.exists()


def test_field_migration_rejects_canvas_rewrite_with_markdown_peer(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    canvas = vault / "世界模型" / "JEPA.canvas"
    canvas.write_text(
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
    source_id = FieldService._load_manifest(vault).source_id
    migrator = FieldMigrationService(
        registry, state_root=tmp_path / "recovery-state", link_resolver=_fixture_pdf
    )

    plan = migrator.plan(source_id, world_id)

    assert "JEPA.canvas" in plan.unmapped_files
    assert any(change.relative_path == "JEPA.canvas" for change in plan.unresolved_legacy_links)
    assert any(
        "Unmapped Field files still contain legacy paper links" in conflict
        for conflict in plan.conflicts
    )


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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )

    assert document.read_text(encoding="utf-8") == "New user edit\n"
    assert not (tmp_path / "recovery").exists()


def test_field_migration_closes_root_fd_if_field_directory_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id
    original_open = migration_module._open_directory_chain
    root_fds: list[int] = []

    def fail_field_open(root: Path, parts: tuple[str, ...] = ()) -> int:
        if parts:
            raise OSError("injected Field directory failure")
        descriptor = original_open(root, parts)
        root_fds.append(descriptor)
        return descriptor

    monkeypatch.setattr(migration_module, "_open_directory_chain", fail_field_open)
    with pytest.raises(FieldMigrationError, match="Field root is unavailable"):
        service._resolve(source_id, world_id, capability="read")

    assert len(root_fds) == 1
    with pytest.raises(OSError):
        os.fstat(root_fds[0])


def test_field_migration_closes_new_recovery_directory_fd_on_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    plan = service.plan(source_id, world_id)
    home = vault / "世界模型" / "00-领域入口.md"
    before = home.read_bytes()
    real_open = migration_module.os.open
    real_fsync = migration_module.os.fsync
    child_fds: list[int] = []
    fsync_calls = 0

    def track_open(path, *args, **kwargs) -> int:
        descriptor = real_open(path, *args, **kwargs)
        if path == "field-recovery":
            child_fds.append(descriptor)
        return descriptor

    def fail_second_fsync(descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("injected recovery-parent fsync failure")
        real_fsync(descriptor)

    with monkeypatch.context() as patcher:
        patcher.setattr(migration_module.os, "open", track_open)
        patcher.setattr(migration_module.os, "fsync", fail_second_fsync)
        with pytest.raises(FieldMigrationError, match="recovery directory is unsafe"):
            service.apply(
                plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
            )

    assert child_fds
    for descriptor in child_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert home.read_bytes() == before


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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )

    assert (home.read_bytes(), jepa.read_bytes(), sibling.read_bytes()) == originals
    snapshots = list((tmp_path / "recovery").rglob("*.zip"))
    assert len(snapshots) == 1


def _interrupt_after_replace(
    registry: KnowledgeSourceRegistry,
    recovery: Path,
    source_id: str,
    field_id: str,
    *,
    after: int = 1,
) -> None:
    """Simulate a hard process stop, bypassing Python's exception rollback."""
    child = os.fork()
    if child == 0:
        try:
            service = FieldMigrationService(
                registry, state_root=recovery, link_resolver=_fixture_pdf
            )
            plan = service.plan(source_id, field_id)
            original_replace = migration_module._replace_at
            calls = 0

            def stop_after_replace(source: str, destination: str, parent_fd: int) -> None:
                nonlocal calls
                original_replace(source, destination, parent_fd)
                calls += 1
                if calls == after:
                    os._exit(75)

            migration_module._replace_at = stop_after_replace
            service.apply(
                plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
            )
        except (AssertionError, FieldMigrationError, OSError):
            os._exit(97)
        os._exit(98)
    _pid, status = os.waitpid(child, 0)
    assert os.WIFEXITED(status)
    assert os.WEXITSTATUS(status) == 75


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovers_after_process_stops_between_replaces(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    jepa = vault / "世界模型" / "JEPA.md"
    sibling = vault / "3DGS" / "00-领域入口.md"
    originals = (home.read_bytes(), jepa.read_bytes(), sibling.read_bytes())
    _interrupt_after_replace(registry, recovery, source_id, world_id)

    assert _NEW in home.read_text(encoding="utf-8")
    assert jepa.read_bytes() == originals[1]
    assert sibling.read_bytes() == originals[2]
    assert len(list(recovery.rglob("pending.json"))) == 1
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)
    with pytest.raises(FieldMigrationError, match="run recover"):
        restarted.plan(source_id, world_id)

    result = restarted.recover(source_id, world_id)

    assert result.recovered_files == ("世界模型/00-领域入口.md",)
    assert result.recovery_is_verified_backup is False
    assert (home.read_bytes(), jepa.read_bytes(), sibling.read_bytes()) == originals
    assert list(recovery.rglob("pending.json")) == []
    assert restarted.recover(source_id, world_id).recovered_files == ()
    assert restarted.plan(source_id, world_id).conflicts == ()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_refuses_external_edit_without_overwrite(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    jepa = vault / "世界模型" / "JEPA.md"
    sibling = vault / "3DGS" / "00-领域入口.md"
    jepa_before, sibling_before = jepa.read_bytes(), sibling.read_bytes()
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    home.write_text("External edit after crash\n", encoding="utf-8")
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="external edit"):
        restarted.recover(source_id, world_id)

    assert home.read_text(encoding="utf-8") == "External edit after crash\n"
    assert jepa.read_bytes() == jepa_before
    assert sibling.read_bytes() == sibling_before
    assert len(list(recovery.rglob("pending.json"))) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_rechecks_write_capability_under_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    before = home.read_bytes()
    original_resolve = registry.resolve
    calls = 0

    def revoke_on_second(source: str, *, capability: str) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FieldRegistryError("write permission revoked")
        return original_resolve(source, capability=capability)

    monkeypatch.setattr(registry, "resolve", revoke_on_second)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="registered Field source is unavailable"):
        restarted.recover(source_id, world_id)

    assert calls == 2
    assert home.read_bytes() == before
    assert len(list(recovery.rglob("pending.json"))) == 1


def test_field_migration_verifies_target_bytes_after_legacy_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    home = vault / "世界模型" / "00-领域入口.md"
    sibling = vault / "3DGS" / "00-领域入口.md"
    sibling_before = sibling.read_bytes()
    original_scan = FieldMigrationService._remaining_legacy_links

    def alter_after_scan(root: Path, manifest, field) -> tuple[str, ...]:
        remaining = original_scan(root, manifest, field)
        home.write_text("External replacement without an old URL\n", encoding="utf-8")
        return remaining

    monkeypatch.setattr(
        FieldMigrationService, "_remaining_legacy_links", staticmethod(alter_after_scan)
    )
    plan = service.plan(source_id, world_id)

    with pytest.raises(FieldMigrationError, match="conditional rollback incomplete"):
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )

    assert home.read_text(encoding="utf-8") == "External replacement without an old URL\n"
    assert sibling.read_bytes() == sibling_before
    assert len(list((tmp_path / "recovery").rglob("pending.json"))) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_refuses_corrupt_snapshot_before_writes(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    before = home.read_bytes()
    snapshot = next(recovery.rglob("*.zip"))
    snapshot.write_bytes(b"corrupt")
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="snapshot is invalid"):
        restarted.recover(source_id, world_id)

    assert home.read_bytes() == before
    assert len(list(recovery.rglob("pending.json"))) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("snapshot_name", 7, "journal is invalid"),
        ("temporary_name", 7, "unsafe file entry"),
        ("old_hash", 7, "unsafe file entry"),
        ("new_hash", 7, "unsafe file entry"),
    ],
)
def test_field_migration_recovery_rejects_wrong_journal_types_without_writes(
    tmp_path: Path, field: str, value: int, expected: str
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    before = home.read_bytes()
    journal = next(recovery.rglob("pending.json"))
    payload = json.loads(journal.read_text(encoding="utf-8"))
    if field in {"temporary_name", "old_hash", "new_hash"}:
        payload["files"][0][field] = value
    else:
        payload[field] = value
    journal.write_text(json.dumps(payload), encoding="utf-8")
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match=expected):
        restarted.recover(source_id, world_id)

    assert home.read_bytes() == before
    assert journal.exists()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_rejects_non_object_receipt_without_writes(
    tmp_path: Path,
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    before = home.read_bytes()
    snapshot = next(recovery.rglob("*.zip"))
    with zipfile.ZipFile(snapshot) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["recovery.json"] = b"[]"
    with zipfile.ZipFile(snapshot, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="receipt is invalid"):
        restarted.recover(source_id, world_id)

    assert home.read_bytes() == before
    assert len(list(recovery.rglob("pending.json"))) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_reports_uncertain_fsync_after_journal_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    original = home.read_bytes()
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    journal = next(recovery.rglob("pending.json"))
    real_fsync = migration_module.os.fsync

    def fail_after_journal_unlink(descriptor: int) -> None:
        if not journal.exists():
            raise OSError("injected final directory fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(migration_module.os, "fsync", fail_after_journal_unlink)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="finalization uncertain after unlink"):
        restarted.recover(source_id, world_id)

    assert home.read_bytes() == original
    assert not journal.exists()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_checks_original_mode_before_clearing_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    original_mode = stat.S_IMODE(home.stat().st_mode)
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    original_replace = migration_module._replace_at
    changed_mode = 0o600 if original_mode != 0o600 else 0o644

    def change_mode_after_restore(source: str, destination: str, parent_fd: int) -> None:
        original_replace(source, destination, parent_fd)
        os.chmod(home, changed_mode)

    monkeypatch.setattr(migration_module, "_replace_at", change_mode_after_restore)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)

    with pytest.raises(FieldMigrationError, match="recovery verification failed"):
        restarted.recover(source_id, world_id)

    assert stat.S_IMODE(home.stat().st_mode) == changed_mode
    assert len(list(recovery.rglob("pending.json"))) == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_temp_cleanup_failure_closes_fd_and_keeps_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    _interrupt_after_replace(registry, recovery, source_id, world_id)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)
    real_unlink = migration_module.os.unlink
    real_write_temp = FieldMigrationService._write_temp
    restore_fds: list[int] = []

    def track_restore_temp(parent_fd: int, name: str, content: bytes, mode: int) -> None:
        if name.startswith(".scholar-restore-"):
            restore_fds.append(parent_fd)
        real_write_temp(parent_fd, name, content, mode)

    def fail_restore_unlink(path, *args, **kwargs) -> None:
        if isinstance(path, str) and path.startswith(".scholar-restore-"):
            raise OSError("injected restore-temp cleanup failure")
        real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(FieldMigrationService, "_write_temp", staticmethod(track_restore_temp))
        patcher.setattr(migration_module.os, "unlink", fail_restore_unlink)
        with pytest.raises(FieldMigrationError, match="restore temp cleanup failed; journal retained"):
            restarted.recover(source_id, world_id)

    assert restore_fds
    for descriptor in restore_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert len(list(recovery.rglob("pending.json"))) == 1
    assert restarted.recover(source_id, world_id).recovered_files == ()


def test_field_migration_apply_cleanup_failure_closes_all_fds_without_success_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    plan = service.plan(source_id, world_id)
    real_write_temp = FieldMigrationService._write_temp
    real_open_recovery = service._open_recovery_directory
    real_clear = FieldMigrationService._clear_journal
    real_unlink = migration_module.os.unlink
    staged_fds: list[int] = []
    recovery_fds: list[int] = []
    finalized = False

    def track_staged_temp(parent_fd: int, name: str, content: bytes, mode: int) -> None:
        if name.startswith(".scholar-migrate-"):
            staged_fds.append(parent_fd)
        real_write_temp(parent_fd, name, content, mode)

    def track_recovery_dir(root: Path, source: str, field: str):
        opened = real_open_recovery(root, source, field)
        if opened is not None:
            recovery_fds.append(opened[1])
        return opened

    def mark_finalized(descriptor: int) -> None:
        nonlocal finalized
        real_clear(descriptor)
        finalized = True

    def fail_first_staged_unlink(path, *args, **kwargs) -> None:
        if finalized and isinstance(path, str) and path.startswith(".scholar-migrate-"):
            raise OSError("injected staged-temp cleanup failure")
        real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(FieldMigrationService, "_write_temp", staticmethod(track_staged_temp))
        patcher.setattr(service, "_open_recovery_directory", track_recovery_dir)
        patcher.setattr(FieldMigrationService, "_clear_journal", staticmethod(mark_finalized))
        patcher.setattr(migration_module.os, "unlink", fail_first_staged_unlink)
        with pytest.raises(FieldMigrationError, match="staged cleanup failed; inspect journal state"):
            service.apply(
                plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
            )

    assert staged_fds and recovery_fds
    for descriptor in (*staged_fds, *recovery_fds):
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert len(list((tmp_path / "recovery").rglob("pending.json"))) == 0


def test_field_migration_staging_cleanup_failure_closes_fd_and_keeps_original_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    plan = service.plan(source_id, world_id)
    home = vault / "世界模型" / "00-领域入口.md"
    before = home.read_bytes()
    real_write_temp = FieldMigrationService._write_temp
    real_unlink = migration_module.os.unlink
    staged_fds: list[int] = []

    def fail_after_staging(parent_fd: int, name: str, content: bytes, mode: int) -> None:
        real_write_temp(parent_fd, name, content, mode)
        staged_fds.append(parent_fd)
        raise FieldMigrationError("injected staging failure")

    def fail_staged_unlink(path, *args, **kwargs) -> None:
        if isinstance(path, str) and path.startswith(".scholar-migrate-"):
            raise OSError("injected staging unlink failure")
        real_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(FieldMigrationService, "_write_temp", staticmethod(fail_after_staging))
        patcher.setattr(migration_module.os, "unlink", fail_staged_unlink)
        with pytest.raises(
            FieldMigrationError, match="injected staging failure; staging cleanup failed"
        ):
            service.apply(
                plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
            )

    assert staged_fds
    for descriptor in staged_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    assert home.read_bytes() == before
    assert list((tmp_path / "recovery").rglob("pending.json")) == []


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires process-stop fault injection")
def test_field_migration_recovery_can_resume_after_interrupted_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault, registry, world_id, _other_id = _registered_vault(tmp_path)
    source_id = FieldService._load_manifest(vault).source_id
    recovery = tmp_path / "recovery"
    home = vault / "世界模型" / "00-领域入口.md"
    jepa = vault / "世界模型" / "JEPA.md"
    originals = (home.read_bytes(), jepa.read_bytes())
    _interrupt_after_replace(registry, recovery, source_id, world_id, after=2)
    restarted = FieldMigrationService(registry, state_root=recovery, link_resolver=_fixture_pdf)
    original_replace = migration_module._replace_at
    calls = 0

    def stop_during_recovery(source: str, destination: str, parent_fd: int) -> None:
        nonlocal calls
        original_replace(source, destination, parent_fd)
        calls += 1
        if calls == 1:
            raise OSError("injected stop after first restore")

    monkeypatch.setattr(migration_module, "_replace_at", stop_during_recovery)
    with pytest.raises(FieldMigrationError, match="journal retained for retry"):
        restarted.recover(source_id, world_id)
    assert len(list(recovery.rglob("pending.json"))) == 1
    monkeypatch.setattr(migration_module, "_replace_at", original_replace)

    result = restarted.recover(source_id, world_id)

    assert result.recovered_files == ("世界模型/JEPA.md",)
    assert (home.read_bytes(), jepa.read_bytes()) == originals
    assert list(recovery.rglob("pending.json")) == []


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
    service.apply(
        plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
    )

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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )

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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
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
    service = FieldMigrationService(
        registry, state_root=tmp_path / "recovery", link_resolver=_fixture_pdf
    )
    source_id = FieldService._load_manifest(vault).source_id

    plan = service.plan(source_id, world_id)

    assert any("unrecognized legacy Hub URL in unmapped file: tree.canvas" in item
               for item in plan.conflicts)
    with pytest.raises(FieldMigrationError, match="unresolved conflicts"):
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )


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
        service.apply(
            plan.plan_token, approved_digest=plan.plan_digest, external_writers_paused=True
        )
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
