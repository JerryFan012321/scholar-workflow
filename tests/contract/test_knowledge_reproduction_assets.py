"""Explicit note assets travel with replay; prose is not relationship authority."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest
import yaml

from scholar_workflow.knowledge.fields import (
    FieldRegistryError,
    FieldService,
    KnowledgeSourceRegistry,
)
from scholar_workflow.knowledge.registration import register, registration_plan
from scholar_workflow.workflows.knowledge_reproduction import (
    reproduction_plan,
    restore,
    restore_plan,
)
from scholar_workflow.analysis.apply_changes import apply_knowledge_change_set
from scholar_workflow.analysis.commit import commit_analysis_bundle
from scholar_workflow.analysis.models import AnalysisCommitRequest, AnalysisDocument
from scholar_workflow.analysis.updates import render_analysis_projection
from scholar_workflow.workflows.register_paper import paper_plan, register_paper
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401


@pytest.fixture
def selected_canvas_scope(scope, tmp_path):
    root, registry, zotero, selection = scope
    proposal = paper_plan(registry, zotero, **selection)
    owner = register_paper(registry, zotero, approved_digest=proposal["approved_digest"], **selection)
    folder = Path(owner["owner_path"]).parent.as_posix()
    artifact_id = "analysis:" + owner["resource_id"]

    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1200, 360, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\0" + b"\xff" * 3600) * 360)) + chunk(b"IEND", b"")
    source = {"kind": "zotero_pdf", "library_type": "personal", "library_id": "123", "attachment_key": "EFGH2345", "content_hash": "sha256:" + hashlib.sha256(zotero.pdf.read_bytes()).hexdigest(), "page_index": 0}
    claims, rows = [], []
    (root / folder / "attachments").mkdir()
    for name, role, path, kind, label in (
        ("flow", "method", "method/overview", "process_diagram", "Figure 1: synthetic process"),
        ("table", "experiments", "experiments/comparison/synthetic", "experimental_table", "Table 1: synthetic comparison"),
    ):
        local = f"attachments/{name}.png"
        (root / folder / local).write_bytes(png)
        rows.append({"asset_id": "asset:" + name, "owner_artifact_ids": [artifact_id], "vault_path": folder + "/" + local, "display_name": name + ".png", "media_type": "image/png", "size": len(png), "sha256": "sha256:" + hashlib.sha256(png).hexdigest(), "role": "embed"})
        claims.append({"claim_id": name, "role": role, "outline_path": path, "title": label, "body": "This is synthetic source content, not a scientific claim.", "evidence": {"kind": "author_stated", "anchor": label, "source_spans": [{**source, "quote": "This is synthetic source content."}]}, "canvas_image": {"kind": kind, "asset_id": "asset:" + name, "caption": label, "image_path": local, "sha256": hashlib.sha256(png).hexdigest(), "pixel_width": 1200, "pixel_height": 360, "source": source}})
    (root / ".scholar-workflow/assets.yml").write_text(yaml.safe_dump({"schema_version": 1, "assets": rows}))
    document = AnalysisDocument.model_validate({"schema_version": 5, "artifact_id": artifact_id, "paper_title": "Synthetic selected images", "language": "en", "profile": {"kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True}, "claims": claims})
    paths = {"markdown": folder + "/Analysis.md", "canvas": folder + "/Tree.canvas", "sidecar": folder + "/analysis.baseline.json"}
    request = AnalysisCommitRequest.model_validate({"commit_id": "selected-images", "batch_id": "selected-images", "item_id": "one", "source_state": "validated", "resource_id": owner["resource_id"], "note_stem": "Analysis", "document": document.model_dump(mode="json"), "paths": paths, "base_revisions": {p: None for p in paths.values()}, "base_catalog_revision": owner["catalog_revision"], "base_snapshot_revision": owner["snapshot_revision"], "zotero_item_key": selection["item_key"], "relations": [{"from_id": owner["resource_id"], "relation": "has-analysis", "to_id": artifact_id}]})
    bundle, baseline = render_analysis_projection(document, note_stem="Analysis")
    receipt = commit_analysis_bundle(vault_root=root, state_root=tmp_path / "image-commit", request=request, bundle=bundle, baseline=baseline, source_registry=registry)
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    apply_knowledge_change_set(state_root=provider, change_set=receipt.change_set)
    return root, registry, selection, rows, paths


def test_selected_canvas_images_export_restore_and_reexport(selected_canvas_scope, scope, tmp_path):
    source, original_registry, selection, rows, paths = selected_canvas_scope
    exported = reproduction_plan(original_registry, source_id=selection["source_id"])
    assert all(exported["package"]["files"][row["vault_path"]] == row["sha256"] for row in rows)
    root = tmp_path / "copied-image-source"
    shutil.copytree(source, root)
    registry = KnowledgeSourceRegistry(tmp_path / "image-host/hub/sources.json")
    service = FieldService(registry)
    preview = registration_plan(service, root, field_root=None, existing_source=True)
    register(service, root, field_root=None, existing_source=True, approved_digest=preview.payload["approved_digest"])
    package = tmp_path / "image-replay.json"
    package.write_text(json.dumps(exported))
    plan = restore_plan(registry, scope[2], source_id=selection["source_id"], package=package)
    result = restore(registry, scope[2], source_id=selection["source_id"], package=package, approved_digest=plan["approved_digest"])
    assert result["status"] == "ownership-restored"
    assert reproduction_plan(registry, source_id=selection["source_id"])["package_digest"] == exported["package_digest"]
    assert all((root / row["vault_path"]).read_bytes() == (source / row["vault_path"]).read_bytes() for row in rows)
    canvas = json.loads((root / paths["canvas"]).read_text())
    assert sum("./attachments/" in node.get("text", "") for node in canvas["nodes"]) == 2


@pytest.mark.parametrize("case", ["undeclared", "different-owner"])
def test_selected_canvas_image_cannot_be_omitted_from_inventory(selected_canvas_scope, case):
    root, registry, selection, rows, _ = selected_canvas_scope
    if case == "undeclared":
        rows.pop()
    else:
        rows[0]["owner_artifact_ids"] = [rows[0]["owner_artifact_ids"][0] + ":canvas"]
    (root / ".scholar-workflow/assets.yml").write_text(yaml.safe_dump({"schema_version": 1, "assets": rows}))
    with pytest.raises(FieldRegistryError, match="Selected Canvas images"):
        reproduction_plan(registry, source_id=selection["source_id"])


@pytest.fixture
def asset_scope(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    snapshot = json.loads((provider / "knowledge-provider.snapshot.json").read_text())
    owner = next(a["artifact_id"] for a in snapshot["artifacts"] if a["kind"] == "analysis_markdown")
    path = "resources/papers/synthetic/attachments/source-region.png"
    content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j7h8AAAAASUVORK5CYII="
    )
    (root / path).parent.mkdir()
    (root / path).write_bytes(content)
    row = {"asset_id": "asset:synthetic-source-region", "owner_artifact_ids": [owner],
           "vault_path": path, "display_name": "source-region.png", "media_type": "image/png",
           "size": len(content), "sha256": "sha256:" + hashlib.sha256(content).hexdigest(), "role": "embed"}
    manifest = root / ".scholar-workflow/assets.yml"
    manifest.write_text(yaml.safe_dump({"schema_version": 1, "assets": [row]}))
    return root, registry, selection, paths, provider, row, manifest


def test_declared_image_and_manifest_are_in_zero_write_export(asset_scope):
    root, registry, selection, _, provider, row, manifest = asset_scope
    original = (provider / "knowledge-provider.snapshot.json").read_bytes()
    files_before = {p: p.read_bytes() for p in (root / row["vault_path"], manifest)}
    exported = reproduction_plan(registry, source_id=selection["source_id"])
    package = exported["package"]
    assert package["files"][row["vault_path"]] == row["sha256"]
    assert ".scholar-workflow/assets.yml" in package["files"]
    assert package["provider"]["catalog"]["assets"] == [row]
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == original
    assert {p: p.read_bytes() for p in files_before} == files_before


@pytest.mark.parametrize("change", ["missing", "hash", "size", "symlink", "unknown-owner",
                                    "duplicate-id", "duplicate-path", "escape", "collision"])
def test_invalid_asset_refuses_export(asset_scope, tmp_path, change):
    root, registry, selection, paths, _, row, manifest = asset_scope
    document = {"schema_version": 1, "assets": [row]}
    image = root / row["vault_path"]
    if change == "missing":
        image.unlink()
    elif change == "hash":
        image.write_bytes(image.read_bytes() + b"changed")
    elif change == "size":
        row["size"] += 1
    elif change == "symlink":
        outside = tmp_path / "outside.png"
        image.rename(outside)
        image.symlink_to(outside)
    elif change == "unknown-owner":
        row["owner_artifact_ids"] = ["analysis:not-owned"]
    elif change == "duplicate-id":
        document["assets"].append(dict(row, vault_path="attachments/other.png"))
    elif change == "duplicate-path":
        document["assets"].append(dict(row, asset_id="asset:other"))
    elif change == "escape":
        row["vault_path"] = "../outside.png"
    else:
        row["vault_path"] = paths["markdown"]
        data = (root / paths["markdown"]).read_bytes()
        row.update(size=len(data), sha256="sha256:" + hashlib.sha256(data).hexdigest())
    manifest.write_text(yaml.safe_dump(document))
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        reproduction_plan(registry, source_id=selection["source_id"])


@pytest.mark.parametrize("member", ["manifest", "image"])
def test_asset_change_during_export_refuses_stale_input(asset_scope, member):
    root, registry, selection, _, _, row, manifest = asset_scope
    target = manifest if member == "manifest" else root / row["vault_path"]
    def change():
        target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(FieldRegistryError, match="changed"):
        reproduction_plan(registry, source_id=selection["source_id"], _before_verify=change)


def test_copy_and_restore_preserve_image_and_explicit_owner(asset_scope, scope, tmp_path):
    source, old_registry, selection, _, _, row, _ = asset_scope
    exported = reproduction_plan(old_registry, source_id=selection["source_id"])
    root = tmp_path / "copied-source"
    shutil.copytree(source, root)
    registry = KnowledgeSourceRegistry(tmp_path / "new-host/hub/sources.json")
    service = FieldService(registry)
    preview = registration_plan(service, root, field_root=None, existing_source=True)
    register(service, root, field_root=None, existing_source=True,
             approved_digest=preview.payload["approved_digest"])
    package = tmp_path / "replay.json"
    package.write_text(json.dumps(exported))
    before = (root / row["vault_path"]).read_bytes()
    plan = restore_plan(registry, scope[2], source_id=selection["source_id"], package=package)
    assert plan["files"][row["vault_path"]] == row["sha256"]
    assert plan["provider_after"]["catalog"]["assets"] == [row]
    receipt = restore(registry, scope[2], source_id=selection["source_id"], package=package,
                      approved_digest=plan["approved_digest"])
    assert receipt["status"] == "ownership-restored"
    assert (root / row["vault_path"]).read_bytes() == before
    reexport = reproduction_plan(registry, source_id=selection["source_id"])
    assert reexport["package_digest"] == exported["package_digest"]


@pytest.mark.parametrize("text", ["schema_version: 1\nassets: []\nassets: []\n",
                                 "schema_version: true\nassets: []\n",
                                 "schema_version: 1\nassets: []\nunknown: ignored\n"])
def test_invalid_asset_manifest_is_not_silently_ignored(asset_scope, text):
    _, registry, selection, _, _, _, manifest = asset_scope
    manifest.write_text(text)
    with pytest.raises((FieldRegistryError, ValueError)):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_new_assets_manifest_during_inspection_invalidates_absence(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    def change():
        (root / ".scholar-workflow/assets.yml").write_text("schema_version: 1\nassets: []\n")
    with pytest.raises(FieldRegistryError, match="changed"):
        reproduction_plan(registry, source_id=selection["source_id"], _before_verify=change)
