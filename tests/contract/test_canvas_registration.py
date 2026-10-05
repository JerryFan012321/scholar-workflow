"""A portable declaration never creates another analysis or takes over user content."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from scholar_workflow.analysis.apply_changes import apply_knowledge_change_set
from scholar_workflow.analysis.commit import commit_analysis_bundle
from scholar_workflow.analysis.models import AnalysisCommitRequest, AnalysisDocument
from scholar_workflow.analysis.rendering import render_analysis
from scholar_workflow.analysis.updates import create_baseline
from scholar_workflow.cli import main
from scholar_workflow.knowledge.fields import FieldRegistryError
from scholar_workflow.workflows.register_canvas import canvas_plan, register_canvas
from scholar_workflow.workflows.register_paper import paper_plan, register_paper
from tests.contract.test_paper_registration import scope  # noqa: F401


@pytest.fixture
def canvas_scope(scope, tmp_path):  # noqa: F811 - pytest fixture injection
    root, registry, zotero, selection = scope
    plan = paper_plan(registry, zotero, **selection)
    owner = register_paper(registry, zotero, approved_digest=plan["approved_digest"], **selection)
    document = AnalysisDocument.model_validate({
        "schema_version": 5, "artifact_id": "analysis:" + owner["resource_id"],
        "paper_title": zotero.title, "language": "en",
        "profile": {"kind": "whole", "framework": "reference_tree_v5", "markdown_quotes": True},
        "claims": [{"claim_id": "task", "role": "abstract", "outline_path": "abstract/task",
                    "title": "Task", "body": "Synthetic fixture, not a scientific claim.",
                    "evidence": {"kind": "not_applicable", "detail": "Synthetic fixture."}}],
    })
    bundle = render_analysis(document, note_stem="Analysis")
    baseline = create_baseline(document, bundle, note_stem="Analysis")
    folder = Path(owner["owner_path"]).parent.as_posix()
    paths = {"markdown": folder + "/Analysis.md", "canvas": folder + "/Tree.canvas",
             "sidecar": folder + "/analysis.baseline.json"}
    request = AnalysisCommitRequest.model_validate({
        "commit_id": "portable-canvas", "batch_id": "synthetic-canvas", "item_id": "one",
        "source_state": "validated", "resource_id": owner["resource_id"], "note_stem": "Analysis",
        "document": document.model_dump(mode="json"), "paths": paths,
        "base_revisions": {p: None for p in paths.values()},
        "base_catalog_revision": owner["catalog_revision"], "base_snapshot_revision": owner["snapshot_revision"],
        "zotero_item_key": selection["item_key"],
        "relations": [{"from_id": owner["resource_id"], "relation": "has-analysis",
                       "to_id": document.artifact_id}],
    })
    receipt = commit_analysis_bundle(vault_root=root, state_root=tmp_path / "commit-state",
                                    request=request, bundle=bundle, baseline=baseline,
                                    source_registry=registry)
    provider = registry.path.parent / "knowledge-providers" / selection["source_id"]
    apply_knowledge_change_set(state_root=provider, change_set=receipt.change_set)
    selection = {"source_id": selection["source_id"], "field_id": selection["field_id"],
                 "artifact_id": document.artifact_id + ":canvas"}
    return root, registry, selection, paths, provider


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_public_zero_write_plan_registration_and_replay(canvas_scope):
    root, registry, selection, paths, provider = canvas_scope
    before, original_provider = _files(root), _files(provider)
    plan = canvas_plan(registry, **selection)
    assert plan == canvas_plan(registry, **selection)
    assert _files(root) == before and _files(provider) == original_provider
    result = register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert result == register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert not result["content_rewritten"] and not result["human_verified"]
    assert {p: (root / p).read_bytes() for p in before} == before
    assert (provider / "knowledge-provider.snapshot.json").read_bytes() == original_provider["knowledge-provider.snapshot.json"]
    assert result["artifact"]["vault_path"] == paths["canvas"]
    assert canvas_plan(registry, **selection)["status"] == "unchanged"
    from scholar_workflow.analysis.apply_changes import load_knowledge_provider_snapshot
    from scholar_workflow.hub.artifact_manifest import VaultArtifactManifestProvider
    from scholar_workflow.hub.catalog import StaticCatalogProvider
    snapshot = load_knowledge_provider_snapshot(provider)
    loaded = VaultArtifactManifestProvider(StaticCatalogProvider(snapshot.catalog), root).load()
    assert selection["artifact_id"] in {a.artifact_id for a in loaded.artifacts}
    assert not any(d.code == "unregistered-vault-canvas" for d in loaded.diagnostics)


def test_existing_unrelated_rows_and_comments_preserved(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    manifest = root / ".scholar-workflow/artifacts.yml"
    manifest.write_text("# Human comment\nschema_version: 1\nartifacts:\n"
                        "  - artifact_id: another:canvas\n    kind: analysis-canvas\n"
                        "    format: canvas\n    vault_path: other.canvas\n    resource_id: another\n")
    plan = canvas_plan(registry, **selection)
    register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    text = manifest.read_text()
    assert "# Human comment" in text and "artifact_id: another:canvas" in text
    assert "vault_path: other.canvas" in text and "resource_id: another" in text


@pytest.mark.parametrize("member", ["markdown", "canvas", "sidecar", "fields", "registry", "provider", "manifest"])
def test_changed_input_never_publishes(canvas_scope, member):
    root, registry, selection, paths, provider = canvas_scope
    plan = canvas_plan(registry, **selection)
    if member in paths:
        path = root / paths[member]
    elif member == "fields":
        path = root / ".scholar-workflow/fields.yml"
    elif member == "registry":
        path = registry.path
    elif member == "provider":
        path = provider / "knowledge-provider.snapshot.json"
    else:
        path = root / ".scholar-workflow/artifacts.yml"
        path.write_text("schema_version: 1\nartifacts: []\n")
    if member != "manifest":
        path.write_bytes(path.read_bytes() + b"\n ")
    before = _files(root)
    with pytest.raises((FieldRegistryError, ValueError)):
        register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert _files(root) == before


def test_interrupted_single_file_publication_recovers(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    plan = canvas_plan(registry, **selection)
    def stop(_):
        raise RuntimeError("interruption")
    with pytest.raises(RuntimeError, match="interruption"):
        register_canvas(registry, approved_digest=plan["approved_digest"], fault_inject=stop, **selection)
    written = (root / ".scholar-workflow/artifacts.yml").read_bytes()
    result = register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert result["status"] == "registered"
    assert (root / ".scholar-workflow/artifacts.yml").read_bytes() == written


def test_human_edit_after_interruption_is_not_overwritten(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    plan = canvas_plan(registry, **selection)
    def stop(_):
        raise RuntimeError("interruption")
    with pytest.raises(RuntimeError):
        register_canvas(registry, approved_digest=plan["approved_digest"], fault_inject=stop, **selection)
    manifest = root / ".scholar-workflow/artifacts.yml"
    manifest.write_text("# Human changed\nschema_version: 1\nartifacts: []\n")
    before = manifest.read_bytes()
    with pytest.raises(FieldRegistryError, match="manifest changed"):
        register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert manifest.read_bytes() == before


@pytest.mark.parametrize("content", ["schema_version: 1\nschema_version: 1\nartifacts: []\n",
    "schema_version: true\nartifacts: []\n", "schema_version: 1\nartifacts: [invalid]\n"])
def test_invalid_manifest_refuses_without_writes(canvas_scope, content):
    root, registry, selection, _, provider = canvas_scope
    (root / ".scholar-workflow/artifacts.yml").write_text(content)
    before, state = _files(root), _files(provider)
    with pytest.raises((FieldRegistryError, ValueError)):
        canvas_plan(registry, **selection)
    assert _files(root) == before and _files(provider) == state


def test_conflicting_identity_refuses(canvas_scope):
    root, registry, selection, _, _ = canvas_scope
    plan = canvas_plan(registry, **selection)
    (root / ".scholar-workflow/artifacts.yml").write_text(plan["manifest_after"].replace("Tree.canvas", "Other.canvas"))
    with pytest.raises(FieldRegistryError, match="conflicts"):
        canvas_plan(registry, **selection)


def test_symlink_manifest_and_journal_tampering_refuse(canvas_scope, tmp_path):
    root, registry, selection, _, provider = canvas_scope
    target = tmp_path / "human.yml"
    target.write_text("schema_version: 1\nartifacts: []\n")
    manifest = root / ".scholar-workflow/artifacts.yml"
    manifest.symlink_to(target)
    with pytest.raises(OSError):
        canvas_plan(registry, **selection)
    manifest.unlink()
    plan = canvas_plan(registry, **selection)
    journal = provider / f"canvas-registration-{plan['approved_digest']}.json"
    record = {"status": "prepared", "plan": dict(plan, manifest_after="forged")}
    journal.write_text(json.dumps(record))
    with pytest.raises(FieldRegistryError, match="digest"):
        register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert not manifest.exists() and target.read_text() == "schema_version: 1\nartifacts: []\n"


def test_public_cli_one_declared_artifact(canvas_scope):
    _root, registry, selection, _, _ = canvas_scope
    args = [value for key, val in selection.items() for value in ("--" + key.replace("_", "-"), val)]
    runner = CliRunner()
    env = {"SCHOLAR_WORKFLOW_HOME": str(registry.path.parent.parent)}
    preview = runner.invoke(main, ["knowledge", "canvas-plan", *args, "--format", "json"], env=env)
    assert preview.exit_code == 0, preview.output
    plan = json.loads(preview.output)
    published = runner.invoke(main, ["knowledge", "register-canvas", *args, "--yes",
                                    "--approved-digest", plan["approved_digest"]], env=env)
    assert published.exit_code == 0, published.output
    assert json.loads(published.output)["content_rewritten"] is False
    bad = runner.invoke(main, ["knowledge", "canvas-plan", *args[:-1], "unknown", "--format", "json"], env=env)
    assert bad.exit_code == 7 and "already-owned" in bad.output


@pytest.mark.parametrize("change", ["path", "id", "duplicate"])
def test_manifest_identity_collision_refuses_without_changes(canvas_scope, change):
    root, registry, selection, _, _ = canvas_scope
    plan = canvas_plan(registry, **selection)
    import yaml
    data = yaml.safe_load(plan["manifest_after"])
    if change == "path":
        data["artifacts"][0]["artifact_id"] = "another:canvas"
    elif change == "id":
        data["artifacts"][0]["resource_id"] = "another:paper"
    else:
        data["artifacts"].append(dict(data["artifacts"][0]))
    manifest = root / ".scholar-workflow/artifacts.yml"
    manifest.write_text(yaml.safe_dump(data))
    before = _files(root)
    with pytest.raises(FieldRegistryError, match="conflicts|duplicate"):
        canvas_plan(registry, **selection)
    assert _files(root) == before


def test_publication_directory_swap_does_not_report_success(canvas_scope):
    root, registry, selection, _, provider = canvas_scope
    plan = canvas_plan(registry, **selection)
    def swap(_):
        (root / ".scholar-workflow").rename(root / "preserved-state")
        (root / ".scholar-workflow").mkdir()
        (root / ".scholar-workflow/artifacts.yml").write_text("Human replacement\n")
    with pytest.raises(FieldRegistryError, match="directory changed"):
        register_canvas(registry, approved_digest=plan["approved_digest"], fault_inject=swap, **selection)
    assert (root / ".scholar-workflow/artifacts.yml").read_text() == "Human replacement\n"
    assert (root / "preserved-state/artifacts.yml").read_text() == plan["manifest_after"]
    journal = provider / f"canvas-registration-{plan['approved_digest']}.json"
    assert json.loads(journal.read_text())["status"] == "prepared"


@pytest.mark.parametrize("content", [[], {"status": [], "plan": {}},
                                    {"status": "prepared", "plan": []}])
def test_malformed_journal_is_a_refusal(canvas_scope, content):
    root, registry, selection, _, provider = canvas_scope
    plan = canvas_plan(registry, **selection)
    journal = provider / f"canvas-registration-{plan['approved_digest']}.json"
    journal.write_text(json.dumps(content))
    with pytest.raises(FieldRegistryError, match="journal"):
        register_canvas(registry, approved_digest=plan["approved_digest"], **selection)
    assert not (root / ".scholar-workflow/artifacts.yml").exists()
