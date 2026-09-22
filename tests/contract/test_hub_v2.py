"""Contract tests for the Hub Control Plane v2 public boundary."""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

import scholar_workflow.hub.project_docs as project_docs_module
from scholar_workflow.adapters.zotero_local import ZoteroItemPage
from scholar_workflow.cli import main
from scholar_workflow.hub.catalog import StaticCatalogProvider
from scholar_workflow.hub.directory import (
    HubDirectoryService,
    ProjectRegistry,
    RegistryError,
    ToolRegistry,
    TypedEntityRef,
    ZoteroPaperLibraryProvider,
)
from scholar_workflow.hub.models import (
    ArtifactFormat,
    ArtifactKind,
    HubArtifact,
    HubCatalog,
    HubResource,
)
from scholar_workflow.hub.project_docs import (
    DocumentCollisionError,
    ProjectConfirmationRequired,
    ProjectDocumentError,
    ProjectDocumentService,
    ProjectPathError,
)
from scholar_workflow.hub.server import start_hub_server
from scholar_workflow.hub.tasks import (
    CodexCapabilityProbe,
    CodexCommandBuilder,
    TaskEffort,
    TaskRecipe,
    TaskRequest,
    TaskSafetyPolicy,
)
from scholar_workflow.hub.workspaces import (
    WorkspaceBindingCoordinator,
    WorkspaceBindingRegistry,
    WorkspaceProfile,
)

NOW = datetime(2026, 9, 22, tzinfo=UTC)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"


def _catalog() -> HubCatalog:
    return HubCatalog(
        generated_at=NOW,
        resources=[
            HubResource(resource_id=f"paper:{index}", kind="paper", title=f"Paper {index}")
            for index in range(3)
        ],
    )


def _write_registry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_project_layout(root: Path, project_id: str = PROJECT_ID) -> None:
    (root / "project-layout.json").write_text(
        json.dumps({"schema_version": 2, "project_id": project_id}),
        encoding="utf-8",
    )


def _request(port: int, path: str, *, method: str = "GET", headers=None, data=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        headers=headers or {},
        data=data,
    )
    return urllib.request.urlopen(request)


