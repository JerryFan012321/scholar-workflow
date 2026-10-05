"""Explicit note assets travel with replay; prose is not relationship authority."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import base64
import hashlib
import json
import shutil

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
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401


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
