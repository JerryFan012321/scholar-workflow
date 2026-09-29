from __future__ import annotations

import hashlib
import json
import plistlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import fitz
import pytest

import scholar_workflow.hub.fields as fields_module
from scholar_workflow.adapters.zotero_local import ZoteroAttachmentLocator
from scholar_workflow.hub.field_transaction import _validate_manifest_with_staged_documents
from scholar_workflow.hub.fields import (
    FieldCandidateExpired,
    FieldDefinition,
    FieldManifest,
    FieldNavigationGroup,
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.hub.pdf_snapshot import (
    AnnotationSnapshotError,
    AnnotationSnapshotService,
    UnsupportedAnnotationSnapshot,
)
from scholar_workflow.hub.zotflow import (
    AnnotationIR,
    PdfRef,
    RegisteredSourceZotFlowAdapter,
    ZotFlowCapability,
    ZotFlowReaderAdapter,
)

_ZOTFLOW_NOTE = (
    "---\n"
    "zotflow-locked: true\n"
    "zotero-key: T3RY3HUA\n"
    "library-id: 17685951\n"
    "---\n"
    "# ZotFlow Source Note\n"
)
_VAULT_ID = "1111111111111111"


def _obsidian_config(tmp_path: Path, vault: Path) -> Path:
    config = tmp_path / "obsidian.json"
    config.write_text(json.dumps({"vaults": {_VAULT_ID: {"path": str(vault)}}}), encoding="utf-8")
    return config


def test_zotflow_owner_requires_frontmatter_and_complete_unique_identity() -> None:
    classify = fields_module._external_markdown_owner
    assert classify(_ZOTFLOW_NOTE.encode()) == "zotflow"
    assert classify(_ZOTFLOW_NOTE.replace("zotflow-locked:", '"zotflow-locked":').encode()) == "zotflow"
    assert classify(_ZOTFLOW_NOTE.replace("true", "false").encode()) == "zotflow"
    assert classify(("# Human note\n" + _ZOTFLOW_NOTE).encode()) is None
    assert classify(b"---\nzotero-key: T3RY3HUA\nlibrary-id: 17685951\n---\n") is None
    assert not fields_module._has_scholar_frontmatter_identity(
        (_ZOTFLOW_NOTE + "\nsw_kind: paper-analysis\n").encode()
    )
    assert classify(b"---\nzotflow-locked: true\n---\n") == "unverified-zotflow"
    assert classify(
        _ZOTFLOW_NOTE.replace("zotflow-locked: true", "zotflow-locked: true\nzotflow-locked: false").encode()
    ) == "unverified-zotflow"
    assert classify(
        _ZOTFLOW_NOTE.replace("zotflow-locked: true", 'zotflow-locked: true\n"zotflow-locked": false').encode()
    ) == "unverified-zotflow"
    with pytest.raises(FieldRegistryError, match="conflicting Scholar and external"):
        fields_module._assert_field_owned_markdown(
            _ZOTFLOW_NOTE.replace("---\n#", "sw_kind: paper-analysis\n---\n#").encode()
        )


def test_field_preview_excludes_external_owner_without_directory_name_rule(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    field = vault / "World Models"
    field.mkdir()
    (field / "00-领域入口.md").write_text("# World Models\n", encoding="utf-8")
    projected = vault / "arbitrary ZotFlow projection" / "My Library"
    projected.mkdir(parents=True)
    (projected / "@paper.md").write_text(_ZOTFLOW_NOTE, encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(vault)

    assert [row.relative_root for row in preview.fields] == ["World Models"]
    assert [row.model_dump() for row in preview.external_managed_documents] == [
        {"relative_path": "arbitrary ZotFlow projection/My Library/@paper.md", "owner": "zotflow"}
    ]
    assert preview.unmapped_markdown == []
    assert not service.registry.path.exists()
    assert not (vault / ".scholar-workflow").exists()

    direct = service.preview(projected)
    assert direct.fields == []
    assert len(direct.external_managed_documents) == 1
    assert direct.unmapped_markdown == []


def test_mixed_field_auto_navigation_excludes_zotflow_note(tmp_path: Path) -> None:
    selected = tmp_path / "mixed"
    selected.mkdir()
    (selected / "00-领域入口.md").write_text("# Human\n", encoding="utf-8")
    (selected / "projection.md").write_text(_ZOTFLOW_NOTE, encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(selected)

    assert [group.items for group in preview.fields[0].navigation] == [["00-领域入口.md"]]
    assert [row.relative_path for row in preview.external_managed_documents] == ["projection.md"]
    assert preview.unmapped_markdown == []


@pytest.mark.parametrize(
    "owner_note,expected_conflict",
    [
        ("---\nzotflow-locked: true\n---\n# Incomplete\n", "incomplete or invalid"),
        (_ZOTFLOW_NOTE.replace("---\n#", "sw_kind: paper-analysis\n---\n#"), "ownership conflict"),
    ],
)
def test_field_preview_reports_untrusted_or_conflicting_owner(
    tmp_path: Path, owner_note: str, expected_conflict: str
) -> None:
    selected = tmp_path / "mixed"
    selected.mkdir()
    (selected / "00-领域入口.md").write_text("# Human\n", encoding="utf-8")
    (selected / "projection.md").write_text(owner_note, encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(selected)

    assert len(preview.external_managed_documents) == 1
    assert any(expected_conflict in message for message in preview.conflicts)
    with pytest.raises(FieldRegistryError, match="unresolved conflicts"):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)


def test_manifest_and_single_file_writes_reject_external_owner(tmp_path: Path) -> None:
    selected = tmp_path / "mixed"
    selected.mkdir()
    home = selected / "00-领域入口.md"
    home.write_text("# Human\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    preview = service.preview(selected)
    field_id = preview.fields[0].field_id
    service.confirm(preview.candidate_token, field_id)
    base = service.read_document(field_id, home.name)["revision"]

    with pytest.raises(FieldRegistryError, match="ZotFlow-managed"):
        service.write_document(field_id, home.name, content=_ZOTFLOW_NOTE, base_revision=base)
    assert home.read_text(encoding="utf-8") == "# Human\n"

    home.write_text(_ZOTFLOW_NOTE, encoding="utf-8")
    with pytest.raises(FieldRegistryError, match="ZotFlow-managed"):
        service.read_document(field_id, home.name)
    with pytest.raises(FieldRegistryError, match="ZotFlow-managed"):
        service.write_document(
            field_id, home.name, content="# New human text\n",
            base_revision="sha256:" + hashlib.sha256(_ZOTFLOW_NOTE.encode()).hexdigest(),
        )
    with pytest.raises(FieldRegistryError, match="ZotFlow-managed"):
        service._validate_manifest_paths(
            selected, FieldManifest(source_id=preview.source_id, fields=preview.fields)
        )
    assert home.read_text(encoding="utf-8") == _ZOTFLOW_NOTE


@pytest.mark.parametrize("external_is_old", [False, True])
def test_field_transaction_rejects_external_owned_staged_or_existing_markdown(
    tmp_path: Path, external_is_old: bool
) -> None:
    selected = tmp_path / "field"
    selected.mkdir()
    note = selected / "00-领域入口.md"
    note.write_text(_ZOTFLOW_NOTE if external_is_old else "# Human\n", encoding="utf-8")
    field = FieldDefinition(
        field_id="de9bd899-7b1c-46cd-a411-e7488862e6a7",
        title="Field",
        relative_root=".",
        home=note.name,
        navigation=[FieldNavigationGroup(label="入口", items=[note.name])],
    )
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    proposed = b"# Human\n" if external_is_old else _ZOTFLOW_NOTE.encode()

    with pytest.raises(FieldRegistryError, match="ZotFlow-managed"):
        _validate_manifest_with_staged_documents(
            service,
            selected,
            FieldManifest(source_id="bcb6be95-75a4-46f0-97e8-d35b02dfae21", fields=[field]),
            field,
            {note.name: proposed},
        )
    assert note.read_text(encoding="utf-8") == (_ZOTFLOW_NOTE if external_is_old else "# Human\n")


@pytest.mark.parametrize("field_name", ["home", "navigation"])
def test_field_manifest_document_targets_must_be_markdown(field_name: str) -> None:
    attributes = {
        "field_id": "de9bd899-7b1c-46cd-a411-e7488862e6a7",
        "title": "World Models",
        "relative_root": ".",
        "home": "00-领域入口.md",
        "navigation": [FieldNavigationGroup(label="Read", items=["notes/paper.md"])],
    }
    FieldDefinition.model_validate(attributes)
    if field_name == "home":
        attributes["home"] = "tree.canvas"
    else:
        attributes["navigation"] = [{"label": "Read", "items": ["tree.canvas"]}]

    with pytest.raises(ValueError, match="Markdown"):
        FieldDefinition.model_validate(attributes)


def test_field_preview_is_read_only_until_one_time_confirm_and_cas_write(tmp_path: Path):
    selected = tmp_path / "世界模型"
    selected.mkdir()
    home = selected / "00-领域入口.md"
    home.write_text("# 世界模型\n", encoding="utf-8")
    (selected / "JEPA.md").write_text("# JEPA\n", encoding="utf-8")
    registry = KnowledgeSourceRegistry(tmp_path / "state" / "sources.json")
    service = FieldService(registry)

    preview = service.preview(selected)

    assert preview.existing_manifest is False
    assert [field.title for field in preview.fields] == ["世界模型"]
    assert preview.legacy_link_changes == []
    assert not (selected / ".scholar-workflow").exists()
    assert not registry.path.exists()

    manifest = service.confirm(preview.candidate_token, preview.fields[0].field_id)
    assert manifest.fields[0].relative_root == "."
    assert (selected / ".scholar-workflow" / "fields.yml").is_file()
    assert registry.path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FieldCandidateExpired):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)

    field_id = manifest.fields[0].field_id
    document = service.read_document(field_id, "00-领域入口.md")
    changed = service.write_document(
        field_id,
        "00-领域入口.md",
        content="# 世界模型\n\n新正文。\n",
        base_revision=document["revision"],
    )
    assert changed["revision"].startswith("sha256:")
    with pytest.raises(Exception, match="changed after"):
        service.write_document(
            field_id,
            "00-领域入口.md",
            content="stale",
            base_revision=document["revision"],
        )


def test_field_preview_reports_legacy_links_and_rejects_changed_content(tmp_path: Path):
    selected = tmp_path / "世界模型"
    selected.mkdir()
    home = selected / "00-领域入口.md"
    home.write_text(
        "[paper](http://127.0.0.1:23128/open/paper/ABCD2345)\n",
        encoding="utf-8",
    )
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(selected)

    assert [row.model_dump() for row in preview.legacy_link_changes] == [
        {
            "relative_path": "00-领域入口.md",
            "attachment_key": "ABCD2345",
            "replacement": "zotero://open-pdf/library/items/ABCD2345",
            "occurrences": 1,
        }
    ]
    home.write_text("# changed after preview\n", encoding="utf-8")
    with pytest.raises(FieldRegistryError, match="content changed"):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)

    assert not (selected / ".scholar-workflow").exists()
    assert not service.registry.path.exists()


@pytest.mark.parametrize(
    "artifact_name,initial,changed",
    [
        ("JEPA.canvas", '{"nodes": []}', '{"nodes": [{"id": "new"}]}'),
        ("JEPA.analysis.json", '{"version": 1}', '{"version": 2}'),
    ],
)
def test_field_preview_rejects_changed_canvas_or_sidecar(
    tmp_path: Path,
    artifact_name: str,
    initial: str,
    changed: str,
) -> None:
    selected = tmp_path / "世界模型"
    selected.mkdir()
    (selected / "00-领域入口.md").write_text("# 世界模型\n", encoding="utf-8")
    artifact = selected / artifact_name
    artifact.write_text(initial, encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(selected)
    artifact.write_text(changed, encoding="utf-8")

    with pytest.raises(FieldRegistryError, match="content changed"):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)
    assert not (selected / ".scholar-workflow").exists()
    assert not service.registry.path.exists()


def test_field_preview_rejects_new_field_artifact_after_selection(tmp_path: Path) -> None:
    selected = tmp_path / "世界模型"
    selected.mkdir()
    (selected / "00-领域入口.md").write_text("# 世界模型\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    preview = service.preview(selected)
    (selected / "unreviewed.canvas").write_text('{"nodes": []}', encoding="utf-8")

    with pytest.raises(FieldRegistryError, match="content changed"):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)


def test_field_manifest_rejects_symlinked_state_directory(tmp_path: Path):
    selected = tmp_path / "field"
    outside = tmp_path / "outside"
    selected.mkdir()
    outside.mkdir()
    (selected / "00-领域入口.md").write_text("# Field\n", encoding="utf-8")
    (selected / ".scholar-workflow").symlink_to(outside, target_is_directory=True)
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))

    with pytest.raises(Exception, match="trusted real directory"):
        service.preview(selected)

    assert not (outside / "fields.yml").exists()


