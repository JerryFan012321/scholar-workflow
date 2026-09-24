"""A Vault preview is read-only; one explicit Field is committed per confirmation."""

from __future__ import annotations

import json
import os
import stat
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import pytest
import yaml

from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.fields import (
    FieldDefinition,
    FieldManifest,
    FieldRegistryCommitUncertain,
    FieldRegistryError,
    FieldService,
    FolderRegistration,
    KnowledgeSourceRegistration,
    KnowledgeSourceRegistry,
    KnowledgeSourceRegistryDocument,
)
from scholar_workflow.hub.models import HubCatalog
from scholar_workflow.hub.server import start_hub_server


def _vault(tmp_path: Path) -> tuple[Path, Path, Path]:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    world = vault / "世界模型"
    rendering = vault / "3DGS"
    world.mkdir()
    rendering.mkdir()
    (world / "00-领域入口.md").write_text("# 世界模型\n", encoding="utf-8")
    (rendering / "00-领域入口.md").write_text("# 3DGS\n", encoding="utf-8")
    return vault, world, rendering


def test_whole_vault_confirms_one_field_then_adds_one_sibling(tmp_path: Path) -> None:
    vault, world, rendering = _vault(tmp_path)
    original = {
        world: (world / "00-领域入口.md").read_bytes(),
        rendering: (rendering / "00-领域入口.md").read_bytes(),
    }
    registry = KnowledgeSourceRegistry(tmp_path / "state" / "sources.json")
    service = FieldService(registry)

    first = service.preview(vault)
    assert [field.relative_root for field in first.fields] == ["3DGS", "世界模型"]
    assert first.registered_fields == []
    assert not registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()

    chosen_world = next(field for field in first.fields if field.relative_root == "世界模型")
    manifest = service.confirm(first.candidate_token, chosen_world.field_id)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    assert [field.relative_root for field in manifest.fields] == ["世界模型"]
    assert [field["relative_root"] for field in yaml.safe_load(manifest_path.read_text())["fields"]] == ["世界模型"]
    assert [field["relative_root"] for field in service.list_fields()] == ["世界模型"]
    assert all((folder / "00-领域入口.md").read_bytes() == content for folder, content in original.items())

    second = service.preview(vault)
    assert second.existing_manifest is True
    assert second.source_id == first.source_id
    assert [field.relative_root for field in second.registered_fields] == ["世界模型"]
    assert [field.relative_root for field in second.fields] == ["3DGS"]
    chosen_rendering = second.fields[0]
    manifest = service.confirm(second.candidate_token, chosen_rendering.field_id)
    assert [field.relative_root for field in manifest.fields] == ["世界模型", "3DGS"]
    assert len(registry.load_document().sources) == 1
    assert all((folder / "00-领域入口.md").read_bytes() == content for folder, content in original.items())


def test_field_confirm_rejects_unselected_or_stale_candidate_without_writes(tmp_path: Path) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    preview = service.preview(vault)

    with pytest.raises(FieldRegistryError, match="candidate"):
        service.confirm(preview.candidate_token, "00000000-0000-4000-8000-000000000001")
    assert not registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()

    selected = preview.fields[0]
    (vault / "世界模型" / "00-领域入口.md").write_text("changed", encoding="utf-8")
    with pytest.raises(FieldRegistryError, match="content changed"):
        service.confirm(preview.candidate_token, selected.field_id)
    assert not registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()


def test_append_rejects_manifest_conflict_without_overwriting_prior_field(tmp_path: Path) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    first = service.preview(vault)
    world = next(field for field in first.fields if field.relative_root == "世界模型")
    service.confirm(first.candidate_token, world.field_id)
    second = service.preview(vault)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    updated = manifest_path.read_bytes() + b"\n# changed by user\n"
    manifest_path.write_bytes(updated)

    with pytest.raises(FieldRegistryError, match="manifest changed"):
        service.confirm(second.candidate_token, second.fields[0].field_id)

    assert manifest_path.read_bytes() == updated
    assert [field["relative_root"] for field in service.list_fields()] == ["世界模型"]