def test_directory_is_the_unique_root_with_fixed_typed_libraries_and_pagination(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    project_registry_path = tmp_path / "projects.json"
    tool_registry_path = tmp_path / "tools.json"
    _write_registry(
        project_registry_path,
        {
            "schema_version": 1,
            "projects": [
                {
                    "project_id": PROJECT_ID,
                    "display_name": "Project One",
                    "root": str(project_root),
                    "enabled": True,
                    "capabilities": ["docs"],
                }
            ],
        },
    )
    _write_registry(tool_registry_path, {"schema_version": 1, "tools": []})

    service = HubDirectoryService(
        StaticCatalogProvider(_catalog()),
        ProjectRegistry(project_registry_path),
        ToolRegistry(tool_registry_path),
    )
    directory = service.load()

    assert directory.schema_version == 2
    assert directory.knowledge_catalog.schema_version == 1
    assert [library.library_id for library in directory.libraries] == [
        "papers",
        "projects",
        "tools",
    ]
    assert directory.libraries[2].available is True
    assert directory.libraries[2].total_count == 0
    assert directory.libraries[2].detail == "No tools are registered"

    first = service.list_items("papers", limit=2)
    assert [item["ref"] for item in first.items] == [
        {"library_id": "papers", "item_type": "paper", "item_id": "paper:0"},
        {"library_id": "papers", "item_type": "paper", "item_id": "paper:1"},
    ]
    assert first.next_cursor
    assert first.items[0]["landing_path"].startswith(
        "/hub/item?library_id=papers&item_type=paper&item_id="
    )
    second = service.list_items("papers", limit=2, cursor=first.next_cursor)
    assert [item["ref"]["item_id"] for item in second.items] == ["paper:2"]
    assert second.next_cursor is None

    with pytest.raises(ValueError, match="cursor"):
        service.list_items(
            "papers",
            limit=2,
            cursor=first.next_cursor,
            sort="id",
        )


def test_registries_are_explicit_and_never_discover_neighboring_projects(tmp_path):
    registered = tmp_path / "registered"
    unregistered = tmp_path / "looks-like-a-project"
    (registered / "docs").mkdir(parents=True)
    _write_project_layout(registered)
    (unregistered / "docs").mkdir(parents=True)
    (unregistered / "project.json").write_text('{"project_id":"hidden"}', encoding="utf-8")
    path = tmp_path / "projects.json"
    _write_registry(
        path,
        {
            "schema_version": 1,
            "projects": [
                {
                    "project_id": PROJECT_ID,
                    "display_name": "Registered",
                    "root": str(registered),
                    "enabled": True,
                    "capabilities": ["docs"],
                }
            ],
        },
    )
    projects = ProjectRegistry(path).load()
    assert [project.project_id for project in projects] == [PROJECT_ID]


@pytest.mark.parametrize(
    "layout",
    [
        None,
        {
            "schema_version": 2,
            "project_id": "22222222-2222-4222-8222-222222222222",
        },
        {"schema_version": 2, "project_id": f"urn:uuid:{PROJECT_ID}"},
    ],
)
def test_project_registry_resolve_requires_matching_portable_manifest(tmp_path, layout):
    root = tmp_path / "project"
    root.mkdir()
    if layout is not None:
        (root / "project-layout.json").write_text(json.dumps(layout), encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project",
                "root": str(root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    with pytest.raises(RegistryError, match="project-layout|identity"):
        ProjectRegistry(registry_path).resolve(PROJECT_ID)


def test_project_registry_rejects_symlinked_layout_manifest(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    external_layout = tmp_path / "external-layout.json"
    external_layout.write_text(
        json.dumps({"schema_version": 2, "project_id": PROJECT_ID}),
        encoding="utf-8",
    )
    (root / "project-layout.json").symlink_to(external_layout)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project",
                "root": str(root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    with pytest.raises(RegistryError, match="trusted project-layout"):
        ProjectRegistry(registry_path).resolve(PROJECT_ID)


def test_zotero_papers_provider_requests_only_the_server_page():
    calls = []

    class FakeAdapter:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def list_items_page(self, *, start, limit, query, sort, direction, item_type):
            calls.append((start, limit, query, sort, direction, item_type))
            return ZoteroItemPage(
                items=(
                    {
                        "key": "ABCD2345",
                        "data": {
                            "itemType": "journalArticle",
                            "title": "Paged paper",
                            "creators": [{"firstName": "A", "lastName": "Author"}],
                            "date": "2026",
                        },
                    },
                ),
                start=start,
                limit=limit,
                total=101,
            )

        def get_children(self, item_key):
            assert item_key == "ABCD2345"
            return [{
                "key": "PDFD2345",
                "data": {
                    "itemType": "attachment",
                    "contentType": "application/pdf",
                    "filename": "paper.pdf",
                },
            }]

    provider = ZoteroPaperLibraryProvider(adapter_factory=FakeAdapter)
    page = provider.page(
        offset=40, limit=20, query="world model", sort="year",
        direction="desc", item_type="journalArticle",
    )
    assert calls == [(40, 20, "world model", "date", "desc", "journalArticle")]
    assert page.total_count == 101
    assert page.has_more is True
    assert page.consumed_count == 1
    assert page.items[0]["ref"] == {
        "library_id": "papers",
        "item_type": "paper",
        "item_id": "ABCD2345",
    }
    assert page.items[0]["attachment_key"] == "PDFD2345"
    assert page.items[0]["pdf_path"] == "/open/paper/PDFD2345"


def test_zotero_cursor_advances_by_consumed_rows_when_nonbibliographic_row_is_skipped(
    tmp_path,
):
    starts = []

    class FakeAdapter:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def list_items_page(self, *, start, limit, **_kwargs):
            starts.append(start)
            if start == 0:
                items = (
                    {"key": "NOTE2345", "data": {"itemType": "note"}},
                    {
                        "key": "PAPR2345",
                        "data": {"itemType": "journalArticle", "title": "Paper"},
                    },
                )
            else:
                items = (
                    {
                        "key": "PAPR6789",
                        "data": {"itemType": "preprint", "title": "Next"},
                    },
                )
            return ZoteroItemPage(items=items, start=start, limit=limit, total=3)

        def get_children(self, _item_key):
            return []

    service = HubDirectoryService(
        StaticCatalogProvider(_catalog()),
        ProjectRegistry(tmp_path / "projects.json"),
        ToolRegistry(tmp_path / "tools.json"),
        paper_provider=ZoteroPaperLibraryProvider(adapter_factory=FakeAdapter),
    )
    first = service.list_items("papers", limit=2)
    assert [item["ref"]["item_id"] for item in first.items] == ["PAPR2345"]
    second = service.list_items("papers", limit=2, cursor=first.next_cursor)
    assert [item["ref"]["item_id"] for item in second.items] == ["PAPR6789"]
    assert starts == [0, 2]


def test_disabled_project_registration_is_visible_without_resolving_host_root(tmp_path):
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Offline project",
                "root": str(tmp_path / "missing-project"),
                "enabled": False,
                "capabilities": ["docs"],
            }],
        },
    )
    service = HubDirectoryService(
        StaticCatalogProvider(_catalog()),
        ProjectRegistry(registry_path),
        ToolRegistry(tmp_path / "tools.json"),
    )
    directory = service.load()
    projects = next(row for row in directory.libraries if row.library_id == "projects")
    assert projects.available is True
    assert projects.total_count == 1
    page = service.list_items("projects")
    assert page.items[0]["enabled"] is False
    assert page.items[0]["docs_available"] is False


def test_project_docs_stay_inside_registered_docs_refuse_collisions_and_trash(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    (docs / "source.md").write_text("source", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [
                {
                    "project_id": PROJECT_ID,
                    "display_name": "Project One",
                    "root": str(project_root),
                    "enabled": True,
                    "capabilities": ["docs"],
                }
            ],
        },
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))

    copied = service.copy_within(PROJECT_ID, "source.md", "copy.md")
    assert copied.relative_path == "copy.md"
    assert (docs / "copy.md").read_text(encoding="utf-8") == "source"
    with pytest.raises(DocumentCollisionError):
        service.copy_within(PROJECT_ID, "source.md", "copy.md")
    with pytest.raises(ProjectPathError):
        service.copy_within(PROJECT_ID, "source.md", "../escape.md")

    trashed = service.trash(PROJECT_ID, "copy.md", now=NOW)
    assert not (docs / "copy.md").exists()
    assert trashed.trash_path.startswith(".scholar-workflow/trash/docs/20260922T000000Z/")
    trash_file = project_root / trashed.trash_path
    assert trash_file.read_text(encoding="utf-8") == "source"
    metadata = json.loads(trash_file.with_name(trash_file.name + ".trash.json").read_text())
    assert metadata["original_path"] == "copy.md"
    assert metadata["sha256"].startswith("sha256:")


def test_project_docs_reject_symlink_traversal(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    outside = tmp_path / "outside"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    outside.mkdir()
    (outside / "secret.md").write_text("secret", encoding="utf-8")
    (docs / "linked").symlink_to(outside, target_is_directory=True)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectPathError):
        service.copy_within(PROJECT_ID, "linked/secret.md", "stolen.md")