def test_field_confirm_rechecks_state_directory_after_preview(tmp_path: Path):
    selected = tmp_path / "field"
    outside = tmp_path / "outside"
    selected.mkdir()
    outside.mkdir()
    (selected / "00-领域入口.md").write_text("# Field\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    preview = service.preview(selected)
    (selected / ".scholar-workflow").symlink_to(outside, target_is_directory=True)

    with pytest.raises(FieldRegistryError):
        service.confirm(preview.candidate_token, preview.fields[0].field_id)

    assert not (outside / "fields.yml").exists()
    assert not service.registry.path.exists()


def _field_with_nested_document(tmp_path: Path, name: str = "doc.md"):
    selected = tmp_path / "field"
    nested = selected / "sub"
    nested.mkdir(parents=True)
    (selected / "00-领域入口.md").write_text("# Field\n", encoding="utf-8")
    document = nested / name
    document.write_text("original\n", encoding="utf-8")
    service = FieldService(KnowledgeSourceRegistry(tmp_path / "sources.json"))
    preview = service.preview(selected)
    manifest = service.confirm(preview.candidate_token, preview.fields[0].field_id)
    return service, manifest.fields[0].field_id, selected, document


def test_field_write_rejects_parent_symlink_swap(tmp_path: Path, monkeypatch):
    service, field_id, selected, _document = _field_with_nested_document(tmp_path)
    base = service.read_document(field_id, "sub/doc.md")
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "doc.md"
    victim.write_text("victim\n", encoding="utf-8")
    held = selected / "held-sub"
    original_open = fields_module._open_directory_chain
    opens = 0

    def swap_before_recheck(root: Path, parts: tuple[str, ...] = ()) -> int:
        nonlocal opens
        if Path(root) == selected and parts == ("sub",):
            opens += 1
            if opens == 2:
                (selected / "sub").rename(held)
                (selected / "sub").symlink_to(outside, target_is_directory=True)
        return original_open(root, parts)

    monkeypatch.setattr(fields_module, "_open_directory_chain", swap_before_recheck)

    with pytest.raises(FieldRegistryError):
        service.write_document(
            field_id,
            "sub/doc.md",
            content="new\n",
            base_revision=base["revision"],
        )

    assert victim.read_text(encoding="utf-8") == "victim\n"
    assert (held / "doc.md").read_text(encoding="utf-8") == "original\n"


def test_field_cas_allows_exactly_one_concurrent_writer(tmp_path: Path):
    service, field_id, _selected, _document = _field_with_nested_document(tmp_path)
    base = service.read_document(field_id, "sub/doc.md")
    barrier = Barrier(2)

    def save(content: str) -> str:
        barrier.wait()
        try:
            service.write_document(
                field_id,
                "sub/doc.md",
                content=content,
                base_revision=base["revision"],
            )
        except FieldRegistryError:
            return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ("first\n", "second\n")))

    assert sorted(results) == ["conflict", "saved"]