def test_append_preserves_existing_host_registration_identity(tmp_path: Path) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    first = service.preview(vault)
    world = next(field for field in first.fields if field.relative_root == "世界模型")
    service.confirm(first.candidate_token, world.field_id)
    document = registry.load_document()
    source_id = document.sources[0].source_id
    registry.save(KnowledgeSourceRegistryDocument(
        folders=[FolderRegistration(
            folder_id="my-vault",
            root=vault,
            capabilities=["read", "write"],
        )],
        sources=[KnowledgeSourceRegistration(
            source_id=source_id,
            folder_id="my-vault",
            capabilities=["read", "write"],
        )],
    ))

    second = service.preview(vault)
    assert second.folder_id == "my-vault"
    service.confirm(second.candidate_token, second.fields[0].field_id)
    assert [row.folder_id for row in registry.load_document().sources] == ["my-vault"]
    assert [row.folder_id for row in registry.load_document().folders] == ["my-vault"]


def test_subfolder_cannot_be_registered_as_second_source_for_same_vault(
    tmp_path: Path,
) -> None:
    vault, world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    first = service.preview(vault)
    selected = next(field for field in first.fields if field.relative_root == "世界模型")
    service.confirm(first.candidate_token, selected.field_id)

    child_preview = service.preview(world)
    assert child_preview.conflicts == [
        f"Selected folder overlaps registered Source {first.source_id}"
    ]
    with pytest.raises(FieldRegistryError, match="unresolved conflicts"):
        service.confirm(child_preview.candidate_token, child_preview.fields[0].field_id)
    assert not (world / ".scholar-workflow").exists()
    assert len(registry.load_document().sources) == 1


@pytest.mark.parametrize("roots", [(".", "世界模型"), ("世界模型", "世界模型/子领域")])
def test_field_manifest_rejects_overlapping_field_roots(roots: tuple[str, str]) -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        FieldManifest(
            source_id="55555555-5555-4555-8555-555555555555",
            fields=[
                FieldDefinition(
                    field_id="11111111-1111-4111-8111-111111111111",
                    title="First",
                    relative_root=roots[0],
                    home="README.md",
                ),
                FieldDefinition(
                    field_id="22222222-2222-4222-8222-222222222222",
                    title="Second",
                    relative_root=roots[1],
                    home="README.md",
                ),
            ],
        )


