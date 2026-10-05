"""Portable replay input must retain ownership without exporting host authority."""
# ruff: noqa: F811 - explicitly imported pytest fixture injection
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from click.testing import CliRunner
from referencing import Registry, Resource

from scholar_workflow.analysis.apply_changes import KnowledgeProviderSnapshot
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldRegistryError
from scholar_workflow.workflows.knowledge_reproduction import reproduction_plan
from tests.contract.test_canvas_registration import canvas_scope  # noqa: F401
from tests.contract.test_paper_registration import scope  # noqa: F401


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_explicit_portable_inventory_is_complete_and_zero_write(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    before, state = files(root), files(registry.path.parent)
    plan = reproduction_plan(registry, source_id=selection["source_id"])
    assert plan == reproduction_plan(registry, source_id=selection["source_id"])
    assert files(root) == before and files(registry.path.parent) == state
    package = plan["package"]
    restored = KnowledgeProviderSnapshot.model_validate(package["provider"])
    assert restored.vault_binding is None and restored.receipts == []
    assert len(restored.manifest.atomic_resources) == 1
    assert len(restored.manifest.supporting_documents) == 2
    assert {a.vault_path for a in restored.artifacts} == set(paths.values())
    assert set(paths.values()) <= set(package["files"])
    assert "resources/papers/synthetic/Paper.md" in package["files"]
    assert "README.md" in package["files"]
    assert ".scholar-workflow/fields.yml" in package["files"]
    assert "local.pdf" not in package["files"]
    assert str(root) not in json.dumps(package) and str(provider) not in json.dumps(package)
    assert plan["restore_performed"] is False and plan["source_verified"] is False


@pytest.mark.parametrize("member", ["markdown", "canvas", "sidecar", "owner", "home"])
def test_missing_declared_file_never_exports_partial_inventory(canvas_scope, member):
    root, registry, selection, paths, _ = canvas_scope
    path = paths.get(member, "resources/papers/synthetic/Paper.md" if member == "owner" else "README.md")
    (root / path).unlink()
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        reproduction_plan(registry, source_id=selection["source_id"])


@pytest.mark.parametrize("member", ["markdown", "canvas", "sidecar"])
def test_drifted_registered_bytes_fail_closed(canvas_scope, member):
    root, registry, selection, paths, _ = canvas_scope
    file = root / paths[member]
    file.write_bytes(file.read_bytes() + b"\n")
    with pytest.raises(FieldRegistryError, match="hash"):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_symlink_declared_owner_is_not_followed(canvas_scope, tmp_path):
    root, registry, selection, _, _ = canvas_scope
    owner = root / "resources/papers/synthetic/Paper.md"
    content = owner.read_bytes()
    owner.unlink()
    outside = tmp_path / "outside.md"
    outside.write_bytes(content)
    owner.symlink_to(outside)
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_unknown_source_never_creates_state(canvas_scope):
    _, registry, _, _, _ = canvas_scope
    before = files(registry.path.parent)
    with pytest.raises((FieldRegistryError, OSError, ValueError)):
        reproduction_plan(registry, source_id="00000000-0000-4000-8000-000000000000")
    assert files(registry.path.parent) == before


def test_provider_missing_is_not_synthesized(canvas_scope):
    _, registry, selection, _, provider = canvas_scope
    (provider / "knowledge-provider.snapshot.json").unlink()
    before = files(registry.path.parent)
    with pytest.raises(FieldRegistryError, match="provider"):
        reproduction_plan(registry, source_id=selection["source_id"])
    assert files(registry.path.parent) == before


@pytest.mark.parametrize("member", ["owner", "home", "provider", "fields", "registry"])
def test_concurrent_input_change_does_not_return_a_stale_package(canvas_scope, member):
    root, registry, selection, _, provider = canvas_scope
    targets = {"owner": root / "resources/papers/synthetic/Paper.md", "home": root / "README.md",
               "provider": provider / "knowledge-provider.snapshot.json",
               "fields": root / ".scholar-workflow/fields.yml", "registry": registry.path}
    target = targets[member]
    def change():
        target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(FieldRegistryError, match="changed"):
        reproduction_plan(registry, source_id=selection["source_id"], _before_verify=change)


def test_read_only_source_may_export_without_write_capability(canvas_scope):
    _, registry, selection, _, _ = canvas_scope
    document = registry.load_document()
    document.sources[0].capabilities = ["read"]
    registry.save(document)
    assert reproduction_plan(registry, source_id=selection["source_id"])["status"] == "exportable"


def test_disabled_source_refuses_export(canvas_scope):
    _, registry, selection, _, _ = canvas_scope
    document = registry.load_document()
    document.sources[0].enabled = False
    registry.save(document)
    with pytest.raises(FieldRegistryError):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_new_portable_manifest_during_inspection_invalidates_input(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    def change():
        (root / ".scholar-workflow/artifacts.yml").write_text("schema_version: 1\nartifacts: []\n")
    with pytest.raises(FieldRegistryError, match="changed"):
        reproduction_plan(registry, source_id=selection["source_id"], _before_verify=change)


def test_partial_provider_does_not_export_as_a_complete_analysis(canvas_scope):
    _, registry, selection, _, provider = canvas_scope
    path = provider / "knowledge-provider.snapshot.json"
    value = json.loads(path.read_text())
    value.update(receipts=[], snapshot_revision="")
    value["artifacts"] = [a for a in value["artifacts"] if a["kind"] != "analysis_sidecar"]
    path.write_text(KnowledgeProviderSnapshot.model_validate(value).model_dump_json())
    with pytest.raises(FieldRegistryError, match="complete"):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_wrong_root_provider_cannot_be_exported(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    path = provider / "knowledge-provider.snapshot.json"
    value = json.loads(path.read_text())
    value["vault_binding"]["root_path"] = str(root.parent / "another-source")
    value.update(snapshot_revision="")
    path.write_text(KnowledgeProviderSnapshot.model_validate(value).model_dump_json())
    with pytest.raises(FieldRegistryError, match="another Source"):
        reproduction_plan(registry, source_id=selection["source_id"])


def test_package_public_schema_accepts_export_but_refuses_host_binding(canvas_scope):
    _, registry, selection, _, _ = canvas_scope
    package = reproduction_plan(registry, source_id=selection["source_id"])["package"]
    contracts = Path(__file__).resolve().parents[2] / "contracts"
    names = ("knowledge-reproduction-package.schema.json", "knowledge-provider-snapshot.schema.json",
             "knowledge-manifest.schema.json", "knowledge-change-set.schema.json",
             "knowledge-apply-receipt.schema.json", "hub-catalog.schema.json")
    schemas = {name: json.loads((contracts / name).read_text()) for name in names}
    resources = Registry()
    for name, value in schemas.items():
        resource = Resource.from_contents(value)
        resources = resources.with_resource(value["$id"], resource).with_resource(
            "https://scholar-workflow.local/contracts/" + name, resource)
    schema = schemas["knowledge-reproduction-package.schema.json"]
    validator = jsonschema.Draft202012Validator(schema, registry=resources)
    validator.validate(package)
    bad = json.loads(json.dumps(package))
    bad["provider"]["vault_binding"] = {"root_path": "/another-host", "device": 1, "inode": 1}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad)


@pytest.mark.parametrize("fmt,language", [("json", "en"), ("md", "en"), ("md", "zh")])
def test_public_cli_separates_readable_summary_from_machine_input(canvas_scope, monkeypatch, fmt, language):
    _, registry, selection, _, _ = canvas_scope
    from types import SimpleNamespace
    monkeypatch.setattr("scholar_workflow.cli._local_field_service", lambda: SimpleNamespace(registry=registry))
    result = CliRunner().invoke(main, ["knowledge", "reproduction-plan", "--source-id", selection["source_id"],
                                      "--format", fmt, "--language", language])
    assert result.exit_code == 0, result.output
    if fmt == "json":
        assert json.loads(result.output)["package"]["source_id"] == selection["source_id"]
    else:
        assert '"snapshot_revision"' not in result.output
        assert "尚未恢复" in result.output if language == "zh" else "not restored" in result.output