@pytest.mark.parametrize(
    "current,proposed",
    [
        ("---\nsw_kind: paper-analysis\n---\n# Analysis\n", "changed\n"),
        ("original\n", "---\nsw_kind: 'paper-analysis'\n---\n# Analysis\n"),
        ("<!-- sw-analysis-field -->\n# Analysis\n", "changed\n"),
    ],
)
def test_field_write_rejects_analysis_identity_in_either_version(
    tmp_path: Path, current: str, proposed: str
) -> None:
    service, field_id, _selected, document = _field_with_nested_document(tmp_path)
    document.write_text(current, encoding="utf-8")
    revision = service.read_document(field_id, "sub/doc.md")["revision"]

    with pytest.raises(FieldRegistryError, match="validated Field transaction"):
        service.write_document(
            field_id,
            "sub/doc.md",
            content=proposed,
            base_revision=revision,
        )

    assert document.read_text(encoding="utf-8") == current


@pytest.mark.parametrize(
    "markdown_name,peer_name",
    [
        ("doc.md", "doc.analysis.json"),
        ("doc.md", "doc.canvas"),
        ("JEPA分析.md", "JEPA解析树.canvas"),
    ],
)
def test_field_write_rejects_analysis_peers_in_same_directory(
    tmp_path: Path, markdown_name: str, peer_name: str
) -> None:
    service, field_id, _selected, document = _field_with_nested_document(
        tmp_path, markdown_name
    )
    peer = document.with_name(peer_name)
    peer.write_text("{}", encoding="utf-8")
    relative = f"sub/{markdown_name}"
    revision = service.read_document(field_id, relative)["revision"]

    with pytest.raises(FieldRegistryError, match="validated Field transaction"):
        service.write_document(
            field_id,
            relative,
            content="changed\n",
            base_revision=revision,
        )

    assert document.read_text(encoding="utf-8") == "original\n"
    assert peer.read_text(encoding="utf-8") == "{}"