def test_existing_manifest_with_overlapping_roots_fails_closed(tmp_path: Path) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    state = vault / ".scholar-workflow"
    state.mkdir()
    (state / "fields.yml").write_text(yaml.safe_dump({
        "schema_version": 1,
        "source_id": "55555555-5555-4555-8555-555555555555",
        "fields": [
            {
                "field_id": "11111111-1111-4111-8111-111111111111",
                "title": "Vault",
                "relative_root": ".",
                "home": "README.md",
            },
            {
                "field_id": "22222222-2222-4222-8222-222222222222",
                "title": "World Models",
                "relative_root": "世界模型",
                "home": "00-领域入口.md",
            },
        ],
    }), encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")

    with pytest.raises(FieldRegistryError, match="manifest is invalid"):
        FieldService(registry).preview(vault)
    assert not registry.path.exists()


def test_existing_portable_manifest_registers_on_fresh_host_without_rewrite(
    tmp_path: Path,
) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    first_host = FieldService(KnowledgeSourceRegistry(tmp_path / "first-host.json"))
    first_preview = first_host.preview(vault)
    first_field = next(field for field in first_preview.fields if field.relative_root == "世界模型")
    first_host.confirm(first_preview.candidate_token, first_field.field_id)
    second_preview = first_host.preview(vault)
    first_host.confirm(second_preview.candidate_token, second_preview.fields[0].field_id)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    portable_bytes = manifest_path.read_bytes()
    portable_manifest = FieldService._load_manifest(vault)

    fresh_registry = KnowledgeSourceRegistry(tmp_path / "fresh-host.json")
    fresh_host = FieldService(fresh_registry)
    preview = fresh_host.preview(vault)
    assert preview.registration_only is True
    assert preview.fields == []
    assert preview.registered_fields == portable_manifest.fields
    assert preview.conflicts == []
    assert not fresh_registry.path.exists()
    with pytest.raises(FieldRegistryError, match="explicit Source registration"):
        fresh_host.confirm(preview.candidate_token, portable_manifest.fields[0].field_id)
    with pytest.raises(FieldRegistryError, match="not in the preview"):
        fresh_host.confirm_source(preview.candidate_token, "00000000-0000-4000-8000-000000000001")

    registered = fresh_host.confirm_source(preview.candidate_token, preview.source_id)
    assert registered == portable_manifest
    assert manifest_path.read_bytes() == portable_bytes
    assert [field["field_id"] for field in fresh_host.list_fields()] == [
        field.field_id for field in portable_manifest.fields
    ]

    robotics = vault / "机器人"
    robotics.mkdir()
    (robotics / "00-领域入口.md").write_text("# 机器人\n", encoding="utf-8")
    next_preview = fresh_host.preview(vault)
    assert next_preview.registration_only is False
    assert [field.relative_root for field in next_preview.fields] == ["机器人"]
    appended = fresh_host.confirm(next_preview.candidate_token, next_preview.fields[0].field_id)
    assert appended.fields[:2] == portable_manifest.fields
    assert len(appended.fields) == 3


def test_existing_source_registration_rechecks_manifest_before_host_write(
    tmp_path: Path,
) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    first_host = FieldService(KnowledgeSourceRegistry(tmp_path / "first-host.json"))
    first = first_host.preview(vault)
    first_host.confirm(first.candidate_token, first.fields[0].field_id)
    fresh_registry = KnowledgeSourceRegistry(tmp_path / "fresh-host.json")
    fresh_host = FieldService(fresh_registry)
    preview = fresh_host.preview(vault)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    changed = manifest_path.read_bytes() + b"\n# edited during preview\n"
    manifest_path.write_bytes(changed)

    with pytest.raises(FieldRegistryError, match="manifest changed"):
        fresh_host.confirm_source(preview.candidate_token, preview.source_id)
    assert manifest_path.read_bytes() == changed
    assert not fresh_registry.path.exists()


def test_registry_directory_sync_failure_reports_uncertain_without_manifest_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    preview = service.preview(vault)
    original_fsync = os.fsync
    registry_parent_inode = registry.path.parent.stat().st_ino

    def fail_registry_directory_sync(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode) and metadata.st_ino == registry_parent_inode:
            raise OSError("directory fsync failed after replace")
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_registry_directory_sync)
    with pytest.raises(FieldRegistryCommitUncertain, match="may be committed"):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)

    assert (vault / ".scholar-workflow" / "fields.yml").exists()
    assert registry.path.exists()
    assert len(registry.load_document().sources) == 1


def test_field_registration_ui_separates_portable_enrollment_and_refresh_failure() -> None:
    script = resources.files("scholar_workflow.hub.static").joinpath("hub.js").read_text()
    assert "preview.registration_only" in script
    assert "source_id: preview.source_id" in script
    assert "原 manifest 与全部 Field ID 保持不变" in script
    assert "登记已成功，但列表刷新失败" in script