def test_project_trash_rejects_symlinked_private_directory_before_move(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    outside = tmp_path / "outside"
    docs.mkdir(parents=True)
    outside.mkdir()
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    (project_root / ".scholar-workflow").symlink_to(outside, target_is_directory=True)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectPathError, match="trash|symbolic"):
        service.trash(PROJECT_ID, "source.md", now=NOW)
    assert source.read_text(encoding="utf-8") == "source"
    assert list(outside.iterdir()) == []


def test_project_trash_restores_source_when_receipt_write_fails(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )

    def fail_receipt(_path, _payload, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(project_docs_module, "_atomic_json", fail_receipt)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectDocumentError, match="restored"):
        service.trash(PROJECT_ID, "source.md", now=NOW)
    assert source.read_text(encoding="utf-8") == "source"
    trash_root = project_root / ".scholar-workflow" / "trash"
    assert not list(trash_root.rglob("*.md"))


def test_project_trash_does_not_overwrite_source_if_moved_bytes_changed(
    tmp_path,
    monkeypatch,
):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )

    def mutate_then_fail(receipt_path, _payload, **_kwargs):
        trashed = receipt_path.with_name(
            receipt_path.name.removesuffix(".trash.json")
        )
        trashed.write_text("changed after move", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(project_docs_module, "_atomic_json", mutate_then_fail)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectDocumentError, match="manual recovery"):
        service.trash(PROJECT_ID, "source.md", now=NOW)
    assert not source.exists()
    trash_root = project_root / ".scholar-workflow" / "trash"
    assert [path.read_text(encoding="utf-8") for path in trash_root.rglob("*.md")] == [
        "changed after move"
    ]


def test_project_trash_destination_race_never_overwrites_victim(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    real_link = project_docs_module.os.link

    def inject_destination(
        src,
        dst,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
        follow_symlinks,
    ):
        victim_fd = os.open(
            dst,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        with os.fdopen(victim_fd, "w", encoding="utf-8") as handle:
            handle.write("concurrent victim")
        return real_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(project_docs_module.os, "link", inject_destination)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(DocumentCollisionError, match="destination"):
        service.trash(PROJECT_ID, "source.md", now=NOW)

    destination = (
        project_root
        / ".scholar-workflow"
        / "trash"
        / "docs"
        / "20260922T000000Z"
        / "source.md"
    )
    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "concurrent victim"


def test_project_trash_rollback_never_overwrites_concurrent_source(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )

    def create_victim_then_fail(_receipt, _payload, **_kwargs):
        source.write_text("concurrent source victim", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(project_docs_module, "_atomic_json", create_victim_then_fail)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectDocumentError, match="manual recovery"):
        service.trash(PROJECT_ID, "source.md", now=NOW)

    assert source.read_text(encoding="utf-8") == "concurrent source victim"
    trash_files = list(
        (project_root / ".scholar-workflow" / "trash").rglob("source.md")
    )
    assert len(trash_files) == 1
    assert trash_files[0].read_text(encoding="utf-8") == "source"


@pytest.mark.parametrize("operation", ["paste", "copy"])
@pytest.mark.parametrize("replacement", ["new-inode", "same-inode-new-bytes"])
def test_failed_exclusive_write_never_deletes_concurrent_victim(
    tmp_path,
    monkeypatch,
    operation,
    replacement,
):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source bytes", encoding="utf-8")
    destination = docs / "destination.md"
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )

    def replace_then_fail(_descriptor):
        if replacement == "new-inode":
            destination.unlink()
        destination.write_text("concurrent victim", encoding="utf-8")
        raise OSError("injected fsync failure")

    monkeypatch.setattr(project_docs_module.os, "fsync", replace_then_fail)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectDocumentError, match="copy failed"):
        if operation == "paste":
            service.paste_text(PROJECT_ID, "destination.md", "pasted bytes")
        else:
            service.copy_within(PROJECT_ID, "source.md", "destination.md")

    assert destination.read_text(encoding="utf-8") == "concurrent victim"
    assert source.read_text(encoding="utf-8") == "source bytes"


def test_project_document_lockfile_symlink_fails_closed(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    locks = project_root / ".scholar-workflow" / "locks"
    docs.mkdir(parents=True)
    locks.mkdir(parents=True)
    _write_project_layout(project_root)
    outside = tmp_path / "outside-lock"
    outside.write_text("outside", encoding="utf-8")
    (locks / "project-docs.lock").symlink_to(outside)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )

    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectPathError, match="lockfile"):
        service.paste_text(PROJECT_ID, "destination.md", "content")
    assert outside.read_text(encoding="utf-8") == "outside"
    assert not (docs / "destination.md").exists()