def test_field_write_rejects_symlinked_analysis_peer(tmp_path: Path) -> None:
    service, field_id, _selected, document = _field_with_nested_document(tmp_path)
    document.with_name("doc.canvas").symlink_to(tmp_path / "missing.canvas")
    revision = service.read_document(field_id, "sub/doc.md")["revision"]

    with pytest.raises(FieldRegistryError, match="validated Field transaction"):
        service.write_document(
            field_id,
            "sub/doc.md",
            content="changed\n",
            base_revision=revision,
        )

    assert document.read_text(encoding="utf-8") == "original\n"


def _write_obsidian_app(app: Path, version: str) -> None:
    info = app / "Contents" / "Info.plist"
    info.parent.mkdir(parents=True)
    with info.open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": version}, handle)


def test_zotflow_probe_enforces_app_version_and_builds_documented_uri(tmp_path: Path):
    vault = tmp_path / "vault"
    plugin = vault / ".obsidian" / "plugins" / "zotflow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": "1.6.6", "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (vault / ".obsidian" / "community-plugins.json").write_text(
        '["zotflow"]', encoding="utf-8"
    )
    app = tmp_path / "Obsidian.app"
    _write_obsidian_app(app, "1.12.7")
    adapter = ZotFlowReaderAdapter(
        vault, app_path=app, obsidian_config_path=_obsidian_config(tmp_path, vault)
    )

    capability = adapter.probe()

    assert capability.available is False
    assert "1.13.4" in (capability.reason or "")
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash="md5:" + "a" * 32,
    )
    assert adapter.attachment_uri(pdf_ref) == (
        f"obsidian://zotflow?vault={_VAULT_ID}&type=open-attachment&libraryID=1&key=PDFD2345"
    )