def test_registry_cas_serializes_two_independent_saves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path = tmp_path / "sources.json"
    original_replace = os.replace
    first_at_replace = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_finished = threading.Event()
    results: dict[str, str] = {}

    def paused_replace(src, dst, **kwargs):
        if threading.current_thread().name == "first-registry-save" and dst == "sources.json":
            first_at_replace.set()
            if not release_first.wait(timeout=5):
                raise AssertionError("first save was not released")
        return original_replace(src, dst, **kwargs)

    monkeypatch.setattr(os, "replace", paused_replace)
    first_document = KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
        folder_id="first-folder", root=tmp_path / "first", capabilities=["read"]
    )])
    second_document = KnowledgeSourceRegistryDocument(folders=[FolderRegistration(
        folder_id="second-folder", root=tmp_path / "second", capabilities=["read"]
    )])

    def save_first() -> None:
        try:
            KnowledgeSourceRegistry(registry_path).save(first_document, expected_revision="absent")
            results["first"] = "saved"
        except FieldRegistryError as exc:
            results["first"] = str(exc)

    def save_second() -> None:
        second_started.set()
        try:
            KnowledgeSourceRegistry(registry_path).save(second_document, expected_revision="absent")
            results["second"] = "saved"
        except FieldRegistryError as exc:
            results["second"] = str(exc)
        finally:
            second_finished.set()

    first_thread = threading.Thread(target=save_first, name="first-registry-save")
    second_thread = threading.Thread(target=save_second, name="second-registry-save")
    first_thread.start()
    assert first_at_replace.wait(timeout=5)
    second_thread.start()
    assert second_started.wait(timeout=5)
    try:
        assert not second_finished.wait(timeout=0.25)
    finally:
        release_first.set()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert results["first"] == "saved"
    assert "changed after preview" in results["second"]
    assert [row.folder_id for row in KnowledgeSourceRegistry(registry_path).load_document().folders] == [
        "first-folder"
    ]


def test_manifest_commit_rejects_state_directory_swap(tmp_path: Path, monkeypatch) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    first = service.preview(vault)
    world = next(field for field in first.fields if field.relative_root == "世界模型")
    service.confirm(first.candidate_token, world.field_id)
    next_preview = service.preview(vault)
    state = vault / ".scholar-workflow"
    manifest_path = state / "fields.yml"
    original_manifest = manifest_path.read_bytes()
    original_registry = registry.path.read_bytes()
    actual_replace = os.replace

    def swap_state_after_manifest_replace(src, dst, **kwargs):
        actual_replace(src, dst, **kwargs)
        if dst == "fields.yml":
            moved = vault / ".scholar-workflow-moved"
            state.rename(moved)
            state.mkdir()
            manifest_path.write_bytes(original_manifest)

    monkeypatch.setattr(os, "replace", swap_state_after_manifest_replace)
    with pytest.raises(FieldRegistryError, match="state directory changed"):
        service.confirm(next_preview.candidate_token, next_preview.fields[0].field_id)

    assert manifest_path.read_bytes() == original_manifest
    assert registry.path.read_bytes() == original_registry


@pytest.mark.parametrize("existing", [False, True])
def test_field_registration_failure_rolls_back_only_selected_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    vault, world, rendering = _vault(tmp_path)
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    service = FieldService(registry)
    if existing:
        first = service.preview(vault)
        world_field = next(field for field in first.fields if field.relative_root == "世界模型")
        service.confirm(first.candidate_token, world_field.field_id)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    before = manifest_path.read_bytes() if existing else None
    registry_before = registry.path.read_bytes() if existing else None
    preview = service.preview(vault)
    selected = next(field for field in preview.fields if field.relative_root == "3DGS")

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(registry, "save", fail)
    with pytest.raises(FieldRegistryError, match="rolled back"):
        service.confirm(preview.candidate_token, selected.field_id)

    assert (manifest_path.read_bytes() if manifest_path.exists() else None) == before
    assert (registry.path.read_bytes() if registry.path.exists() else None) == registry_before
    assert (world / "00-领域入口.md").read_text(encoding="utf-8") == "# 世界模型\n"
    assert (rendering / "00-领域入口.md").read_text(encoding="utf-8") == "# 3DGS\n"


class _Picker:
    def __init__(self, root: Path) -> None:
        self.root = root

    def choose(self) -> Path:
        return self.root