@pytest.mark.parametrize("operation", ["paste", "copy"])
def test_project_document_final_open_rejects_parent_symlink_swap(
    tmp_path,
    monkeypatch,
    operation,
):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    nested = docs / "nested"
    nested.mkdir(parents=True)
    _write_project_layout(project_root)
    source = docs / "source.md"
    source.write_text("source", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    held = docs / "held-parent"
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    real_open = project_docs_module.os.open
    swapped = False

    def swap_parent(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if (
            not swapped
            and path == "destination.md"
            and flags & os.O_EXCL
            and dir_fd is not None
        ):
            nested.rename(held)
            nested.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(project_docs_module.os, "open", swap_parent)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectPathError, match="parent changed"):
        if operation == "paste":
            service.paste_text(PROJECT_ID, "nested/destination.md", "pasted")
        else:
            service.copy_within(PROJECT_ID, "source.md", "nested/destination.md")

    assert swapped
    assert list(outside.iterdir()) == []
    assert not (held / "destination.md").exists()
    assert source.read_text(encoding="utf-8") == "source"


def test_project_trash_final_link_rejects_parent_symlink_swap(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    source = docs / "nested" / "source.md"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    _write_project_layout(project_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    trash_parent = (
        project_root
        / ".scholar-workflow"
        / "trash"
        / "docs"
        / "20260922T000000Z"
        / "nested"
    )
    held = trash_parent.with_name("held-parent")
    real_link = project_docs_module.os.link
    swapped = False

    def swap_parent(
        src,
        dst,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
        follow_symlinks,
    ):
        nonlocal swapped
        if not swapped:
            trash_parent.rename(held)
            trash_parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_link(
            src,
            dst,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(project_docs_module.os, "link", swap_parent)
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectPathError, match="parent changed"):
        service.trash(PROJECT_ID, "nested/source.md", now=NOW)

    assert swapped
    assert source.read_text(encoding="utf-8") == "source"
    assert list(outside.iterdir()) == []
    assert not (held / "source.md").exists()


def test_project_document_mutation_waits_for_cross_process_lock(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    locks = project_root / ".scholar-workflow" / "locks"
    docs.mkdir(parents=True)
    locks.mkdir(parents=True)
    _write_project_layout(project_root)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    lock_path = locks / "project-docs.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    started = threading.Event()
    finished = threading.Event()
    errors = []
    service = ProjectDocumentService(ProjectRegistry(registry_path))

    def mutate():
        started.set()
        try:
            service.paste_text(PROJECT_ID, "destination.md", "content")
        except ProjectDocumentError as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=mutate)
    thread.start()
    assert started.wait(timeout=2)
    assert not finished.wait(timeout=0.1)
    fcntl.flock(lock_fd, fcntl.LOCK_UN)
    os.close(lock_fd)
    thread.join(timeout=2)

    assert not errors
    assert not thread.is_alive()
    assert (docs / "destination.md").read_text(encoding="utf-8") == "content"


def test_copy_requires_confirmation_for_tracked_deleted_destination(tmp_path):
    project_root = tmp_path / "project"
    docs = project_root / "docs"
    docs.mkdir(parents=True)
    _write_project_layout(project_root)
    (docs / "source.md").write_text("source", encoding="utf-8")
    destination = docs / "destination.md"
    destination.write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    subprocess.run(
        ["git", "add", "docs/destination.md"],
        cwd=project_root,
        check=True,
    )
    destination.unlink()
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    with pytest.raises(ProjectConfirmationRequired, match="destination"):
        service.copy_within(PROJECT_ID, "source.md", "destination.md")
    result = service.copy_within(
        PROJECT_ID,
        "source.md",
        "destination.md",
        confirm_git=True,
    )
    assert "destination=modified" in result.git_state


def test_knowledge_copy_strips_managed_identity_and_has_no_backlink(tmp_path):
    project_root = tmp_path / "project"
    vault = tmp_path / "vault"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    vault.mkdir()
    (vault / "analysis.md").write_text(
        "---\nsw_schema: 1\nsw_catalog_id: analysis:one\ntags: [human]\n---\n"
        "# Analysis\n\n"
        "<!-- scholar-workflow:start -->\n"
        "Human-readable claim. ^claim-task\n"
        '<!-- sw-analysis-claim id="task" role="task" -->\n'
        "<!-- scholar-workflow:end -->\n",
        encoding="utf-8",
    )
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    catalog = HubCatalog(
        generated_at=NOW,
        artifacts=[HubArtifact(
            artifact_id="analysis:one",
            kind=ArtifactKind.PAPER_ANALYSIS,
            format=ArtifactFormat.MARKDOWN,
            vault_path="analysis.md",
        )],
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    result = service.copy_knowledge_artifact(
        PROJECT_ID,
        "analysis:one",
        "knowledge/analysis.md",
        catalog_provider=StaticCatalogProvider(catalog),
        vault_root=vault,
    )
    copied = (project_root / "docs" / result.relative_path).read_text(encoding="utf-8")
    assert "sw_schema" not in copied
    assert "sw_catalog_id" not in copied
    assert "tags:" in copied
    assert "# Analysis" in copied
    assert "Human-readable claim." in copied
    assert "sw-analysis-claim" not in copied
    assert "scholar-workflow:start" not in copied
    assert "^claim-task" not in copied
    assert not (project_root / ".scholar-workflow" / "knowledge-links.json").exists()


def test_knowledge_canvas_copy_regenerates_identity_and_removes_managed_backlinks(tmp_path):
    project_root = tmp_path / "project"
    vault = tmp_path / "vault"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    vault.mkdir()
    (vault / "analysis.canvas").write_text(
        json.dumps({
            "nodes": [
                {
                    "id": "source-root",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 400,
                    "height": 160,
                    "text": "# 论文解析树\n[[分析正文]]\nReadable title",
                },
                {
                    "id": "source-claim",
                    "type": "text",
                    "x": 500,
                    "y": 0,
                    "width": 400,
                    "height": 180,
                    "text": (
                        "### Claim\nReadable evidence\n"
                        "↩ [[分析正文#^claim-task|正文]]\n"
                        '<!-- sw-analysis-claim id="task" role="task" -->'
                    ),
                },
            ],
            "edges": [{
                "id": "source-edge",
                "fromNode": "source-root",
                "toNode": "source-claim",
                "toEnd": "arrow",
            }],
        }),
        encoding="utf-8",
    )
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    catalog = HubCatalog(
        generated_at=NOW,
        artifacts=[HubArtifact(
            artifact_id="analysis:one:canvas",
            kind=ArtifactKind.ANALYSIS_CANVAS,
            format=ArtifactFormat.CANVAS,
            vault_path="analysis.canvas",
        )],
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    result = service.copy_knowledge_artifact(
        PROJECT_ID,
        "analysis:one:canvas",
        "analysis.canvas",
        catalog_provider=StaticCatalogProvider(catalog),
        vault_root=vault,
    )
    copied = json.loads((project_root / "docs" / result.relative_path).read_text())
    copied_text = "\n".join(node.get("text", "") for node in copied["nodes"])
    copied_ids = {node["id"] for node in copied["nodes"]}
    assert copied_ids.isdisjoint({"source-root", "source-claim"})
    assert {node["type"] for node in copied["nodes"]} == {"text"}
    assert copied["edges"][0]["id"] != "source-edge"
    assert copied["edges"][0]["fromNode"] in copied_ids
    assert copied["edges"][0]["toNode"] in copied_ids
    assert "Readable title" in copied_text
    assert "Readable evidence" in copied_text
    assert "sw-analysis-claim" not in copied_text
    assert "#^claim-task" not in copied_text
    assert "[[分析正文]]" not in copied_text


def test_knowledge_canvas_copy_rejects_node_without_standard_type(tmp_path):
    project_root = tmp_path / "project"
    vault = tmp_path / "vault"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    vault.mkdir()
    (vault / "analysis.canvas").write_text(
        json.dumps({
            "nodes": [{
                "id": "missing-type",
                "x": 0,
                "y": 0,
                "width": 400,
                "height": 160,
                "text": "Readable text",
            }],
            "edges": [],
        }),
        encoding="utf-8",
    )
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    catalog = HubCatalog(
        generated_at=NOW,
        artifacts=[HubArtifact(
            artifact_id="analysis:one:canvas",
            kind=ArtifactKind.ANALYSIS_CANVAS,
            format=ArtifactFormat.CANVAS,
            vault_path="analysis.canvas",
        )],
    )

    with pytest.raises(ProjectDocumentError, match="node type is invalid"):
        ProjectDocumentService(ProjectRegistry(registry_path)).copy_knowledge_artifact(
            PROJECT_ID,
            "analysis:one:canvas",
            "analysis.canvas",
            catalog_provider=StaticCatalogProvider(catalog),
            vault_root=vault,
        )
    assert not (project_root / "docs" / "analysis.canvas").exists()


def test_project_paste_is_additive_and_refuses_collision(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    service = ProjectDocumentService(ProjectRegistry(registry_path))
    result = service.paste_text(PROJECT_ID, "notes/pasted.md", "# Pasted\n")
    assert result.relative_path == "notes/pasted.md"
    assert (project_root / "docs" / "notes" / "pasted.md").read_text() == "# Pasted\n"
    with pytest.raises(DocumentCollisionError):
        service.paste_text(PROJECT_ID, "notes/pasted.md", "replacement")


def test_workspace_binding_requires_nonce_generation_and_instance_match():
    registry = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
        now=lambda: NOW,
    )
    nonce = registry.issue_nonce("hub-instance")
    lease = registry.bind(
        instance_token="hub-instance",
        nonce=nonce,
        profile_id="runtime",
        opaque_workspace_id="workspace-opaque",
        cmux_instance_fingerprint="sha256:" + "a" * 64,
        ttl=timedelta(minutes=5),
    )
    assert registry.is_bound("hub-instance")
    assert lease.service_generation == "service-1"
    with pytest.raises(ValueError, match="nonce"):
        registry.bind(
            instance_token="hub-instance",
            nonce=nonce,
            profile_id="runtime",
            opaque_workspace_id="other",
            cmux_instance_fingerprint="sha256:" + "a" * 64,
        )
    with pytest.raises(ValueError, match="cmux instance"):
        registry.require_binding(
            "hub-instance",
            cmux_instance_fingerprint="sha256:" + "b" * 64,
        )


def test_workspace_bind_rejects_instance_change_during_live_resolution():
    registry = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
        now=lambda: NOW,
    )
    fingerprints = iter(["sha256:" + "a" * 64, "sha256:" + "b" * 64])
    coordinator = WorkspaceBindingCoordinator(
        registry,
        resolve_workspace=lambda _opaque: "raw-workspace",
        instance_fingerprint=lambda: next(fingerprints),
    )
    nonce = coordinator.issue_nonce("hub-instance")

    with pytest.raises(ValueError, match="changed while binding"):
        coordinator.bind(
            instance_token="hub-instance",
            nonce=nonce,
            profile_id="runtime",
            opaque_workspace_id="opaque-workspace",
        )

    assert not registry.is_bound("hub-instance")


def test_workspace_mutation_rejects_instance_change_during_live_resolution():
    registry = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
        now=lambda: NOW,
    )
    nonce = registry.issue_nonce("hub-instance")
    registry.bind(
        instance_token="hub-instance",
        nonce=nonce,
        profile_id="runtime",
        opaque_workspace_id="opaque-workspace",
        cmux_instance_fingerprint="sha256:" + "a" * 64,
        ttl=timedelta(minutes=5),
    )
    current = ["sha256:" + "a" * 64]

    def resolve_workspace(_opaque):
        current[0] = "sha256:" + "b" * 64
        return "reused-raw-workspace"

    coordinator = WorkspaceBindingCoordinator(
        registry,
        resolve_workspace=resolve_workspace,
        instance_fingerprint=lambda: current[0],
    )

    with pytest.raises(ValueError, match="changed during workspace validation"):
        coordinator.require_current_binding("hub-instance")

    assert not registry.is_bound("hub-instance")


def test_task_request_is_bounded_and_command_is_server_derived(tmp_path):
    project_root = tmp_path / "project"
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["codex"],
            }],
        },
    )
    recipe = TaskRecipe(
        recipe_id="analyze-project",
        title="Analyze project",
        project_required=True,
        allowed_efforts=[TaskEffort.FAST, TaskEffort.STANDARD, TaskEffort.DEEP],
    )
    request = TaskRequest(
        recipe_id="analyze-project",
        project_id=PROJECT_ID,
        effort="deep",
        brief="Review this; $(touch /tmp/must-not-run)",
        idempotency_key="request-001",
    )
    invocation = CodexCommandBuilder(
        codex_executable=Path("/opt/codex/bin/codex"),
        project_registry=ProjectRegistry(registry_path),
        safety_policies={
            "default": TaskSafetyPolicy(
                policy_id="default",
                policy_version=1,
                model="gpt-5.6-codex",
                sandbox="workspace-write",
            )
        },
    ).build_new(recipe, request)
    assert invocation.argv == (
        "/opt/codex/bin/codex",
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--json",
        "-C",
        str(project_root.resolve()),
        "-m",
        "gpt-5.6-codex",
        "-s",
        "workspace-write",
        "-c",
        'approval_policy="never"',
        "-c",
        'model_reasoning_effort="high"',
        "-",
    )
    assert invocation.stdin == request.brief
    assert request.brief not in invocation.argv

    with pytest.raises(ValidationError):
        TaskRequest(
            recipe_id="analyze-project",
            project_id=PROJECT_ID,
            effort="standard",
            brief="x" * 8193,
            idempotency_key="request-002",
        )
    with pytest.raises(ValidationError):
        TaskRequest.model_validate({**request.model_dump(), "model": "unsafe"})