def test_zotflow_probe_accepts_case_alias_only_for_same_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    canonical_parent = tmp_path / "Documents"
    vault = canonical_parent / "vault"
    plugin = vault / ".obsidian" / "plugins" / "zotflow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": "1.6.6", "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (vault / ".obsidian" / "community-plugins.json").write_text(
        '["zotflow"]', encoding="utf-8"
    )
    alias_parent = tmp_path / "documents"
    if not alias_parent.exists():
        alias_parent.symlink_to(canonical_parent, target_is_directory=True)
    configured_vault = alias_parent / "vault"
    assert configured_vault.samefile(vault)

    # On a case-sensitive filesystem, preserve the symlink alias in resolve()
    # to model macOS paths whose different case spellings resolve to one inode.
    original_resolve = Path.resolve
    if configured_vault.resolve(strict=True) == vault.resolve(strict=True):
        def preserve_case_alias(path: Path, strict: bool = False) -> Path:
            resolved = original_resolve(path, strict=strict)
            return path if path == configured_vault else resolved

        monkeypatch.setattr(Path, "resolve", preserve_case_alias)
    assert configured_vault.resolve(strict=True) != vault.resolve(strict=True)

    app = tmp_path / "Obsidian.app"
    _write_obsidian_app(app, "1.13.7")
    storage = tmp_path / "storage"
    storage.mkdir()
    reported_vault = vault

    def cli_runner(_argv, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="=> " + json.dumps({
                "protocol": "zotflow-local-v1",
                "vault": str(reported_vault),
                "enabled": True,
                "local": True,
                "storagePath": str(storage),
            }),
        )

    adapter = ZotFlowReaderAdapter(
        configured_vault, app_path=app, cli_runner=cli_runner,
        obsidian_config_path=_obsidian_config(tmp_path, vault),
    )
    assert adapter.probe().available is True

    reported_vault = tmp_path / "Other" / "vault"
    reported_vault.mkdir(parents=True)
    capability = adapter.probe()
    assert capability.available is False
    assert "registered ZotFlow Vault" in (capability.reason or "")