def _request(port: int, path: str, *, data: bytes | None = None, headers=None):
    return urllib.request.urlopen(
        urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            method="POST" if data is not None else "GET",
            data=data,
            headers=headers or {},
        ),
        timeout=3,
    )


def test_field_confirm_api_requires_exactly_one_field_id(tmp_path: Path) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    storage = tmp_path / "storage"
    storage.mkdir()
    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(
            HubCatalog(generated_at=datetime(2026, 9, 25, tzinfo=UTC), resources=[])
        ),
        field_service=FieldService(registry),
        folder_picker=_Picker(vault),
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
        }
        selected = json.loads(
            _request(port, "/api/v3/fields/select", data=b"{}", headers=headers).read()
        )["preview"]
        with pytest.raises(urllib.error.HTTPError) as missing:
            _request(
                port,
                "/api/v3/fields/confirm",
                data=json.dumps({"candidate_token": selected["candidate_token"]}).encode(),
                headers=headers,
            )
        assert missing.value.code == 400
        chosen = next(field for field in selected["fields"] if field["relative_root"] == "世界模型")
        result = json.loads(
            _request(
                port,
                "/api/v3/fields/confirm",
                data=json.dumps({
                    "candidate_token": selected["candidate_token"],
                    "field_id": chosen["field_id"],
                }).encode(),
                headers=headers,
            ).read()
        )
        assert [field["relative_root"] for field in result["manifest"]["fields"]] == ["世界模型"]
        next_preview = json.loads(
            _request(port, "/api/v3/fields/select", data=b"{}", headers=headers).read()
        )["preview"]
        assert [field["relative_root"] for field in next_preview["registered_fields"]] == [
            "世界模型"
        ]
        assert [field["relative_root"] for field in next_preview["fields"]] == ["3DGS"]
        second = json.loads(
            _request(
                port,
                "/api/v3/fields/confirm",
                data=json.dumps({
                    "candidate_token": next_preview["candidate_token"],
                    "field_id": next_preview["fields"][0]["field_id"],
                }).encode(),
                headers=headers,
            ).read()
        )
        assert [field["relative_root"] for field in second["manifest"]["fields"]] == [
            "世界模型",
            "3DGS",
        ]
    finally:
        server.shutdown()
        server.server_close()


def test_field_confirm_api_registers_existing_portable_source_without_manifest_write(
    tmp_path: Path,
) -> None:
    vault, _world, _rendering = _vault(tmp_path)
    old_host = FieldService(KnowledgeSourceRegistry(tmp_path / "old-host.json"))
    old_preview = old_host.preview(vault)
    old_host.confirm(old_preview.candidate_token, old_preview.fields[0].field_id)
    manifest_path = vault / ".scholar-workflow" / "fields.yml"
    original = manifest_path.read_bytes()
    storage = tmp_path / "storage"
    storage.mkdir()
    fresh_registry = KnowledgeSourceRegistry(tmp_path / "fresh-host.json")
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(
            HubCatalog(generated_at=datetime(2026, 9, 25, tzinfo=UTC), resources=[])
        ),
        field_service=FieldService(fresh_registry),
        folder_picker=_Picker(vault),
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
        }
        preview = json.loads(
            _request(port, "/api/v3/fields/select", data=b"{}", headers=headers).read()
        )["preview"]
        assert preview["registration_only"] is True
        assert preview["fields"] == []
        assert len(preview["registered_fields"]) == 1
        response = json.loads(_request(
            port,
            "/api/v3/fields/confirm",
            data=json.dumps({
                "candidate_token": preview["candidate_token"],
                "source_id": preview["source_id"],
            }).encode(),
            headers=headers,
        ).read())
        assert response["ok"] is True
        assert response["manifest"]["source_id"] == preview["source_id"]
        assert manifest_path.read_bytes() == original
        assert len(fresh_registry.load_document().sources) == 1
    finally:
        server.shutdown()
        server.server_close()