def test_codex_capability_probe_uses_argv_without_shell():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        stdout = (
            "--config --strict-config --model --sandbox --cd "
            "--ignore-user-config --ignore-rules --json"
            if argv == ["/opt/codex/bin/codex", "exec", "--help"]
            else f"Usage: codex exec {argv[2]} [OPTIONS] --json"
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    result = CodexCapabilityProbe(Path("/opt/codex/bin/codex"), runner=runner).probe()
    assert result.available is True
    assert [call[0] for call in calls] == [
        ["/opt/codex/bin/codex", "exec", "--help"],
        ["/opt/codex/bin/codex", "exec", "resume", "--help"],
        ["/opt/codex/bin/codex", "exec", "fork", "--help"],
    ]
    assert all(call[1]["shell"] is False for call in calls)


def test_v2_http_root_pages_libraries_and_keeps_writes_unbound(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    storage.mkdir()
    vault.mkdir()
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    project_path = tmp_path / "projects.json"
    tool_path = tmp_path / "tools.json"
    _write_registry(
        project_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    _write_registry(tool_path, {"schema_version": 1, "tools": []})
    provider = StaticCatalogProvider(_catalog())
    directory = HubDirectoryService(
        provider,
        ProjectRegistry(project_path),
        ToolRegistry(tool_path),
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=provider,
        directory_service=directory,
        project_document_service=ProjectDocumentService(ProjectRegistry(project_path)),
    )
    try:
        port = server.server_address[1]
        root = json.loads(_request(port, "/api/v2/directory").read())
        compatibility = json.loads(_request(port, "/api/v1/catalog").read())
        assert root["knowledge_catalog"] == compatibility
        page = json.loads(_request(port, "/api/v2/libraries/papers/items?limit=2").read())
        assert len(page["items"]) == 2
        assert page["next_cursor"]

        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        body = json.dumps({"source_path": "missing.md", "destination_path": "copy.md"}).encode()
        with pytest.raises(urllib.error.HTTPError) as error:
            _request(
                port,
                f"/api/v2/projects/{PROJECT_ID}/docs/copy",
                method="POST",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{port}",
                    "X-Scholar-Hub-Token": token,
                    "X-Scholar-Hub-Instance": "unbound-instance",
                },
            )
        assert error.value.code == 409
        assert json.loads(error.value.read())["code"] == "headless_read_only"
    finally:
        server.shutdown()
        server.server_close()


def test_typed_paper_attachment_and_analysis_landings_keep_raw_urls_internal(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    (storage / "PDFD2345").mkdir()
    (storage / "PDFD2345" / "paper.pdf").write_bytes(b"%PDF-1.7\n")
    provider = StaticCatalogProvider(
        HubCatalog(
            generated_at=NOW,
            resources=[
                HubResource(
                    resource_id="paper:landing",
                    kind="paper",
                    title="Typed landing",
                    authors=["A. Author"],
                    zotero={"item_key": "PAPR2345", "attachment_key": "PDFD2345"},
                )
            ],
            artifacts=[
                HubArtifact(
                    artifact_id="analysis:landing",
                    kind=ArtifactKind.PAPER_ANALYSIS,
                    format=ArtifactFormat.MARKDOWN,
                    vault_path="analysis/landing.md",
                )
            ],
        )
    )
    directory = HubDirectoryService(
        provider,
        ProjectRegistry(tmp_path / "projects.json"),
        ToolRegistry(tmp_path / "tools.json"),
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=provider,
        directory_service=directory,
    )
    try:
        response = _request(
            server.server_address[1],
            "/hub/item?library_id=papers&item_type=paper&item_id=paper%3Alanding",
        )
        html = response.read().decode("utf-8")
        assert "Typed landing" in html
        assert "papers:paper:paper:landing" in html
        assert "item_type=attachment" in html
        assert "/open/paper/PDFD2345" not in html

        attachment = _request(
            server.server_address[1],
            "/hub/item?library_id=papers&item_type=attachment&item_id=PDFD2345",
        ).read().decode("utf-8")
        assert "papers:attachment:PDFD2345" in attachment
        assert 'href="/open/paper/PDFD2345"' in attachment

        analysis = _request(
            server.server_address[1],
            "/hub/item?library_id=knowledge&item_type=artifact&item_id=analysis%3Alanding",
        ).read().decode("utf-8")
        assert "knowledge:artifact:analysis:landing" in analysis
        assert "/hub/?artifact=analysis%3Alanding" in analysis
        assert directory.resolve_item(
            TypedEntityRef(
                library_id="papers",
                item_type="artifact",
                item_id="analysis:landing",
            )
        ) is None
    finally:
        server.shutdown()
        server.server_close()


def test_hub_ui_is_library_first_and_surfaces_read_only_binding_state(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
    )
    try:
        port = server.server_address[1]
        html = _request(port, "/hub/").read().decode("utf-8")
        script = _request(port, "/hub/assets/hub.js").read().decode("utf-8")
        assert 'id="library-nav"' in html
        assert 'id="operation-status"' in html
        assert 'id="project-ops-dialog"' in html
        assert "相对于已注册项目的" in html
        assert "Libraries" in html
        assert "Knowledge Contexts" in html
        assert "/api/v2/directory" in script
        assert "/api/v2/libraries/" in script
        assert 'query.set("query"' in script
        assert 'query.set("sort"' in script
        assert 'query.set("type"' in script
        assert "/hub/item?" in script
        assert "state.catalog.resources" in script
        assert "`/open/paper/${" not in script
        assert "knowledge_catalog" in script
        assert "只读 · 未绑定工作区" in script
        assert "只读入口；请在 cmux 终端运行 scholar-workflow open-hub" in script
        assert "Boolean(hubInstance())" in script
        assert "openProjectOperations" in script
        assert "/docs/${operation}" in script
        assert "confirmation_required" in script
        assert "innerHTML" not in script
    finally:
        server.shutdown()
        server.server_close()


def test_hub_doctor_verifies_structured_v2_health_on_temporary_port(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        owner_mode="headless",
    )
    try:
        result = CliRunner().invoke(
            main,
            ["hub-doctor", "--port", str(server.server_address[1]), "--json"],
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["protocol"]["version"] == 2
        assert report["hub_directory"]["schema_version"] == 2
        assert report["owner_mode"] == "headless"
        assert report["task_execution"] is False
        assert report["process"]["pid"] > 0
        assert report["process"]["executable"]
        assert report["origin"].endswith(str(server.server_address[1]))
        assert report["roots"]["catalog"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_bound_v2_project_copy_accepts_only_relative_docs_paths(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    storage.mkdir()
    vault.mkdir()
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    (project_root / "docs" / "source.md").write_text("body", encoding="utf-8")
    project_path = tmp_path / "projects.json"
    _write_registry(
        project_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    bindings = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
    )
    nonce = bindings.issue_nonce("bound-instance")
    bindings.bind(
        instance_token="bound-instance",
        nonce=nonce,
        profile_id="runtime",
        opaque_workspace_id="workspace-opaque",
        cmux_instance_fingerprint="sha256:" + "a" * 64,
    )
    coordinator = WorkspaceBindingCoordinator(
        bindings,
        resolve_workspace=lambda _opaque: "raw-workspace",
        instance_fingerprint=lambda: "sha256:" + "a" * 64,
    )
    provider = StaticCatalogProvider(_catalog())
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=provider,
        project_document_service=ProjectDocumentService(ProjectRegistry(project_path)),
        binding_coordinator=coordinator,
        owner_mode="cmux-visible",
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        response = _request(
            port,
            f"/api/v2/projects/{PROJECT_ID}/docs/copy",
            method="POST",
            data=json.dumps({
                "source_path": "source.md",
                "destination_path": "nested/copy.md",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "X-Scholar-Hub-Token": token,
                "X-Scholar-Hub-Instance": "bound-instance",
            },
        )
        assert json.loads(response.read())["relative_path"] == "nested/copy.md"
        assert (project_root / "docs" / "nested" / "copy.md").read_text() == "body"

        pasted = _request(
            port,
            f"/api/v2/projects/{PROJECT_ID}/docs/paste",
            method="POST",
            data=json.dumps({
                "destination_path": "nested/pasted.md",
                "content": "# Pasted\n",
            }).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "X-Scholar-Hub-Token": token,
                "X-Scholar-Hub-Instance": "bound-instance",
            },
        )
        assert json.loads(pasted.read())["relative_path"] == "nested/pasted.md"
        assert (project_root / "docs" / "nested" / "pasted.md").read_text() == "# Pasted\n"
    finally:
        server.shutdown()
        server.server_close()


def test_workspace_nonce_and_bind_api_resolve_opaque_workspace_server_side(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    bindings = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
    )
    resolved = []
    coordinator = WorkspaceBindingCoordinator(
        bindings,
        resolve_workspace=lambda opaque: resolved.append(opaque) or "raw-never-returned",
        instance_fingerprint=lambda: "sha256:" + "c" * 64,
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        binding_coordinator=coordinator,
        owner_mode="cmux-visible",
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
            "X-Scholar-Hub-Instance": "hub-instance",
        }
        nonce_response = _request(
            port,
            "/api/v2/workspaces/nonce",
            method="POST",
            headers=headers,
            data=b"{}",
        )
        nonce = json.loads(nonce_response.read())["nonce"]
        binding = _request(
            port,
            "/api/v2/workspaces/bind",
            method="POST",
            headers=headers,
            data=json.dumps({
                "nonce": nonce,
                "profile_id": "runtime",
                "workspace_id": "opaque-workspace",
            }).encode(),
        )
        payload = json.loads(binding.read())
        assert payload["ok"] is True
        assert payload["profile_id"] == "runtime"
        assert resolved == ["opaque-workspace"]
        directory = json.loads(
            _request(port, "/api/v2/directory?instance=hub-instance").read()
        )
        assert directory["operations"]["bound"] is True
        status = json.loads(
            _request(port, "/api/v2/workspaces/status?instance=hub-instance").read()
        )
        assert status == {
            "bound": True,
            "service_generation": bindings.service_generation,
            "workspace_binding_available": True,
        }
        assert "raw-never-returned" not in json.dumps(payload)
    finally:
        server.shutdown()
        server.server_close()


def test_v2_mutation_revalidates_live_workspace_before_each_write(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    project_root = tmp_path / "project"
    storage.mkdir()
    vault.mkdir()
    (project_root / "docs").mkdir(parents=True)
    _write_project_layout(project_root)
    (project_root / "docs" / "source.md").write_text("body", encoding="utf-8")
    registry_path = tmp_path / "projects.json"
    _write_registry(
        registry_path,
        {
            "schema_version": 1,
            "projects": [{
                "project_id": PROJECT_ID,
                "display_name": "Project One",
                "root": str(project_root),
                "enabled": True,
                "capabilities": ["docs"],
            }],
        },
    )
    bindings = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
    )
    workspace_live = True

    def resolve_workspace(_opaque):
        if not workspace_live:
            raise ValueError("workspace disappeared")
        return "raw-workspace"

    coordinator = WorkspaceBindingCoordinator(
        bindings,
        resolve_workspace=resolve_workspace,
        instance_fingerprint=lambda: "sha256:" + "a" * 64,
    )
    nonce = coordinator.issue_nonce("bound-instance")
    coordinator.bind(
        instance_token="bound-instance",
        nonce=nonce,
        profile_id="runtime",
        opaque_workspace_id="opaque-workspace",
    )
    workspace_live = False
    provider = StaticCatalogProvider(_catalog())
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=provider,
        project_document_service=ProjectDocumentService(ProjectRegistry(registry_path)),
        binding_coordinator=coordinator,
        owner_mode="cmux-visible",
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        with pytest.raises(urllib.error.HTTPError) as error:
            _request(
                port,
                f"/api/v2/projects/{PROJECT_ID}/docs/copy",
                method="POST",
                data=json.dumps({
                    "source_path": "source.md",
                    "destination_path": "copy.md",
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{port}",
                    "X-Scholar-Hub-Token": token,
                    "X-Scholar-Hub-Instance": "bound-instance",
                },
            )
        assert error.value.code == 409
        assert json.loads(error.value.read())["code"] == "workspace_unbound"
        assert not (project_root / "docs" / "copy.md").exists()
    finally:
        server.shutdown()
        server.server_close()


def test_headless_service_stays_read_only_even_with_an_existing_lease(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    bindings = WorkspaceBindingRegistry(
        service_generation="service-1",
        profiles=[WorkspaceProfile(profile_id="runtime", role="runtime")],
    )
    coordinator = WorkspaceBindingCoordinator(
        bindings,
        resolve_workspace=lambda _opaque: "raw-workspace",
        instance_fingerprint=lambda: "sha256:" + "a" * 64,
    )
    nonce = coordinator.issue_nonce("bound-instance")
    coordinator.bind(
        instance_token="bound-instance",
        nonce=nonce,
        profile_id="runtime",
        opaque_workspace_id="opaque-workspace",
    )
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
        binding_coordinator=coordinator,
        owner_mode="headless",
    )
    try:
        port = server.server_address[1]
        token = json.loads(_request(port, "/api/v1/session").read())["csrf_token"]
        headers = {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
            "X-Scholar-Hub-Token": token,
            "X-Scholar-Hub-Instance": "bound-instance",
        }
        with pytest.raises(urllib.error.HTTPError) as error:
            _request(
                port,
                "/api/v2/workspaces/nonce",
                method="POST",
                headers=headers,
                data=b"{}",
            )
        assert error.value.code == 409
        assert json.loads(error.value.read())["code"] == "headless_read_only"

        with pytest.raises(urllib.error.HTTPError) as mutation_error:
            _request(
                port,
                f"/api/v2/projects/{PROJECT_ID}/docs/copy",
                method="POST",
                headers=headers,
                data=json.dumps({
                    "source_path": "source.md",
                    "destination_path": "copy.md",
                }).encode(),
            )
        assert mutation_error.value.code == 409
        assert json.loads(mutation_error.value.read())["code"] == "headless_read_only"

        with pytest.raises(urllib.error.HTTPError) as legacy_error:
            _request(
                port,
                "/api/v1/actions/anything",
                method="POST",
                headers=headers,
                data=b"{}",
            )
        assert legacy_error.value.code == 409
        assert json.loads(legacy_error.value.read())["code"] == "headless_read_only"

        directory = json.loads(
            _request(port, "/api/v2/directory?instance=bound-instance").read()
        )
        assert directory["operations"]["bound"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_v2_health_reports_explicit_build_provider_worker_and_cmux_state(tmp_path):
    storage = tmp_path / "storage"
    vault = tmp_path / "vault"
    storage.mkdir()
    vault.mkdir()
    server = start_hub_server(
        port=0,
        storage_root=storage,
        vault_root=vault,
        catalog_provider=StaticCatalogProvider(_catalog()),
    )
    try:
        payload = json.loads(
            _request(server.server_address[1], "/api/v2/health").read()
        )
        assert payload["service"]["name"] == "scholar-workflow-hub"
        assert payload["package"]["name"] == "scholar-workflow"
        assert payload["protocol"] == {"name": "hub-http", "version": 2}
        assert payload["hub_directory"]["schema_version"] == 2
        assert payload["owner_mode"] == "headless"
        assert payload["cmux"]["instance_fingerprint"] is None
        assert payload["worker_capabilities"]["task_execution"] is False
        assert payload["log"]["path"] is None
        assert set(payload["provider_capabilities"]) == {"papers", "projects", "tools"}
    finally:
        server.shutdown()
        server.server_close()