def test_zotflow_probe_rejects_vault_symlink_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    original_resolve = Path.resolve

    def resolve_with_loop(path: Path, strict: bool = False) -> Path:
        if path == loop:
            raise RuntimeError("Symlink loop")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", resolve_with_loop)

    def cli_runner(_argv, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="=> " + json.dumps({
                "protocol": "zotflow-local-v1",
                "vault": str(loop),
                "enabled": True,
                "local": True,
                "storagePath": str(tmp_path),
            }),
        )

    adapter = ZotFlowReaderAdapter(
        vault, cli_runner=cli_runner,
        obsidian_config_path=_obsidian_config(tmp_path, vault),
    )
    monkeypatch.setattr(adapter, "_version_probe", lambda: ZotFlowCapability(available=True))

    capability = adapter.probe()

    assert capability.available is False
    assert "registered ZotFlow Vault" in (capability.reason or "")


def test_zotflow_adapter_discovers_only_explicit_registered_sources(tmp_path: Path):
    vault = tmp_path / "vault"
    plugin = vault / ".obsidian" / "plugins" / "zotflow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": "1.6.6", "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (vault / ".obsidian" / "community-plugins.json").write_text(
        '["zotflow"]', encoding="utf-8"
    )
    field_root = vault / "World Models"
    field_root.mkdir()
    (field_root / "00-领域入口.md").write_text("# Vault\n", encoding="utf-8")
    app = tmp_path / "Obsidian.app"
    _write_obsidian_app(app, "1.13.7")
    calls = []
    storage = tmp_path / "storage"
    pdf = storage / "PDFD2345" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7\n")
    pdf_hash = "md5:" + hashlib.md5(pdf.read_bytes()).hexdigest()

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Result", (), {"returncode": 0})()

    def cli_runner(_argv, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="=> " + json.dumps({
                "protocol": "zotflow-local-v1",
                "vault": str(vault),
                "enabled": True,
                "local": True,
                "storagePath": str(storage),
            }),
        )

    class LocalZotero:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get_item(self, _key):
            return {"data": {
                "itemType": "attachment",
                "linkMode": "imported_file",
                "filename": pdf.name,
            }}

        def resolve_attachment_locator(self, _key):
            return ZoteroAttachmentLocator(
                attachment_key="PDFD2345",
                library_id="1",
                content_hash=pdf_hash,
                path=pdf,
                filename=pdf.name,
            )

    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    adapter = RegisteredSourceZotFlowAdapter(
        registry,
        app_path=app,
        runner=runner,
        cli_runner=cli_runner,
        zotero_factory=LocalZotero,
        obsidian_config_path=_obsidian_config(tmp_path, vault),
    )
    assert adapter.probe().available is False

    service = FieldService(registry)
    preview = service.preview(vault)
    service.confirm(preview.candidate_token, preview.fields[0].field_id)
    capability = adapter.probe()
    assert capability.available is True
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash=pdf_hash,
    )
    assert adapter.open_attachment(pdf_ref) == {"opened": True}
    assert calls[0][0][0] == "/usr/bin/open"
    assert "type=open-attachment" in calls[0][0][1]


