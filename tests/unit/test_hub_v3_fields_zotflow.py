from __future__ import annotations

import hashlib
import json
import plistlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import fitz
import pytest

import scholar_workflow.hub.fields as fields_module
from scholar_workflow.hub.fields import (
    FieldCandidateExpired,
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
    ZotFlowReaderAdapter,
)


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


def _field_with_nested_document(tmp_path: Path):
    selected = tmp_path / "field"
    nested = selected / "sub"
    nested.mkdir(parents=True)
    (selected / "00-领域入口.md").write_text("# Field\n", encoding="utf-8")
    document = nested / "doc.md"
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
        json.dumps({"id": "zotflow", "version": "1.6.5", "minAppVersion": "1.13.4"}),
        encoding="utf-8",
    )
    (vault / ".obsidian" / "community-plugins.json").write_text(
        '["zotflow"]', encoding="utf-8"
    )
    app = tmp_path / "Obsidian.app"
    _write_obsidian_app(app, "1.12.7")
    adapter = ZotFlowReaderAdapter(vault, app_path=app)

    capability = adapter.probe()

    assert capability.available is False
    assert "1.13.4" in (capability.reason or "")
    pdf_ref = PdfRef(
        library_id="1",
        attachment_key="PDFD2345",
        content_hash="md5:" + "a" * 32,
    )
    assert adapter.attachment_uri(pdf_ref) == (
        "obsidian://zotflow?type=open-attachment&libraryID=1&key=PDFD2345"
    )


def test_zotflow_adapter_discovers_only_explicit_registered_sources(tmp_path: Path):
    vault = tmp_path / "vault"
    plugin = vault / ".obsidian" / "plugins" / "zotflow"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text(
        json.dumps({"id": "zotflow", "version": "1.6.5", "minAppVersion": "1.13.4"}),
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

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return type("Result", (), {"returncode": 0})()

    registry = KnowledgeSourceRegistry(tmp_path / "sources.json")
    adapter = RegisteredSourceZotFlowAdapter(
        registry,
        app_path=app,
        runner=runner,
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
        content_hash="md5:" + "a" * 32,
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