def _annotation(pdf_ref: PdfRef, *, annotation_type: str = "highlight") -> AnnotationIR:
    return AnnotationIR(
        annotation_id="ANNP2345",
        pdf_ref=pdf_ref,
        source_id="ANNP2345",
        type=annotation_type,
        quoted_text="evidence",
        page_index=0,
        geometry={"rects": [[20, 20, 120, 40]]},
        source_link="zotero://open-pdf/library/items/PDFD2345?annotation=ANNP2345",
        source_pdf_hash=pdf_ref.content_hash,
    )


def test_annotation_snapshot_never_overwrites_and_refuses_unsupported_types(tmp_path: Path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=200)
    document.save(source)
    document.close()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash=f"sha256:{digest}",
    )
    service = AnnotationSnapshotService()
    destination = tmp_path / "annotated.pdf"

    receipt = service.generate(source, destination, [_annotation(pdf_ref)])

    assert receipt.annotation_count == 1
    assert receipt.output_hash.startswith("sha256:")
    assert destination.is_file()
    assert receipt.metadata_path.is_file()
    metadata = json.loads(receipt.metadata_path.read_text(encoding="utf-8"))
    assert metadata["pdf_ref"]["attachment_key"] == "PDFD2345"
    assert metadata["output_hash"] == receipt.output_hash
    assert metadata["omitted_types"] == []
    with pytest.raises(Exception, match="already exists"):
        service.generate(source, destination, [_annotation(pdf_ref)])
    with pytest.raises(UnsupportedAnnotationSnapshot):
        service.generate(
            source,
            tmp_path / "image.pdf",
            [_annotation(pdf_ref, annotation_type="image")],
        )


@pytest.mark.parametrize(
    ("annotation_type", "geometry"),
    [
        ("highlight", {"rects": [[20, 20, 120, 40]]}),
        ("underline", {"rects": [[20, 20, 120, 40]]}),
        ("note", {"rects": [[20, 20, 40, 40]]}),
        ("ink", {"paths": [[[20, 20], [40, 40], [60, 20]]]}),
    ],
)
def test_annotation_snapshot_validates_each_supported_type(
    tmp_path: Path,
    annotation_type: str,
    geometry: dict,
):
    source = tmp_path / f"{annotation_type}-source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=200)
    document.save(source)
    document.close()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash=f"sha256:{digest}",
    )
    annotation = _annotation(pdf_ref, annotation_type=annotation_type).model_copy(
        update={"geometry": geometry}
    )
    destination = tmp_path / f"{annotation_type}-annotated.pdf"

    receipt = AnnotationSnapshotService().generate(
        source,
        destination,
        [annotation],
    )

    assert receipt.annotation_count == 1
    with fitz.open(destination) as verified:
        page = verified[0]
        annotations = list(page.annots() or ())
        assert len(annotations) == 1
        if annotation_type == "ink":
            assert annotations[0].vertices == [
                [(20.0, 180.0), (40.0, 160.0), (60.0, 180.0)]
            ]


@pytest.mark.parametrize(
    "bad_point",
    [[float("nan"), 30], [float("inf"), 30], ["20", 30], [True, 30], [20]],
)
def test_annotation_snapshot_rejects_invalid_ink_points_without_output(
    tmp_path: Path, bad_point: list,
):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=200)
    document.save(source)
    document.close()
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash="sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    annotation = _annotation(pdf_ref, annotation_type="ink").model_copy(
        update={"geometry": {"paths": [[[20, 20], bad_point]]}}
    )
    destination = tmp_path / "annotated.pdf"

    with pytest.raises(AnnotationSnapshotError, match="invalid ink point"):
        AnnotationSnapshotService().generate(source, destination, [annotation])

    assert not destination.exists()
    assert not destination.with_suffix(".pdf.snapshot.json").exists()
